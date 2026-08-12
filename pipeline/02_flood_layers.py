#!/usr/bin/env python3
"""02 — Fetch + normalize P3 (FEMA NFHL flood zones) and P4 (NJDEP CAFE SLR 5ft)
per county (§6.3), log a zone inventory and future-coverage map (§11 Phase 2 exit
criteria).

P3 has no county/state attribute field at all (confirmed Phase 2) -- queried
spatially per county via bounding-box envelope + esriSpatialRelIntersects. A bbox
(not the precise county polygon) is deliberate: it may pull in a thin edge of an
adjacent county's zones near the boundary, which is harmless (03_intersect.py's
actual parcel-level intersection is what determines real overlap; parcels
themselves are already correctly county-scoped from Phase 1) and far simpler than
POSTing a full polygon geometry through a GET-based query helper.

P4 *does* have a COUNTY attribute (confirmed Phase 2) -- queried directly, only for
the 15 counties in lib.P4_COASTAL_COUNTIES; the other 6 are skipped on purpose, not
queried-and-found-empty, so a genuinely missing response isn't confused with "no
flood risk here" (§5.2's fut_coverage=false is a pipeline-level flag applied later,
in 03_intersect.py, not something this script fabricates from an empty result).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import nj_parcel_lib as lib  # imported first: sets PROJ env before geopandas init

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

FLOOD_DIR = lib.PROCESSED / "flood_layers"
COVERAGE_REPORT = lib.PROCESSED / "flood_coverage_report.json"
COVERAGE_MD = lib.REPO / "FLOOD_COVERAGE.md"


def fetch_nj_counties(force: bool) -> gpd.GeoDataFrame:
    lid = 1  # confirmed Phase 2: min Counties layer id, 21/21 NJ counties
    gj = lib.get_json(f"{lib.TIGERWEB_STATE_COUNTY}/{lid}/query", params={
        "where": "STATE='34'", "outFields": "NAME,GEOID", "outSR": lib.WGS84,
        "f": "geojson"}, force=force, timeout=60)
    rows = []
    for f in gj.get("features", []):
        rows.append({**f["properties"], "geometry": shape(f["geometry"])})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)
    gdf["county_upper"] = gdf["NAME"].str.replace(" County", "", regex=False).str.upper()
    return gdf


NFHL_PAGE_SIZE = 200  # not the server's advertised maxRecordCount (2000) -- confirmed
# live (Cape May) that this specific layer 500s on full-geometry pages of 500 but
# succeeds at 200. Its polygons (following a convoluted barrier-island coastline)
# are evidently far heavier per-feature than a generic maxRecordCount assumes;
# this is a response-size/complexity limit, not a count limit (a returnCountOnly
# query against the identical spatial filter succeeds instantly) and not the
# per-record server bug seen on P4 (§ fetch_p4_county) -- a plain smaller page
# size is the right fix here, not retries or bisection.


def fetch_nfhl_bbox(bbox: tuple[float, float, float, float], force: bool) -> gpd.GeoDataFrame:
    # f=json (esri JSON), not geojson -- this specific FEMA layer 500s on geojson
    # output (confirmed live, §4 P3 note). Geometry converted via
    # lib.esri_rings_to_geom() instead of shapely.geometry.shape().
    xmin, ymin, xmax, ymax = bbox
    rows: list[dict] = []
    offset = 0
    while True:
        page = lib.get_json(
            f"{lib.P3_NFHL_BASE}/{lib.P3_NFHL_FLOOD_ZONES_LAYER}/query", params={
                "geometry": f"{xmin},{ymin},{xmax},{ymax}", "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects", "inSR": lib.WGS84,
                "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM,DEPTH",
                "outSR": lib.WGS84, "resultOffset": offset,
                "resultRecordCount": NFHL_PAGE_SIZE, "f": "json"}, force=force, timeout=90,
            retries=4, backoff_base=2.0)
        feats = page.get("features", [])
        if not feats:
            break
        for f in feats:
            rings = (f.get("geometry") or {}).get("rings")
            if not rings:
                continue
            geom = lib.esri_rings_to_geom(rings)
            if geom is not None:
                rows.append({**f["attributes"], "geometry": geom})
        if len(feats) < NFHL_PAGE_SIZE:
            break
        offset += NFHL_PAGE_SIZE
        time.sleep(0.3)  # light spacing between pages, cheap insurance
    if not rows:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=lib.WGS84)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)


P4_BAD_IDS_LOG: list[int] = []  # populated by _fetch_p4_batch, reported in main()


def _fetch_p4_batch(batch: list[int], force: bool, rows: list[dict], depth: int = 0) -> None:
    """Fetch one batch of P4 objectIds, appending parsed rows to `rows` in place.

    f=json (esri JSON), not geojson: confirmed live that this specific NJDEP host
    returns a clean, parseable {"error": {...}} for f=json but an HTML page for
    f=geojson on the *identical* failing request -- geojson was masking a real
    server-side "Error performing query operation" as what looked like a WAF
    block. It isn't rate-limiting (confirmed: retries with 8-40s backoff didn't
    help, same batch failed every time) -- it's a genuine per-record server bug,
    most likely one specific feature's geometry the server chokes on. Standard
    fix: bisect the batch and retry each half; at batch size 1, a still-failing
    single record is a real bad record on the source side, not a client error --
    skip it, log it, keep going (§13.2's "log, don't silently drop" spirit, but
    for a source-side defect rather than an ambiguous mapping)."""
    try:
        page = lib.get_json(f"{lib.P4_CAFE_SLR5_URL}/query", params={
            "objectIds": ",".join(str(x) for x in batch),
            "outFields": "FLD_ZONE,COUNTY", "outSR": lib.WGS84,
            "f": "json"}, force=force, timeout=90, retries=2, backoff_base=2.0)
    except RuntimeError:
        if len(batch) == 1:
            P4_BAD_IDS_LOG.append(batch[0])
            return
        mid = len(batch) // 2
        _fetch_p4_batch(batch[:mid], force, rows, depth + 1)
        _fetch_p4_batch(batch[mid:], force, rows, depth + 1)
        return
    for f in page.get("features", []):
        rings = (f.get("geometry") or {}).get("rings")
        if not rings:
            continue
        geom = lib.esri_rings_to_geom(rings)
        if geom is not None:
            rows.append({**f["attributes"], "geometry": geom})


def fetch_p4_county(county_upper: str, force: bool) -> gpd.GeoDataFrame:
    # OBJECTID-based, not resultOffset: this host also fails on some deep-offset
    # queries (separate finding, confirmed live) -- returnIdsOnly + explicit
    # objectIds avoids resultOffset entirely regardless.
    where = f"COUNTY='{county_upper}'"
    ids_resp = lib.get_json(f"{lib.P4_CAFE_SLR5_URL}/query",
                            params={"where": where, "returnIdsOnly": "true", "f": "json"},
                            force=force, timeout=60)
    ids = sorted(ids_resp.get("objectIds") or [])
    if not ids:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=lib.WGS84)

    rows: list[dict] = []
    chunk = 1000
    for i in range(0, len(ids), chunk):
        _fetch_p4_batch(ids[i:i + chunk], force, rows)
        if i + chunk < len(ids):
            time.sleep(0.5)
    if not rows:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=lib.WGS84)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)


def zone_inventory(gdf: gpd.GeoDataFrame, zone_field: str) -> dict:
    if len(gdf) == 0:
        return {}
    gdf_utm = gdf.to_crs(lib.UTM18N)
    gdf_utm["_area_km2"] = gdf_utm.geometry.area / 1e6
    return (gdf_utm.groupby(zone_field)["_area_km2"].agg(["count", "sum"])
            .rename(columns={"count": "n_features", "sum": "area_km2"})
            .round({"area_km2": 3}).to_dict("index"))


def process_county(row, force: bool) -> dict:
    county_upper = row["county_upper"]
    fips = lib.COUNTY_FIPS.get(county_upper)
    bbox = row.geometry.bounds  # (xmin, ymin, xmax, ymax)

    nfhl = fetch_nfhl_bbox(bbox, force)
    (FLOOD_DIR / "nfhl").mkdir(parents=True, exist_ok=True)
    if len(nfhl):
        nfhl["geometry"] = nfhl.geometry.buffer(0)
        nfhl.to_file(FLOOD_DIR / "nfhl" / f"{fips}.gpkg", driver="GPKG")
    nfhl_inv = zone_inventory(nfhl, "FLD_ZONE")
    n_sfha = int((nfhl["SFHA_TF"] == "T").sum()) if len(nfhl) else 0

    result = {
        "county": county_upper, "fips": fips,
        "nfhl_n_features": len(nfhl), "nfhl_n_sfha": n_sfha,
        "nfhl_zone_inventory": nfhl_inv,
        "p4_covered": county_upper in lib.P4_COASTAL_COUNTIES,
    }

    if county_upper in lib.P4_COASTAL_COUNTIES:
        n_bad_before = len(P4_BAD_IDS_LOG)
        p4 = fetch_p4_county(county_upper, force)
        (FLOOD_DIR / "cafe_slr5").mkdir(parents=True, exist_ok=True)
        if len(p4):
            p4["geometry"] = p4.geometry.buffer(0)
            p4.to_file(FLOOD_DIR / "cafe_slr5" / f"{fips}.gpkg", driver="GPKG")
        result["p4_n_features"] = len(p4)
        result["p4_zone_inventory"] = zone_inventory(p4, "FLD_ZONE")
        result["p4_bad_ids_skipped"] = P4_BAD_IDS_LOG[n_bad_before:]
    else:
        result["p4_n_features"] = None
        result["p4_zone_inventory"] = None
        result["p4_bad_ids_skipped"] = []

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--county", help="Comma-separated county names, or omit for ALL.")
    args = ap.parse_args()

    counties = fetch_nj_counties(args.force)
    if args.county:
        wanted = {c.strip().upper() for c in args.county.split(",")}
        counties = counties[counties["county_upper"].isin(wanted)]

    results = []
    for _, row in counties.iterrows():
        print(f"\n--- {row['NAME']} ---")
        r = process_county(row, args.force)
        results.append(r)
        print(f"  NFHL: {r['nfhl_n_features']} zones ({r['nfhl_n_sfha']} SFHA)")
        if r["p4_covered"]:
            print(f"  P4 (CAFE SLR 5ft): {r['p4_n_features']} features")
            if r["p4_bad_ids_skipped"]:
                print(f"  [WARN] {len(r['p4_bad_ids_skipped'])} P4 record(s) skipped "
                      f"(server-side query error, not a client issue): "
                      f"{r['p4_bad_ids_skipped']}")
        else:
            print("  P4 (CAFE SLR 5ft): not covered (fut_coverage=false for this county)")

    lib.PROCESSED.mkdir(parents=True, exist_ok=True)
    COVERAGE_REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    total_bad_ids = sum(len(r["p4_bad_ids_skipped"]) for r in results)
    n_covered = sum(1 for r in results if r["p4_covered"])
    lines = [
        "# NJ Parcel Flood Risk Dashboard — Flood Layer Coverage (FLOOD_COVERAGE.md)",
        "",
        "Auto-written by `pipeline/02_flood_layers.py` (§11 Phase 2 exit criterion: "
        "zone inventories per county + a future-coverage map).",
        "",
        "## Per-county summary",
        "",
        "| County | FIPS | NFHL zones | NFHL SFHA zones | P4 (CAFE SLR 5ft) covered | P4 features |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: r["county"]):
        p4_cell = f"{r['p4_n_features']}" if r["p4_covered"] else "—"
        lines.append(f"| {r['county']} | {r['fips']} | {r['nfhl_n_features']} | "
                     f"{r['nfhl_n_sfha']} | {'✅' if r['p4_covered'] else '❌ no data'} | {p4_cell} |")
    lines += [
        "",
        f"**{n_covered}/{len(results)} counties have P4 future-risk coverage.** The "
        f"other {len(results) - n_covered} get `fut_coverage=false` in Phase 3/4 -- "
        "the UI must show \"future data n/a here\", never \"no future risk\" (§5.2).",
        "",
    ]
    if total_bad_ids:
        bad_by_county = {r["county"]: r["p4_bad_ids_skipped"] for r in results if r["p4_bad_ids_skipped"]}
        lines += [
            f"**{total_bad_ids} P4 record(s) skipped statewide** (server-side query "
            "error on this specific record, reproduced directly against the source "
            "with a clean {\"error\":...} response -- not a client-side/rate-limit "
            "issue). Logged here, not silently dropped:",
            "",
        ]
        for county, ids in bad_by_county.items():
            lines.append(f"- {county}: objectIds {ids}")
        lines.append("")
    COVERAGE_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {COVERAGE_REPORT.relative_to(lib.REPO)} and FLOOD_COVERAGE.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
