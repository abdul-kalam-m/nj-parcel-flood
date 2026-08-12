#!/usr/bin/env python3
"""01 — Ingest the statewide parcel composite (P1), strip to a privacy-safe field
set, apply the §5.4 class-group crosswalk, and write per-county
parcel_master/{fips}.parquet + parcel_geoms/{fips}.gpkg (§6.3/§6.5).

Privacy (§5.6, NON-NEGOTIABLE): only ever *requests* an allowlisted field set from
the source -- OWNER_NAME, ST_ADDRESS, CITY_STATE, ZIP_CODE/ZIP5/ZIP_PLUS4 are never
fetched at all, not just filtered out after the fact. ST_ADDRESS/CITY_STATE/ZIP were
verified live (2026-08-02, see PROGRESS.md) to be the OWNER's mailing address, not
the parcel's own situs address, despite looking address-shaped -- confirmed via
PO-Box entries and properties whose "address" is in a different municipality than
the parcel itself. PROP_LOC is the real situs address field and is the one this
script keeps.

Also builds the mini-state fixture (§11 Phase 1 exit criterion): Bound Brook
(riverine, explicitly named in the guide), Atlantic City (coastal), Mendham Boro
(inland) -- written to pipeline/tests/fixtures/ instead of data/processed/, small
enough to commit.
"""
from __future__ import annotations

import argparse
import sys

import nj_parcel_lib as lib  # imported first: sets PROJ env before geopandas init

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

# Privacy-safe allowlist (§5.1) -- OWNER_NAME/ST_ADDRESS/CITY_STATE/ZIP* deliberately
# absent; never requested from the source, not just dropped after fetch.
OUT_FIELDS = ("PAMS_PIN,COUNTY,MUN_NAME,PCL_MUN,PCLBLOCK,PCLLOT,PCLQCODE,"
              "PROP_LOC,PROP_CLASS,LAND_VAL,IMPRVT_VAL,NET_VALUE,CALC_ACRE")

# §5.4 class-group crosswalk (LOCKED). Any code not listed here -> "Other", logged,
# never silently dropped (guide's explicit instruction).
CLASS_GROUPS: dict[str, str] = {
    "2": "Residential", "4C": "Residential",
    "4A": "Commercial",
    "4B": "Industrial",
    "3A": "Farm/Agricultural", "3B": "Farm/Agricultural",
    "1": "Vacant",
    "15A": "Public/Institutional/Exempt", "15B": "Public/Institutional/Exempt",
    "15C": "Public/Institutional/Exempt", "15D": "Public/Institutional/Exempt",
    "15E": "Public/Institutional/Exempt", "15F": "Public/Institutional/Exempt",
    "5A": "Other", "5B": "Other", "6A": "Other", "6B": "Other",
}
EXEMPT_CODES = {"15A", "15B", "15C", "15D", "15E", "15F"}

# (label, PCL_MUN exact code, county name) -- PCL_MUN, not "MUN_NAME LIKE ... AND
# COUNTY=...": COUNTY/MUN_NAME are NULL for any parcel that never matched a MOD-IV
# record (confirmed live, 2026-08-03 -- 405,573 statewide, ~11.7%), so a MUN_NAME/
# COUNTY-based filter silently drops every one of them, exactly the bug that made
# the join-rate QA gate read a tautological 100%. PCL_MUN comes from the base
# parcel layer, independent of any MOD-IV join, so it's the field that actually
# finds every parcel. Bound Brook explicitly required by the guide (riverine,
# narrative link to FloodOps v1); Atlantic City = coastal (real P4 CAFE coverage);
# Mendham Boro = inland (Morris Co., one of the 6 counties with no P4 coverage --
# exercises the fut_coverage=false path deliberately).
FIXTURE_MUNIS = [
    ("bound-brook", "1804", "SOMERSET"),
    ("atlantic-city", "0102", "ATLANTIC"),
    ("mendham-boro", "1418", "MORRIS"),
]


