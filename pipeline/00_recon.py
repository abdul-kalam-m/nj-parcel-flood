#!/usr/bin/env python3
"""00 — Verify P1-P9 (§4) against their live sources, identify the exact P4 future-
flood-layer set, verify P8's geocoder, check local tooling (GDAL/ogr2ogr, tippecanoe
route), and write RECON.md + data/processed/recon_report.json.

Every URL/finding here was independently verified live on 2026-08-02 before being
encoded (see nj_parcel_lib.py's per-source comments for how each was found and what
went wrong with the guide's original assumptions) -- this script re-checks them,
it does not just trust that verification forever.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import nj_parcel_lib as lib  # imported first: sets PROJ env before any geo import

RECON_MD = lib.REPO / "RECON.md"
REPORT_JSON = lib.PROCESSED / "recon_report.json"


def check_p1_parcels(force: bool) -> dict:
    meta = lib.check_url(f"{lib.P1_PARCELS_URL}", params={"f": "json"})
    if not meta["ok"]:
        return {"source": "P1 parcels", "ok": False, "detail": meta}
    count = lib.get_json(f"{lib.P1_PARCELS_URL}/query",
                         params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                         force=force)
    sample = lib.get_json(f"{lib.P1_PARCELS_URL}/query", params={
        "where": "COUNTY='OCEAN'", "outFields": "OWNER_NAME", "resultRecordCount": 200,
        "f": "json"}, force=force)
    non_blank = sum(1 for f in sample.get("features", []) if f["attributes"]["OWNER_NAME"])
    return {
        "source": "P1 parcels (NJOGIS Parcels_Composite_NJ_WM)", "ok": True,
        "url": lib.P1_PARCELS_URL, "record_count": count.get("count"),
        "max_record_count": lib.P1_MAX_RECORD_COUNT,
        "owner_name_redaction_check": f"{non_blank}/{len(sample.get('features', []))} non-blank in OCEAN sample",
        "note": "Bulk .gdb.zip on geoapps.nj.gov is Incapsula-blocked to plain requests; "
                "use this FeatureServer for query-based county-by-county ingest instead.",
    }


def check_p3_nfhl(force: bool) -> dict:
    meta = lib.get_json(f"{lib.P3_NFHL_BASE}", params={"f": "json"}, force=force)
    layers = {l["id"]: l["name"] for l in meta.get("layers", [])}
    zones_ok = lib.P3_NFHL_FLOOD_ZONES_LAYER in layers
    return {
        "source": "P3 FEMA NFHL", "ok": zones_ok, "url": lib.P3_NFHL_BASE,
        "flood_zones_layer_id": lib.P3_NFHL_FLOOD_ZONES_LAYER,
        "flood_zones_layer_name": layers.get(lib.P3_NFHL_FLOOD_ZONES_LAYER),
        "total_layers": len(layers),
        "note": "Guide's original hazards.fema.gov/gis/nfhl/rest/... path 404s "
                "(WebSEAL error) -- corrected to /arcgis/rest/... 2026-08-02.",
    }


def check_p4_future_layers(force: bool) -> dict:
    meta = lib.get_json(f"{lib.P4_CAFE_SLR5_URL}", params={"f": "json"}, force=force)
    count = lib.get_json(f"{lib.P4_CAFE_SLR5_URL}/query",
                         params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                         force=force)
    return {
        "source": "P4 NJDEP Tidal CAFE SLR 5ft", "ok": True, "url": lib.P4_CAFE_SLR5_URL,
        "feature_count": count.get("count"),
        "height_model": meta.get("sourceHeightModelInfo"),
        "coastal_counties_covered": lib.P4_COASTAL_COUNTIES,
        "n_counties_covered": len(lib.P4_COASTAL_COUNTIES), "n_counties_total_nj": 21,
        "note": "Single scenario (+5 ft over FEMA coastal SFHA), not multiple SLR "
                "increments. Coastal-only -- inland counties get fut_coverage=false "
                "per §5.2, exactly as the guide's partial-coverage contingency "
                "anticipated. An ArcGIS *item* pointing at this URL is flagged "
                "'deprecated' but the live MapServer layer is what NJDEP's own "
                "current DCAT catalog names -- treated as a stale item label.",
    }


def check_p6_claims(force: bool) -> dict:
    meta_probe = lib.check_url(lib.P6_CLAIMS_METADATA_URL,
                               params={"$filter": "name eq 'FimaNfipClaims'"})
    data_probe = lib.check_url(lib.P6_CLAIMS_QUERY_URL,
                               params={"$filter": "state eq 'NJ'", "$top": 2})
    return {
        "source": "P6 OpenFEMA NFIP Redacted Claims", "ok": False,
        "metadata_endpoint_ok": meta_probe["ok"], "data_endpoint_probe": data_probe,
        "note": "CONFIRMED UNAVAILABLE 2026-08-02: metadata endpoint works (dataset "
                "exists, lastRefresh 2025-12-19) but the live query endpoint returns "
                "HTTP 503. Consistent with public reporting of a suspension of "
                "FimaNfipClaims/FimaNfipPolicies access. Bulk CSV/parquet export URLs "
                "from the metadata also 403 (Akamai) to a plain request. §5.3's "
                "documented fallback applies: redistribute C_loss's 0.25 weight "
                "proportionally to C_cur/C_fut (effective ~0.643/0.357), record the "
                "variant in meta.json. Re-check before Phase 4, not assumed fixed.",
    }


def check_p7_tiger(force: bool) -> dict:
    meta = lib.get_json(lib.TIGERWEB_STATE_COUNTY, params={"f": "json"}, force=force)
    ok = len(meta.get("layers", [])) > 0
    return {
        "source": "P7 TIGERweb State_County", "ok": ok, "url": lib.TIGERWEB_STATE_COUNTY,
        "n_layers": len(meta.get("layers", [])),
        "note": "Same service family already proven working in the FloodOps projects.",
    }


def check_p8_geocoder(force: bool) -> dict:
    meta = lib.check_url(lib.P8_GEOCODER_URL, params={"f": "json"})
    return {
        "source": "P8 NJ statewide geocoder", "ok": meta["ok"], "url": lib.P8_GEOCODER_URL,
        "note": "The Addr_NJ_cascade service name some pages advertise 404s -- "
                "NJ_Geocode is the real, live one, confirmed 2026-08-02.",
    }


def check_p9_basemap(force: bool) -> dict:
    probe = lib.check_url(lib.P9_BASEMAP_STYLE)
    return {"source": "P9 OpenFreeMap basemap", "ok": probe["ok"], "url": lib.P9_BASEMAP_STYLE}


def check_tooling() -> dict:
    ogr2ogr = shutil.which("ogr2ogr")
    docker = shutil.which("docker")
    wsl = shutil.which("wsl")
    docker_ok = False
    if docker:
        try:
            r = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=10)
            docker_ok = r.returncode == 0
        except Exception:  # noqa: BLE001
            docker_ok = False
    return {
        "ogr2ogr_on_path": bool(ogr2ogr), "ogr2ogr_path": ogr2ogr,
        "docker_on_path": bool(docker), "docker_working": docker_ok,
        "wsl_on_path": bool(wsl),
        "tippecanoe_route": "docker" if docker_ok else ("wsl" if wsl else "NEEDS SETUP"),
        "note": "GDAL/ogr2ogr is a system dependency (§6.2), not pip-installable "
                "reliably on Windows -- install via conda-forge or OSGeo4W before "
                "Phase 1 if not already on PATH.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check-only", action="store_true",
                    help="Quick liveness pass without writing RECON.md/report (CI smoke test).")
    args = ap.parse_args()

    checks = [
        check_p1_parcels(args.force), check_p3_nfhl(args.force),
        check_p4_future_layers(args.force), check_p6_claims(args.force),
        check_p7_tiger(args.force), check_p8_geocoder(args.force),
        check_p9_basemap(args.force),
    ]
    tooling = check_tooling()

    for c in checks:
        status = "OK" if c["ok"] else "FAIL/UNAVAILABLE"
        print(f"[{status}] {c['source']}")
        if c.get("note"):
            print(f"    {c['note']}")
        if c.get("url"):
            lib.manifest_add(f"recon_{c['source'].split()[0]}", c["url"], None,
                             "public government/open data source (see RECON.md for full terms)",
                             extra={"ok_at_recon": c["ok"], "checked_utc": datetime.now(timezone.utc).isoformat()})

    print(f"\nTooling: ogr2ogr={'yes' if tooling['ogr2ogr_on_path'] else 'NO'}, "
          f"tippecanoe route={tooling['tippecanoe_route']}")

    if args.check_only:
        # P6 is a known, documented exception -- everything load-bearing for Phase 1
        # (P1, P7, P8) and the flood layers (P3, P4) must be reachable, but P6's
        # absence doesn't block the pipeline (§5.3's fallback exists precisely for
        # this), so it isn't part of the smoke-test's pass/fail gate.
        blocking = [c for c in checks if not c["ok"] and c["source"] != checks[3]["source"]]
        return 0 if not blocking else 2

    lib.PROCESSED.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks, "tooling": tooling,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# NJ Parcel Flood Risk Dashboard — Data Source Recon (RECON.md)",
        "",
        f"Generated: {report['generated_utc']} · auto-written by `pipeline/00_recon.py` (§4).",
        "",
        "## Data sources (P1-P9)",
        "",
        "| # | Source | Status | Detail |",
        "|---|---|---|---|",
    ]
    for c in checks:
        status = "✅" if c["ok"] else "⚠️ unavailable"
        detail = c.get("note", "")
        lines.append(f"| | {c['source']} | {status} | {detail} |")
    lines += [
        "",
        "P2 (raw MOD-IV enrichment) and P5 (flood design/profile context) are lower-"
        "priority per the guide (fallback/context-only) and were not deep-verified "
        "in this pass -- defer to Phase 1/2 when actually needed.",
        "",
        "## Local tooling",
        "",
        f"- `ogr2ogr` on PATH: {'yes, ' + str(tooling['ogr2ogr_path']) if tooling['ogr2ogr_on_path'] else '**NO — install via conda-forge or OSGeo4W before Phase 1**'}",
        f"- tippecanoe route: **{tooling['tippecanoe_route']}** "
        f"(docker working: {tooling['docker_working']}, wsl on PATH: {tooling['wsl_on_path']})",
        "",
    ]
    RECON_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_JSON.relative_to(lib.REPO)} and RECON.md")

    blocking = [c for c in checks if not c["ok"] and c is not checks[3]]
    return 0 if not blocking else 2


if __name__ == "__main__":
    sys.exit(main())
