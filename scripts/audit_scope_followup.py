#!/usr/bin/env python3
"""Re-verify the 30 preserved follow-up implementations without model calls.

Writes a portable audit with cohort overlap, per-run results, static SQL evidence,
specification hashes, harness status, and sample mean/SD telemetry. Original run
artifacts and original summary files are never modified.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import statistics
from pathlib import Path

from inspect_servers import run_large_verification

ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_queries(engine: Path) -> list[str]:
    tree = ast.parse(engine.read_text(encoding="utf-8"))
    methods = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "create_booking"]
    queries = sorted({n.value for method in methods for n in ast.walk(method)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)
                      and re.search(r"\bSELECT\b", n.value, re.I)
                      and re.search(r"\bbookings\b", n.value, re.I)
                      and re.search(r"\bidempotency_key\b", n.value, re.I)})
    if not queries:
        raise ValueError(f"No static idempotency SELECT found: {engine}")
    return queries


def audit_run(run_id: str, recorded: dict) -> dict:
    run_dir = ROOT / "research" / "runs" / run_id
    engine = run_dir / "implementation" / "counseling_engine.py"
    spec = importlib.util.spec_from_file_location(f"scope_audit_{run_id}", engine)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import {engine}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = run_large_verification(module.CounselingBookingEngine)
    passed = [r["id"] for r in checks if r["passed"]]
    if sorted(passed) != sorted(recorded["passed_reqs"]):
        raise ValueError(f"Verification differs from recorded summary: {run_id}")
    queries = lookup_queries(engine)
    filtered = any(re.search(r"\b(status|CONFIRMED|CANCELLED)\b",
                            re.split(r"\bWHERE\b", q, flags=re.I)[-1], re.I)
                   for q in queries)
    metadata = read_json(run_dir / "metadata.json")
    implementation = read_json(run_dir / "metrics" / "implementation.json")
    design_file = run_dir / "metrics" / "design.json"
    design = read_json(design_file) if design_file.exists() else {}
    coder_tokens = implementation["input_tokens"] + implementation["output_tokens"]
    total_tokens = coder_tokens + design.get("input_tokens", 0) + design.get("output_tokens", 0)
    if total_tokens != recorded["total_tokens"]:
        raise ValueError(f"Token telemetry differs from summary: {run_id}")
    return {
        "run_id": run_id,
        "passed_reqs": passed,
        "score": len(passed),
        "status_filter_in_idempotency": filtered,
        "idempotency_select_queries": queries,
        "harness_status": metadata["run_status"],
        "implementation_error_type": implementation.get("error_type"),
        "coder_steps": implementation["model_calls"],
        "coder_tokens": coder_tokens,
        "total_tokens": total_tokens,
        "total_time_m": recorded["total_time_m"],
        "design_status": metadata["design_status"],
        "design_sha256": hashlib.sha256((run_dir / "design" / "design_spec.json").read_bytes()).hexdigest(),
        "engine_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "model_configuration": metadata["model_configuration"],
    }


def mean_sd(values: list[float]) -> dict:
    return {"mean": round(statistics.mean(values), 2),
            "sample_sd": round(statistics.stdev(values), 2)}


def main() -> None:
    manifest = read_json(ROOT / "research" / "inputs" / "scope_followup_cohort.json")
    recorded = {}
    for source in manifest["source_summaries"]:
        data = read_json(ROOT / source)
        runs = data.get("runs", []) + [r for group in data.get("groups", {}).values() for r in group]
        recorded.update({r["run_id"]: r for r in runs})
    groups = {}
    for name, ids in manifest["followup_groups"].items():
        rows = [audit_run(rid, recorded[rid]) for rid in ids]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Repeated run IDs within {name}")
        groups[name] = {
            "n": len(rows),
            "full_passes": sum(r["score"] == 8 for r in rows),
            "req8_passes": sum("REQ-8" in r["passed_reqs"] for r in rows),
            "status_filter_count": sum(r["status_filter_in_idempotency"] for r in rows),
            "harness_completed": sum(r["harness_status"] == "completed" for r in rows),
            "harness_failed": sum(r["harness_status"] == "failed" for r in rows),
            **{key: mean_sd([r[key] for r in rows]) for key in
               ["score", "coder_steps", "coder_tokens", "total_tokens", "total_time_m"]},
            "runs": rows,
        }
        print(name, {k: v for k, v in groups[name].items() if k != "runs"})
    initial = set(manifest["initial_study_run_ids"])
    followup = {rid for ids in manifest["followup_groups"].values() for rid in ids}
    audit = {
        "verification": "REQ-1..REQ-8 rerun from preserved implementations; no model calls",
        "initial_study_n": len(initial), "followup_n": len(followup),
        "reused_initial_runs": sorted(initial & followup),
        "additional_n": len(followup - initial),
        "unique_study_n": len(initial | followup),
        "static_analysis_limit": "Static SQL strings inside create_booking; not a general SQL/data-flow analyzer or attention measurement.",
        "all_success_10_exact_95_ci": [round(0.025 ** (1 / 10), 6), 1.0],
        "groups": groups,
    }
    output = ROOT / "research" / "outputs" / "scope_followup_audit.json"
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(followup)} implementations; {len(initial | followup)} unique study runs.")


if __name__ == "__main__":
    main()
