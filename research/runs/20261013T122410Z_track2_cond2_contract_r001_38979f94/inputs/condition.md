# Condition 2: Formal Contract Blueprint

In this condition, the Designer stage must define strict interface contracts, data schemas, and storage definitions before implementation.

## Designer Instructions
1. Define explicit data models / entity schemas with exact field names and types (e.g., dataclass or typing annotations for Slot, Booking).
2. Specify exact method signatures for `CounselingService` including parameter names, types, return types, and potential domain exceptions.
3. Provide the exact SQLite database DDL (`CREATE TABLE` statements with primary keys, foreign keys, and indexes).
4. Do not include full implementation code, but make the interface and type contracts unambiguously clear for the Coder stage.
