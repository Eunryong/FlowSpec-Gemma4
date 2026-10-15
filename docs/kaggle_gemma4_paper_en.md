# Ordering Matters More Than Rules: Execution-Flow Specifications for Multi-Table Transactional Coding with Gemma 4 31B

**Subtitle:** Design Representations, Information-Controlled Ablations, and Multi-Run Stability in a Local Agent Harness

---

## 1. Abstract

Engineering teams often add an upfront design stage before asking local open-weights models to write code. We study how upfront design artifacts affect a locally hosted **Gemma 4 31B-IT** model (`temperature = 0.2`, `12,288`-token context) building SQLite transactional reservation engines under a 15-step tool budget. Using a controlled two-stage local harness isolating a single-turn Designer session from a Coder session with five workspace-jailed file and test tools, we analyze **22 end-to-end runs** across two 1:1 counseling benchmarks: a small-scale task (2 tables, 5 public methods, 6 checks) and a large-scale task (4 subsystems, 7 coupled tables, 13 public methods, 8 checks covering prepaid pass ledgers, atomic rescheduling, FIFO waitlist promotion, cross-table reconciliation, and idempotent replay of cancelled bookings). Evaluating six design representations, a pure no-design baseline, an information-controlled unordered ablation, and `n = 3` repetitions on core large-scale groups yields four findings:
1. **Unstructured prose design underperforms no design at both scales**, hitting the 15-step ceiling, adding 59%–219% more tokens, and causing branch-omission bugs (`6/8` on the large-scale task vs. `7/8` without design).
2. **Declarative state invariants are brittle across repetitions (`n = 3`)**, passing `7/8` in run 1 (`67,569` tokens) but dropping to `1/8` in runs 2 and 3 (`146,112` and `154,716` tokens) due to an SQLite double-counting bug during pass issuance (`3.00 ± 3.46 / 8`).
3. **Numbered execution-flow specifications (`Step 1` → `Step N`) maximize accuracy and stability**, achieving the lowest cost on the small-scale task (`33,219` tokens, `7` steps, `6/6`) and the highest score on the large-scale task (`7.67 ± 0.58 / 8`, passing `8/8` in `2/3` runs) with **`83,878 ± 3,302` total tokens (`CV = 3.9%`)** and **`16,560 ± 418` coder output tokens (`CV = 2.5%`)**—12.9×–14.9× lower total token standard deviation than other repeated groups.
4. **Information-content control proves that step ordering—not wording—prevents lifecycle bugs.** Giving the Coder the identical JSON text, schemas, and unconditional lookup rule (`"If idempotency_key exists in bookings, return existing booking."`) with step numbers stripped and bullets shuffled cuts the `8/8` pass rate from `2/3` (`66.7%`) to `1/3` (`33.3%`) and inflates total token standard deviation 12.9-fold (`± 42,688` vs. `± 3,302`).

---

## 2. Introduction

Open-weights 30B-class models such as Gemma 4 31B-IT execute multi-step coding workflows on a single workstation, often split into a *Designer* stage producing a specification and a *Coder* stage writing and testing code. Yet specifications range from free-form prose and static schemas to declarative invariants and numbered execution flows. Under bounded context windows (`12,288` tokens) and step budgets (`15` steps), local 31B models face a sharp trade-off: verbose specifications trigger mid-run history compaction and truncated tool calls, whereas underspecified state-transition ordering causes multi-table SQLite bugs.

We address two questions in a local harness without commercial framework retries:
1. **Representation:** How do six progressively structured design representations affect verification accuracy and token cost across small- and large-scale transactional coding benchmarks?
2. **Mechanism (Content vs. Order):** When a numbered execution-flow specification prevents a lifecycle bug that breaks declarative invariants, does the gain come from extra domain wording or from sequential `Step 1` → `Step N` ordering?

---

## 3. Methodology

### 3.1 Experimental Harness and Model Configuration

All 22 runs used **Gemma 4 31B-IT** (`Q4_K_M` GGUF) on `llama.cpp` (`llama-server`, `/v1/chat/completions`, single slot `-np 1`) at `temperature = 0.2`, `context_length = 12,288` tokens (near ceiling, history compaction retains the initial prompt and 6 latest messages while summarizing older turns), and a `15`-step budget.
- **Stage 1 (Designer):** Takes task requirements and condition instructions, generating `design_spec.json` and markdown in one turn without tools.
- **Stage 2 (Coder):** Receives only task requirements and the Stage 1 artifact in a clean workspace with five jailed tools: (1) file inspection (`list_files`, `read_file`), (2) file writing/editing (`write_file`, `replace_text`), and (3) testing (`run_tests`, returning `pytest` output).

