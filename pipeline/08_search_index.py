#!/usr/bin/env python3
"""08 — Per-municipality search shards + full-row parquet (§7.1, guide-Phase 6).

- `search/{fips}/{mun}.json.gz`: address/block-lot/PIN -> PIN + centroid,
  lazy-loaded per selected muni (small, so the client never has to load a
  statewide search index).
- `parcels/{fips}/{mun}.parquet`: full scored rows per muni, for table
  drill-down + the stretch WASM explorer.

Same `{county FIPS}{mun_code suffix}` muni-key convention as Phase 5/06_aggregate.py
and Phase 6/07_tiles.py's boundaries -- `search/{fips}/{mun}...` is a nested
path per §7.1 (fips as directory, mun as filename), not a concatenated
filename, but the underlying key derivation is identical.

Centroid computed in the working CRS (EPSG:26918, meters, §4) then
reprojected back to WGS84 for output -- not computed directly in a geographic
CRS, even though the distortion would be negligible at parcel scale.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys

import nj_parcel_lib as lib  # imported first: sets PROJ env before any geo import

import geopandas as gpd
import pandas as pd

PARCEL_GEOMS = lib.PROCESSED / "parcel_geoms"
PARCEL_MASTER = lib.PROCESSED / "parcel_master"
PARCEL_SCORES = lib.PROCESSED / "parcel_scores"
SEARCH_DIR = lib.ARTIFACTS / "search"
PARCELS_DIR = lib.ARTIFACTS / "parcels"


def process_county(fips: str) -> dict:
    geoms_path = PARCEL_GEOMS / f"{fips}.gpkg"
    master_path = PARCEL_MASTER / f"{fips}.parquet"
    scores_path = PARCEL_SCORES / f"{fips}.parquet"
    if not (geoms_path.exists() and master_path.exists() and scores_path.exists()):
        return {"fips": fips, "skipped": True}

    geoms = gpd.read_file(geoms_path)
    master = pd.read_parquet(master_path, columns=[
        "pin", "mun_code", "block", "lot", "qual", "situs_address", "class_group",
        "prop_class", "land_val", "imprvt_val", "net_value", "area_acres", "exempt"])
    scores = pd.read_parquet(scores_path)

    n = len(geoms)
    if len(master) != n or len(scores) != n:
        raise ValueError(f"{fips}: row count mismatch (geoms={n}, master={len(master)}, scores={len(scores)})")
    if not (geoms["pin"].to_numpy() == master["pin"].to_numpy()).all():
        raise ValueError(f"{fips}: pin sequence mismatch, parcel_geoms vs parcel_master")
    if not (geoms["pin"].to_numpy() == scores["pin"].to_numpy()).all():
        raise ValueError(f"{fips}: pin sequence mismatch, parcel_geoms vs parcel_scores")

    centroids_utm = geoms.to_crs(lib.UTM18N).geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_utm, crs=lib.UTM18N).to_crs(lib.WGS84)
    lon = centroids_wgs84.x.to_numpy()
    lat = centroids_wgs84.y.to_numpy()

    full = pd.concat([master.reset_index(drop=True),
                       scores.drop(columns="pin").reset_index(drop=True)], axis=1)
    full["lon"] = lon
    full["lat"] = lat

    n_munis = 0
    n_records = 0
    for mun_code, grp in full.groupby("mun_code"):
        fips_mun = f"{fips}{mun_code[-2:]}"
        search_records = [
            {"pin": r["pin"], "block": r["block"], "lot": r["lot"], "qual": r["qual"],
             "address": r["situs_address"], "lon": round(r["lon"], 6), "lat": round(r["lat"], 6)}
            for _, r in grp.iterrows()
        ]
        search_dir = SEARCH_DIR / fips
        search_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(search_dir / f"{mun_code[-2:]}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(search_records, fh)

        parcels_dir = PARCELS_DIR / fips
        parcels_dir.mkdir(parents=True, exist_ok=True)
        grp.drop(columns=["mun_code"]).to_parquet(
            parcels_dir / f"{mun_code[-2:]}.parquet", index=False)

        n_munis += 1
        n_records += len(grp)

    return {"fips": fips, "n_parcels": n, "n_munis": n_munis, "n_records": n_records}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", help="Comma-separated county names, or omit for ALL.")
    args = ap.parse_args()

    if args.county:
        wanted = {c.strip().upper() for c in args.county.split(",")}
        fips_list = [lib.COUNTY_FIPS[c] for c in sorted(wanted) if c in lib.COUNTY_FIPS]
    else:
        fips_list = sorted(lib.COUNTY_FIPS.values())

    results = []
    for fips in fips_list:
        r = process_county(fips)
        results.append(r)
        if r.get("skipped"):
            print(f"  [SKIP] {fips}: required Phase 1/4b outputs not found")
        else:
            print(f"  {fips}: {r['n_parcels']} parcels -> {r['n_munis']} muni shard(s), "
                  f"{r['n_records']} records total")

    done = [r for r in results if not r.get("skipped")]
    if not done:
        print("No counties processed -- nothing to do.")
        return 1

    total_parcels = sum(r["n_parcels"] for r in done)
    total_munis = sum(r["n_munis"] for r in done)
    print(f"\n{len(done)}/{len(results)} counties processed, {total_parcels} parcels, "
          f"{total_munis} muni shard(s) written under search/ and parcels/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
