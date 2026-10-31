# V2 Order and Scope Follow-Up: Per-Run Evidence

## Cohort and verification

The initial study contains 22 runs. This follow-up contains 30 observations and reuses six of those initial runs; 24 are additional, giving **46 unique study runs**. This count excludes other harness experiments in the repository.

The [cohort manifest](../research/inputs/scope_followup_cohort.json) fixes the initial and follow-up run IDs. The [audit](../research/outputs/scope_followup_audit.json) reruns REQ-1–REQ-8, checks original summary outcomes and token totals, extracts static idempotency SQL, and records design/engine hashes. No model calls are required:

```bash
python3 scripts/audit_scope_followup.py
```

Original summaries: [Flow/Unordered n=10](../research/outputs/flow_vs_unordered_full_10reps_summary.json), [Scoped n=10](../research/outputs/flow_scoped_10reps_summary.json), [earlier scoped pilot](../research/outputs/flow_scoped_trial_results.json). These are preserved without rewriting historical outcomes.

## Design provenance

- Flow r1–r3 are reused original sessions with three separately generated designs. New r4–r10 use the frozen [Flow r1 specification](../research/inputs/design_spec_cond4_flow.json).
- All Unordered observations use the same [shuffled specification](../research/inputs/design_spec_cond4_unordered.json); r1–r3 are reused.
- All Scoped observations use the same [scoped specification](../research/inputs/design_spec_cond4_flow_scoped.json). Its earlier pilot r1 is included; subsequent r2–r10 also pass 9/9.
- Scoped repeats a Korean/English clarification in step 1 and `scope_rule`, adding about 984 characters to the serialized input file. It is not a token-matched scope-label-only intervention.
- Seeds are unset. Flow r1 has a 300-second timeout; later follow-up settings have 900 seconds. Configurations and specification hashes are in the audit.

The static SQL inspection searches string literals in `create_booking`, including multiline strings; it is not a general data-flow analysis. In all 30 artifacts, status filtering coincides with REQ-8 failure. The remaining seven checks pass in all 30. This is behavioral/code evidence rather than an attention measurement.

## Per-run artifacts

`failed` is the recorded harness status. The seven failed sessions in this follow-up exhausted the 15-step budget; their saved artifacts are still included in external verification. Token totals include original Designer costs where applicable.

### cond4_flow

| Rep | Run artifact | Score | Status filter | Harness | Steps | Total tokens |
| ---: | :--- | :---: | :---: | :--- | ---: | ---: |
| 1 | [20261014T145844Z_track2_cond4_flow_r001_a90209d0](../research/runs/20261014T145844Z_track2_cond4_flow_r001_a90209d0) | 8/8 | no | completed | 10 | 85,332 |
| 2 | [20261015T033705Z_track2_cond4_flow_r001_c9f9986f](../research/runs/20261015T033705Z_track2_cond4_flow_r001_c9f9986f) | 7/8 | yes | completed | 8 | 80,098 |
| 3 | [20261015T075232Z_track2_cond4_flow_r001_e5655784](../research/runs/20261015T075232Z_track2_cond4_flow_r001_e5655784) | 8/8 | no | completed | 8 | 86,204 |
| 4 | [20261029T101223Z_track2_cond4_flow_r004_5fd493f7](../research/runs/20261029T101223Z_track2_cond4_flow_r004_5fd493f7) | 7/8 | yes | completed | 8 | 73,600 |
| 5 | [20261029T122750Z_track2_cond4_flow_r005_4a58377d](../research/runs/20261029T122750Z_track2_cond4_flow_r005_4a58377d) | 8/8 | no | completed | 8 | 73,092 |
| 6 | [20261029T134018Z_track2_cond4_flow_r006_4d393c1d](../research/runs/20261029T134018Z_track2_cond4_flow_r006_4d393c1d) | 8/8 | no | completed | 6 | 52,490 |
| 7 | [20261029T142541Z_track2_cond4_flow_r007_2f080d03](../research/runs/20261029T142541Z_track2_cond4_flow_r007_2f080d03) | 7/8 | yes | completed | 10 | 96,293 |
| 8 | [20261029T152711Z_track2_cond4_flow_r008_bd603a95](../research/runs/20261029T152711Z_track2_cond4_flow_r008_bd603a95) | 7/8 | yes | failed | 15 | 155,384 |
| 9 | [20261029T164621Z_track2_cond4_flow_r009_2b4bbbdd](../research/runs/20261029T164621Z_track2_cond4_flow_r009_2b4bbbdd) | 8/8 | no | completed | 6 | 53,366 |
| 10 | [20261029T172442Z_track2_cond4_flow_r010_8d5e4de9](../research/runs/20261029T172442Z_track2_cond4_flow_r010_8d5e4de9) | 7/8 | yes | failed | 15 | 164,152 |

### cond4_unordered