def class_group(code) -> str:
    # code can be None, NaN (float -- how a missing value round-trips through a
    # mixed string/null GeoJSON->DataFrame column, confirmed live once the
    # PCL_MUN-based fetch started genuinely returning MOD-IV-unmatched parcels
    # with a real absent PROP_CLASS), or a real string. `code or ""` doesn't
    # normalize NaN -- float('nan') is truthy in Python, so that produced a float
    # instead of "" and crashed on .strip(). isinstance-check first instead.
    #
    # Returns just the group ("Other" for both "no code at all" and "a code that
    # isn't in the crosswalk") -- callers that need to distinguish those two cases
    # for QA purposes (§12.1: join rate and unmapped-code-rate are two *separate*
    # gates, not one) should check for a present-but-unrecognized code themselves,
    # not infer it from this function's "Other" result alone.
    if not isinstance(code, str):
        return "Other"
    code = code.strip()
    if not code:
        return "Other"
    return CLASS_GROUPS.get(code, "Other")


def fetch_where(where: str, force: bool) -> gpd.GeoDataFrame:
    """Paginated FeatureServer fetch (maxRecordCount=2000, confirmed Phase 0)."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = lib.get_json(f"{lib.P1_PARCELS_URL}/query", params={
            "where": where, "outFields": OUT_FIELDS, "outSR": lib.WGS84,
            "resultOffset": offset, "resultRecordCount": lib.P1_MAX_RECORD_COUNT,
            "f": "geojson"}, force=force, timeout=90)
        feats = page.get("features", [])
        if not feats:
            break
        for f in feats:
            attrs = dict(f["properties"])
            attrs["geometry"] = shape(f["geometry"]) if f.get("geometry") else None
            rows.append(attrs)
        if len(feats) < lib.P1_MAX_RECORD_COUNT:
            break
        offset += lib.P1_MAX_RECORD_COUNT
    if not rows:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=lib.WGS84)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)


def _clean_str(series: pd.Series) -> pd.Series:
    """Null-safe string conversion -- plain .astype(str) turns a None/NaN cell into
    the literal text "None"/"nan", which is worse than an empty string for a field
    that's genuinely absent on unmatched parcels."""
    return series.fillna("").astype(str)


