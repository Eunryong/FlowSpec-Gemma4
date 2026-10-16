# Ordering Matters More Than Rules: Execution-Flow Specifications for Multi-Table Transactional Coding with Gemma 4 31B

**Subtitle:** Design Representations, Information-Controlled Ablations, and Multi-Run Stability in a Local Agent Harness

---

## 1. Abstract

Engineering teams often add an upfront design stage before asking local open-weights models to write software. We study how the structure of upfront design artifacts affects a locally hosted **Gemma 4 31B-IT** model (`temperature=0.2`, `12,288`-token context) implementing multi-table SQLite transactional reservation engines under a 15-step tool budget. Using a controlled two-stage local harness isolating a single-turn Designer session from a Coder session equipped with five workspace-jailed file and test tools, we analyze **22 end-to-end runs** across two 1:1 counseling benchmarks: a small-scale task (2 relational tables, 5 public operations, 6 checks) and a large-scale task (4 subsystems, 7 coupled tables, 13 public operations, and 8 checks covering prepaid pass ledgers, atomic rescheduling, FIFO waitlist promotion, cross-table reconciliation, and idempotent replay of cancelled bookings). Evaluating six design representations, a pure no-design baseline, an information-controlled unordered ablation, and `n=3` repetitions on core large-scale groups yields four findings:
1. **Unstructured prose design underperforms no design at both scales**, hitting the 15-step ceiling, adding 59%–219% more tokens, and causing branch-omission bugs (`6/8` on the large-scale task vs. `7/8` without design).
2. **Declarative state invariants are brittle across repetitions (`n=3`)**, passing `7/8` in run 1 (`67,569` tokens) but dropping to `1/8` in runs 2 and 3 (`146,112` and `154,716` tokens) due to a mid-generation SQL self-correction bug that double-counts issued passes (`3.00±3.46 / 8`).
3. **Numbered execution-flow specifications (`Step 1→Step N`) maximize accuracy and stability**, achieving the lowest cost on the small-scale task (`33,219` tokens, `7` steps, `6/6`) and the highest score on the large-scale task (`7.67±0.58 / 8`, passing `8/8` in `2/3` runs) with **`83,878±3,302` total tokens (`CV=3.9%`)** and **`16,560±418` coder output tokens (`CV=2.5%`)**—12.9×–14.9× lower total token standard deviation than other repeated groups.
4. **Information-content control proves that step ordering—not wording—prevents lifecycle bugs.** Giving the Coder the identical JSON text, schemas, and unconditional lookup rule (`"If idempotency_key exists in bookings, return existing booking."`) with step numbers stripped and bullets shuffled cuts the `8/8` pass rate from `2/3` (`66.7%`) to `1/3` (`33.3%`) and inflates total token standard deviation 12.9-fold (`± 42,688` vs. `± 3,302`).

---

## 2. Introduction

Open-weights 30B-class models such as Gemma 4 31B-IT execute multi-step coding workflows on a single workstation, often split into a *Designer* stage producing a specification and a *Coder* stage writing and testing code. Yet specifications range from free-form prose and static schemas to declarative invariants and numbered execution flows. Under bounded context windows (`12,288` tokens) and step budgets (`15` steps), local 31B models face a sharp trade-off: verbose guidelines trigger mid-run history compaction and truncated tool calls, whereas underspecified state-transition ordering causes multi-table SQLite bugs.

We address two questions in a local harness without commercial framework retries:
1. **Representation:** How do six progressively structured design representations affect verification accuracy and token cost across small- and large-scale transactional coding benchmarks?
2. **Mechanism (Content vs. Order):** When a numbered execution-flow specification prevents a lifecycle bug that breaks declarative invariants, does the gain come from extra domain wording or from sequential `Step 1→Step N` ordering?

---

## 3. Methodology

### 3.1 Experimental Harness and Model Configuration

All 22 runs used **Gemma 4 31B-IT** (`Q4_K_M` GGUF) on `llama.cpp` (single server slot) at `temperature=0.2` (standard low-temperature coding setting to prevent tool-call JSON syntax noise), `context_length=12,288` tokens (near ceiling, history compaction retains the initial prompt and 6 latest messages while summarizing older turns), and a `15`-step budget.
- **Stage 1 (Designer):** Takes task requirements and condition instructions, generating a structured JSON specification and markdown overview in one turn without tools.
- **Stage 2 (Coder):** Receives only task requirements and the Stage 1 artifact in a clean workspace with five jailed tools across three roles: (1) workspace inspection (listing directories and reading files), (2) code editing (writing full files and replacing text blocks), and (3) automated testing (running `pytest` and returning output traces).