| Rep | Run artifact | Score | Status filter | Harness | Steps | Total tokens |
| ---: | :--- | :---: | :---: | :--- | ---: | ---: |
| 1 | [20261015T020114Z_track2_cond4_unordered_r001_f61b6f80](../research/runs/20261015T020114Z_track2_cond4_unordered_r001_f61b6f80) | 8/8 | no | completed | 6 | 54,705 |
| 2 | [20261015T040724Z_track2_cond4_unordered_r001_739903ea](../research/runs/20261015T040724Z_track2_cond4_unordered_r001_739903ea) | 7/8 | yes | completed | 8 | 73,917 |
| 3 | [20261015T092254Z_track2_cond4_unordered_r001_574b9eb5](../research/runs/20261015T092254Z_track2_cond4_unordered_r001_574b9eb5) | 7/8 | yes | completed | 14 | 136,352 |
| 4 | [20261029T105642Z_track2_cond4_unordered_r004_be184ca4](../research/runs/20261029T105642Z_track2_cond4_unordered_r004_be184ca4) | 7/8 | yes | completed | 6 | 53,388 |
| 5 | [20261029T131553Z_track2_cond4_unordered_r005_7f0d7f01](../research/runs/20261029T131553Z_track2_cond4_unordered_r005_7f0d7f01) | 8/8 | no | completed | 7 | 60,733 |
| 6 | [20261029T135951Z_track2_cond4_unordered_r006_0581c346](../research/runs/20261029T135951Z_track2_cond4_unordered_r006_0581c346) | 7/8 | yes | completed | 8 | 72,988 |
| 7 | [20261029T150113Z_track2_cond4_unordered_r007_56ddd9bd](../research/runs/20261029T150113Z_track2_cond4_unordered_r007_56ddd9bd) | 7/8 | yes | completed | 8 | 73,050 |
| 8 | [20261029T162409Z_track2_cond4_unordered_r008_5c4b8dd1](../research/runs/20261029T162409Z_track2_cond4_unordered_r008_5c4b8dd1) | 8/8 | no | completed | 7 | 60,897 |
| 9 | [20261029T170612Z_track2_cond4_unordered_r009_a3888de2](../research/runs/20261029T170612Z_track2_cond4_unordered_r009_a3888de2) | 8/8 | no | completed | 6 | 52,664 |
| 10 | [20261029T183411Z_track2_cond4_unordered_r010_2b3cc446](../research/runs/20261029T183411Z_track2_cond4_unordered_r010_2b3cc446) | 7/8 | yes | completed | 8 | 72,742 |

### cond4_flow_scoped

| Rep | Run artifact | Score | Status filter | Harness | Steps | Total tokens |
| ---: | :--- | :---: | :---: | :--- | ---: | ---: |
| 1 | [20261029T225731Z_track2_cond4_flow_scoped_r001_e11217cb](../research/runs/20261029T225731Z_track2_cond4_flow_scoped_r001_e11217cb) | 8/8 | no | completed | 8 | 75,228 |
| 2 | [20261030T003851Z_track2_cond4_flow_scoped_r002_fceb113d](../research/runs/20261030T003851Z_track2_cond4_flow_scoped_r002_fceb113d) | 8/8 | no | failed | 15 | 166,315 |
| 3 | [20261030T020805Z_track2_cond4_flow_scoped_r003_7d83e144](../research/runs/20261030T020805Z_track2_cond4_flow_scoped_r003_7d83e144) | 8/8 | no | failed | 15 | 162,360 |
| 4 | [20261030T033713Z_track2_cond4_flow_scoped_r004_b91374e5](../research/runs/20261030T033713Z_track2_cond4_flow_scoped_r004_b91374e5) | 8/8 | no | failed | 15 | 166,750 |
| 5 | [20261030T050721Z_track2_cond4_flow_scoped_r005_f3826222](../research/runs/20261030T050721Z_track2_cond4_flow_scoped_r005_f3826222) | 8/8 | no | completed | 9 | 90,927 |
| 6 | [20261030T054851Z_track2_cond4_flow_scoped_r006_2ff7e287](../research/runs/20261030T054851Z_track2_cond4_flow_scoped_r006_2ff7e287) | 8/8 | no | completed | 7 | 63,296 |
| 7 | [20261030T062622Z_track2_cond4_flow_scoped_r007_8a5f2167](../research/runs/20261030T062622Z_track2_cond4_flow_scoped_r007_8a5f2167) | 8/8 | no | completed | 6 | 54,088 |
| 8 | [20261030T070701Z_track2_cond4_flow_scoped_r008_4460c477](../research/runs/20261030T070701Z_track2_cond4_flow_scoped_r008_4460c477) | 8/8 | no | failed | 15 | 162,251 |
| 9 | [20261030T101226Z_track2_cond4_flow_scoped_r009_3aecc0f0](../research/runs/20261030T101226Z_track2_cond4_flow_scoped_r009_3aecc0f0) | 8/8 | no | completed | 9 | 86,500 |
| 10 | [20261030T112121Z_track2_cond4_flow_scoped_r010_1c552853](../research/runs/20261030T112121Z_track2_cond4_flow_scoped_r010_1c552853) | 8/8 | no | failed | 15 | 162,821 |

## What changed in the revised submission

The original tables remain historical results. The revised abstract, title, conclusion, and new Tables 4–5 replace the earlier claim that ordering proves reliability with a narrower observation about explicit scope guidance, increased cost, and incomplete agent sessions. The missing `Unordered + Scoped` cell, pilot inclusion, mixed initial Flow designs, semantic additions, and sampling limits are explicit.

A complete factorial follow-up and independent task/model replications are planned, not completed.

The comparison figure is generated from the audit with Matplotlib: `uv run --no-project --with matplotlib python scripts/render_followup_figure.py`. Both PNG and SVG are preserved.