### 3.2 Benchmark Architecture and Standard Verification Suites

Both benchmarks require building a Python 3.11+ SQLite engine (`counseling_engine.py`, supporting file paths and single-connection `:memory:` persistence) and unit tests (`test_counseling.py`) for a 1:1 counseling service ("Yeobaek Counseling").

#### Small-Scale Task (V1): 2 Tables, 5 Public Methods, 6 Requirements
`CounselingService` (`counseling_engine.py`) manages two tables (`slots`, `bookings`) via **5 public methods**: `add_available_slot`, `query_available_slots`, `create_booking`, `lookup_booking`, and `cancel_booking`. Six checks verify: `REQ-1` slot registration (`add_available_slot`) and filtered queries (`query_available_slots`); `REQ-2` booking creation (`create_booking`) and availability exclusion; `REQ-3` blocking duplicate slots and double-bookings; `REQ-4` `client_email` ownership check in `lookup_booking`; `REQ-5` cancellation (`cancel_booking` with `client_email` check) restoring slot availability for re-booking; and `REQ-6` single-connection `:memory:` persistence.

#### Large-Scale Task (V2): 4 Subsystems, 7 Coupled Tables, 13 Public Methods, 8 Requirements
`CounselingBookingEngine` (`counseling_engine.py`) coordinates **7 coupled tables** (`counselors`, `slots`, `session_passes`, `pass_ledger`, `bookings`, `waitlist`, `audit_logs`) across **4 subsystems** and **13 public methods**:
1. **Subsystem A — Counselor & Slot Lifecycle (`counselors`, `slots`):** `register_counselor`, `add_slot` (creates `AVAILABLE` slot), `block_slot` (`AVAILABLE` → `BLOCKED`, rejecting `BOOKED` slots), and `query_available_slots` (**`REQ-1`**).
2. **Subsystem B — Prepaid Session Pass & Idempotent Ledger (`session_passes`, `pass_ledger`):** `issue_session_pass` (credits `remaining_sessions`, logs `ISSUE` with `delta_sessions = +N` in `pass_ledger`, and returns existing balance on duplicate `idempotency_key` without double-crediting) and `get_session_pass` (**`REQ-2`**).
3. **Subsystem C — Booking & Atomic Rescheduling Saga (`bookings`):** `create_booking` (checks `idempotency_key`, verifies `AVAILABLE` slot and `remaining_sessions >= 1`, sets slot `BOOKED`, deducts `-1` session with `USE` ledger entry, inserts `CONFIRMED` booking, and logs `BOOKING_CREATED`, rolling back if sessions are insufficient [`REQ-3`]), `lookup_booking` (verifies `client_email`), and `reschedule_booking` (atomically swaps old slot to `AVAILABLE` and new slot to `BOOKED` without changing pass balances, logs `BOOKING_RESCHEDULED`, and preserves the original booking on failure [`REQ-4`]).
4. **Subsystem D — Waitlist Auto-Promotion, Audit & Reconciliation (`waitlist`, `audit_logs`):** `join_waitlist` (queues client with `remaining_sessions >= 1` as FIFO `WAITING` on a `BOOKED` slot), `cancel_booking` (marks booking `CANCELLED`, refunds `+1` session via `RESTORE` ledger and `BOOKING_CANCELLED` log, and branches on the FIFO waitlist: if no eligible `WAITING` client exists, resets slot to `AVAILABLE` [`REQ-5`]; if one exists, marks them `PROMOTED` while expiring zero-balance rows, deducts `-1` session via `USE` ledger, creates a new `CONFIRMED` booking with `WAITLIST_PROMOTED` log, and keeps the slot `BOOKED` [`REQ-6`]), `get_booking_audit_log`, and `get_system_reconciliation` (verifies `total_issued_sessions == total_remaining_sessions + total_used_sessions` and `total_used_sessions == active_confirmed_bookings == booked_slots_count` for `is_balanced: True` [`REQ-7`]).
- **`REQ-8` (Cancelled-Booking Idempotency Replay):** After a booking created with `idempotency_key = "k1"` is cancelled (`status = 'CANCELLED'`, slot reopened to `AVAILABLE`), calling `create_booking` again with `idempotency_key = "k1"` must return the existing cancelled record (same `booking_id`) without deducting another session or crashing on `UNIQUE(idempotency_key)`.

