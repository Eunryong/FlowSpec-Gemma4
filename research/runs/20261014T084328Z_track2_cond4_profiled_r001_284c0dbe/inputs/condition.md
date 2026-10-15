# Condition 4: Developer-Profiled Blueprint (P1~P5 Integrated)

In this condition, the Designer stage operates under the developer's explicit reasoning profile (P1~P5) combined with anti-overengineering guardrails.

## Developer Reasoning Profile Directives
- **P1 (Constraint Boundary Enforcement)**: Prioritize non-functional constraints (e.g. database connection lifecycle, test isolation, zero leaking state) before feature branching.
- **P2 (Caller & Flow Traceability)**: Explicitly map who calls which method, expected return shapes, and exception propagation chains.
- **P3 (Informed Architecture Decisions)**: For every architectural choice (e.g. primary key design, transaction management), record the concrete rationale and rejected alternatives.
- **P4 (Separation of Concerns)**: Keep domain rules, database access, and interface layer strictly separated without unnecessary micro-framework abstraction.
- **P5 (Reproducible Failure Pre-emption & Pragmatism)**: Pre-emptively identify failure modes seen in real-world environments (such as in-memory SQLite table drops or timezone parsing differences), while strictly prohibiting speculative over-engineering.
