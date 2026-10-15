# Condition 3: Defensive Invariant Blueprint

In this condition, the Designer stage must explicitly analyze system invariants, concurrency boundaries, and state transitions in addition to contracts.

## Designer Instructions
1. Specify explicit state machine transitions: clearly define all legal states, valid state transitions, terminal states, and forbidden transitions that must raise exceptions.
2. Explicitly specify business invariants, compensating rollback rules, and integrity constraints:
   - Uniqueness, non-negativity, and conservation invariants across domain tables (e.g., stock reservation vs available stock, wallet balance, quota limits).
   - Atomicity of multi-step state mutations and compensating rollback actions when a downstream step fails.
   - In-memory SQLite lifecycle considerations (single persistent `sqlite3.Connection` instance per service so `:memory:` tables persist across method calls).
   - Idempotency guarantees and error boundaries for duplicate or invalid requests.
3. List critical edge cases and concrete assertion conditions for the test suite.
