# FlowSpec-Gemma4: Execution Order and Method Scope in Transactional Code Generation

**Subtitle:** 46 preserved runs, a 30-run follow-up, and the limits of ordering alone in a local Gemma 4 coding harness

## 1. Abstract

We study how design specifications affect a local coding agent implementing SQLite reservation engines. The reported model is **Gemma 4 31B-IT**, served through `llama.cpp` with a `12,288`-token context and `temperature=0.2`. The study comprises **46 unique runs**: an initial 22-run comparison across two task scales and 24 additional V2 runs. The follow-up contains **30 observations, n=10 per condition**, including six observations reused from the initial study. It compares numbered execution flow, shuffled unnumbered flow, and execution flow augmented with an explicit method-scoped idempotency rule.

Re-running eight external requirement checks on the 30 preserved implementations reproduces full-pass counts of **5/10, 4/10, and 10/10**, respectively. A booking-status predicate in the idempotency lookup appears in **5/10, 6/10, and 0/10** implementations. The scoped intervention therefore has the best observed artifact correctness, but costs more tokens and yields only **5/10 normally completed agent sessions**; five sessions exhaust the 15-step budget despite leaving code that passes all checks. The result supports further study of explicit rule boundaries. It does not establish deterministic reliability, a general ordering advantage, or an internal attention mechanism.

## 2. Research Questions