### 3.3 Experimental Conditions and Controlled Ablations

|Condition|Mode|Specification Provided to Stage 2 (Coder)|
|:---|:---:|:---|
|**Cond 0-Pure (`Direct`)**|1-Stage|**Pure No-Design Baseline.** Stage 1 skipped (`0` design tokens); Coder receives raw requirements.|
|**Cond 0-Min (`Unprimed`)**|2-Stage|**Minimal Wrapper Baseline.** Stage 1 runs with an unconstrained pass-through prompt.|
|**Cond 1 (`Free-Form Prose`)**|2-Stage|**Free-Form Prose.** Unconstrained markdown architecture and component narrative.|
|**Cond 2 (`Static Contracts`)**|2-Stage|**Structural Contracts.** Explicit SQLite schemas, method signatures, types, and exceptions.|
|**Cond 3 (`State Invariants`)**|2-Stage|**State Invariants.** Structural contracts plus declarative conservation equations and transitions.|
|**Cond 4-Flow (`Execution Flow`)**|2-Stage|**Execution-Flow Specification.** Contracts plus numbered pipelines (`Step 1` → `Step N`) per method.|
|**Cond 4-Unordered (`Shuffled`)**|Fixed-S2|**Information-Controlled Ablation.** Frozen `Cond 4-Flow` (`r1`) `design_spec.json` with `1..6` numbers stripped and bullets shuffled.|
|**Cond 5 (`Profiled Flow`)**|2-Stage|**Profiled Specification.** Full specification plus developer behavioral rules and checklists.|

*Note: V1 `Cond 0-Pure` ran under an initial 40-step ceiling and finished early in `9` steps; per-turn `max_output_tokens` was `3,584` for V1 `Cond 1`–`Cond 3` and `Cond 5`, and `4,608` for V1 `Cond 4-Flow` and all V2 runs.*

---

## 4. Results

Each run was evaluated by **Agent Pytest** and our **Standard Verification Suite** (`REQ-1`–`REQ-6` on V1; `REQ-1`–`REQ-8` on V2; `Total Tokens = Design In + Design Out + Impl In + Impl Out`).

### 4.1 Small-Scale vs. Large-Scale Single-Run Sweep (`r1`)

#### Table 1: Small-Scale Task (V1, 2 Tables, 5 Methods, 6 Requirements)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**Cond 0-Pure (`No Design`)**|`completed`|0|0|0.0s|9 (8)|44,221|5,648|49,869|8.7m|10/10|**6/6**|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|1,271|2,035|173.6s|15 (15)|67,215|8,973|79,494|17.8m|10/12|**6/6***|
|**Cond 2 (`Static Contracts`)**|`completed`|1,308|2,547|217.9s|11 (10)|50,205|16,036|70,096|27.9m|11/11|**6/6**|
|**Cond 3 (`State Invariants`)**|`step_limit`|1,328|2,663|230.0s|15 (15)|84,413|19,091|107,495|39.0m|0/11†|**6/6**|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|1,715|2,009|172.5s|**7 (6)**|**24,142**|**5,353**|**33,219**|**10.5m**|8/8|**6/6**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|1,409|2,501|241.2s|15 (15)|65,576|6,826|76,312|17.5m|0/12‡|0/6 (6/6‡)|

*\*V1 `Cond 1` initially opened a new `sqlite3.connect()` per call (breaking `:memory:` state), cached `self._conn` at Step 14 (`6/6`), and left an unimported `CounselingError` on duplicate cancellation (`10/12` agent tests).*  
*†V1 `Cond 3` passed `6/6`, but its tests imported `BookingVerificationError` while the engine raised `PermissionError`, exhausting 15 steps.*  
*‡V1 `Cond 5` placed DB setup in `DatabaseManager`, whose constructor called `self._initialize_db()` (line 7) above `self._init_db()` (line 8) while only defining `def _init_db(self):` (line 15), raising `AttributeError` (`6/6` once line 7 is removed).*