### 3.2 Benchmark Architecture and Standard Verification Suites

Both benchmarks require building a standalone Python 3.11+ SQLite transactional backend (supporting file paths and single-connection `:memory:` persistence) and unit tests for a 1:1 counseling service ("Yeobaek Counseling").

#### Small-Scale Task (V1): 2 Tables, 5 Public Operations, 6 Requirements
The small-scale benchmark models a reservation service over **2 relational tables** (counselor slots and bookings) and **5 public operations**: registering available slots, querying open slots by counselor and date filters, creating a booking, looking up a booking with client email authentication, and cancelling a booking. Six checks verify: `REQ-1` slot registration and filtered queries; `REQ-2` booking creation and availability exclusion; `REQ-3` blocking duplicate slots and double-bookings; `REQ-4` client email ownership verification on lookup; `REQ-5` authenticated cancellation restoring slot availability for re-booking; and `REQ-6` single-connection `:memory:` persistence.

#### Large-Scale Task (V2): 4 Subsystems, 7 Coupled Tables, 13 Public Operations, 8 Requirements
The large-scale benchmark coordinates **7 coupled SQLite tables** (counselors, time slots, session passes, a pass transaction ledger, bookings, a priority waitlist, and chronological audit logs) across **4 domain subsystems** and **13 public operations**:
1. **Subsystem A — Counselor & Slot Lifecycle:** Registering counselor profiles, adding `AVAILABLE` slots, blocking unbooked slots (`AVAILABLE→BLOCKED`, rejecting `BOOKED` slots), and querying available slots (**`REQ-1`**).
2. **Subsystem B — Prepaid Session Pass & Idempotent Ledger:** Issuing or topping up multi-session passes backed by an append-only ledger (`ISSUE`, `USE`, `RESTORE` entries with signed deltas) that prevents duplicate credits on repeated idempotency keys, plus querying remaining and used balances (**`REQ-2`**).
3. **Subsystem C — Booking & Atomic Rescheduling Saga:** Creating bookings (checking idempotency keys, verifying `AVAILABLE` slot and `remaining_sessions >= 1`, atomically setting slot `BOOKED`, deducting `-1` session with a `USE` ledger entry, inserting a `CONFIRMED` booking, and logging creation, with rollback on insufficient quota [`REQ-3`]), authenticated lookup, and atomic rescheduling (swapping old slot to `AVAILABLE` and new slot to `BOOKED` without changing pass balances, logging the reschedule event, and preserving the original booking on failure [`REQ-4`]).
4. **Subsystem D — Waitlist Auto-Promotion, Audit & Reconciliation:** Enqueuing clients with `remaining_sessions >= 1` as FIFO `WAITING` on `BOOKED` slots, cancelling bookings (marking `CANCELLED`, refunding `+1` session via `RESTORE` ledger, and branching on the FIFO waitlist: if no eligible waiting client exists, resetting the slot to `AVAILABLE` [`REQ-5`]; if one exists, expiring zero-balance rows, promoting the first eligible client to a `CONFIRMED` booking, deducting `-1` session via `USE` ledger, and keeping the slot `BOOKED` [`REQ-6`]), querying audit logs, and computing global reconciliation verifying `total_issued_sessions == total_remaining_sessions + total_used_sessions` and `total_used_sessions == active_confirmed_bookings == booked_slots_count` (**`REQ-7`**).
- **`REQ-8` (Cancelled-Booking Idempotency Replay):** After a booking created with a client-supplied `idempotency_key` is cancelled (`status='CANCELLED'`, slot reopened to `AVAILABLE`), calling booking creation again with that same `idempotency_key` must return the existing cancelled record without deducting another session or crashing on a `UNIQUE` constraint.

### 3.3 Experimental Conditions and Controlled Ablations

