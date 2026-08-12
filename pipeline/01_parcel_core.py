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

FIXTURE_MUNIS = [
    # (label, where_clause) -- Bound Brook explicitly required by the guide
    # (riverine, narrative link to FloodOps v1); Atlantic City = coastal (real P4
    # CAFE coverage); Mendham Boro = inland (Morris Co., one of the 7 counties with
    # no P4 coverage at all -- exercises the fut_coverage=false path deliberately).
    ("bound-brook", "MUN_NAME LIKE 'BOUND BROOK%' AND COUNTY='SOMERSET'"),
    ("atlantic-city", "MUN_NAME LIKE 'ATLANTIC CITY%' AND COUNTY='ATLANTIC'"),
    ("mendham-boro", "MUN_NAME LIKE 'MENDHAM BORO%' AND COUNTY='MORRIS'"),
]


def class_group(code: str | None) -> tuple[str, bool]:
    code = (code or "").strip()
    if not code:
        return "Other", True
    group = CLASS_GROUPS.get(code)
    return (group, False) if group else ("Other", True)


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


def build_master(gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    n_total = len(gdf)
    n_no_class = int((gdf["PROP_CLASS"].isna() | (gdf["PROP_CLASS"].astype(str).str.strip() == "")).sum())
    groups, unmapped_flags = zip(*(class_group(c) for c in gdf["PROP_CLASS"])) if n_total else ((), ())
    unmapped_codes = sorted({
        str(c) for c, u in zip(gdf["PROP_CLASS"], unmapped_flags) if u and str(c).strip()
    })

    master = pd.DataFrame({
        "pin": gdf["PAMS_PIN"].astype(str),
        "county": gdf["COUNTY"].astype(str),
        "mun_code": gdf["PCL_MUN"].astype(str),
        "mun_name": gdf["MUN_NAME"].astype(str),
        "block": gdf["PCLBLOCK"].astype(str),
        "lot": gdf["PCLLOT"].astype(str),
        "qual": gdf["PCLQCODE"].astype(str),
        "situs_address": gdf["PROP_LOC"].astype(str),
        "prop_class": gdf["PROP_CLASS"].astype(str),
        "class_group": list(groups),
        "exempt": gdf["PROP_CLASS"].isin(EXEMPT_CODES),
        "land_val": pd.to_numeric(gdf["LAND_VAL"], errors="coerce"),
        "imprvt_val": pd.to_numeric(gdf["IMPRVT_VAL"], errors="coerce"),
        "net_value": pd.to_numeric(gdf["NET_VALUE"], errors="coerce"),
        "area_acres": pd.to_numeric(gdf["CALC_ACRE"], errors="coerce"),
    })
    # Composite key fallback for the rare case PIN isn't unique (§5.1) -- always
    # present, not just computed on collision, so downstream code never has to
    # special-case its absence.
    master["composite_key"] = (master["county"] + "_" + master["mun_code"] + "_" +
                               master["block"] + "_" + master["lot"] + "_" + master["qual"])

    stats = {
        "n_total": n_total,
        "n_dupe_pin": int(master["pin"].duplicated().sum()),
        "n_dupe_composite_key": int(master["composite_key"].duplicated().sum()),
        "join_rate": round(1 - (n_no_class / n_total), 4) if n_total else None,
        "unmapped_class_codes": unmapped_codes,
        "unmapped_count": sum(unmapped_flags),
        "unmapped_pct": round(100 * sum(unmapped_flags) / n_total, 3) if n_total else 0,
    }
    return master, stats


def fetch_and_write(label: str, where: str, out_master, out_geoms, force: bool) -> dict:
    gdf = fetch_where(where, force)
    if len(gdf) == 0:
        return {"label": label, "ok": False, "detail": "0 features returned"}

    master, stats = build_master(gdf)
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
        for label, where in FIXTURE_MUNIS:
            print(f"\n--- fixture: {label} ---")
            r = fetch_and_write(
                label, where,
                fixtures_dir / "parcel_master" / f"{label}.parquet",
                fixtures_dir / "parcel_geoms" / f"{label}.gpkg",
                args.force)
            results.append(r)
            if r["ok"]:
                print(f"  {r['n_total']} parcels, join_rate={r['join_rate']}, "
                      f"dupe_pin={r['n_dupe_pin']}, unmapped={r['unmapped_count']} "
                      f"({r['unmapped_pct']}%), geom invalid before/after repair="
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
        if not fips:
            print(f"  [FAIL] unknown county name: {county!r}")
            results.append({"label": county, "ok": False, "detail": "unknown county name"})
            continue
        print(f"\n--- {county} ({fips}) ---")
        r = fetch_and_write(
            county, f"COUNTY='{county}'",
            lib.PROCESSED / "parcel_master" / f"{fips}.parquet",
            lib.PROCESSED / "parcel_geoms" / f"{fips}.gpkg",
            args.force)
        results.append(r)
        if r["ok"]:
            print(f"  {r['n_total']} parcels, join_rate={r['join_rate']}, "
                  f"dupe_pin={r['n_dupe_pin']}, unmapped={r['unmapped_count']} "
                  f"({r['unmapped_pct']}%), geom invalid before/after repair="
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
