#!/usr/bin/env python3
"""04 — P6 (NFIP claims) to tract-level claims-density percentile (§5.2/§5.3
`C_loss`).

Privacy (§5.6, NON-NEGOTIABLE): "NFIP claims never shown below tract level."
Only `censusGeoid` is ever requested from P6 (via OData `$select`) -- the
other 83 fields on a claims record (addresses, damage amounts, dates,
elevation certs, etc.) are never fetched at all, not fetched-then-dropped,
mirroring Phase 1's field-allowlist discipline (§5.1's note that stripping
happens "at ingest boundary"). Individual claim records are never joined to
a specific parcel or written to any output file -- only tract-level
aggregate counts and the derived percentile are retained; the per-parcel
output below carries a tract-level *statistic*, not claims data.

P6 status (see nj_parcel_lib.py's P6 comment and PROGRESS.md 2026-08-13):
confirmed unavailable 2026-08-02 (old v2 FimaNfipClaims, HTTP 503);
re-checked live for this phase and found available again under a renamed v3
endpoint (`NfipClaims`). Real ingest below, not the §5.3 fallback -- but if a
future session finds P6 down again, that fallback (redistribute C_loss's
0.25 weight proportionally to C_cur/C_fut) is Phase 5's concern, not this
script's; this script's job is simply to not silently produce a wrong or
empty percentile table if the fetch fails.
"""
from __future__ import annotations

import argparse
import sys
import time

import nj_parcel_lib as lib  # imported first: sets PROJ env before geopandas init

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

PARCEL_GEOMS = lib.PROCESSED / "parcel_geoms"
CLAIMS_OUT_DIR = lib.PROCESSED / "parcel_claims"
TRACT_SUMMARY_PARQUET = lib.PROCESSED / "tract_claims_summary.parquet"
TRACT_SUMMARY_MD = lib.REPO / "TRACT_CLAIMS_SUMMARY.md"

CLAIMS_PAGE_SIZE = 1000


def fetch_nj_tracts(force: bool) -> gpd.GeoDataFrame:
    lid = lib.TIGERWEB_TRACTS_LAYER
    gj = lib.get_json(f"{lib.TIGERWEB_TRACTS}/{lid}/query", params={
        "where": f"STATE='{lib.STATE_FIPS}'", "outFields": "GEOID", "outSR": lib.WGS84,
        "f": "geojson"}, force=force, timeout=90)
    rows = []
    for f in gj.get("features", []):
        rows.append({**f["properties"], "geometry": shape(f["geometry"])})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)


def fetch_nj_claims_geoids(force: bool) -> list[str]:
    """Fetch *only* the censusGeoid field for every NJ NFIP claim record.
    Paginated via $skip, not a known total -- $inlinecount timed out in
    testing (likely an expensive server-side count over the full nationwide
    table), so this pages until an empty page comes back instead."""
    geoids: list[str] = []
    skip = 0
    while True:
        page = lib.get_json(lib.P6_CLAIMS_QUERY_URL, params={
            "$filter": "state eq 'NJ'", "$select": "censusGeoid",
            "$top": CLAIMS_PAGE_SIZE, "$skip": skip, "$metadata": "off",
        }, force=force, timeout=60, retries=4, backoff_base=2.0)
        records = page.get("NfipClaims", [])
        if not records:
            break
        geoids.extend(r.get("censusGeoid") for r in records)
        if len(records) < CLAIMS_PAGE_SIZE:
            break
        skip += CLAIMS_PAGE_SIZE
        time.sleep(0.2)
    return geoids


