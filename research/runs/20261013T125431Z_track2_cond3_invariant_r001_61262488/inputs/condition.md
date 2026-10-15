# Condition 3: Defensive Invariant Blueprint

In this condition, the Designer stage must explicitly analyze system invariants, concurrency boundaries, and state transitions in addition to contracts.

## Designer Instructions
1. Specify state machine transitions: clearly define legal transitions (e.g., `UNBOOKED -> BOOKED -> CANCELLED`, and whether a cancelled booking can be reopened).
2. Explicitly specify business invariants and integrity constraints:
   - Slot uniqueness per counselor and start time.
   - Atomicity of booking reservation (preventing race conditions or double booking).
   - In-memory SQLite lifecycle considerations (single connection persistence for test suites).
   - Idempotency and error boundaries for duplicate cancellation requests.
3. List critical edge cases and concrete assertion conditions for the test suite.
