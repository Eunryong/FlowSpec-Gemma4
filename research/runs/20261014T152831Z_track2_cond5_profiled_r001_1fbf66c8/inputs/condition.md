# Condition 5: Developer-Profiled Blueprint (Contracts + Invariants + Execution Flows + P1~P5 Profile)

In this condition, the Designer stage combines strict contracts, state/conservation invariants, step-by-step feature execution flows, and the developer's explicit reasoning profile (P1~P5) with anti-overengineering guardrails.

## Developer Reasoning Profile & Blueprint Directives
1. **P1 (Constraint Boundary Enforcement)**: Prioritize non-functional constraints (single persistent `self.conn = sqlite3.connect(db_path)` for `:memory:` compatibility, atomic `with self.conn:` transactions, and strict idempotency checks at the very start of mutating methods) before feature branching.
2. **P2 (Caller & Execution Flow Traceability)**: For every public method, map the exact step-by-step execution flow (`[Pre-check / Idempotency] -> [Guard Validation] -> [Atomic DB Mutation & Waitlist/Rollback Branching] -> [Audit Log & Return Dict]`), expected return shapes, and exception propagation chains.
3. **P3 (Informed Architecture Decisions)**: For key architectural choices (primary key design, FIFO waitlist promotion query, idempotency enforcement via `pass_ledger` and `bookings`), state the concrete design choice clearly.
4. **P4 (Cohesive Single-Module Separation of Concerns)**: Keep all domain logic cohesive inside the single requested module (`counseling_engine.py`) without splitting into unnecessary multi-file subpackages that waste implementation steps.
5. **P5 (Reproducible Failure Pre-emption & Pragmatism)**: Pre-emptively guard against common failure modes (such as checking target slot availability in `reschedule_booking` BEFORE releasing the original slot, or verifying waitlisted clients still have `remaining_sessions >= 1` before promoting them on `cancel_booking`).