def compute_tract_summary(all_tract_geoids, parcels_per_tract: pd.Series,
                           claims_per_tract: pd.Series) -> pd.DataFrame:
    """Pure aggregation step (§5.2/§5.3): given every known tract GEOID plus
    per-tract parcel and claim counts (as pandas Series keyed by GEOID, as
    produced by value_counts() -- absent GEOIDs implicitly mean 0), return a
    DataFrame with claims_per_1000_parcels and a statewide percentile rank
    (0-1). Percentile is ranked only among tracts with >=1 parcel in scope --
    a 0-parcel tract's rate is undefined/0 by construction (no scored parcel
    ever looks it up), not a real "low risk" signal, so it shouldn't dilute
    the ranked population with an artificial tie at the bottom."""
    summary = pd.DataFrame({"tract_geoid": list(all_tract_geoids)})
    summary["n_parcels"] = summary["tract_geoid"].map(parcels_per_tract).fillna(0).astype(int)
    summary["n_claims"] = summary["tract_geoid"].map(claims_per_tract).fillna(0).astype(int)
    summary["claims_per_1000_parcels"] = np.where(
        summary["n_parcels"] > 0, 1000 * summary["n_claims"] / summary["n_parcels"], 0.0)
    populated = summary["n_parcels"] > 0
    summary["tract_loss_pctile"] = 0.0
    summary.loc[populated, "tract_loss_pctile"] = (
        summary.loc[populated, "claims_per_1000_parcels"].rank(pct=True, method="average"))
    return summary


def assign_tracts(pins, centroids_utm: gpd.GeoSeries, tracts_utm: gpd.GeoDataFrame):
    """Pure spatial-assignment step: given parcel PINs + their centroids
    (already projected, meters) and the statewide tracts layer (already
    projected), return (DataFrame[pin, tract_geoid], n_unmatched, n_tie).
    Keyed by a synthetic row id, not 'pin', for the same reason as Phase 3
    (§12.1 uniqueness gate; PINs aren't guaranteed unique within a county) --
    a boundary tie or unmatched centroid must resolve per physical parcel,
    not accidentally merge two same-PIN parcels' assignments."""
    n = len(pins)
    centroids = gpd.GeoDataFrame(
        {"pin": np.asarray(pins), "_row_id": np.arange(n)},
        geometry=centroids_utm, crs=tracts_utm.crs)
    joined = gpd.sjoin(centroids, tracts_utm[["GEOID", "geometry"]], predicate="within", how="left")
    n_tie = len(joined) - n  # a centroid landing exactly on a shared tract boundary could match >1
    if n_tie:
        joined = joined.sort_values("_row_id").drop_duplicates(subset="_row_id", keep="first")
    joined = joined.sort_values("_row_id").reset_index(drop=True)
    n_unmatched = int(joined["GEOID"].isna().sum())
    return joined[["pin", "GEOID"]].rename(columns={"GEOID": "tract_geoid"}), n_unmatched, n_tie