#### Table 2: Large-Scale Task Initial Sweep (V2, 7 Tables, 13 Methods, 8 Requirements, `r1`)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|Failed Reqs|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
|**Cond 0-Pure (`Direct`)**|`completed`|0|0|0.0s|6 (5)|30,999|12,383|43,382|19.3m|8/8|7/8|`REQ-8`|
|**Cond 0-Min (`Unprimed`)**|`completed`|3,967|2,537|261.9s|7 (5)|42,005|15,389|63,898|28.2m|8/8|7/8|`REQ-8`|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|4,014|2,542|212.9s|15 (14)|105,782|25,892|138,230|42.1m|6/8|6/8|`REQ-5, REQ-7`|
|**Cond 2 (`Static Contracts`)**|`completed`|4,091|2,068|190.1s|12 (11)|80,475|39,609|126,243|59.5m|8/8|7/8|`REQ-8`|
|**Cond 3 (`State Invariants`)**|`completed`|4,135|2,141|180.3s|7 (5)|41,439|19,854|67,569|31.3m|8/8|7/8|`REQ-8`|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|4,501|1,547|285.8s|10 (8)|63,150|16,134|85,332|28.3m|8/8|**8/8**|**None (100%)**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|4,329|1,353|116.2s|15 (15)|96,795|54,413|156,890|79.1m|—§|7/8|`REQ-8`|

*§V2 `Cond 5` suffered repeated output truncations and compactions (`54,413` coder output tokens), hitting Step 15 before creating `test_counseling.py`; its final `counseling_engine.py` passes `7/8`.*

### 4.2 Multi-Run Repetitions (`n = 3`) and Information-Controlled Ablation (`Cond 4-Unordered`)

