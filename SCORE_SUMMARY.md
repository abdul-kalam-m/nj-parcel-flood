# NJ Parcel Flood Risk Dashboard — Score Summary

Auto-written by `pipeline/05_score.py` (§5.3 composite score + bands). `C_loss` weight redistributed to `C_cur`/`C_fut` (0.60/0.40) for any parcel without a usable tract percentile -- §5.3's documented mechanism, applied per-parcel here since the only rows affected are Phase 4's 31 statewide tract-unmatched parcels, not a P6 outage.

- Parcels scored: **3478722**
- `C_loss` redistributed (no tract match): **31**

## Statewide band distribution

| Band | Parcels | % |
|---|---|---|
| none | 10 | 0.00% |
| low | 2806930 | 80.69% |
| moderate | 194462 | 5.59% |
| high | 189233 | 5.44% |
| severe | 288087 | 8.28% |
