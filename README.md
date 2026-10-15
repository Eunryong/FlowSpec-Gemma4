# FlowSpec-Gemma4: Ordering Matters More Than Rules

> **Execution-Flow Specifications for Multi-Table Transactional Coding with Gemma 4 31B**  
> *Design Representations, Information-Controlled Ablations, and Multi-Run Stability in a Local Agent Harness*

- 📄 **Full Paper (English, Kaggle Submission):** [`docs/kaggle_gemma4_paper_en.md`](docs/kaggle_gemma4_paper_en.md)
- 📄 **Full Paper (Korean):** [`docs/kaggle_gemma4_paper_ko.md`](docs/kaggle_gemma4_paper_ko.md)
- 📊 **Aggregated Telemetry & Multi-Run Summary (`n = 3`):** [`research/outputs/ablation_and_repetitions_summary.json`](research/outputs/ablation_and_repetitions_summary.json)
- 🗂️ **All 22 End-to-End Run Artifacts & Traces:** [`research/runs/`](research/runs/)

### Key Findings (Large-Scale 7-Table, 13-Method SQLite Benchmark, `n = 3` per Core Group)

| Group (`n = 3` on Large-Scale V2) | Per-Run Verify (`r1, r2, r3`) | Mean Verify | `8/8` (`REQ-8`) Pass Rate | Impl Steps | Impl Out Tokens | Total Tokens | Total Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`Cond 0-Pure` (Direct, 0 design tok)** | `7/8, 7/8, 7/8` | `7.00 ± 0.00` | `0/3 (0.0%)` | `10.00 ± 4.58` | `25,775 ± 19,505` | `83,419 ± 49,236` | `40.6 ± 30.7m` |
| **`Cond 3 Invariant` (2-stage)** | `7/8, 1/8, 1/8` | `3.00 ± 3.46` | `0/3 (0.0%)` | `12.33 ± 4.62` | `27,626 ± 7,784` | `122,799 ± 48,024` | `46.4 ± 15.4m` |
| **`Cond 4-Unordered` (Fixed Shuffled)** | `8/8, 7/8, 7/8` | `7.33 ± 0.58` | `1/3 (33.3%)` | `9.33 ± 4.16` | `22,653 ± 10,584` | `88,325 ± 42,688` | `34.4 ± 16.2m` |
| **`Cond 4-Flow` (`Step 1..N`)** ⭐ | **`8/8, 7/8, 8/8`** | **`7.67 ± 0.58`** | **`2/3 (66.7%)`** | **`8.67 ± 1.15`** | **`16,560 ± 418`** | **`83,878 ± 3,302`** | **`30.9 ± 3.0m`** |

---

## Harness Overview (`gemma-agent-worker`)

Minimal research harness for running a local Gemma coding agent through `llama.cpp` without Codex/Claude Code-style hidden orchestration.

## What this first version does

The model gets exactly five automatic tools, all restricted to one workspace:

- `list_files`
- `read_file`
- `write_file`
- `replace_text`
- `run_tests`

There is deliberately **no arbitrary shell**, internet access, sudo, or access outside the chosen workspace. Every model response and tool result is written to `.agent/trace.jsonl` for later research analysis.

## 1. Start llama.cpp

Tool calling requires `llama-server` to be started with a compatible chat template. Current upstream llama.cpp supports OpenAI-style function calling with `--jinja`; depending on the Gemma 4 model/template you may need the model's official tool-use Jinja template or a custom template.

Example shape only (adjust model path / cache flags for your Gemma 4 build):

```bash
llama-server \
  -m /path/to/gemma4.gguf \
  --jinja \
  --host 127.0.0.1 \
  --port 8080
```

## 2. Install

Using `uv`:

```bash
cd /Users/eunryong/develop/tools/gemma-agent-worker
uv venv
source .venv/bin/activate
uv pip install -e .
uv pip install pytest
```

Or pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest
```

## 3. Configure

Defaults:

```bash
export LLAMA_BASE_URL=http://127.0.0.1:8080/v1
export LLAMA_MODEL=local-model
export LLAMA_TEMPERATURE=0.2
export LLAMA_MAX_TOKENS=4096
export AGENT_MAX_STEPS=40
```

If your llama-server exposes a specific model id, set `LLAMA_MODEL` to it.

## 4. Run

Create a separate experiment workspace. Do **not** point it at the whole home directory.

```bash
mkdir -p /Users/eunryong/develop/tools/agent-workspaces/smoke-test

gemma-agent \
  --workspace /Users/eunryong/develop/tools/agent-workspaces/smoke-test \
  --prompt "Create a small Python function add(a, b), add tests, and run them."