We ran `n = 3` repetitions (`r1`–`r3`) for four V2 groups: **Cond 0-Pure**, **Cond 3 Invariant**, **Cond 4-Flow**, and **Cond 4-Unordered** (feeding Stage 2 the exact `Cond 4-Flow` `r1` `design_spec.json` with `1..6` step numbers stripped and bullets shuffled so `create_booking`'s idempotency check moves from `Step 1` to the 5th bullet after slot validation, pass validation, and transaction writes).

#### Table 3: Large-Scale Task Multi-Run Stability & Information-Controlled Ablation (`n = 3` per Group)

|Group (`n = 3` on Large-Scale V2)|Per-Run Verify (`r1, r2, r3`)|Mean Verify|8/8 (`REQ-8`) Pass Rate|Impl Steps|Impl Out Tokens|Total Tokens|Total Time|
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**`Cond 0-Pure` (Direct, 0 design tok)**|`7/8, 7/8, 7/8`|`7.00 ± 0.00`|`0/3 (0.0%)`|`10.00 ± 4.58`|`25,775 ± 19,505`|`83,419 ± 49,236`|`40.6 ± 30.7m`|
|**`Cond 3 Invariant` (2-stage)**|`7/8, 1/8, 1/8`|`3.00 ± 3.46`|`0/3 (0.0%)`|`12.33 ± 4.62`|`27,626 ± 7,784`|`122,799 ± 48,024`|`46.4 ± 15.4m`|
|**`Cond 4-Unordered` (Fixed Shuffled)**|`8/8, 7/8, 7/8`|`7.33 ± 0.58`|`1/3 (33.3%)`|`9.33 ± 4.16`|`22,653 ± 10,584`|`88,325 ± 42,688`|`34.4 ± 16.2m`|
|**`Cond 4-Flow` (`Step 1..N`)** ⭐|**`8/8, 7/8, 8/8`**|**`7.67 ± 0.58`**|**`2/3 (66.7%)`**|**`8.67 ± 1.15`**|**`16,560 ± 418`**|**`83,878 ± 3,302`**|**`30.9 ± 3.0m`**|

### 4.3 Code- and Trace-Level Root-Cause Analysis

Inspecting `counseling_engine.py` and step traces across all 22 runs reveals five mechanisms behind Tables 1–3.

#### Mechanism 1: Branch-Omission Bug under Free-Form Prose (`Cond 1`, Failing `REQ-5` and `REQ-7`)
In V2 `Cond 1`, `cancel_booking` (lines 133–146 of the 188-line `counseling_engine.py`) delegates waitlist promotion and slot recovery to a custom helper, `_process_waitlist(self, counselor_id, start_time)` (lines 148–168). Because prose design emphasized positive waitlist promotion without enumerating branch postconditions, the Coder's `while waitlist_entry:` loop kept the slot `'BOOKED'` on promotion **but omitted the fallback query to reset `slots.status = 'AVAILABLE'` when no waitlisted client was promoted**:
```python
# Large-Scale V2 Cond 1: counseling_engine.py (lines 148-168)
def _process_waitlist(self, counselor_id: str, start_time: str):
    waitlist_entry = self.conn.execute(
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
            waitlist_entry = ...
    # BUG: Missing fallback `UPDATE slots SET status='AVAILABLE'` when no waitlisted client is promoted
```
Cancelled slots with empty waitlists stayed `'BOOKED'`, failing `REQ-5` and `REQ-7`.

#### Mechanism 2: Mid-Generation Self-Correction Bug under Declarative Invariants (`Cond 3`, `r2` & `r3`)
In `Cond 3 Invariant`, Stage 1 supplies declarative conservation laws rather than procedural steps. While `r1` passed `7/8` (`67,569` tokens), `r2` and `r3` fell to `1/8` (`146,112` and `154,716` tokens, 15 steps). In both runs, the Coder wrote `INSERT OR REPLACE` inside `issue_session_pass` during `write_file`, realized mid-generation that `REPLACE` overwrites existing balances, and appended a corrective comment and an `UPDATE` query below it—since an autoregressive model cannot retract tokens already emitted in the same tool call:
```python
# Large-Scale V2 Cond 3 (r2 lines 68-73 of 197; r3 lines 63-69 of 177): Double-Counting Bug
self.conn.execute("INSERT OR REPLACE INTO session_passes (client_email, remaining_sessions, used_sessions) VALUES (?, ?, ?)", 
                 (client_email, sessions_to_add, 0))
# Note: INSERT OR REPLACE is simplified; should be UPDATE if exists.
# Correcting to:
self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions + ? WHERE client_email = ?", (sessions_to_add, client_email))
```
Issuing 3 sessions inserts `remaining_sessions = 3` and immediately adds `+3` (`remaining_sessions = 6`), failing `REQ-2`–`REQ-8`. (The same inability to retract emitted lines caused V1 `Cond 5`'s crash in `DatabaseManager.__init__`, calling `self._initialize_db()` on line 7 and `self._init_db()` on line 8 while defining only `def _init_db(self):` on line 15.) Conversely, `Cond 4-Flow` pre-plans `issue_session_pass` as `Step 1 (check pass_ledger) -> Step 2 (validate) -> Step 3 (atomic upsert)`, passing `REQ-1`–`REQ-7` in 100% of runs.

#### Mechanism 3: Premature Predicate Conjoining on Cancelled Idempotency Replay (`REQ-8`)
Across all 9 V2 runs failing `REQ-8` without an execution-flow specification—`Cond 0-Pure` (`r1` line 80, `r2` line 84, `r3` line 84), `Cond 0-Min` (line 80), `Cond 2` (line 99), `Cond 3` (`r1` line 98, `r2` line 86, `r3` line 79), and `Cond 5` (line 87)—the Coder emitted the identical flawed query in `create_booking`:
```python
# Identical bug in Cond 0-Pure (r1 L80, r2 L84, r3 L84), Cond 0-Min (L80), Cond 2 (L99), Cond 3 (r1 L98, r2 L86, r3 L79), Cond 5 (L87)
existing = self.conn.execute(
    "SELECT * FROM bookings WHERE idempotency_key = ? AND status = 'CONFIRMED'",
    (idempotency_key,),
).fetchone()
```
Conjoining `AND status = 'CONFIRMED'` misses `'CANCELLED'` rows on replay, crashing on `UNIQUE(idempotency_key)` or double-deducting a pass.

#### Mechanism 4: Proof via Information-Controlled Ablation (`Cond 4-Flow` vs. `Cond 4-Unordered`)
In `Cond 4-Flow`, `r1` (line 82) and `r3` (line 82) passed `8/8` (`REQ-8` passed) because Stage 1 placed the idempotency check at `Step 1` of `create_booking`, leading Stage 2 to query `WHERE idempotency_key = ?` without a status filter (in `r2` line 75, Stage 2 appended `AND status = 'CONFIRMED'`, scoring `7/8`).

To test whether `Cond 4-Flow` `r1` passed `REQ-8` due to the wording of its idempotency rule rather than its `Step 1` position, `Cond 4-Unordered` (`n = 3`) kept the `r1` JSON text 100% identical—preserving the exact string `"If idempotency_key exists in bookings, return existing booking."`—while stripping `1..6` step numbers and moving that bullet from `Step 1` to the 5th (final) bullet of `create_booking` (after `"Verify slot exists and status == 'AVAILABLE'."`, `"Verify client remaining_sessions >= 1."`, and `"Transaction: ... Insert booking (status='CONFIRMED')..."`).
- In **2 of 3 `Cond 4-Unordered` runs (`r2` line 77 and `r3` line 95)**, despite receiving the identical unconditional rule `"If idempotency_key exists in bookings, return existing booking."`, the Coder conjoined `WHERE idempotency_key = ? AND status = 'CONFIRMED'`, failing `REQ-8` (`1/3` pass rate vs. `2/3` in `Cond 4-Flow`).
- Stripping step numbers also destabilized execution: `Cond 4-Unordered` `r3` took `14` steps and `136,352` tokens (`34,778` coder output tokens), inflating group total token standard deviation 12.9-fold (`± 42,688` vs. `± 3,302` in `Cond 4-Flow`). Because an autoregressive Coder writes `def create_booking(...)` top-to-bottom, anchoring the guard at `Step 1` aligns the rule with the token position where the entry guard is generated.

#### Mechanism 5: Output Truncation and Compaction Loops under Over-Profiled Prompts (`Cond 5`)
In V2 `Cond 5`, behavioral rules and checklists pushed Stage 2 into a truncation-and-compaction loop (`15` steps, `54,413` coder output tokens, `156,890` total tokens). In 7 of 15 steps, `write_file` hit token limits—`max_output_tokens = 4,608` in Steps 2, 5, 6, 7, 10, and 12, and the `12,288` context ceiling in Step 15 (`9,610` in + `2,678` out)—returning `Invalid tool JSON: Unterminated string`. These failed payloads triggered history compaction three times (after Steps 5, 10, and 12), causing the Coder to overwrite `counseling_engine.py` five times (Steps 3, 4, 9, 11, and 13: `6,194` → `14,639` → `15,471` → `16,616` → `15,189` chars) without calling `run_tests`.

---

## 5. Discussion and Conclusion

### 5.1 Engineering Guidelines for Local Gemma 4 Coding Agents
1. **Drop unstructured prose design (`Cond 1`),** which adds 59%–219% more tokens than `Cond 0-Pure` and causes branch-omission bugs (`_process_waitlist`).
2. **Replace declarative invariants (`Cond 3`) with numbered execution flows (`Cond 4-Flow`),** avoiding mid-generation SQL self-correction bugs (`3.00 ± 3.46 / 8` → `7.67 ± 0.58 / 8`) and cutting coder output token variance to `CV = 2.5%` (`16,560 ± 418` tokens).
3. **Anchor entry guards at `Step 1`,** as `Cond 4-Unordered` shows that identical unconditional lookup rules (`"If idempotency_key exists in bookings, return existing booking."`) fail in `2/3` runs when displaced from their chronological execution position.
4. **Keep design outputs compact (`~1,500`–`2,500` tokens) under `12k` context windows** to avoid `4,608`-token output truncations and compaction loops (`Cond 5`, `156,890` tokens).

### 5.2 Limitations and Reproducibility
Our study covers single-file SQLite engines (`n = 3` per core group, 15-step budget) on local quantized hardware. All 22 run directories, `design_spec.json` files, `counseling_engine.py` implementations, JSONL traces, and verification scripts are preserved for deterministic reproduction.

### References
1. Gemma Team, Google DeepMind. *Gemma 4 Technical Report.* arXiv:2607.02770 (2026); and *Gemma: Open Models Based on Gemini Research and Technology.* arXiv:2403.08295 (2024).
2. Markowitz, E., Perozzi, B., Rózemberczki, B., Cameron, G., Hemmati, H., Li, Y., Galkin, M., Farhadi, M., Holbrook, R., & Oldacre, A. *Google - The Gemma 4 Developer Agent Paper Track.* Kaggle (2026).
3. Hong, S., et al. *MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework.* ICLR (2024).
4. Pei, K., et al. *Can Large Language Models Reason about Program Invariants?* ICML (2023).
5. Olausson, T. X., et al. *Is Self-Repair a Silver Bullet for Code Generation?* ICLR (2024).
6. Jimenez, C. E., et al. *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR (2024).
