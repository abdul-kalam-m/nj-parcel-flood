# NJ Parcel Flood Risk Dashboard — Validation Report

Auto-written by `pipeline/09_validate.py` (§12.1 QA gates, guide-Phase 8). Every gate re-derived fresh from processed/published data, not trusted from an earlier phase's own report.

## ✅ PASS — Gate 1_uniqueness

- **n_total**: 3478722
- **n_dupe_pin_statewide**: 742
- **n_dupe_composite_key_statewide**: 745
- **n_unresolved_full_row_identical**: 1285
- **n_unresolved_but_fixable**: 0

## ❌ FAIL — Gate 2_completeness

- **join_rate**: 0.8834
- **join_rate_gate_ok**: False
- **unmapped_class_pct**: 0.0
- **unmapped_gate_ok**: True

## ✅ PASS — Gate 3_geometry

- **n_total**: 3478722
- **n_invalid**: 0
- **n_empty**: 0
- **n_zero_area**: 0

## ✅ PASS — Gate 4_consistency

- **problems**: []
- **n_score_recompute_mismatches**: 0

## ✅ PASS — Gate 5_distribution_sanity

- **statewide_current_flag_share**: 0.1296
- **envelope_ok**: True
- **bound_brook_moderate_or_worse_pctile**: 0.895
- **bound_brook_ranks_high**: True
- **manville_moderate_or_worse_pctile**: 0.798
- **manville_ranks_high**: True
- **coastal_atlantic_ocean_moderate_or_worse_share**: 0.3435
- **statewide_moderate_or_worse_share**: 0.1931
- **coastal_elevated_vs_statewide**: True

## ✅ PASS — Gate 6_rollup_invariants

- **problems**: []

## ✅ PASS — Gate 7_privacy_audit

- **files_checked**: 587
- **artifact_hits**: []
- **tiles_attrs_source_hits**: []
- **note**: tiles attrs audited via 07_tiles.py source, not the binary pmtiles file