```

Interactive mode:

```bash
gemma-agent \
  --workspace /Users/eunryong/develop/tools/agent-workspaces/smoke-test \
  --interactive
```

The interactive session keeps one agent and its conversation history alive across turns. Enter `exit` or `quit` to leave; Ctrl-C and Ctrl-D also end the session. Omitting both `--prompt` and `--interactive` continues to start interactive mode for compatibility.

## Trace metrics

Each model request keeps its token usage, TTFT, generation time, total latency, generation speed, and server timing data in the existing model_response event. Each user request also writes one turn_metrics event, including input/output/total token counts, TTFT, first text time, summed generation and request latency, model/tool call counts, tool time, and total agent turn time. Turn metrics are written for failed requests too, with status and error type.

Input tokens are the prompt tokens reported by llama.cpp. They include the system prompt, conversation history, and tool schemas sent on each model call. Turn totals sum across all model calls, so repeated history in a tool-using turn is counted each time. TTFT measures time to the first generated model token; first_text_ms is recorded separately for turns that first emit a tool call. The CLI still prints the completed answer after the agent turn finishes.

Every trace event carries a generated run_id and a turn_id. Optional task, condition, and stage labels can be added to the trace with --task-id, --condition, and --stage; these labels are not added to the model prompt and do not change agent behavior. Pass --run-id to set a stable run label. llama.cpp server timing fields are retained when provided. Host peak memory and KV cache usage are not currently collected.

For example, add --task-id task-01 --condition generic --stage implementation to a gemma-agent command to label its trace rows.

## Research design note

Keep this baseline harness stable. Add Design Reasoning Profile and Revision-aware Design as separate prompt/condition layers later. Do not bake planning behavior into the base harness or it becomes a confound.

## Reproducible research harness

연구 결정·설계 문서의 읽기 순서는 [docs/README.md](docs/README.md)에 있습니다. 새 실험을 실행하기 전에는 문서에 정의된 요구 승인과 readiness gate를 완료해야 합니다.

The separate `run-experiment` command manages file-based runs for `track1` and `track2`. It keeps the existing `gemma-agent` one-shot and interactive commands intact. The repository includes placeholder condition files and schemas only; it does not include a service brief, study condition wording, hidden tests, or future-change content.

Install the research dependency and command in the project environment:

```bash
cd /Users/eunryong/develop/tools/gemma-agent-worker
source .venv/bin/activate
pip install -e .
```

Before a study, replace `research/briefs/placeholder.md` with the approved shared brief (or pass a separate `.md`/`.json` file). Put the finalized condition wording in exactly one selected file under `research/conditions/track1/` or `research/conditions/track2/`. Do not put hidden evaluation files in the brief, condition, or source workspace.

Check the local setup and run an example condition three times:

```bash
run-experiment check
run-experiment full \
  --track track1 \
  --condition profile_edge_case \
  --brief research/briefs/placeholder.md \
  --repetitions 3 \
  --seed 100 \
  --context-length 32768 \
  --server-config "llama.cpp build and launch flags"
```

The command without a subcommand also means `full` for convenience. Other useful operations:

```bash
run-experiment design --track track1 --condition generic --brief research/briefs/placeholder.md
run-experiment show <run_id>
run-experiment verify-group --track track1 --condition profile_edge_case
run-experiment export --format csv --output research/evaluation/comparison.csv
run-experiment blind-export
run-experiment revise <track2_run_id>
```

Each run lives under `research/runs/<run_id>/` with the input snapshots and hashes, design output/schema validation, an isolated implementation workspace, stage traces, cost metrics, and an evaluation result template. The separate design and coder sessions have independent traces. Track 2 changes are read from `research/hidden/changes/change_01.md`, `change_02.md`, and so on, and each next file is revealed only after the prior stage completes. Hidden content is never copied from the project `research/` tree into a model-visible workspace.

`research/conditions/` files are intentionally placeholders: edit them only when the study conditions are ready to be specified. The research harness validates the Designer JSON and records errors without repairing the output. It stores token counts, TTFT, optional llama.cpp prompt/prefill timings, generation and total latency, generation speed, tool counts/timing, and stage/cumulative totals. Server context length is configured when starting llama.cpp; `--context-length` records the study's intended value in metadata. Host peak memory and KV-cache usage are not collected.
## Local service prototype

A separate, locally runnable 1:1 counseling booking prototype lives in [prototype/counseling-booking](prototype/counseling-booking/README.md). It is a demo only and is not part of the research harness inputs.

Start it from the project root with one command:

    python3 prototype/counseling-booking/server.py

Then open http://127.0.0.1:8765. Scope assumptions and data limitations are documented in the prototype README.
