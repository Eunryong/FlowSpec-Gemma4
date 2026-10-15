import json
import time
from pathlib import Path
import sys

from gemma_agent.config import Config
from gemma_agent.research_runner import ExperimentRunner

def main():
    research_root = Path("research")
    brief_path = research_root / "briefs/brief_v1.md"
    outputs_dir = research_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    conditions = [
        ("cond1_generic", outputs_dir / "cond1_generic.json"),
        ("cond2_contract", outputs_dir / "cond2_contract.json"),
        ("cond3_invariant", outputs_dir / "cond3_invariant.json"),
        ("cond4_profiled", outputs_dir / "cond4_profiled.json"),
    ]

    config = Config(
        context_length=12288,
        max_tokens=3584,
    )

    runner = ExperimentRunner(research_root, config=config)

    for cond_name, output_file in conditions:
        print(f"\n[RUNNER] >>> Starting {cond_name} ...", flush=True)
        started = time.time()
        try:
            results = runner.run_full(
                track="track2",
                condition=cond_name,
                brief=brief_path,
                repetitions=1,
            )
            elapsed = time.time() - started
            output_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
            status = results[0].get("run_status") if results else "unknown"
            design_status = results[0].get("design_status") if results else "unknown"
            impl_status = results[0].get("implementation_status") if results else "unknown"
            print(f"[RUNNER] <<< Finished {cond_name} in {elapsed:.1f}s | run_status: {status} | design: {design_status} | impl: {impl_status}", flush=True)
        except Exception as exc:
            print(f"[RUNNER] !!! Error in {cond_name}: {type(exc).__name__}: {exc}", flush=True)

    print("\n[RUNNER] All conditions finished sequentially.", flush=True)

if __name__ == "__main__":
    main()