|Condition|Mode|Specification Provided to Stage 2 (Coder)|
|:---|:---:|:---|
|**Cond 0-Pure (`Direct`)**|1-Stage|**Pure No-Design Baseline.** Stage 1 skipped (`0` design tokens); Coder receives raw requirements.|
|**Cond 0-Min (`Unprimed`)**|2-Stage|**Minimal Wrapper Baseline.** Stage 1 runs with an unconstrained pass-through prompt.|
|**Cond 1 (`Free-Form Prose`)**|2-Stage|**Free-Form Prose.** Unconstrained markdown architecture and component narrative.|
|**Cond 2 (`Static Contracts`)**|2-Stage|**Structural Contracts.** Explicit SQLite schemas, operation signatures, types, and exceptions.|
|**Cond 3 (`State Invariants`)**|2-Stage|**State Invariants.** Structural contracts plus declarative conservation equations and transitions.|
|**Cond 4-Flow (`Execution Flow`)**|2-Stage|**Execution-Flow Specification.** Contracts plus numbered pipelines (`Step 1→Step N`) per operation.|
|**Cond 4-Unordered (`Shuffled`)**|Fixed-S2|**Information-Controlled Ablation.** Frozen `Cond 4-Flow` (`r1`) JSON specification with `1..6` numbers stripped and bullets shuffled.|
|**Cond 5 (`Profiled Flow`)**|2-Stage|**Profiled Specification.** Full specification plus developer behavioral rules and checklists.|

*Note: V1 `Cond 0-Pure` ran under an initial 40-step ceiling and finished early in `9` steps; per-turn `max_output_tokens` was `3,584` for V1 `Cond 1`–`Cond 3` and `Cond 5`, and `4,608` for V1 `Cond 4-Flow` and all V2 runs.*

---

## 4. Results

Each run was evaluated by **Agent Pytest** and our **Standard Verification Suite** (`REQ-1`–`REQ-6` on V1; `REQ-1`–`REQ-8` on V2; `Total Tokens=Design In + Design Out + Impl In + Impl Out`).

### 4.1 Small-Scale vs. Large-Scale Single-Run Sweep (`r1`)

#### Table 1: Small-Scale Task (V1, 2 Tables, 5 Operations, 6 Requirements)

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

### 4.2 Multi-Run Repetitions (`n=3`) and Information-Controlled Ablation (`Cond 4-Unordered`)

