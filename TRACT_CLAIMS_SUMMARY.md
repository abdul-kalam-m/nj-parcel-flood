# NJ Parcel Flood Risk Dashboard — Tract Claims-Density Summary

Auto-written by `pipeline/04_claims.py` (§5.2/§5.3 `C_loss` input). Aggregate tract-level counts only -- §5.6: NFIP claims never shown below tract level; no individual claim record is retained anywhere in this pipeline's outputs.

- NJ tracts: **2181**
- NJ claim records fetched: **202287**
- Claims matched to a current (2020) tract: **182606/200327**
- Tracts with at least one scored parcel: **2178/2181**

## 10 highest claims-density tracts (parcels in scope only)

| Tract GEOID | Parcels | Claims | Claims / 1,000 parcels | Percentile |
|---|---|---|---|---|
| 34031246300 | 1935 | 5275 | 2726.1 | 1.000 |
| 34031196401 | 1533 | 2425 | 1581.9 | 1.000 |
| 34035051100 | 847 | 1332 | 1572.6 | 0.999 |
| 34025812100 | 1590 | 1887 | 1186.8 | 0.999 |
| 34027040101 | 1282 | 1342 | 1046.8 | 0.998 |
| 34029736105 | 3625 | 3752 | 1035.0 | 0.998 |
| 34001010101 | 2955 | 2686 | 909.0 | 0.997 |
| 34009021400 | 4059 | 3621 | 892.1 | 0.997 |
| 34025809302 | 2443 | 2146 | 878.4 | 0.996 |
| 34029738001 | 6514 | 5664 | 869.5 | 0.996 |