def build_master(gdf: gpd.GeoDataFrame, known_county: str):
    # Returns (master_df, stats_dict, keep_mask) -- keep_mask lets fetch_and_write()
    # apply the identical exact-dupe row selection to the geometry GeoDataFrame.
    n_fetched = len(gdf)  # before exact-dupe collapse below; rate denominators use
    # this (not the post-dedup row count) since a dropped exact duplicate doesn't
    # change how many real, distinct parcels were or weren't matched.
    has_code = gdf["PROP_CLASS"].apply(lambda c: isinstance(c, str) and c.strip() != "")
    n_no_class = int((~has_code).sum())
    groups = [class_group(c) for c in gdf["PROP_CLASS"]]
    # "Unmapped" (§12.1: < 0.5% of parcels) means a REAL, present PROP_CLASS value
    # our crosswalk doesn't recognize -- a genuine crosswalk gap. A parcel with no
    # code at all isn't a crosswalk problem, it's a join-rate problem (n_no_class/
    # join_rate above) -- conflating the two made an ordinary ~5-12% MOD-IV
    # unmatched rate look like a wildly failing crosswalk (it isn't: the crosswalk
    # itself was already verified against every code actually in use, Phase 1).
    unmapped_mask = has_code & ~gdf["PROP_CLASS"].isin(CLASS_GROUPS)
    unmapped_codes = sorted(set(gdf.loc[unmapped_mask, "PROP_CLASS"]))

    master = pd.DataFrame({
        "pin": gdf["PAMS_PIN"].astype(str),
        # county: always the KNOWN county we queried for, never the source COUNTY
        # field directly -- that field is NULL for any parcel without a MOD-IV
        # match (see FIXTURE_MUNIS comment), which would otherwise put NaN/"None"
        # into every county-level rollup for exactly the records this fix exists
        # to stop losing.
        "county": known_county,
        "mun_code": gdf["PCL_MUN"].astype(str),
        "mun_name": _clean_str(gdf["MUN_NAME"]),
        "block": gdf["PCLBLOCK"].astype(str),
        "lot": gdf["PCLLOT"].astype(str),
        "qual": _clean_str(gdf["PCLQCODE"]),
        "situs_address": _clean_str(gdf["PROP_LOC"]),
        "prop_class": _clean_str(gdf["PROP_CLASS"]),
        "class_group": list(groups),
        "exempt": gdf["PROP_CLASS"].isin(EXEMPT_CODES),
        "land_val": pd.to_numeric(gdf["LAND_VAL"], errors="coerce"),
        "imprvt_val": pd.to_numeric(gdf["IMPRVT_VAL"], errors="coerce"),
        "net_value": pd.to_numeric(gdf["NET_VALUE"], errors="coerce"),
        "area_acres": pd.to_numeric(gdf["CALC_ACRE"], errors="coerce"),
        "mod_iv_matched": has_code.to_numpy(),
    })
    # Composite key fallback for the rare case PIN isn't unique (§5.1) -- always
    # present, not just computed on collision, so downstream code never has to
    # special-case its absence.
    master["composite_key"] = (master["county"] + "_" + master["mun_code"] + "_" +
                               master["block"] + "_" + master["lot"] + "_" + master["qual"])

    # §12.1: "PIN unique statewide (dupes logged + resolved by composite key)" --
    # the guide anticipates dupes existing, so they aren't dropped unexamined. But
    # an *exact*-duplicate row (same PIN, identical in every other column too --
    # confirmed live: Mendham Boro's 1418_2301_14, both copies null/unmatched) adds
    # nothing and would double-count in any aggregate, so those are collapsed. A
    # dupe PIN whose rows actually *differ* is the real, more concerning case the
    # composite-key fallback exists for -- logged, not silently resolved here.
    exact_dupe_mask = master.duplicated(keep="first")
    n_exact_dupes_dropped = int(exact_dupe_mask.sum())
    keep_mask = ~exact_dupe_mask.to_numpy()  # returned below so fetch_and_write()
    # applies the identical row selection to the geometry GeoDataFrame -- this
    # dedup is attribute-only (geometry isn't one of master's columns), so
    # filtering geoms independently by PIN afterward could silently pick a
    # different, potentially-mismatched geometry for a conflicting-attribute PIN.
    master = master.loc[keep_mask].reset_index(drop=True)
    n_conflicting_dupe_pins = int(master["pin"].duplicated().sum())

    stats = {
        "n_total": len(master),
        "n_exact_dupes_dropped": n_exact_dupes_dropped,
        "n_dupe_pin": n_conflicting_dupe_pins,
        "n_dupe_composite_key": int(master["composite_key"].duplicated().sum()),
        "n_mod_iv_unmatched": n_no_class,
        "join_rate": round(1 - (n_no_class / n_fetched), 4) if n_fetched else None,
        "unmapped_class_codes": unmapped_codes,
        "unmapped_count": int(unmapped_mask.sum()),
        "unmapped_pct": round(100 * int(unmapped_mask.sum()) / n_fetched, 3) if n_fetched else 0,
    }
    return master, stats, keep_mask


