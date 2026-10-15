#!/usr/bin/env python3
"""Sequential runner and verifier for Kaggle Paper Track follow-up experiments:
1. Large V2 Pure No-Design baseline (`Cond 0-Pure`, mode="direct", 0 design tokens)
2. Information-Content Controlled Ablation (`Cond 4-Unordered`, fixed-design with step numbers stripped & permuted)
3. n=3 Repetitions (`r001`..`r003`) for core Large V2 conditions (`Cond 0-Pure`, `Cond 3 Invariant`, `Cond 4 Flow`, `Cond 4-Unordered`)
"""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from gemma_agent.config import Config
from gemma_agent.research_runner import ExperimentRunner
from inspect_servers import run_large_verification

BRIEF_LARGE = ROOT_DIR / "research" / "briefs" / "brief_v2_counseling_large.md"
UNORDERED_SPEC = ROOT_DIR / "research" / "inputs" / "design_spec_cond4_unordered.json"
SUMMARY_OUT = ROOT_DIR / "research" / "outputs" / "ablation_and_repetitions_summary.json"


def evaluate_run_dir(run_dir: Path) -> dict[str, Any]:
    impl_dir = run_dir / "implementation"
    metadata_path = run_dir / "metadata.json"
    design_metrics_path = run_dir / "metrics" / "design.json"
    impl_metrics_path = run_dir / "metrics" / "implementation.json"
    total_metrics_path = run_dir / "metrics" / "total.json"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    design_m = json.loads(design_metrics_path.read_text(encoding="utf-8")) if design_metrics_path.is_file() else {}
    impl_m = json.loads(impl_metrics_path.read_text(encoding="utf-8")) if impl_metrics_path.is_file() else {}
    total_m = json.loads(total_metrics_path.read_text(encoding="utf-8")) if total_metrics_path.is_file() else {}

    # Load CounselingBookingEngine from implementation/counseling_engine.py
    engine_cls = None
    load_error = None
    engine_file = impl_dir / "counseling_engine.py"
    if not engine_file.is_file():
        py_files = [p for p in impl_dir.glob("*.py") if not p.name.startswith("test_")]
        if py_files:
            engine_file = py_files[0]

    if engine_file.is_file():
        try:
            spec = importlib.util.spec_from_file_location(f"eng_{run_dir.name}", engine_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                engine_cls = getattr(mod, "CounselingBookingEngine", None)
                if engine_cls is None:
                    for attr in dir(mod):
                        obj = getattr(mod, attr)
                        if isinstance(obj, type) and "Engine" in attr or "Service" in attr:
                            engine_cls = obj
                            break
        except Exception as exc:
            load_error = f"{type(exc).__name__}: {exc}"
    else:
        load_error = "counseling_engine.py not found"

    req_results = run_large_verification(engine_cls) if engine_cls is not None else []
    passed_reqs = [r["id"] for r in req_results if r.get("passed")]
    failed_reqs = [r["id"] for r in req_results if not r.get("passed")]

    # Also check agent pytest if test file exists
    pytest_summary = None
    try:
        proc = subprocess.run(
            [str(ROOT_DIR / ".venv" / "bin" / "pytest"), "-q"],
            cwd=str(impl_dir),
            env={"PYTHONPATH": str(impl_dir), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        last_line = (proc.stdout.strip().splitlines() or [""])[-1]
        pytest_summary = last_line
    except Exception as exc:
        pytest_summary = f"error: {exc}"

    cum = total_m.get("cumulative_total_cost") or {}
    design_in = design_m.get("input_tokens") or 0
    design_out = design_m.get("output_tokens") or 0
    impl_in = impl_m.get("input_tokens") or 0
    impl_out = impl_m.get("output_tokens") or 0
    total_tok = (design_in + design_out + impl_in + impl_out)
    design_sec = round((design_m.get("agent_turn_ms") or 0) / 1000.0, 2)
    impl_sec = round((impl_m.get("agent_turn_ms") or 0) / 1000.0, 2)
    total_min = round((design_sec + impl_sec) / 60.0, 2)

    # Check trace for step_limit
    trace_file = impl_dir / ".agent" / "trace.jsonl"
    hit_step_limit = False
    if trace_file.is_file():
        for line in trace_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"step_limit"' in line:
                hit_step_limit = True

    effective_status = "step_limit" if hit_step_limit else metadata.get("run_status", "unknown")

    return {
        "run_id": metadata.get("run_id", run_dir.name),
        "condition": metadata.get("condition"),
        "design_status": metadata.get("design_status"),
        "effective_status": effective_status,
        "design_input_tokens": design_in,
        "design_output_tokens": design_out,
        "design_time_s": design_sec,
        "impl_steps": impl_m.get("model_calls") or 0,
        "impl_tool_calls": impl_m.get("tool_calls") or 0,
        "impl_input_tokens": impl_in,
        "impl_output_tokens": impl_out,
        "impl_time_s": impl_sec,
        "total_tokens": total_tok,
        "total_time_m": total_min,
        "agent_pytest": pytest_summary,
        "std_verify_passed": len(passed_reqs),
        "std_verify_total": 8,
        "passed_reqs": passed_reqs,
        "failed_reqs": failed_reqs,
        "req_details": {r["id"]: {"passed": r["passed"], "actual": r["actual"]} for r in req_results},
        "load_error": load_error,
    }


def compute_group_stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {}

    def mean_std(values: list[float]) -> dict[str, float]:
        n = len(values)
        m = sum(values) / n
        if n < 2:
            return {"mean": round(m, 2), "std": 0.0, "n": n}
        var = sum((x - m) ** 2 for x in values) / (n - 1)
        return {"mean": round(m, 2), "std": round(math.sqrt(var), 2), "n": n}

    req8_passes = sum(1 for r in runs if "REQ-8" in r.get("passed_reqs", []))
    full_passes = sum(1 for r in runs if r.get("std_verify_passed") == 8)

    return {
        "n": len(runs),
        "total_tokens": mean_std([float(r["total_tokens"]) for r in runs]),
        "impl_output_tokens": mean_std([float(r["impl_output_tokens"]) for r in runs]),
        "impl_steps": mean_std([float(r["impl_steps"]) for r in runs]),
        "total_time_m": mean_std([float(r["total_time_m"]) for r in runs]),
        "std_verify_passed": mean_std([float(r["std_verify_passed"]) for r in runs]),
        "req8_pass_rate": f"{req8_passes}/{len(runs)}",
        "full_8_of_8_rate": f"{full_passes}/{len(runs)}",
    }


def save_summary(summary: dict[str, Any]) -> None:
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    config = Config(
        temperature=0.2,
        context_length=12288,
        max_tokens=4608,
        max_steps=15,
        timeout_seconds=900.0,
    )
    runner = ExperimentRunner(ROOT_DIR / "research", config=config)

    # Seed summary with existing r001 runs for Cond 3 Invariant and Cond 4 Flow
    existing_cond3_r1 = ROOT_DIR / "research" / "runs" / "20261014T142644Z_track2_cond3_invariant_r001_41f6db1b"
    existing_cond4_r1 = ROOT_DIR / "research" / "runs" / "20261014T145844Z_track2_cond4_flow_r001_a90209d0"

    if SUMMARY_OUT.is_file():
        summary = json.loads(SUMMARY_OUT.read_text(encoding="utf-8"))
    else:
        summary = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_jobs": [],
            "groups": {
                "cond0_pure": [],
                "cond4_unordered": [],
                "cond3_invariant": [evaluate_run_dir(existing_cond3_r1)] if existing_cond3_r1.is_dir() else [],
                "cond4_flow": [evaluate_run_dir(existing_cond4_r1)] if existing_cond4_r1.is_dir() else [],
            },
            "group_stats": {},
        }
        for g, rlist in summary["groups"].items():
            summary["group_stats"][g] = compute_group_stats(rlist)
        save_summary(summary)

    done_prefixes = {item.split(":")[0] for item in summary.get("completed_jobs", [])}

    jobs: list[dict[str, Any]] = [
        {"group": "cond0_pure", "rep": 1, "mode": "direct", "condition": "no_design", "fixed_design": None},
        {"group": "cond4_unordered", "rep": 1, "mode": "full", "condition": "cond4_unordered", "fixed_design": UNORDERED_SPEC},
        {"group": "cond0_pure", "rep": 2, "mode": "direct", "condition": "no_design", "fixed_design": None},
        {"group": "cond3_invariant", "rep": 2, "mode": "full", "condition": "cond3_invariant", "fixed_design": None},
        {"group": "cond4_flow", "rep": 2, "mode": "full", "condition": "cond4_flow", "fixed_design": None},
        {"group": "cond4_unordered", "rep": 2, "mode": "full", "condition": "cond4_unordered", "fixed_design": UNORDERED_SPEC},
        {"group": "cond0_pure", "rep": 3, "mode": "direct", "condition": "no_design", "fixed_design": None},
        {"group": "cond3_invariant", "rep": 3, "mode": "full", "condition": "cond3_invariant", "fixed_design": None},
        {"group": "cond4_flow", "rep": 3, "mode": "full", "condition": "cond4_flow", "fixed_design": None},
        {"group": "cond4_unordered", "rep": 3, "mode": "full", "condition": "cond4_unordered", "fixed_design": UNORDERED_SPEC},
    ]

    for idx, job in enumerate(jobs, 1):
        group = job["group"]
        job_key = f"{group}_r{job['rep']:03d}"
        if job_key in done_prefixes:
            print(f"[{idx}/{len(jobs)}] Skipping already completed {job_key}", flush=True)
            continue
        print(f"\n[{idx}/{len(jobs)}] Starting {group} (rep {job['rep']})...", flush=True)
        t0 = time.time()
        metas = runner.run_repetitions(
            track="track2",
            condition=job["condition"],
            brief=BRIEF_LARGE,
            repetitions=1,
            mode=job["mode"],
            task_id="brief_v2_counseling_large",
            fixed_design=job["fixed_design"],
        )
        meta = metas[0]
        run_dir = ROOT_DIR / "research" / "runs" / meta["run_id"]
        eval_res = evaluate_run_dir(run_dir)
        eval_res["repetition_number"] = job["rep"]
        elapsed = round((time.time() - t0) / 60.0, 2)
        print(
            f"[{idx}/{len(jobs)}] Finished {group} (rep {job['rep']}) in {elapsed}m -> "
            f"Verify: {eval_res['std_verify_passed']}/8 (Failed: {eval_res['failed_reqs']}), "
            f"Tokens: {eval_res['total_tokens']}",
            flush=True,
        )
        summary["completed_jobs"].append(f"{job_key}:{meta['run_id']}")
        summary["groups"][group].append(eval_res)
        summary["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for g, rlist in summary["groups"].items():
            summary["group_stats"][g] = compute_group_stats(rlist)
        save_summary(summary)


if __name__ == "__main__":
    main()
