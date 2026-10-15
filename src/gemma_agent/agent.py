from __future__ import annotations

import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Config
from .llama_client import LlamaClient
from .tools import ToolRegistry
from .trace import TraceLogger
from .workspace import Workspace


DEFAULT_SYSTEM_PROMPT = """You are a local coding agent running inside a restricted experiment workspace.

You may inspect and modify files only through the provided tools. All tool calls inside the workspace are automatically approved.

Rules:
1. Inspect relevant files before changing them.
2. Keep changes scoped to the user's request.
3. Do not invent access to the internet, system files, or tools that are not provided.
4. After code changes, run tests when a test suite is available or when you create one.
5. If a tool fails, inspect the failure and recover rather than pretending it succeeded.
6. When the task is complete, return a concise summary of changes and test status.
"""


TRACE_LABELS = {"task_id", "condition", "stage"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _token_count(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _sum_complete(values: list[int | float | None], expected: int) -> int | float | None:
    if expected == 0:
        return 0
    if len(values) != expected or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


class CodingAgent:
    def __init__(
        self,
        workspace_path: str | Path,
        *,
        config: Config | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        trace_path: str | Path | None = None,
        run_id: str | None = None,
        trace_metadata: dict[str, str | None] | None = None,
    ):
        self.config = config or Config()
        self.workspace = Workspace(workspace_path)
        self.tools = ToolRegistry(self.workspace)
        self.client = LlamaClient(self.config)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.trace = TraceLogger(trace_path or (self.workspace.root / ".agent" / "trace.jsonl"))
        self.run_id = run_id or str(uuid.uuid4())
        metadata = trace_metadata or {}
        self.trace_metadata = {
            key: str(value)
            for key, value in metadata.items()
            if key in TRACE_LABELS and value is not None and str(value).strip()
        }
        self.turn_count = 0

    def _write_trace(self, event: str, turn_id: int, **data: Any) -> None:
        self.trace.write(
            event,
            run_id=self.run_id,
            turn_id=turn_id,
            **self.trace_metadata,
            **data,
        )

    def _compact_messages(self) -> None:
        if len(self.messages) <= 4:
            return

        def _message_len(m: dict[str, Any]) -> int:
            length = len(str(m.get("content", "") or ""))
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                length += len(str(fn.get("name", "")))
                length += len(str(fn.get("arguments", "")))
            return length

        # First pass: compact huge (>3000 chars) write_file payloads from earlier turns
        # (excluding the most recent assistant+tool pair) so the model sees its full most-recent write.
        for i in range(1, max(1, len(self.messages) - 2)):
            msg = self.messages[i]
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    args_str = fn.get("arguments", "")
                    if name == "write_file" and len(args_str) > 3_000:
                        try:
                            parsed = json.loads(args_str)
                            path = parsed.get("path", "file.py")
                            content = str(parsed.get("content", ""))
                            lines = content.splitlines()
                            preview = (
                                "\n".join(lines[:15])
                                + f"\n# [HISTORY COMPACTED: All {len(lines)} lines were completely saved to disk at {path}]\n"
                                + "\n".join(lines[-10:])
                            )
                            fn["arguments"] = json.dumps({"path": path, "content": preview})
                        except Exception:
                            pass

        total_chars = sum(_message_len(m) for m in self.messages)
        if total_chars <= 16_000:
            return

        # Second pass: prune older messages from index 1 to len - 2
        for i in range(1, max(1, len(self.messages) - 2)):
            msg = self.messages[i]
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 300:
                    msg["content"] = content[:150] + "\n... [earlier tool output truncated for context limit] ...\n" + content[-150:]
            elif msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    args_str = fn.get("arguments", "")
                    if name == "write_file" and len(args_str) > 400:
                        try:
                            parsed = json.loads(args_str)
                            path = parsed.get("path", "file.py")
                            fn["arguments"] = json.dumps({
                                "path": path,
                                "content": f"# [Code written to {path}; use read_file to inspect]"
                            })
                        except Exception:
                            pass
                    elif name == "replace_text" and len(args_str) > 400:
                        try:
                            parsed = json.loads(args_str)
                            path = parsed.get("path", "file.py")
                            fn["arguments"] = json.dumps({
                                "path": path,
                                "old": "[omitted to conserve context]",
                                "new": "[omitted to conserve context]"
                            })
                        except Exception:
                            pass
            total_chars = sum(_message_len(m) for m in self.messages)
            if total_chars <= 16_000:
                break

    def run(self, user_request: str) -> str:
        turn_started = time.perf_counter()
        self.turn_count += 1
        turn_id = self.turn_count
        self.messages.append({"role": "user", "content": user_request})

        model_calls = 0
        tool_calls = 0
        tool_time_total_ms = 0.0
        token_samples: list[dict[str, int | None]] = []
        generation_samples: list[float | None] = []
        latency_samples: list[float | None] = []
        turn_ttft_ms: float | None = None
        first_text_ms: float | None = None
        status = "failed"
        error_type: str | None = None

        try:
            self._write_trace("user_request", turn_id, content=user_request)
            for step in range(1, self.config.max_steps + 1):
                self._compact_messages()
                call_started = time.perf_counter()
                model_calls += 1
                try:
                    message, meta = self.client.chat(self.messages, self.tools.schemas)
                except BaseException as exc:
                    if isinstance(exc, RuntimeError) and "HTTP 500" in str(exc) and "Failed to parse tool call arguments" in str(exc):
                        for m in self.messages:
                            for tc in m.get("tool_calls") or []:
                                fn = tc.get("function") or {}
                                args_str = fn.get("arguments", "")
                                try:
                                    json.loads(args_str)
                                except Exception:
                                    fn["arguments"] = "{}"
                        self.messages.append({
                            "role": "user",
                            "content": "System notice: Your previous tool call arguments failed to parse as valid JSON because the output was truncated. Keep your thinking brief (<100 words) and emit concise code.",
                        })
                        try:
                            message, meta = self.client.chat(self.messages, self.tools.schemas)
                        except BaseException:
                            call_elapsed_ms = (time.perf_counter() - call_started) * 1000
                            latency_samples.append(call_elapsed_ms)
                            generation_samples.append(None)
                            token_samples.append({"input_tokens": None, "output_tokens": None, "total_tokens": None})
                            self._write_trace(
                                "model_error",
                                turn_id,
                                step=step,
                                error_type=type(exc).__name__,
                                total_latency_ms=round(call_elapsed_ms, 3),
                            )
                            raise
                    else:
                        call_elapsed_ms = (time.perf_counter() - call_started) * 1000
                        latency_samples.append(call_elapsed_ms)
                        generation_samples.append(None)
                        token_samples.append({"input_tokens": None, "output_tokens": None, "total_tokens": None})
                        self._write_trace(
                            "model_error",
                            turn_id,
                            step=step,
                            error_type=type(exc).__name__,
                            total_latency_ms=round(call_elapsed_ms, 3),
                        )
                        raise

                call_elapsed_ms = (time.perf_counter() - call_started) * 1000
                meta = meta or {}
                usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
                input_tokens = _token_count(meta.get("input_tokens"))
                if input_tokens is None:
                    input_tokens = _token_count(usage.get("prompt_tokens", usage.get("input_tokens")))
                output_tokens = _token_count(meta.get("output_tokens"))
                if output_tokens is None:
                    output_tokens = _token_count(usage.get("completion_tokens", usage.get("output_tokens")))
                total_tokens = _token_count(meta.get("total_tokens"))
                if total_tokens is None:
                    total_tokens = _token_count(usage.get("total_tokens"))
                if total_tokens is None and input_tokens is not None and output_tokens is not None:
                    total_tokens = input_tokens + output_tokens
                token_samples.append({
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                })

                request_latency = _number(meta.get("total_latency_ms"))
                if request_latency is None:
                    elapsed_seconds = _number(meta.get("elapsed_seconds"))
                    request_latency = elapsed_seconds * 1000 if elapsed_seconds is not None else call_elapsed_ms
                latency_samples.append(request_latency)
                generation_samples.append(_number(meta.get("generation_ms")))

                call_offset_ms = (call_started - turn_started) * 1000
                call_ttft_ms = _number(meta.get("ttft_ms"))
                if turn_ttft_ms is None and call_ttft_ms is not None:
                    turn_ttft_ms = call_offset_ms + call_ttft_ms
                call_first_text_ms = _number(meta.get("first_text_ms"))
                if first_text_ms is None and call_first_text_ms is not None:
                    first_text_ms = call_offset_ms + call_first_text_ms

                self._write_trace("model_response", turn_id, step=step, message=message, meta=meta)
                self.messages.append(message)

                calls = message.get("tool_calls") or []
                if not calls:
                    content = message.get("content") or ""
                    if meta.get("finish_reason") == "length":
                        message["content"] = content or "[thinking truncated due to max_output_tokens]"
                        self.messages.append({
                            "role": "user",
                            "content": (
                                "System notice: Your previous turn hit max_output_tokens during thinking before "
                                "emitting a tool call. Keep your thinking under 50 words and immediately call "
                                "the required tool (e.g. write_file or run_tests)."
                            ),
                        })
                        continue
                    status = "completed"
                    self._write_trace("finished", turn_id, step=step, content=content)
                    return content

                for call in calls:
                    tool_calls += 1
                    tool_started = time.perf_counter()
                    function = call.get("function") or {}
                    name = function.get("name", "")
                    raw_arguments = function.get("arguments", "{}")
                    try:
                        arguments = raw_arguments if isinstance(raw_arguments, dict) else json.loads(raw_arguments or "{}")
                    except (json.JSONDecodeError, TypeError) as exc:
                        result_text = json.dumps({
                            "ok": False,
                            "output": (
                                f"Invalid tool JSON: {exc}. Your tool call was cut off because your thinking + code "
                                "exceeded max_output_tokens. Keep your thinking very short (<100 words) and write "
                                "compact code (omit docstrings/comments) or split into smaller files."
                            ),
                        })
                        if name == "write_file":
                            function["arguments"] = json.dumps({"path": "file.py", "content": "# [truncated; retry with shorter code]"})
                        else:
                            function["arguments"] = "{}"
                    else:
                        result = self.tools.execute(name, arguments)
                        result_text = result.as_text()
                    tool_elapsed_ms = (time.perf_counter() - tool_started) * 1000
                    tool_time_total_ms += tool_elapsed_ms

                    self._write_trace(
                        "tool_result",
                        turn_id,
                        step=step,
                        tool_call_id=call.get("id"),
                        name=name,
                        arguments=raw_arguments,
                        result=result_text,
                        elapsed_ms=round(tool_elapsed_ms, 3),
                    )
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": name,
                            "content": result_text,
                        }
                    )

            raise RuntimeError(f"Agent exceeded max steps ({self.config.max_steps})")
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            input_tokens = _sum_complete(
                [sample["input_tokens"] for sample in token_samples], model_calls
            )
            output_tokens = _sum_complete(
                [sample["output_tokens"] for sample in token_samples], model_calls
            )
            total_tokens = (
                input_tokens + output_tokens
                if input_tokens is not None and output_tokens is not None
                else _sum_complete([sample["total_tokens"] for sample in token_samples], model_calls)
            )
            generation_ms = _sum_complete(generation_samples, model_calls)
            total_latency_ms = _sum_complete(latency_samples, model_calls)
            generation_tokens_per_second = None
            if output_tokens is not None and generation_ms is not None and generation_ms > 0:
                generation_tokens_per_second = output_tokens / (generation_ms / 1000)
            agent_turn_ms = (time.perf_counter() - turn_started) * 1000
            self._write_trace(
                "turn_metrics",
                turn_id,
                status=status,
                error_type=error_type,
                model_calls=model_calls,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                token_usage_complete=(
                    model_calls > 0
                    and input_tokens is not None
                    and output_tokens is not None
                ),
                model_calls_with_usage=sum(
                    sample["input_tokens"] is not None or sample["output_tokens"] is not None
                    for sample in token_samples
                ),
                ttft_ms=round(turn_ttft_ms, 3) if turn_ttft_ms is not None else None,
                first_text_ms=round(first_text_ms, 3) if first_text_ms is not None else None,
                generation_ms=round(generation_ms, 3) if generation_ms is not None else None,
                total_latency_ms=round(total_latency_ms, 3) if total_latency_ms is not None else None,
                generation_tokens_per_second=(
                    round(generation_tokens_per_second, 3)
                    if generation_tokens_per_second is not None
                    else None
                ),
                tool_time_ms=round(tool_time_total_ms, 3),
                agent_turn_ms=round(agent_turn_ms, 3),
            )