def fetch_and_write(label: str, where: str, known_county: str, out_master, out_geoms, force: bool) -> dict:
    gdf = fetch_where(where, force)
    if len(gdf) == 0:
        return {"label": label, "ok": False, "detail": "0 features returned"}

    master, stats, keep_mask = build_master(gdf, known_county)
    gdf = gdf.loc[keep_mask].reset_index(drop=True)  # same exact-dupe rows dropped
    # from master, applied here too -- keeps master/geoms in 1:1 correspondence by
    # construction rather than re-deriving it from PIN afterward.
    invalid_before = int((~gdf.geometry.is_valid).sum())
    # Build geoms as a real GeoDataFrame from construction -- selecting a single
    # non-geometry column (gdf[["PAMS_PIN"]]) silently demotes it to a plain
    # DataFrame, and .geometry then resolves to a plain pandas attribute instead of
    # the GeoSeries accessor, breaking .is_valid/.is_empty downstream.
    geoms = gpd.GeoDataFrame(
        {"pin": gdf["PAMS_PIN"].to_numpy(), "geometry": gdf.geometry.buffer(0)},
        geometry="geometry", crs=lib.WGS84)  # buffer(0) repairs invalid rings, same as FloodOps pattern
    invalid_after = int((~geoms.geometry.is_valid).sum())
    empty_after = int(geoms.geometry.is_empty.sum())

    out_master.parent.mkdir(parents=True, exist_ok=True)
    out_geoms.parent.mkdir(parents=True, exist_ok=True)
    master.to_parquet(out_master, index=False)
    geoms.to_file(out_geoms, driver="GPKG")

    stats.update({
        "label": label, "ok": True,
        "n_geom_invalid_before_repair": invalid_before,
        "n_geom_invalid_after_repair": invalid_after,
        "n_geom_empty_after_repair": empty_after,
        "master_path": str(out_master), "geoms_path": str(out_geoms),
    })
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fixture", action="store_true", help="Build the 3-muni mini-state fixture only.")
    ap.add_argument("--county", help="Comma-separated county names, or ALL for statewide.")
    args = ap.parse_args()

    if args.fixture:
        fixtures_dir = lib.PIPELINE_DIR / "tests" / "fixtures"
        results = []
        for label, pcl_mun, county in FIXTURE_MUNIS:
            print(f"\n--- fixture: {label} ---")
            r = fetch_and_write(
                label, f"PCL_MUN='{pcl_mun}'", county,
                fixtures_dir / "parcel_master" / f"{label}.parquet",
                fixtures_dir / "parcel_geoms" / f"{label}.gpkg",
                args.force)
            results.append(r)
            if r["ok"]:
                print(f"  {r['n_total']} parcels, join_rate={r['join_rate']} "
                      f"({r['n_mod_iv_unmatched']} unmatched), dupe_pin={r['n_dupe_pin']}, "
                      f"unmapped={r['unmapped_count']} ({r['unmapped_pct']}%), "
                      f"geom invalid before/after repair="
                      f"{r['n_geom_invalid_before_repair']}/{r['n_geom_invalid_after_repair']}")
            else:
                print(f"  [FAIL] {r['detail']}")
        ok = all(r["ok"] for r in results)
        return 0 if ok else 2

    if not args.county:
        print("Specify --fixture, or --county <NAME[,NAME...]|ALL>", file=sys.stderr)
        return 2

    counties = (list(lib.COUNTY_FIPS.keys()) if args.county == "ALL"
                else [c.strip().upper() for c in args.county.split(",")])
    results = []
    for county in counties:
        fips = lib.COUNTY_FIPS.get(county)
        prefix = lib.COUNTY_PREFIX.get(county)
        if not fips or not prefix:
            print(f"  [FAIL] unknown county name: {county!r}")
            results.append({"label": county, "ok": False, "detail": "unknown county name"})
            continue
        print(f"\n--- {county} ({fips}) ---")
        r = fetch_and_write(
            county, f"PCL_MUN LIKE '{prefix}%'", county,
            lib.PROCESSED / "parcel_master" / f"{fips}.parquet",
            lib.PROCESSED / "parcel_geoms" / f"{fips}.gpkg",
            args.force)
        results.append(r)
        if r["ok"]:
            print(f"  {r['n_total']} parcels, join_rate={r['join_rate']} "
                  f"({r['n_mod_iv_unmatched']} unmatched), dupe_pin={r['n_dupe_pin']}, "
                  f"unmapped={r['unmapped_count']} ({r['unmapped_pct']}%), "
                  f"geom invalid before/after repair="
                  f"{r['n_geom_invalid_before_repair']}/{r['n_geom_invalid_after_repair']}")
            if r["unmapped_class_codes"]:
                print(f"  unmapped codes seen: {r['unmapped_class_codes']}")
        else:
            print(f"  [FAIL] {r['detail']}")

    print(f"\n{'='*68}\n{sum(1 for r in results if r['ok'])}/{len(results)} counties processed.")
    failures = [r for r in results if not r["ok"]]
    if failures:
        print("Failures:", [r["label"] for r in failures])
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
