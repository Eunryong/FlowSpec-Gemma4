# Condition 2: Formal Contract Blueprint

In this condition, the Designer stage must define strict interface contracts, data schemas, and storage definitions before implementation.

## Designer Instructions
1. Define explicit data models / entity schemas with exact field names and types (e.g., dataclass, TypedDict, or typing annotations for every core domain entity).
2. Specify exact public method signatures for the core service/engine class(es) requested in the brief, including parameter names, types, return types, and domain exceptions.
3. Provide the exact SQLite database DDL (`CREATE TABLE` statements with primary keys, foreign keys, constraints, and indexes).
4. Do not include full implementation code, but make the interface and type contracts unambiguously clear for the Coder stage.