We ran `n=3` repetitions (`r1`–`r3`) for four V2 groups: **Cond 0-Pure**, **Cond 3 Invariant**, **Cond 4-Flow**, and **Cond 4-Unordered** (feeding Stage 2 the exact `Cond 4-Flow` `r1` JSON specification with `1..6` step numbers stripped and bullets shuffled so booking creation's idempotency lookup moves from `Step 1` to the 5th bullet after slot validation, pass validation, and transaction writes).

#### Table 3: Large-Scale Task Multi-Run Stability & Information-Controlled Ablation (`n=3` per Group)

|Group (`n=3` on Large-Scale V2)|Per-Run Verify (`r1, r2, r3`)|Mean Verify|8/8 (`REQ-8`) Pass Rate|Impl Steps|Impl Out Tokens|Total Tokens|Total Time|
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**`Cond 0-Pure` (Direct, 0 design tok)**|`7/8, 7/8, 7/8`|`7.00±0.00`|`0/3 (0.0%)`|`10.00±4.58`|`25,775±19,505`|`83,419±49,236`|`40.6±30.7m`|
|**`Cond 3 Invariant` (2-stage)**|`7/8, 1/8, 1/8`|`3.00±3.46`|`0/3 (0.0%)`|`12.33±4.62`|`27,626±7,784`|`122,799±48,024`|`46.4±15.4m`|
|**`Cond 4-Unordered` (Fixed Shuffled)**|`8/8, 7/8, 7/8`|`7.33±0.58`|`1/3 (33.3%)`|`9.33±4.16`|`22,653±10,584`|`88,325±42,688`|`34.4±16.2m`|
|**`Cond 4-Flow` (`Step 1..N`)** ⭐|**`8/8, 7/8, 8/8`**|**`7.67±0.58`**|**`2/3 (66.7%)`**|**`8.67±1.15`**|**`16,560±418`**|**`83,878±3,302`**|**`30.9±3.0m`**|

### 4.3 Code- and Trace-Level Root-Cause Analysis

Inspecting generated SQL queries and step traces across all 22 runs reveals five mechanisms behind Tables 1–3.

#### Mechanism 1: Branch-Omission Bug under Free-Form Prose (`Cond 1`, Failing `REQ-5` and `REQ-7`)
In V2 `Cond 1`, prose design emphasized positive waitlist promotion on cancellation without enumerating branch postconditions. In the waitlist-processing routine invoked during cancellation, the Coder's `while waitlist_entry:` loop kept the slot `'BOOKED'` on promotion **but omitted the fallback query to reset `slots.status='AVAILABLE'` when no waitlisted client was promoted**:
```python
# Observed in Large-Scale V2 Cond 1 (waitlist processing during cancellation)
waitlist_entry=self.conn.execute(
    "SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY created_at ASC LIMIT 1",
    (counselor_id, start_time)
).fetchone()
while waitlist_entry:
    ...
    if remaining >= 1:
        ...
        self.conn.execute("UPDATE slots SET status='BOOKED' WHERE counselor_id=? AND start_time=?", (counselor_id, start_time))
        break
    else:
        self.conn.execute("UPDATE waitlist SET status='EXPIRED' WHERE waitlist_id=?", (waitlist_entry["waitlist_id"],))
        waitlist_entry=...
# BUG: Missing fallback `UPDATE slots SET status='AVAILABLE'` when no waitlisted client is promoted
```
Cancelled slots with empty waitlists stayed `'BOOKED'`, failing `REQ-5` and `REQ-7`.

#### Mechanism 2: Mid-Generation Self-Correction Bug under Declarative Invariants (`Cond 3`, `r2` & `r3`)
In `Cond 3 Invariant`, Stage 1 supplies declarative conservation laws rather than procedural steps. While `r1` passed `7/8` (`67,569` tokens), `r2` and `r3` fell to `1/8` (`146,112` and `154,716` tokens, 15 steps). In both runs, the Coder wrote `INSERT OR REPLACE` inside pass issuance during a full-file write, realized mid-generation that `REPLACE` overwrites existing balances on top-ups, and appended a corrective comment and an `UPDATE` query below it—since an autoregressive model cannot retract SQL statements already emitted in the same tool call:
```python
# Observed in Large-Scale V2 Cond 3 (r2 and r3 session-pass issuance)
self.conn.execute("INSERT OR REPLACE INTO session_passes (client_email, remaining_sessions, used_sessions) VALUES (?, ?, ?)", 
                 (client_email, sessions_to_add, 0))
# Note: INSERT OR REPLACE is simplified; should be UPDATE if exists.
# Correcting to:
self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions + ? WHERE client_email=?", (sessions_to_add, client_email))
```
Issuing 3 sessions inserts `remaining_sessions=3` and immediately adds `+3` (`remaining_sessions=6`), failing `REQ-2`–`REQ-8`. (The same inability to retract emitted lines caused V1 `Cond 5`'s crash, where the constructor emitted two differently named initialization calls back-to-back while defining only the second method.) Conversely, `Cond 4-Flow` pre-plans pass issuance as `Step 1 (check ledger idempotency)→Step 2 (validate)→Step 3 (atomic upsert)`, passing `REQ-1`–`REQ-7` in 100% of runs.

#### Mechanism 3: Premature Predicate Conjoining on Cancelled Idempotency Replay (`REQ-8`)
Across all 9 V2 runs failing `REQ-8` without an execution-flow specification—all 3 `Cond 0-Pure` runs, `Cond 0-Min`, `Cond 2`, all 3 `Cond 3` runs, and `Cond 5`—the Coder emitted the identical flawed query at the entry of booking creation:
```python
# Identical bug observed across all 9 failing non-flow runs on Large-Scale V2
existing=self.conn.execute(
    "SELECT * FROM bookings WHERE idempotency_key=? AND status='CONFIRMED'",
    (idempotency_key,),
).fetchone()
```
Conjoining `AND status='CONFIRMED'` misses `'CANCELLED'` rows on replay, either double-deducting a pass (`Cond 0-Pure`, `Cond 0-Min`, `Cond 3`, `Cond 5`) or crashing on `UNIQUE(idempotency_key)` (`Cond 2`).

#### Mechanism 4: Proof via Information-Controlled Ablation (`Cond 4-Flow` vs. `Cond 4-Unordered`)
In `Cond 4-Flow`, `r1` and `r3` passed `8/8` (`REQ-8` passed) because Stage 1 placed the unconditional idempotency check at `Step 1` of booking creation (`"1. If idempotency_key exists in bookings, return existing booking."`) ahead of `Step 2` (`"2. Verify slot exists and status == 'AVAILABLE'."`), leading Stage 2 to query `WHERE idempotency_key=?` without a status filter:
```python
# Observed in Large-Scale V2 Cond 4-Flow (r1 and r3 booking creation entry guard)
if idempotency_key:
    existing=self.conn.execute("SELECT * FROM bookings WHERE idempotency_key=?", (idempotency_key,)).fetchone()
    if existing: return dict(existing)
```
To test whether `Cond 4-Flow` `r1` passed `REQ-8` due to the wording of its rule rather than its `Step 1` position, `Cond 4-Unordered` (`n=3`) kept the `r1` JSON text 100% identical—preserving `"If idempotency_key exists in bookings, return existing booking."`—while stripping `1..6` step numbers and moving that bullet from `Step 1` to the 5th (final) bullet after slot validation, pass validation, and transaction writes:
- In **2 of 3 `Cond 4-Unordered` runs (`r2` and `r3`)**, despite receiving the identical unconditional rule `"If idempotency_key exists in bookings, return existing booking."`, the Coder conjoined `WHERE idempotency_key=? AND status='CONFIRMED'`, failing `REQ-8` (`1/3` pass rate vs. `2/3` in `Cond 4-Flow`).
- Stripping step numbers also destabilized execution: `Cond 4-Unordered` `r3` took `14` steps and `136,352` tokens (`34,778` coder output tokens), inflating group total token standard deviation 12.9-fold (`± 42,688` vs. `± 3,302` in `Cond 4-Flow`). Because an autoregressive Coder writes a method body top-to-bottom, anchoring the guard at `Step 1` aligns the rule with the token position where the entry guard is generated.

#### Mechanism 5: Output Truncation and Compaction Loops under Over-Profiled Prompts (`Cond 5`)
In V2 `Cond 5`, behavioral rules and checklists stimulated Gemma 4's thinking mode prior to tool calls, pushing Stage 2 into a truncation-and-compaction loop (`15` steps, `54,413` coder output tokens, `156,890` total tokens). In 7 of 15 steps, full-file write calls hit token limits—`max_output_tokens=4,608` in Steps 2, 5, 6, 7, 10, and 12, and the `12,288` context ceiling in Step 15 (`9,610` in + `2,678` out)—failing with unterminated JSON string errors. These failed payloads triggered history compaction three times (after Steps 5, 10, and 12), erasing prior file-write turns and causing the Coder to overwrite the backend file five times (Steps 3, 4, 9, 11, and 13) without running tests.

---

## 5. Discussion and Conclusion

### 5.1 Engineering Guidelines for Local Gemma 4 Coding Agents
1. **Drop unstructured prose design (`Cond 1`),** which adds 59%–219% more tokens than `Cond 0-Pure` and causes branch-omission bugs.
2. **Replace declarative invariants (`Cond 3`) with numbered execution flows (`Cond 4-Flow`),** avoiding mid-generation SQL self-correction bugs (`3.00±3.46 / 8→7.67±0.58 / 8`) and cutting coder output token variance to `CV=2.5%` (`16,560±418` tokens).
3. **Structure stateful operations as a 5-step template anchored by `Step 1` entry guards:** `[Step 1: Unconditional Entry/Idempotency Lookup]→[Step 2: Cross-Table State & Quota Guards]→[Step 3: Atomic Multi-Table Mutation]→[Step 4: Explicit If/Else Branching & Fallback]→[Step 5: Audit Logging & Return]`. As `Cond 4-Unordered` shows, identical unconditional lookup rules fail in `2/3` runs when displaced from `Step 1`.
4. **Keep design outputs compact (`~1,500`–`2,500` tokens) without meta-behavioral checklists under `12k` context windows** to avoid `4,608`-token output truncations and compaction loops (`Cond 5`, `156,890` tokens).

### 5.2 Limitations and Reproducibility
Our study covers single-module SQLite backends (`n=3` per core group, 15-step budget) on local quantized hardware at `temperature=0.2`; evaluating higher temperatures (`0.6`–`0.8`) under `pass@k` sampling and multi-file repositories remains future work. All 22 run artifacts, prompts, JSON specifications, generated engines, JSONL traces, and verification suites are publicly preserved for deterministic reproduction.

### References
1. Gemma Team, Google DeepMind. *Gemma 4 Technical Report.* arXiv:2607.02770 (2026); and *Gemma: Open Models Based on Gemini Research and Technology.* arXiv:2403.08295 (2024).
2. Markowitz, E., Perozzi, B., Rózemberczki, B., Cameron, G., Hemmati, H., Li, Y., Galkin, M., Farhadi, M., Holbrook, R., & Oldacre, A. *Google - The Gemma 4 Developer Agent Paper Track.* Kaggle (2026).
3. Hong, S., et al. *MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework.* ICLR (2024).
4. Pei, K., et al. *Can Large Language Models Reason about Program Invariants?* ICML (2023).
5. Olausson, T. X., et al. *Is Self-Repair a Silver Bullet for Code Generation?* ICLR (2024).
6. Jimenez, C. E., et al. *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR (2024).
