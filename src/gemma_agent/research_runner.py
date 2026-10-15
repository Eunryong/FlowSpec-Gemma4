from __future__ import annotations

import csv
import hashlib
import json
import secrets
import shutil
import string
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from jsonschema import Draft202012Validator

from .agent import CodingAgent
from .config import Config
from .llama_client import LlamaClient
from .research_store import (
    DEFAULT_RESEARCH_ROOT,
    PROJECT_ROOT,
    ResearchError,
    atomic_write_json,
    copy_workspace,
    git_commit,
    initialize_research_layout,
    load_run_metadata,
    read_json,
    resolve_condition_file,
    sha256_bytes,
    sha256_file,
    sha256_tree,
    timestamp_utc,
    write_run_metadata,
)
from .trace import TraceLogger


EVALUATION_CATEGORIES = (
    "functional_tests",
    "edge_case_tests",
    "regression_tests",
    "future_change_tests",
    "ui_usability_tests",
    "static_complexity_metrics",
)


def _safe_label(value: str) -> str:
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    result = "".join(char.lower() if char in keep else "-" for char in value).strip("-")
    return result or "run"


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 and result < float("inf") else None


def _model_metrics(meta: dict[str, Any] | None, *, model_calls: int, tool_calls: int,
                   tool_time_ms: float, agent_turn_ms: float, status: str,
                   error_type: str | None = None) -> dict[str, Any]:
    data = meta or {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    input_tokens = _optional_int(data.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _optional_int(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _optional_int(data.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _optional_int(usage.get("completion_tokens", usage.get("output_tokens")))
    total_tokens = _optional_int(data.get("total_tokens"))
    if total_tokens is None:
        total_tokens = _optional_int(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    server_timings = data.get("server_timings") if isinstance(data.get("server_timings"), dict) else {}
    prefill_ms = data.get("prefill_ms")
    if prefill_ms is None:
        prefill_ms = server_timings.get("prompt_ms")
    return {
        "status": status,
        "error_type": error_type,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "token_usage_complete": input_tokens is not None and output_tokens is not None,
        "ttft_ms": _optional_number(data.get("ttft_ms")),
        "first_text_ms": _optional_number(data.get("first_text_ms")),
        "prefill_ms": _optional_number(prefill_ms),
        "generation_ms": _optional_number(data.get("generation_ms")),
        "total_latency_ms": _optional_number(
            data.get("total_latency_ms", _optional_number(data.get("elapsed_seconds")) * 1000
                     if _optional_number(data.get("elapsed_seconds")) is not None else None)
        ),
        "generation_tokens_per_second": _optional_number(data.get("generation_tokens_per_second")),
        "tool_time_ms": round(tool_time_ms, 3),
        "agent_turn_ms": round(agent_turn_ms, 3),
    }


def _empty_evaluation(anonymous_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {category: [] for category in EVALUATION_CATEGORIES}
    if anonymous_id is not None:
        result = {"anonymous_id": anonymous_id, **result}
    return result


def aggregate_cost(stages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stage_values = list(stages.values())
    expected = len(stage_values)

    def observed_sum(key: str) -> float | int:
        return sum(value for value in (stage.get(key) for stage in stage_values) if isinstance(value, (int, float)))

    def complete_sum(key: str, complete: bool = True) -> float | int | None:
        values = [stage.get(key) for stage in stage_values]
        if not expected:
            return 0
        if complete and any(value is None for value in values):
            return None
        return sum(value for value in values if isinstance(value, (int, float)))

    token_complete = bool(expected) and all(stage.get("token_usage_complete", False) for stage in stage_values)
    generation_complete = bool(expected) and all(stage.get("generation_ms") is not None for stage in stage_values)
    prefill_complete = bool(expected) and all(stage.get("prefill_ms") is not None for stage in stage_values)
    latency_complete = bool(expected) and all(stage.get("total_latency_ms") is not None for stage in stage_values)
    turn_complete = bool(expected) and all(stage.get("agent_turn_ms") is not None for stage in stage_values)
    input_observed = observed_sum("input_tokens")
    output_observed = observed_sum("output_tokens")
    total_observed = observed_sum("total_tokens")
    generation_observed = observed_sum("generation_ms")
    latency_observed = observed_sum("total_latency_ms")
    turn_observed = observed_sum("agent_turn_ms")
    speed = None
    if output_observed > 0 and generation_observed > 0:
        speed = round(output_observed / (generation_observed / 1000), 3)

    return {
        "stage_count": expected,
        "model_calls": int(observed_sum("model_calls")),
        "tool_calls": int(observed_sum("tool_calls")),
        "input_tokens": input_observed if token_complete else None,
        "output_tokens": output_observed if token_complete else None,
        "total_tokens": total_observed if token_complete else None,
        "input_tokens_observed": input_observed,
        "output_tokens_observed": output_observed,
        "total_tokens_observed": total_observed,
        "token_usage_complete": token_complete,
        "ttft_ms": stages.get("design", {}).get("ttft_ms"),
        "prefill_ms": observed_sum("prefill_ms") if prefill_complete else None,
        "prefill_ms_observed": observed_sum("prefill_ms"),
        "prefill_complete": prefill_complete,
        "generation_ms": generation_observed if generation_complete else None,
        "generation_ms_observed": generation_observed,
        "generation_complete": generation_complete,
        "total_latency_ms": latency_observed if latency_complete else None,
        "total_latency_ms_observed": latency_observed,
        "latency_complete": latency_complete,
        "generation_tokens_per_second": speed,
        "tool_time_ms": round(observed_sum("tool_time_ms"), 3),
        "agent_turn_ms": turn_observed if turn_complete else None,
        "agent_turn_ms_observed": turn_observed,
        "agent_turn_complete": turn_complete,
    }


class ExperimentRunner:
    def __init__(
        self,
        research_root: str | Path = DEFAULT_RESEARCH_ROOT,
        *,
        config: Config | None = None,
        project_root: str | Path = PROJECT_ROOT,
        source_workspace: str | Path | None = None,
        server_config: str | None = None,
        client_factory: Callable[[Config], Any] | None = None,
        agent_factory: Callable[..., Any] | None = None,
    ):
        self.research_root = initialize_research_layout(research_root)
        self.project_root = Path(project_root).expanduser().resolve()
        self.config = config or Config()
        self.source_workspace = Path(source_workspace).expanduser().resolve() if source_workspace else None
        self.source_excludes: tuple[str, ...] = ()
        if self.source_workspace is not None:
            try:
                self.source_workspace.relative_to(self.research_root)
            except ValueError:
                pass
            else:
                raise ResearchError("Source workspace cannot be inside the research data directory")
            try:
                relative_research = self.research_root.relative_to(self.source_workspace)
            except ValueError:
                pass
            else:
                if relative_research == Path("."):
                    raise ResearchError("Source workspace cannot be the research data directory")
                self.source_excludes = (relative_research.as_posix(),)
        self.server_config = server_config
        self.client_factory = client_factory or LlamaClient
        self.agent_factory = agent_factory or CodingAgent

    def _snapshot(self, track: str, condition: str, brief: str | Path) -> dict[str, Any]:
        brief_path = Path(brief).expanduser().resolve()
        if not brief_path.is_file():
            raise ResearchError(f"Brief file not found: {brief_path}")
        suffix = brief_path.suffix.lower()
        if suffix not in {".md", ".json"}:
            raise ResearchError("Brief must be a Markdown (.md) or JSON (.json) file")
        brief_bytes = brief_path.read_bytes()
        brief_text = brief_bytes.decode("utf-8")
        if suffix == ".json":
            try:
                json.loads(brief_text)
            except json.JSONDecodeError as exc:
                raise ResearchError(f"Brief JSON is invalid: {exc}") from exc

        condition_path = resolve_condition_file(self.research_root, track, condition)
        condition_bytes = condition_path.read_bytes()
        schema_path = self.research_root / "schemas" / "design-specification.schema.json"
        schema_bytes = schema_path.read_bytes()
        schema = json.loads(schema_bytes.decode("utf-8"))
        Draft202012Validator.check_schema(schema)

        designer_path = self.research_root / "prompts" / "designer-common.md"
        coder_path = self.research_root / "prompts" / "coder-common.md"
        designer_bytes = designer_path.read_bytes()
        coder_bytes = coder_path.read_bytes()
        return {
            "track": track,
            "condition": condition,
            "brief_path": brief_path,
            "brief_bytes": brief_bytes,
            "brief_text": brief_text,
            "brief_sha256": sha256_bytes(brief_bytes),
            "brief_suffix": suffix,
            "condition_path": condition_path,
            "condition_bytes": condition_bytes,
            "condition_text": condition_bytes.decode("utf-8"),
            "condition_sha256": sha256_bytes(condition_bytes),
            "schema_path": schema_path,
            "schema_bytes": schema_bytes,
            "schema": schema,
            "schema_sha256": sha256_bytes(schema_bytes),
            "designer_prompt_path": designer_path,
            "designer_prompt_bytes": designer_bytes,
            "coder_prompt_path": coder_path,
            "coder_prompt_bytes": coder_bytes,
        }

    def _new_run(
        self,
        snapshot: dict[str, Any],
        *,
        repetition_index: int,
        repetitions: int,
        task_id: str | None,
        seed_base: int | None,
    ) -> tuple[Path, dict[str, Any], Config]:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + f"_{_safe_label(snapshot['track'])}_{_safe_label(snapshot['condition'])}"
            + f"_r{repetition_index:03d}_{uuid.uuid4().hex[:8]}"
        )
        run_dir = self.research_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        for relative in (
            "inputs",
            "inputs/revisions",
            "design/.agent",
            "implementation",
            "traces",
            "metrics",
            "evaluation",
        ):
            (run_dir / relative).mkdir(parents=True, exist_ok=True)

        if snapshot["brief_suffix"] == ".json":
            brief_snapshot = run_dir / "inputs" / "brief.json"
        else:
            brief_snapshot = run_dir / "inputs" / "brief.md"
        brief_snapshot.write_bytes(snapshot["brief_bytes"])
        condition_snapshot = run_dir / "inputs" / "condition.md"
        condition_snapshot.write_bytes(snapshot["condition_bytes"])
        (run_dir / "inputs" / "design-schema.json").write_bytes(snapshot["schema_bytes"])
        (run_dir / "inputs" / "designer-common.md").write_bytes(snapshot["designer_prompt_bytes"])
        (run_dir / "inputs" / "coder-common.md").write_bytes(snapshot["coder_prompt_bytes"])

        base_seed = seed_base if seed_base is not None else self.config.seed
        run_seed = base_seed + repetition_index - 1 if base_seed is not None else None
        run_config = replace(self.config, seed=run_seed)
        source_descriptor = None
        if self.source_workspace is not None:
            source_descriptor = {
                "path": str(self.source_workspace),
                "sha256": sha256_tree(self.source_workspace),
            }
            copy_workspace(
                self.source_workspace,
                run_dir / "implementation",
                exclude_paths=self.source_excludes,
            )
        implementation_hash = sha256_tree(run_dir / "implementation")

        actual_task_id = task_id or snapshot["brief_path"].stem
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "task_id": actual_task_id,
            "timestamp": timestamp_utc(),
            "track": snapshot["track"],
            "condition": snapshot["condition"],
            "repetition_index": repetition_index,
            "repetitions": repetitions,
            "model_identifier": run_config.model,
            "model_server_configuration": {
                "base_url": run_config.base_url,
                "descriptor": self.server_config,
            },
            "model_configuration": {
                "temperature": run_config.temperature,
                "seed": run_seed,
                "context_length": run_config.context_length,
                "max_output_tokens": run_config.max_tokens,
                "timeout_seconds": run_config.timeout_seconds,
                "max_agent_steps": run_config.max_steps,
            },
            "brief_file": {
                "path": str(snapshot["brief_path"]),
                "snapshot": str(brief_snapshot.relative_to(run_dir)),
                "sha256": snapshot["brief_sha256"],
            },
            "condition_file": {
                "path": str(snapshot["condition_path"]),
                "snapshot": str(condition_snapshot.relative_to(run_dir)),
                "sha256": snapshot["condition_sha256"],
            },
            "design_schema": {
                "path": str(snapshot["schema_path"]),
                "snapshot": "inputs/design-schema.json",
                "sha256": snapshot["schema_sha256"],
            },
            "harness_prompts": {
                "designer": {
                    "path": str(snapshot["designer_prompt_path"]),
                    "sha256": sha256_bytes(snapshot["designer_prompt_bytes"]),
                },
                "coder": {
                    "path": str(snapshot["coder_prompt_path"]),
                    "sha256": sha256_bytes(snapshot["coder_prompt_bytes"]),
                },
            },
            "design_output_sha256": None,
            "implementation_workspace": {
                "path": str((run_dir / "implementation").resolve()),
                "sha256": implementation_hash,
                "source": source_descriptor,
            },
            "git_commit": git_commit(self.project_root),
            "design_status": "pending",
            "implementation_status": "not_started",
            "run_status": "pending",
            "revisions": [],
            "metrics_files": {},
        }
        write_run_metadata(run_dir, metadata)
        atomic_write_json(run_dir / "evaluation" / "result.json", _empty_evaluation())
        atomic_write_json(run_dir / "traces" / "index.json", {})
        atomic_write_json(run_dir / "metrics" / "total.json", {
            "run_id": run_id,
            "design_cost": None,
            "implementation_cost": None,
            "revision_cost": aggregate_cost({}),
            "cumulative_total_cost": aggregate_cost({}),
        })
        return run_dir, metadata, run_config

    def _trace_context(self, metadata: dict[str, Any], stage: str) -> dict[str, Any]:
        return {
            "run_id": metadata["run_id"],
            "turn_id": 1,
            "task_id": metadata["task_id"],
            "condition": metadata["condition"],
            "stage": stage,
        }

    def _update_trace_index(self, run_dir: Path, stage: str, trace_path: Path) -> None:
        index_path = run_dir / "traces" / "index.json"
        try:
            index = read_json(index_path)
        except (FileNotFoundError, json.JSONDecodeError):
            index = {}
        index[stage] = trace_path.relative_to(run_dir).as_posix()
        atomic_write_json(index_path, index)

    def _record_metrics(self, run_dir: Path, metadata: dict[str, Any], stage: str,
                        metrics: dict[str, Any], trace_path: Path) -> None:
        metrics_path = run_dir / "metrics" / f"{stage}.json"
        metrics = {"run_id": metadata["run_id"], "task_id": metadata["task_id"],
                   "condition": metadata["condition"], "stage": stage, **metrics}
        atomic_write_json(metrics_path, metrics)
        metadata.setdefault("metrics_files", {})[stage] = metrics_path.relative_to(run_dir).as_posix()
        self._update_trace_index(run_dir, stage, trace_path)
        self._update_total_metrics(run_dir, metadata)

    def _update_total_metrics(self, run_dir: Path, metadata: dict[str, Any]) -> None:
        stages: dict[str, dict[str, Any]] = {}
        for stage, relative in metadata.get("metrics_files", {}).items():
            path = run_dir / relative
            if path.is_file():
                stages[stage] = read_json(path)
        revisions = {key: value for key, value in stages.items() if key.startswith("revision_")}
        atomic_write_json(run_dir / "metrics" / "total.json", {
            "run_id": metadata["run_id"],
            "design_cost": stages.get("design"),
            "implementation_cost": stages.get("implementation"),
            "revision_cost": aggregate_cost(revisions),
            "cumulative_total_cost": aggregate_cost(stages),
        })

    def _run_design(self, run_dir: Path, metadata: dict[str, Any], config: Config,
                    snapshot: dict[str, Any]) -> str:
        stage = "design"
        trace_path = run_dir / "design" / ".agent" / "trace.jsonl"
        trace = TraceLogger(trace_path)
        trace_context = self._trace_context(metadata, stage)
        brief_text = (run_dir / metadata["brief_file"]["snapshot"]).read_text(encoding="utf-8")
        condition_text = (run_dir / metadata["condition_file"]["snapshot"]).read_text(encoding="utf-8")
        schema_text = (run_dir / "inputs" / "design-schema.json").read_text(encoding="utf-8")
        system_prompt = (run_dir / "inputs" / "designer-common.md").read_text(encoding="utf-8")
        request = (
            "## Shared brief\n"
            + brief_text
            + "\n\n## Single experiment condition\n"
            + condition_text
            + "\n\n## Required output schema\n"
            + schema_text
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request},
        ]
        started = time.perf_counter()
        meta: dict[str, Any] = {}
        model_call_count = 0
        status = "failed"
        error_type: str | None = None
        raw_response = ""
        validation: dict[str, Any]
        client = self.client_factory(config)
        trace.write("user_request", **trace_context, content=request)
        try:
            model_call_count = 1
            message, meta = client.chat(messages, [])
            trace.write("model_response", **trace_context, step=1, message=message, meta=meta)
            raw_response = message.get("content") or ""
            (run_dir / "design" / "raw_response.txt").write_text(raw_response, encoding="utf-8")
            cleaned_response = raw_response.strip()
            if cleaned_response.startswith("```"):
                lines = cleaned_response.splitlines()
                if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                    cleaned_response = "\n".join(lines[1:-1]).strip()
            try:
                design = json.loads(cleaned_response)
            except json.JSONDecodeError:
                retry_messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            "System notice: Your previous JSON response was truncated because internal thinking "
                            "plus JSON exceeded max_output_tokens. Keep your internal thinking under 50 words "
                            "and write a compact, valid JSON object matching the schema."
                        ),
                    }
                ]
                model_call_count = 2
                message, meta = client.chat(retry_messages, [])
                trace.write("model_response", **trace_context, step=2, message=message, meta=meta)
                raw_response = message.get("content") or ""
                (run_dir / "design" / "raw_response.txt").write_text(raw_response, encoding="utf-8")
                cleaned_response = raw_response.strip()
                if cleaned_response.startswith("```"):
                    lines = cleaned_response.splitlines()
                    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                        cleaned_response = "\n".join(lines[1:-1]).strip()
            try:
                design = json.loads(cleaned_response)
            except json.JSONDecodeError as exc:
                validation = {
                    "valid": False,
                    "parse_error": str(exc),
                    "schema_errors": [],
                    "auto_corrected": False,
                }
                stage_status = "invalid"
            else:
                validator = Draft202012Validator(snapshot["schema"])
                errors = sorted(validator.iter_errors(design), key=lambda error: list(map(str, error.absolute_path)))
                schema_errors = []
                for error in errors:
                    schema_errors.append({
                        "path": "/" + "/".join(str(part) for part in error.absolute_path),
                        "message": error.message,
                        "validator": error.validator,
                    })
                validation = {
                    "valid": not schema_errors,
                    "parse_error": None,
                    "schema_errors": schema_errors,
                    "auto_corrected": False,
                }
                if schema_errors:
                    stage_status = "invalid"
                else:
                    stage_status = "valid"
                    design_path = run_dir / "design" / "design_spec.json"
                    atomic_write_json(design_path, design)
                    metadata["design_output_sha256"] = sha256_file(design_path)
            atomic_write_json(run_dir / "design" / "validation.json", validation)
            trace.write("design_validation", **trace_context, **validation)
            trace.write("finished", **trace_context, step=1, content=raw_response)
            status = "completed"
        except Exception as exc:
            stage_status = "failed"
            status = "failed"
            error_type = type(exc).__name__
            validation = {
                "valid": False,
                "stage_error": str(exc),
                "schema_errors": [],
                "auto_corrected": False,
            }
            atomic_write_json(run_dir / "design" / "validation.json", validation)
            trace.write("model_error", **trace_context, step=1, error_type=error_type, message=str(exc))
        finally:
            try:
                client.client.close()
            except (AttributeError, OSError):
                pass
            if raw_response and metadata.get("design_output_sha256") is None:
                metadata["design_output_sha256"] = sha256_bytes(raw_response.encode("utf-8"))
            elapsed_ms = (time.perf_counter() - started) * 1000
            metrics = _model_metrics(
                meta,
                model_calls=model_call_count,
                tool_calls=0,
                tool_time_ms=0,
                agent_turn_ms=elapsed_ms,
                status=status,
                error_type=error_type,
            )
            trace.write("turn_metrics", **trace_context, **metrics)
            metadata["design_status"] = stage_status
            metadata["run_status"] = "design_complete" if stage_status == "valid" else stage_status
            self._record_metrics(run_dir, metadata, stage, metrics, trace_path)
            write_run_metadata(run_dir, metadata)
        return stage_status

    def _run_coder(self, run_dir: Path, metadata: dict[str, Any], config: Config,
                   stage: str, workspace: Path, request: str) -> tuple[str, str | None]:
        system_prompt = (run_dir / "inputs" / "coder-common.md").read_text(encoding="utf-8")
        trace_path = workspace / ".agent" / "trace.jsonl"
        workspace.mkdir(parents=True, exist_ok=True)
        agent = self.agent_factory(
            workspace_path=workspace,
            config=config,
            system_prompt=system_prompt,
            trace_path=trace_path,
            run_id=metadata["run_id"],
            trace_metadata={
                "task_id": metadata["task_id"],
                "condition": metadata["condition"],
                "stage": stage,
            },
        )
        status = "completed"
        error_type = None
        try:
            agent.run(request)
        except Exception as exc:
            status = "failed"
            error_type = type(exc).__name__
            atomic_write_json(run_dir / stage / "stage_error.json", {
                "error_type": error_type,
                "message": str(exc),
            })
        finally:
            try:
                agent.client.client.close()
            except (AttributeError, OSError):
                pass
        metrics_events: list[dict[str, Any]] = []
        if trace_path.is_file():
            for line in trace_path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "turn_metrics":
                    metrics_events.append(event)
        if metrics_events:
            metrics = dict(metrics_events[-1])
            metrics.pop("event", None)
            metrics.pop("ts", None)
        else:
            metrics = _model_metrics(
                None,
                model_calls=0,
                tool_calls=0,
                tool_time_ms=0,
                agent_turn_ms=0,
                status=status,
                error_type=error_type,
            )
        metrics["status"] = status
        metrics["error_type"] = error_type
        return status, metrics

    def _implementation_request(self, run_dir: Path, design: dict[str, Any] | None,
                                change_text: str | None = None) -> str:
        brief = (run_dir / "inputs" / "brief.md")
        if not brief.exists():
            brief = run_dir / "inputs" / "brief.json"
        brief_text = brief.read_text(encoding="utf-8")
        sections = [
            "## Shared brief\n" + brief_text,
        ]
        if design:
            sections.append("## Final structured design specification\n" + json.dumps(design, ensure_ascii=False, indent=2))
        if change_text is not None:
            sections.append("## Newly revealed change request\n" + change_text)
        return "\n\n".join(sections)

    def _run_implementation(self, run_dir: Path, metadata: dict[str, Any],
                            config: Config, design: dict[str, Any] | None) -> str:
        stage = "implementation"
        workspace = run_dir / "implementation"
        request = self._implementation_request(run_dir, design)
        status, metrics = self._run_coder(run_dir, metadata, config, stage, workspace, request)
        metadata["implementation_status"] = status
        metadata["run_status"] = "completed" if status == "completed" else "failed"
        metadata["implementation_workspace"]["sha256"] = sha256_tree(workspace)
        self._record_metrics(run_dir, metadata, stage, metrics, workspace / ".agent" / "trace.jsonl")
        write_run_metadata(run_dir, metadata)
        return status

    def run_repetitions(
        self,
        *,
        track: str,
        condition: str,
        brief: str | Path,
        repetitions: int = 1,
        mode: str = "full",
        seed: int | None = None,
        task_id: str | None = None,
        fixed_design: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        if repetitions < 1:
            raise ResearchError("repetitions must be at least 1")
        if mode not in {"design", "full", "direct"}:
            raise ResearchError(f"Unsupported run mode: {mode}")
        snapshot = self._snapshot(track, condition, brief)
        fixed_design_data: dict[str, Any] | None = None
        if fixed_design is not None:
            fixed_path = Path(fixed_design).expanduser().resolve()
            if not fixed_path.is_file():
                raise ResearchError(f"Fixed design file not found: {fixed_path}")
            fixed_design_data = read_json(fixed_path)
        results = []
        for repetition_index in range(1, repetitions + 1):
            run_dir, metadata, config = self._new_run(
                snapshot,
                repetition_index=repetition_index,
                repetitions=repetitions,
                task_id=task_id,
                seed_base=seed,
            )
            if fixed_design_data is not None:
                design_path = run_dir / "design" / "design_spec.json"
                atomic_write_json(design_path, fixed_design_data)
                metadata["design_output_sha256"] = sha256_file(design_path)
                metadata["design_status"] = "fixed"
                self._run_implementation(run_dir, metadata, config, fixed_design_data)
            elif mode == "direct":
                metadata["design_status"] = "skipped"
                self._run_implementation(run_dir, metadata, config, None)
            else:
                design_status = self._run_design(run_dir, metadata, config, snapshot)
                if design_status == "valid" and mode == "full":
                    design = read_json(run_dir / "design" / "design_spec.json")
                    self._run_implementation(run_dir, metadata, config, design)
                elif design_status == "valid":
                    metadata["run_status"] = "design_complete"
                    write_run_metadata(run_dir, metadata)
            results.append(metadata)
        return results

    def run_design(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.run_repetitions(mode="design", **kwargs)

    def run_full(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.run_repetitions(mode="full", **kwargs)

    def run_direct(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.run_repetitions(mode="direct", **kwargs)

    def revise(self, run_id: str) -> dict[str, Any]:
        run_dir, metadata = load_run_metadata(self.research_root, run_id)
        if metadata.get("track") != "track2":
            raise ResearchError("Revision runs are available only for track2")
        if metadata.get("design_status") not in {"valid", "skipped"} or metadata.get("implementation_status") != "completed":
            raise ResearchError("V1 design and implementation must both complete before revealing a change")
        revisions = metadata.get("revisions", [])
        if revisions and revisions[-1].get("status") != "completed":
            raise ResearchError("The previous revision did not complete; no later change will be revealed")
        change_files = sorted(
            path for path in (self.research_root / "hidden" / "changes").glob("*.md")
            if path.name.lower() != "readme.md"
        )
        next_index = len(revisions)
        if next_index >= len(change_files):
            raise ResearchError("No unrevealed future change file is available")
        change_path = change_files[next_index]
        revision_number = next_index + 1
        stage = f"revision_{revision_number}"
        source_workspace = Path(
            metadata.get("latest_workspace_path")
            or metadata["implementation_workspace"]["path"]
        )
        workspace = run_dir / stage
        copy_workspace(source_workspace, workspace)

        # Reveal only this change after V1 has been verified complete.
        revealed_path = run_dir / "inputs" / "revisions" / f"{stage}.md"
        revealed_path.write_bytes(change_path.read_bytes())
        change_text = revealed_path.read_text(encoding="utf-8")
        design_path = run_dir / "design" / "design_spec.json"
        design = read_json(design_path) if design_path.exists() else None
        request = self._implementation_request(run_dir, design, change_text)
        config = replace(self.config, seed=metadata.get("model_configuration", {}).get("seed"))
        revisions.append({
            "stage": stage,
            "status": "pending",
            "change_file": str(change_path.resolve()),
            "change_sha256": sha256_file(revealed_path),
            "revealed_snapshot": str(revealed_path.relative_to(run_dir)),
            "workspace_path": str(workspace.resolve()),
        })
        metadata["revisions"] = revisions
        metadata["run_status"] = "revision_in_progress"
        write_run_metadata(run_dir, metadata)

        status, metrics = self._run_coder(run_dir, metadata, config, stage, workspace, request)
        revisions[-1]["status"] = status
        revisions[-1]["workspace_sha256"] = sha256_tree(workspace)
        revisions[-1]["completed_at"] = timestamp_utc()
        metadata["latest_workspace_path"] = str(workspace.resolve())
        metadata["run_status"] = "completed" if status == "completed" else "revision_failed"
        self._record_metrics(run_dir, metadata, stage, metrics, workspace / ".agent" / "trace.jsonl")
        write_run_metadata(run_dir, metadata)
        return metadata

    def verify_group(self, *, track: str, condition: str | None = None) -> dict[str, Any]:
        runs_root = self.research_root / "runs"
        matches = []
        for path in sorted(runs_root.iterdir()):
            metadata_path = path / "metadata.json"
            if not metadata_path.is_file():
                continue
            metadata = read_json(metadata_path)
            if metadata.get("track") != track:
                continue
            if condition is not None and metadata.get("condition") != condition:
                continue
            matches.append((path, metadata))
        errors: list[str] = []
        if not matches:
            errors.append("No runs match the requested group")
        brief_hashes = {item[1].get("brief_file", {}).get("sha256") for item in matches}
        if len(brief_hashes) > 1:
            errors.append("Brief hashes differ within this track group")
        by_condition: dict[str, set[str | None]] = {}
        for _, metadata in matches:
            by_condition.setdefault(metadata.get("condition", ""), set()).add(
                metadata.get("condition_file", {}).get("sha256")
            )
        for label, hashes in by_condition.items():
            if len(hashes) > 1:
                errors.append(f"Condition hashes differ for condition {label}")
        for run_dir, metadata in matches:
            brief_snapshot = run_dir / metadata["brief_file"]["snapshot"]
            condition_snapshot = run_dir / metadata["condition_file"]["snapshot"]
            if not brief_snapshot.is_file() or sha256_file(brief_snapshot) != metadata["brief_file"]["sha256"]:
                errors.append(f"Brief snapshot hash mismatch in {metadata['run_id']}")
            if not condition_snapshot.is_file() or sha256_file(condition_snapshot) != metadata["condition_file"]["sha256"]:
                errors.append(f"Condition snapshot hash mismatch in {metadata['run_id']}")
        return {
            "valid": not errors,
            "track": track,
            "condition": condition,
            "run_count": len(matches),
            "brief_sha256": next(iter(brief_hashes)) if len(brief_hashes) == 1 else None,
            "condition_sha256_by_name": {
                label: next(iter(hashes)) if len(hashes) == 1 else None
                for label, hashes in by_condition.items()
            },
            "errors": errors,
        }

    def show(self, run_id: str) -> dict[str, Any]:
        _, metadata = load_run_metadata(self.research_root, run_id)
        return metadata

    def list_metadata(self, *, track: str | None = None) -> list[dict[str, Any]]:
        result = []
        for path in sorted((self.research_root / "runs").iterdir()):
            metadata_path = path / "metadata.json"
            if not metadata_path.is_file():
                continue
            metadata = read_json(metadata_path)
            if track is None or metadata.get("track") == track:
                result.append(metadata)
        return result

    def export_comparison(self, *, output: str | Path, format: str = "json",
                          track: str | None = None) -> Path:
        if format not in {"json", "csv"}:
            raise ResearchError("Export format must be json or csv")
        rows = []
        for metadata in self.list_metadata(track=track):
            run_dir, _ = load_run_metadata(self.research_root, metadata["run_id"])
            metrics_path = run_dir / "metrics" / "total.json"
            metrics = read_json(metrics_path) if metrics_path.is_file() else {}
            cumulative = metrics.get("cumulative_total_cost") or {}
            design = metrics.get("design_cost") or {}
            implementation = metrics.get("implementation_cost") or {}
            revisions = metrics.get("revision_cost") or {}
            rows.append({
                "run_id": metadata.get("run_id"),
                "task_id": metadata.get("task_id"),
                "track": metadata.get("track"),
                "condition": metadata.get("condition"),
                "repetition_index": metadata.get("repetition_index"),
                "run_status": metadata.get("run_status"),
                "brief_sha256": metadata.get("brief_file", {}).get("sha256"),
                "condition_sha256": metadata.get("condition_file", {}).get("sha256"),
                "model_identifier": metadata.get("model_identifier"),
                "design_total_tokens": design.get("total_tokens"),
                "implementation_total_tokens": implementation.get("total_tokens"),
                "revision_total_tokens": revisions.get("total_tokens"),
                "cumulative_total_tokens": cumulative.get("total_tokens"),
                "cumulative_input_tokens": cumulative.get("input_tokens"),
                "cumulative_output_tokens": cumulative.get("output_tokens"),
                "cumulative_total_latency_ms": cumulative.get("total_latency_ms"),
                "cumulative_agent_turn_ms": cumulative.get("agent_turn_ms"),
                "cumulative_tool_calls": cumulative.get("tool_calls"),
                "cumulative_tool_time_ms": cumulative.get("tool_time_ms"),
            })
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if format == "json":
            atomic_write_json(target, rows)
        else:
            columns = list(rows[0]) if rows else [
                "run_id", "task_id", "track", "condition", "repetition_index", "run_status"
            ]
            with target.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
        return target

    def blind_export(self, run_ids: list[str] | None = None,
                     output_root: str | Path | None = None) -> tuple[Path, dict[str, str]]:
        selected = [self.show(run_id) for run_id in run_ids] if run_ids else self.list_metadata()
        if not selected:
            raise ResearchError("No runs are available for blind export")
        seen_run_ids: set[str] = set()
        for metadata in selected:
            run_id = metadata["run_id"]
            if run_id in seen_run_ids:
                raise ResearchError(f"Duplicate run id in blind export: {run_id}")
            seen_run_ids.add(run_id)
            if metadata.get("design_status") not in {"valid", "skipped"} or metadata.get("implementation_status") != "completed":
                raise ResearchError(f"Run is not ready for blind evaluation: {run_id}")
        export_id = uuid.uuid4().hex[:12]
        destination = Path(output_root).expanduser().resolve() if output_root else (
            self.research_root / "evaluation" / "blinded" / export_id
        )
        destination.mkdir(parents=True, exist_ok=False)
        used_aliases: set[str] = set()
        mapping: dict[str, str] = {}
        manifest: list[str] = []
        for metadata in selected:
            alias = "run_" + secrets.choice(string.ascii_lowercase) + f"{secrets.randbelow(100):02d}"
            while alias in used_aliases:
                alias = "run_" + secrets.choice(string.ascii_lowercase) + f"{secrets.randbelow(100):02d}"
            used_aliases.add(alias)
            mapping[alias] = metadata["run_id"]
            manifest.append(alias)
            run_dir, _ = load_run_metadata(self.research_root, metadata["run_id"])
            artifact_dir = destination / alias
            artifact_dir.mkdir()
            brief_snapshot = run_dir / metadata["brief_file"]["snapshot"]
            shutil.copy2(brief_snapshot, artifact_dir / ("brief" + brief_snapshot.suffix))
            design_spec = run_dir / "design" / "design_spec.json"
            if design_spec.exists():
                shutil.copy2(design_spec, artifact_dir / "design_spec.json")
            latest = Path(metadata.get("latest_workspace_path") or metadata["implementation_workspace"]["path"])
            copy_workspace(latest, artifact_dir / "implementation")
            atomic_write_json(artifact_dir / "evaluation.json", _empty_evaluation(alias))
        atomic_write_json(destination / "manifest.json", {"anonymous_ids": manifest})
        mapping_path = self.research_root / "hidden" / "evaluation-maps" / f"{export_id}.json"
        atomic_write_json(mapping_path, mapping)
        return destination, mapping


def check_environment(research_root: str | Path = DEFAULT_RESEARCH_ROOT,
                      config: Config | None = None) -> dict[str, Any]:
    config = config or Config()
    root = initialize_research_layout(research_root)
    try:
        from importlib.metadata import version
        schema_dependency = {"available": True, "version": version("jsonschema")}
    except ImportError:
        schema_dependency = {"available": False, "version": None}
    schema_path = root / "schemas" / "design-specification.schema.json"
    schema_valid = False
    schema_error = None
    try:
        schema = read_json(schema_path)
        Draft202012Validator.check_schema(schema)
        schema_valid = True
    except Exception as exc:
        schema_error = str(exc)
    parts = urlsplit(config.base_url)
    health_url = urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))
    try:
        response = httpx.get(health_url, timeout=2.0)
        server = {"reachable": response.is_success, "status_code": response.status_code, "url": health_url}
    except httpx.HTTPError as exc:
        server = {"reachable": False, "error": f"{type(exc).__name__}: {exc}", "url": health_url}
    return {
        "project_root": str(PROJECT_ROOT),
        "research_root": str(root),
        "python_version": __import__("sys").version.split()[0],
        "model_identifier": config.model,
        "model_server": {"base_url": config.base_url, "health": server},
        "model_configuration": {
            "temperature": config.temperature,
            "seed": config.seed,
            "context_length": config.context_length,
            "max_output_tokens": config.max_tokens,
            "timeout_seconds": config.timeout_seconds,
            "max_agent_steps": config.max_steps,
        },
        "dependencies": {"jsonschema": schema_dependency},
        "design_schema": {"valid": schema_valid, "error": schema_error},
        "directories": {
            relative: (root / relative).is_dir()
            for relative in ("briefs", "conditions", "schemas", "runs", "hidden", "evaluation", "scripts")
        },
        "ready": schema_dependency["available"] and schema_valid and server["reachable"],
    }