Structured development workflows motivate separating a Designer from a Coder, as in work on SOP-based agent coordination ([MetaGPT](https://arxiv.org/abs/2308.00352)). Here we isolate the specification artifact within a small local harness. This is a code-generation study on two related benchmarks; its scores are not comparable to repository issue-resolution benchmarks such as [SWE-bench](https://arxiv.org/abs/2310.06770).

We ask: (1) how do design representations change correctness and cost; (2) does preserving rule content while removing numbering and shuffling bullets change outcomes; and (3) does explicitly restricting a rule to its intended method reduce a recurring cancelled-booking replay error?

## 3. Methodology

### 3.1 Harness, Tasks, and Outcomes

The original two-stage pipeline generates a JSON design in a single-turn Designer session, then gives the brief and design to a fresh Coder workspace. The Coder has five tools: `list_files`, `read_file`, `write_file`, `replace_text`, and `run_tests`. Fixed-design follow-ups inject a saved JSON artifact without a new Designer call. Prompts, metrics, generated code, and JSONL traces are preserved.

Reported settings are Gemma 4 31B-IT `Q4_K_M`, one `llama.cpp` slot, `temperature=0.2`, context `12,288`, and a 15-step budget. **Exceptions:** V1 no-design had a 40-step ceiling and finished in nine steps; per-turn output limits were `3,584` for V1 Cond 1–3 and 5, and `4,608` for V1 Flow and V2. V2 Flow r1 records a 300-second timeout; later follow-up configurations record 900 seconds. Seeds are unset. Metadata labels the endpoint `local-model` and does not contain an immutable model-file fingerprint.

V1 is a two-table, five-operation booking backend with six checks. V2 is a **seven-table, thirteen-operation backend** covering counselors, slots, prepaid passes, an idempotent ledger, bookings, a FIFO waitlist, and audit logs. Its eight checks cover slot lifecycle (REQ-1), pass issuance (REQ-2), booking creation (REQ-3), atomic rescheduling (REQ-4), cancellation without promotion (REQ-5), waitlist promotion (REQ-6), reconciliation (REQ-7), and cancelled-booking replay (REQ-8). REQ-8 requires a repeated idempotency key to return the existing cancelled booking without another pass deduction.

We distinguish **external artifact verification**, agent-written pytest results, and **harness completion**. A budget-exhausted session can leave a passing artifact. Eight checks do not establish correctness for all inputs or concurrency schedules. Means are reported with sample standard deviations. Total tokens sum Designer and Coder input/output usage across calls; they include repeated context, not just unique text. Coder-only tokens are also reported for the mixed follow-up cohort.

### 3.2 Conditions and Cohort Accounting

The initial 22-run study includes no-design baselines (direct and minimal wrapper), prose, structural contracts, declarative invariants, numbered execution flow, shuffled flow, and flow with behavioral checklists. Tables 1–3 retain these original observations.

The extension compares:

- **Flow Base:** numbered flows; original r1–r3 plus seven new runs. The first three used separately generated designs. New r4–r10 freeze r1's design.
- **Unordered:** r1's flow rule content and schemas, with step numbers removed and bullets shuffled; three original plus seven new runs. This preserves rule content, not identical token sequences, and changes numbering and position together.
- **Flow + Scoped:** the frozen Flow design plus a Korean/English clarification attached to `create_booking` step 1 and repeated in a `scope_rule` field. It says to return an existing booking regardless of status and restricts the `CONFIRMED` eligibility check to rescheduling/cancellation. An earlier pilot r1 is included with nine subsequent runs.

Thus **22 + 24 = 46 unique study runs**, not 52. The 30 follow-up observations overlap the initial study by six runs. Scoped changes instruction content, length, repetition, and language as well as scope. These are exploratory sequential cohorts, not a fully randomized, token-matched factorial experiment. No `Unordered + Scoped` condition has been run.

## 4. Results

### 4.1 Initial Sweep: Historical Results

#### Table 1: V1 (2 tables, 5 operations, 6 requirements)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**Cond 0-Pure (`No Design`)**|`completed`|0|0|0.0s|9 (8)|44,221|5,648|49,869|8.7m|10/10|**6/6**|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|1,271|2,035|173.6s|15 (15)|67,215|8,973|79,494|17.8m|10/12|**6/6***|
|**Cond 2 (`Static Contracts`)**|`completed`|1,308|2,547|217.9s|11 (10)|50,205|16,036|70,096|27.9m|11/11|**6/6**|
|**Cond 3 (`State Invariants`)**|`step_limit`|1,328|2,663|230.0s|15 (15)|84,413|19,091|107,495|39.0m|0/11†|**6/6**|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|1,715|2,009|172.5s|**7 (6)**|**24,142**|**5,353**|**33,219**|**10.5m**|8/8|**6/6**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|1,409|2,501|241.2s|15 (15)|65,576|6,826|76,312|17.5m|0/12‡|0/6 (6/6‡)|

*\*V1 `Cond 1` initially opened a new SQLite connection per query (breaking `:memory:` state), cached a persistent connection at Step 14 (`6/6`), and left an unimported exception reference on duplicate cancellation (`10/12` agent tests).*  
*†V1 `Cond 3` passed `6/6`, but its tests imported a custom verification exception while the engine raised a standard permission exception, exhausting 15 steps.*  
*‡V1 `Cond 5` placed DB setup in a helper class whose constructor called two different initialization method names in consecutive lines while only defining the second name (`6/6` once the first call is removed).*

#### Table 2: Large-Scale Task Initial Sweep (V2, 7 Tables, 13 Operations, 8 Requirements, `r1`)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|Failed Reqs|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
|**Cond 0-Pure (`Direct`)**|`completed`|0|0|0.0s|6 (5)|30,999|12,383|43,382|19.3m|8/8|7/8|`REQ-8`|
|**Cond 0-Min (`Unprimed`)**|`completed`|3,967|2,537|261.9s|7 (5)|42,005|15,389|63,898|28.2m|8/8|7/8|`REQ-8`|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|4,014|2,542|212.9s|15 (14)|105,782|25,892|138,230|42.1m|6/8|6/8|`REQ-5, REQ-7`|
|**Cond 2 (`Static Contracts`)**|`completed`|4,091|2,068|190.1s|12 (11)|80,475|39,609|126,243|59.5m|8/8|7/8|`REQ-8`|
|**Cond 3 (`State Invariants`)**|`completed`|4,135|2,141|180.3s|7 (5)|41,439|19,854|67,569|31.3m|8/8|7/8|`REQ-8`|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|4,501|1,547|285.8s|10 (8)|63,150|16,134|85,332|28.3m|8/8|**8/8**|**None (100%)**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|4,329|1,353|116.2s|15 (15)|96,795|54,413|156,890|79.1m|—§|7/8|`REQ-8`|

*§V2 `Cond 5` suffered repeated output truncations and compactions (`54,413` coder output tokens), hitting Step 15 before creating unit tests; its generated engine passes `7/8`.*

### 4.2 Initial Repetitions: Historical n=3 Results

Table 3 describes the original subset; its two-of-three versus one-of-three result is not an independent replication of the expanded cohort.

#### Table 3: Original V2 repetitions (mean ± sample SD)

|Group (`n=3` on Large-Scale V2)|Per-Run Verify (`r1, r2, r3`)|Mean Verify|8/8 (`REQ-8`) Pass Rate|Impl Steps|Impl Out Tokens|Total Tokens|Total Time|
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**`Cond 0-Pure` (Direct, 0 design tok)**|`7/8, 7/8, 7/8`|`7.00±0.00`|`0/3 (0.0%)`|`10.00±4.58`|`25,775±19,505`|`83,419±49,236`|`40.6±30.7m`|
|**`Cond 3 Invariant` (2-stage)**|`7/8, 1/8, 1/8`|`3.00±3.46`|`0/3 (0.0%)`|`12.33±4.62`|`27,626±7,784`|`122,799±48,024`|`46.4±15.4m`|
|**`Cond 4-Unordered` (Fixed Shuffled)**|`8/8, 7/8, 7/8`|`7.33±0.58`|`1/3 (33.3%)`|`9.33±4.16`|`22,653±10,584`|`88,325±42,688`|`34.4±16.2m`|
|**`Cond 4-Flow` (`Step 1..N`)** ⭐|**`8/8, 7/8, 8/8`**|**`7.67±0.58`**|**`2/3 (66.7%)`**|**`8.67±1.15`**|**`16,560±418`**|**`83,878±3,302`**|**`30.9±3.0m`**|

### 4.3 Expanded V2 Follow-Up (n=10 per condition)

The external verifier was rerun against all 30 preserved implementations. Every per-run pass/fail pattern matched the original summaries. Static inspection of SQL strings inside `create_booking` independently reproduced the status-filter counts. This inspection handles multiline literals but is not a general SQL/data-flow analyzer.

#### Table 4: Correctness, Lookup Predicates, and Harness Completion

| Condition | n | Status-filter instances | REQ-8 pass | Full 8/8 pass | Mean score ± SD | Harness completed |
| :--- | ---: | :---: | :---: | :---: | :---: | :---: |
| Flow Base | 10 | 5/10 | 5/10 | 5/10 (50%) | 7.50 ± 0.53 | 8/10 |
| Unordered | 10 | 6/10 | 4/10 | 4/10 (40%) | 7.40 ± 0.52 | 10/10 |
| Flow + Scoped | 10 | 0/10 | 10/10 | 10/10 (100%) | 8.00 ± 0.00 | 5/10 |

In this cohort, every status-filter instance coincides with a REQ-8 failure; all other checks pass. The scoped artifact pass rate is 50 percentage points above Flow Base. The nine subsequent scoped runs also pass 9/9 when the earlier pilot is excluded. Five scoped sessions (r2, r3, r4, r8, r10) nevertheless record `failed` after exhausting 15 steps. Artifact verification and session completion must not be conflated.

#### Table 5: Recorded Follow-Up Cost (mean ± sample SD)

| Condition | Coder steps | Coder tokens | Total tokens | Recorded time (min) |
| :--- | :---: | :---: | :---: | :---: |
| Flow Base | 9.40 ± 3.24 | 89,959 ± 38,921 | 92,001 ± 38,313 | 38.65 ± 16.09 |
| Unordered | 7.80 ± 2.35 | 71,144 ± 24,517 | 71,144 ± 24,517 | 28.57 ± 10.31 |
| Flow + Scoped | 11.40 ± 3.89 | 119,054 ± 48,610 | 119,054 ± 48,610 | 68.25 ± 35.67 |

Flow Base includes Designer costs for its first three observations; the fixed-design conditions do not. Scoped uses about 29% more total tokens, or 32% more Coder tokens, than Flow Base. Timings come from sequential sessions and do not isolate prompt effects from workstation conditions. The initial Flow group's low token variance (Table 3) does not persist in the expanded cohort (Table 5).

Ten successes do not imply a true success probability of one. Under an independent, identical Bernoulli-trial assumption, the two-sided 95% Clopper–Pearson interval for 10/10 is approximately **69.2%–100%** (exact interval convention documented by [SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html)). Cohort reuse and pilot inclusion further limit a confirmatory interpretation. We make no claim of statistical proof of a general causal effect.

## 5. Code and Trace Evidence

### 5.1 Predicate Mixing in Idempotency Replay

A recurring failing implementation uses:

```sql
SELECT * FROM bookings WHERE idempotency_key=? AND status='CONFIRMED'
```

A cancelled record cannot satisfy this predicate. Replay then continues into creation logic instead of returning the existing booking. Passing implementations use an idempotency-key lookup without that status restriction. The scoped prompt states this boundary explicitly. The observed pattern is consistent with confusion between replay lookup and mutation eligibility; it does not directly measure attention or establish that adjacent-method interference is the sole cause.

### 5.2 Other Failure Patterns in the Initial Study

- **Prose (V2):** cancellation omits the fallback that reopens a slot when no eligible waitlisted client is promoted, failing REQ-5 and REQ-7.
- **Invariants (r2/r3):** pass issuance emits `INSERT OR REPLACE` followed by an additive `UPDATE`, double-counting the initial balance. The code shows an appended correction rather than replacement of the original statement; this observation does not establish a general limitation of invariant specifications.
- **Profiled flow (V2):** traces show repeated truncated write payloads and history compaction, ending at the step budget without agent tests. The remaining engine passes 7/8 external checks.

These examples motivate method-level guards, explicit branch postconditions, and evaluation of final artifacts independently of the agent's own tests. They are case evidence rather than direct measurements of model cognition.

## 6. Interpretation, Limitations, and Next Experiment

The initial study suggested execution ordering might improve reliability. The extension narrows that claim: **ordering alone yields 5/10 versus 4/10 full passes**, while the scoped intervention yields 10/10 artifact passes with higher cost and lower session completion. We therefore describe order and scope jointly rather than claim that ordering matters more than rules.

A practical candidate template is: (1) unconditional replay lookup; (2) method-specific eligibility and quota guards; (3) atomic mutations; (4) explicit branch fallback; (5) logging and return. The distinction between existing-record lookup and eligibility for a new mutation should be stated directly. This is a hypothesis supported on this task, not a universal prescription.

Limits include two related single-module tasks, one reported quantized model, unset seeds, sequential cohorts, mixed design generation in Flow r1–r3, changed timeout settings, an included successful scoped pilot, and an intervention developed after observing the failure. The scoped text adds explicit cancelled-replay semantics twice and in two languages, so its result cannot isolate scope labels from semantic emphasis or repetition. No activation analysis, broad task distribution, or independent model replication was performed.

The next experiment should complete **order × scope** with `Unordered + Scoped`, freeze a single base design, match semantic content and language across scoped variants, predefine all sample inclusion and outcomes, and counterbalance run order. Scope wording, repetition, and language should then be ablated separately. Higher-temperature sampling and multi-file tasks remain future work.

## 7. Reproducibility

The [GitHub repository](https://github.com/Eunryong/FlowSpec-Gemma4) preserves the original 22 study runs and 24 additional runs. The follow-up manifest lists all 30 observations and overlap explicitly. A CPU-only audit reruns REQ-1–REQ-8, checks recorded results and token totals, extracts lookup SQL, and records design/code hashes:

```bash
python3 scripts/audit_scope_followup.py
```

See `research/inputs/scope_followup_cohort.json`, the two original n=10 summary JSON files, `research/outputs/scope_followup_audit.json`, and `docs/scope_followup_results.md` for per-run provenance. Rechecking a preserved implementation is repeatable; generating the same implementation again is not guaranteed. No new model-generation runs were performed for this revision.

### References

1. Hong et al. [MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352).
2. Jimenez et al. [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770).
3. SciPy. [Exact binomial proportion confidence intervals](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html).
