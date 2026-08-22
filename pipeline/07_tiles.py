#!/usr/bin/env python3
"""07 — GeoJSONL -> tippecanoe -> PMTiles (§7.1, guide-Phase 6).

Two tilesets:
- `tiles/parcels.pmtiles` (z9-16, minimal attrs: pin, band, class_group,
  current/future flags -- deliberately NOT the full parcel_scores schema,
  per §7.1's own "minimal attrs" instruction and the ≤4GB budget). Minzoom
  widened from the original 13 to 9 post-launch (PROGRESS.md 2026-08-13,
  "Parcel zoom-out fix") so the web app's Parcel detail-level toggle can
  zoom out to match Municipality's own floor while still showing real
  parcel geometry, not switching to the municipality choropleth underneath
  it -- `--drop-densest-as-needed` (already in use below) handles the
  much larger per-tile feature counts at the wider zoom range.
- `tiles/boundaries.pmtiles` (counties + municipalities, two named layers in
  one tileset, summary attrs from Phase 5's aggregates, for choropleths at
  z<13).

Tippecanoe route: Docker (`klokantech/tippecanoe`, v1.24.1) -- the guide's
other stated option (§6.2), WSL-native install, was tried first and blocked:
`apt-get` needs an interactive sudo password this session has no way to
supply. Documented here per §6.2's explicit "document the chosen route"
instruction.

**Real bug found and fixed while building the web app (guide-Phase 7), not
here at build time:** this tippecanoe image's binary has no actual PMTiles
output support -- `tippecanoe --help` only documents `--output=x.mbtiles`.
Handing it an `.pmtiles` filename doesn't error, it silently writes MBTiles
(SQLite) content to that path regardless of the extension -- confirmed live,
the file's own first bytes read "SQLite format 3", not PMTiles' "PMTi"
magic. Every `.pmtiles` file this project had produced before the web app
tried to actually read one this way was mislabeled MBTiles, not caught
because file-size/row-count checks don't inspect internal format. Fixed by
having tippecanoe output real `.mbtiles`, then converting with
`protomaps/go-pmtiles convert` (the format's own canonical converter) to
produce the genuine `.pmtiles` file; the mbtiles intermediate is discarded.

County-subdivision (municipality) boundaries come from a different TIGERweb
service than the one already used for counties/tracts (`Places_CouSub_
ConCity_SubMCD`, not `State_County`) -- verified live it returns 570 rows for
NJ, 5 of which are literal Census placeholders ("County subdivisions not
defined", unincorporated open water off 5 shore counties) excluded by
COUSUBCC. The remaining 565 are matched to this project's own 564 `mun_code`
values by a normalized (county, name) join; whatever doesn't match is logged,
not silently dropped or forced to match.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

import nj_parcel_lib as lib  # imported first: sets PROJ env before any geo import

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

PARCEL_GEOMS = lib.PROCESSED / "parcel_geoms"
PARCEL_SCORES = lib.PROCESSED / "parcel_scores"
PARCEL_MASTER = lib.PROCESSED / "parcel_master"
SUMMARIES_DIR = lib.ARTIFACTS / "summaries"
TILES_DIR = lib.ARTIFACTS / "tiles"
GEOJSONL_DIR = lib.RAW / "_geojsonl"  # scratch, gitignored (under data/raw/)

TIPPECANOE_IMAGE = "klokantech/tippecanoe"
PMTILES_IMAGE = "protomaps/go-pmtiles"  # the format's own canonical converter
PARCEL_MIN_ZOOM, PARCEL_MAX_ZOOM = 9, 16


def fetch_nj_counties(force: bool) -> gpd.GeoDataFrame:
    lid = 1  # confirmed Phase 2: min Counties layer id, 21/21 NJ counties
    gj = lib.get_json(f"{lib.TIGERWEB_STATE_COUNTY}/{lid}/query", params={
        "where": f"STATE='{lib.STATE_FIPS}'", "outFields": "NAME,GEOID", "outSR": lib.WGS84,
        "f": "geojson"}, force=force, timeout=60)
    rows = [{**f["properties"], "geometry": shape(f["geometry"])} for f in gj.get("features", [])]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)
    gdf["county_upper"] = gdf["NAME"].str.replace(" County", "", regex=False).str.upper()
    return gdf


def fetch_nj_cousub(force: bool) -> gpd.GeoDataFrame:
    gj = lib.get_json(f"{lib.TIGERWEB_COUSUB}/{lib.TIGERWEB_COUSUB_LAYER}/query", params={
        "where": f"STATE='{lib.STATE_FIPS}'", "outFields": "GEOID,NAME,COUSUBCC,COUNTY", "outSR": lib.WGS84,
        "f": "geojson"}, force=force, timeout=90)
    rows = [{**f["properties"], "geometry": shape(f["geometry"])} for f in gj.get("features", [])]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=lib.WGS84)
    return gdf[gdf["COUSUBCC"] != "Z9"].reset_index(drop=True)  # drop "not defined" placeholders


# Canonicalize the municipal-type word, DON'T strip it -- verified live this
# is load-bearing for NJ specifically: many towns have a Borough *and* a
# separately-incorporated Township (or City) sharing the same base name --
# Berlin Boro vs. Berlin Twp, Chatham Boro vs. Chatham Twp, Egg Harbor City
# vs. Egg Harbor Twp, 19 such pairs found live -- genuinely different
# municipalities, not duplicate records. An earlier version of this function
# stripped the type word entirely and silently collapsed 19 pairs of real,
# distinct towns onto the same key, inflating the muni count past 564 (the
# fan-out from the resulting many-to-many join was the tell).
_TYPE_CANON = {"TOWNSHIP": "TWP", "TWNSHP": "TWP", "TWSHP": "TWP", "TWP": "TWP", "TW": "TWP",
               "BOROUGH": "BORO", "BORO": "BORO", "BOR": "BORO",
               "CITY": "CITY", "TOWN": "TOWN", "VILLAGE": "VILLAGE"}
_CONNECTOR_WORDS = {"AND", "THE", "OF"}
# Common word abbreviations confirmed live in this project's own mun_name
# data (MOD-IV), applied to every word, not just the trailing type word --
# e.g. "NO HANOVER TWP", "SO HACKENSACK TWP", "MT LAUREL TWP" vs TIGER's full
# "North Hanover", "South Hackensack", "Mount Laurel". EAST/TROY/HILLS/POINT
# added closing an 11-of-564-muni boundary gap (E Rutherford, Parsippany
# Tr[oy] Hls, Pt[.] Pleasant Beach) -- each checked against the *full* live
# TIGER+MOD-IV dataset (564 munis, 565 TIGER rows), not just the case it was
# added for, since a general word rule can collide somewhere unintended (see
# next paragraph for the one that did).
#
# RIVER -> RIV was tried here too (for "Upper Saddle River"/"UPPER SADDLE
# RIV BORO") and reverted: it broke River Vale and River Edge, whose MOD-IV
# mun_name stores the town name as one concatenated word ("RIVERVALE",
# "RIVEREDGE") rather than "RIVER" + "VALE" -- TIGER's separate "River"
# token got abbreviated to "RIV" while MOD-IV's fused token didn't, turning
# two previously-matching pairs into mismatches. Upper Saddle River is
# handled as a specific override instead (below), which can't have this
# kind of unintended side effect on an unrelated place.
_WORD_CANON = {"MOUNT": "MT", "MT": "MT", "SOUTH": "SO", "SO": "SO",
               "NORTH": "NO", "HEIGHTS": "HGHTS", "HGHTS": "HGHTS",
               "EAST": "E", "E": "E",
               "TROY": "TR", "TR": "TR", "HILLS": "HLS", "HLS": "HLS",
               "POINT": "PT", "PT": "PT"}
# Remaining mismatches the general normalizer can't safely resolve, keyed on
# (county_name, normalized TIGER name) -> mun_code. Hand-verified against
# real rows, not a blanket fallback -- two different root causes, neither
# fixable by extending the tables above:
# - Caldwell / North Caldwell / Essex Fells: TIGER calls all three boroughs,
#   but this project's own mun_name genuinely ends in "TWP" for all three --
#   a real disagreement between the two sources about the type word itself,
#   not an abbreviation gap. NOT safe to fix by loosening the general
#   type-word rule -- that rule exists specifically to keep genuinely-
#   different Boro/Twp pairs apart (Berlin Boro vs. Berlin Twp, etc.).
# - City of Orange: word order differs ("City of Orange" vs "Orange City").
# - Lower Alloway(s) Creek: a real spelling difference between the sources
#   (TIGER "Alloways", MOD-IV "Alloway"), not an abbreviation.
# - Upper Saddle River: MOD-IV abbreviates "River" to "RIV" here, but a
#   general RIVER->RIV word rule breaks River Vale/River Edge elsewhere (see
#   _WORD_CANON's own comment) -- a one-off override is the safe fix.
_KNOWN_COUSUB_OVERRIDES: dict[tuple[str, str], str] = {
    ("ESSEX", "CALDWELLBORO"): "0703",
    ("ESSEX", "NOCALDWELLBORO"): "0715",
    ("ESSEX", "ESSEXFELLSBORO"): "0706",
    ("ESSEX", "CITYORANGETWP"): "0717",
    ("SALEM", "LOWERALLOWAYSCREEKTWP"): "1705",
    ("BERGEN", "UPPERSADDLERIVERBORO"): "0263",
}


def _normalize_name(name: str) -> str:
    """Collapse formatting differences (hyphen/space/none, "and" insertion,
    TIGER's full words vs. MOD-IV's abbreviations) to a comparable key, while
    preserving the type-word distinction (see above). A redundant *doubled*
    type suffix (TIGER's "Ventnor City city") is deduped -- but only when the
    two trailing words are the same canonical type, never a blanket strip."""
    words = [w for w in re.findall(r"[A-Z0-9]+", name.upper()) if w not in _CONNECTOR_WORDS]
    canon = [_TYPE_CANON.get(w, _WORD_CANON.get(w, w)) for w in words]
    while len(canon) >= 2 and canon[-1] == canon[-2] and canon[-1] in _TYPE_CANON.values():
        canon.pop()
    return "".join(canon)


def match_cousub_to_mun_code(cousub: gpd.GeoDataFrame, mun_lookup: pd.DataFrame) -> gpd.GeoDataFrame:
    """Join TIGER's county-subdivision rows to this project's own mun_code
    via a normalized (county, name) match -- the two schemes don't share a
    key otherwise. Rows that don't match are logged and dropped (not forced),
    since forcing a wrong match would corrupt the choropleth attrs."""
    fips_to_county = {v: k for k, v in lib.COUNTY_FIPS.items()}
    cousub = cousub.copy()
    cousub["county_name"] = cousub["COUNTY"].map(fips_to_county)
    cousub["name_norm"] = cousub["NAME"].apply(_normalize_name)

    mine = mun_lookup.copy()
    mine["name_norm"] = mine["mun_name"].apply(_normalize_name)

    merged = cousub.merge(mine[["county", "mun_code", "name_norm"]],
                           left_on=["county_name", "name_norm"], right_on=["county", "name_norm"],
                           how="left")

    # Rescue the known cases the general normalizer can't safely resolve
    # (see _KNOWN_COUSUB_OVERRIDES) before logging what's still unmatched.
    still_missing = merged["mun_code"].isna()
    for idx in merged.index[still_missing]:
        override = _KNOWN_COUSUB_OVERRIDES.get(
            (merged.at[idx, "county_name"], merged.at[idx, "name_norm"]))
        if override:
            merged.at[idx, "mun_code"] = override

    unmatched = merged[merged["mun_code"].isna()]
    if len(unmatched):
        print(f"  [WARN] {len(unmatched)} TIGER county-subdivision(s) did not match a mun_code "
              f"(logged, dropped from boundaries.pmtiles, not forced):")
        for _, r in unmatched.iterrows():
            print(f"    - {r['NAME']!r} ({r['county_name']})")
    matched = merged[merged["mun_code"].notna()].reset_index(drop=True)
    return gpd.GeoDataFrame(matched, geometry="geometry", crs=cousub.crs)


def build_mun_lookup() -> pd.DataFrame:
    frames = []
    for f in sorted(PARCEL_MASTER.glob("*.parquet")):
        frames.append(pd.read_parquet(f, columns=["county", "mun_code", "mun_name"]))
    df = pd.concat(frames, ignore_index=True)
    named = df[df["mun_name"] != ""]
    lookup = named.groupby("mun_code").agg(
        mun_name=("mun_name", lambda s: s.value_counts().idxmax()),
        county=("county", "first")).reset_index()
    return lookup


def load_summary(path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def summary_attrs(payload: dict) -> dict:
    """Flatten one geography's summary JSON into flat choropleth attrs --
    either lens, ALL classes (the same broad view the ranked-muni table
    uses), plus current/future for lens toggling on the map."""
    out = {}
    for lens in ("current", "future", "either"):
        cell = payload.get(lens, {}).get("ALL")
        if cell:
            out[f"{lens}_pct_at_risk"] = cell["pct_at_risk"]
            out[f"{lens}_value_exposure_pct"] = cell["value_exposure_pct"]
    return out


def write_boundaries_geojsonl(force: bool) -> tuple[object, object]:
    counties = fetch_nj_counties(force)
    mun_lookup = build_mun_lookup()
    cousub = fetch_nj_cousub(force)
    munis = match_cousub_to_mun_code(cousub, mun_lookup)

    GEOJSONL_DIR.mkdir(parents=True, exist_ok=True)
    county_path = GEOJSONL_DIR / "boundaries_counties.geojsonl"
    muni_path = GEOJSONL_DIR / "boundaries_munis.geojsonl"

    with open(county_path, "w", encoding="utf-8") as fh:
        for _, row in counties.iterrows():
            fips = lib.COUNTY_FIPS.get(row["county_upper"])
            attrs = {"fips": fips, "county_name": row["county_upper"]}
            attrs.update(summary_attrs(load_summary(SUMMARIES_DIR / "county" / f"{fips}.json")))
            fh.write(json.dumps({"type": "Feature", "properties": attrs,
                                  "geometry": row.geometry.__geo_interface__}) + "\n")

    with open(muni_path, "w", encoding="utf-8") as fh:
        for _, row in munis.iterrows():
            fips = lib.COUNTY_FIPS.get(row["county_name"])
            fips_mun = f"{fips}{row['mun_code'][-2:]}"
            attrs = {"fips_mun": fips_mun, "mun_name": row["NAME"], "county_name": row["county_name"]}
            attrs.update(summary_attrs(load_summary(SUMMARIES_DIR / "muni" / f"{fips_mun}.json")))
            fh.write(json.dumps({"type": "Feature", "properties": attrs,
                                  "geometry": row.geometry.__geo_interface__}) + "\n")
    return county_path, muni_path


def write_parcels_geojsonl(fips_list: list[str]) -> object:
    # Attrs are rich enough for a full parcel detail panel (§7.2: "attrs,
    # flags, score + drivers §5.3") straight from a map click -- no second
    # fetch to parcels/{fips}/{mun}.parquet needed for the base experience,
    # so the map doesn't depend on a WASM parquet reader for its core
    # interaction (§7.2: "map interactions degrade gracefully without
    # WASM" -- read as "the base app shouldn't need WASM at all", DuckDB-WASM
    # is the explicit §7.4 *stretch* explorer, not this). First version of
    # this function only carried pin/band/class_group/cur/fut/fut_cov --
    # found the gap building the web app itself (guide-Phase 7), fixed here
    # rather than shipping a detail panel missing its own score/drivers.
    GEOJSONL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GEOJSONL_DIR / "parcels.geojsonl"
    n_written = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for fips in fips_list:
            geoms_path = PARCEL_GEOMS / f"{fips}.gpkg"
            scores_path = PARCEL_SCORES / f"{fips}.parquet"
            if not (geoms_path.exists() and scores_path.exists()):
                print(f"  [SKIP] {fips}: parcel_geoms/parcel_scores not found")
                continue
            geoms = gpd.read_file(geoms_path)
            scores = pd.read_parquet(scores_path, columns=[
                "pin", "band", "score", "sfha_pct", "mod_risk_pct", "fut_pct", "fut_coverage",
                "C_cur", "C_fut", "C_loss"])
            if len(geoms) != len(scores) or not (geoms["pin"].to_numpy() == scores["pin"].to_numpy()).all():
                raise ValueError(f"{fips}: pin sequence mismatch, parcel_geoms vs parcel_scores")
            master = pd.read_parquet(PARCEL_MASTER / f"{fips}.parquet", columns=[
                "pin", "class_group", "prop_class", "situs_address", "block", "lot", "qual",
                "net_value", "county", "mun_name"])
            if not (geoms["pin"].to_numpy() == master["pin"].to_numpy()).all():
                raise ValueError(f"{fips}: pin sequence mismatch, parcel_geoms vs parcel_master")

            current_flag = (scores["sfha_pct"] > 0).to_numpy()
            future_flag = (scores["fut_pct"].fillna(0) > 0).to_numpy()
            fut_coverage = scores["fut_coverage"].to_numpy()
            net_value = master["net_value"].to_numpy()
            fut_pct = scores["fut_pct"].to_numpy()
            for i in range(len(geoms)):
                attrs = {
                    "pin": geoms["pin"].iat[i], "band": scores["band"].iat[i],
                    "score": int(scores["score"].iat[i]),
                    "class_group": master["class_group"].iat[i],
                    "prop_class": master["prop_class"].iat[i],
                    "cur": bool(current_flag[i]),
                    "fut": bool(future_flag[i]) if fut_coverage[i] else None,
                    "fut_cov": bool(fut_coverage[i]),
                    "sfha_pct": round(float(scores["sfha_pct"].iat[i]), 4),
                    "mod_risk_pct": round(float(scores["mod_risk_pct"].iat[i]), 4),
                    "fut_pct": round(float(fut_pct[i]), 4) if fut_coverage[i] else None,
                    "c_cur": round(float(scores["C_cur"].iat[i]), 4),
                    "c_fut": round(float(scores["C_fut"].iat[i]), 4),
                    "c_loss": round(float(scores["C_loss"].iat[i]), 4),
                    "situs_address": master["situs_address"].iat[i],
                    "block": master["block"].iat[i], "lot": master["lot"].iat[i],
                    "qual": master["qual"].iat[i],
                    "net_value": float(net_value[i]) if pd.notna(net_value[i]) else None,
                    "county": master["county"].iat[i], "mun_name": master["mun_name"].iat[i],
                }
                fh.write(json.dumps({"type": "Feature", "properties": attrs,
                                      "geometry": geoms.geometry.iat[i].__geo_interface__}) + "\n")
                n_written += 1
            print(f"  {fips}: {len(geoms)} parcels written to GeoJSONL")
    print(f"  {n_written} total parcels written")
    return out_path


def run_tippecanoe(args: list[str]) -> None:
    """Runs tippecanoe inside the klokantech/tippecanoe Docker image, with
    GEOJSONL_DIR and TILES_DIR bind-mounted so paths pass straight through."""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{GEOJSONL_DIR}:/geojsonl",
        "-v", f"{TILES_DIR}:/tiles",
        "--entrypoint", "tippecanoe",
        TIPPECANOE_IMAGE,
    ] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"tippecanoe failed (exit {result.returncode}):\n{result.stderr}")
    print(result.stderr)  # tippecanoe logs progress to stderr even on success


def mbtiles_to_pmtiles(mbtiles_name: str, pmtiles_name: str) -> None:
    """tippecanoe (this image) only actually writes MBTiles, whatever
    extension you give it -- see module docstring. Converts for real with
    go-pmtiles, then removes the mbtiles intermediate."""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{TILES_DIR}:/tiles",
        PMTILES_IMAGE, "convert",
        f"/tiles/{mbtiles_name}", f"/tiles/{pmtiles_name}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"go-pmtiles convert failed (exit {result.returncode}):\n{result.stderr}")
    print(result.stderr)  # go-pmtiles logs its progress bar to stderr too
    (TILES_DIR / mbtiles_name).unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-fetch boundary sources even if cached.")
    ap.add_argument("--county", help="Comma-separated county names for parcels.pmtiles, or omit for ALL.")
    ap.add_argument("--skip-boundaries", action="store_true")
    ap.add_argument("--skip-parcels", action="store_true")
    args = ap.parse_args()

    TILES_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_boundaries:
        print("Building boundaries.pmtiles...")
        county_path, muni_path = write_boundaries_geojsonl(args.force)
        run_tippecanoe([
            "-o", "/tiles/boundaries.mbtiles", "--force",
            "-L", f"counties:/geojsonl/{county_path.name}",
            "-L", f"munis:/geojsonl/{muni_path.name}",
            "-Z0", "-z12",
        ])
        mbtiles_to_pmtiles("boundaries.mbtiles", "boundaries.pmtiles")
        print(f"  Wrote {TILES_DIR / 'boundaries.pmtiles'}")

    if not args.skip_parcels:
        print("Building parcels.pmtiles...")
        if args.county:
            wanted = {c.strip().upper() for c in args.county.split(",")}
            fips_list = [lib.COUNTY_FIPS[c] for c in sorted(wanted) if c in lib.COUNTY_FIPS]
        else:
            fips_list = sorted(lib.COUNTY_FIPS.values())
        parcels_path = write_parcels_geojsonl(fips_list)
        run_tippecanoe([
            "-o", "/tiles/parcels.mbtiles", "--force",
            "-l", "parcels",
            "-Z", str(PARCEL_MIN_ZOOM), "-z", str(PARCEL_MAX_ZOOM),
            "--drop-densest-as-needed",
            f"/geojsonl/{parcels_path.name}",
        ])
        mbtiles_to_pmtiles("parcels.mbtiles", "parcels.pmtiles")
        out_path = TILES_DIR / "parcels.pmtiles"
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"  Wrote {out_path} ({size_mb:.1f} MB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