def process_county(fips: str, tracts_utm: gpd.GeoDataFrame, force: bool):
    """Assign every parcel in `fips` to a tract via centroid-in-polygon.
    Returns (DataFrame[pin, tract_geoid], n_unmatched, n_tie) or None if this
    county's Phase 1 output isn't present."""
    geoms_path = PARCEL_GEOMS / f"{fips}.gpkg"
    if not geoms_path.exists():
        return None
    geoms = gpd.read_file(geoms_path)
    geoms_utm = geoms.to_crs(lib.UTM18N)
    return assign_tracts(geoms["pin"].to_numpy(), geoms_utm.geometry.centroid, tracts_utm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--county", help="Comma-separated county names, or omit for ALL.")
    args = ap.parse_args()

    print("Fetching NJ census tracts (TIGERweb)...")
    tracts = fetch_nj_tracts(args.force)
    tracts_utm = tracts.to_crs(lib.UTM18N)
    print(f"  {len(tracts)} NJ tracts")

    print("Fetching NJ NFIP claims (censusGeoid only, §5.6 privacy)...")
    claim_geoids = fetch_nj_claims_geoids(args.force)
    print(f"  {len(claim_geoids)} NJ claim records")

    n_bad_geoid = sum(1 for g in claim_geoids if not g or len(g) < 11)
    claim_tract_geoids = pd.Series([g[:11] for g in claim_geoids if g and len(g) >= 11])
    known_tracts = set(tracts["GEOID"])
    n_unmatched_claims = int((~claim_tract_geoids.isin(known_tracts)).sum())
    print(f"  {n_bad_geoid} claim(s) with missing/short censusGeoid; "
          f"{n_unmatched_claims}/{len(claim_tract_geoids)} claim geoids don't match a current "
          f"2020 tract (expected to be nonzero -- claims span decades, some predate 2020 "
          f"tract boundaries; only affects those specific claims, not the whole dataset)")
    claims_per_tract = claim_tract_geoids[claim_tract_geoids.isin(known_tracts)].value_counts()

    if args.county:
        wanted = {c.strip().upper() for c in args.county.split(",")}
        fips_list = [lib.COUNTY_FIPS[c] for c in sorted(wanted) if c in lib.COUNTY_FIPS]
    else:
        fips_list = sorted(lib.COUNTY_FIPS.values())

    assignments: dict[str, pd.DataFrame] = {}
    for fips in fips_list:
        result = process_county(fips, tracts_utm, args.force)
        if result is None:
            print(f"  [SKIP] {fips}: parcel_geoms not found")
            continue
        df, n_unmatched, n_tie = result
        assignments[fips] = df
        msg = f"  {fips}: {len(df)} parcels, {n_unmatched} unmatched to any tract"
        if n_tie:
            msg += f", {n_tie} boundary tie(s) resolved"
        print(msg)

    if not assignments:
        print("No counties processed -- nothing to do.")
        return 1

    parcels_per_tract = pd.concat(assignments.values())["tract_geoid"].value_counts()
    summary = compute_tract_summary(tracts["GEOID"], parcels_per_tract, claims_per_tract)
    populated = summary["n_parcels"] > 0

    lib.PROCESSED.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(TRACT_SUMMARY_PARQUET, index=False)

    CLAIMS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fips, df in assignments.items():
        out = df.merge(summary[["tract_geoid", "claims_per_1000_parcels", "tract_loss_pctile"]],
                        on="tract_geoid", how="left")
        out.to_parquet(CLAIMS_OUT_DIR / f"{fips}.parquet", index=False)

    top10 = summary.sort_values("claims_per_1000_parcels", ascending=False).head(10)
    lines = [
        "# NJ Parcel Flood Risk Dashboard — Tract Claims-Density Summary",
        "",
        "Auto-written by `pipeline/04_claims.py` (§5.2/§5.3 `C_loss` input). "
        "Aggregate tract-level counts only -- §5.6: NFIP claims never shown "
        "below tract level; no individual claim record is retained anywhere "
        "in this pipeline's outputs.",
        "",
        f"- NJ tracts: **{len(tracts)}**",
        f"- NJ claim records fetched: **{len(claim_geoids)}**",
        f"- Claims matched to a current (2020) tract: "
        f"**{len(claim_tract_geoids) - n_unmatched_claims}/{len(claim_tract_geoids)}**",
        f"- Tracts with at least one scored parcel: **{int(populated.sum())}/{len(tracts)}**",
        "",
        "## 10 highest claims-density tracts (parcels in scope only)",
        "",
        "| Tract GEOID | Parcels | Claims | Claims / 1,000 parcels | Percentile |",
        "|---|---|---|---|---|",
    ]
    for _, r in top10.iterrows():
        lines.append(f"| {r['tract_geoid']} | {r['n_parcels']} | {r['n_claims']} | "
                     f"{r['claims_per_1000_parcels']:.1f} | {r['tract_loss_pctile']:.3f} |")
    lines.append("")
    TRACT_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {TRACT_SUMMARY_PARQUET.relative_to(lib.REPO)} and TRACT_CLAIMS_SUMMARY.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
