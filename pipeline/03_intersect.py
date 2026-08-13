#!/usr/bin/env python3
"""03 — Parcel-level flood overlap metrics (§5.2). The heaviest pipeline stage
(guide budget: <=12h statewide, county-checkpointed) and the first stage where
§12.1's geometry/consistency QA gates actually apply.

Per county: parcel_master + parcel_geoms (Phase 1) intersected against NFHL
(current) and CAFE SLR5 (future, where covered) flood layers (Phase 2), all
reprojected to the working CRS (EPSG:26918, meters, §4) before any area math.

Design decisions (empirically verified against real fetched data, not assumed
from field names -- see PROGRESS.md 2026-08-12):
- `sfha_pct` uses NFHL's own SFHA_TF=='T' flag directly, not a hand-rolled
  FLD_ZONE-prefix match. Verified live against Atlantic + Essex NFHL data that
  SFHA_TF=='T' <=> FLD_ZONE in {A,AE,AH,AO,VE} exactly (and SFHA_TF=='F' <=>
  FLD_ZONE in {X, OPEN WATER}) -- trusting FEMA's own classification is both
  simpler and more robust than re-deriving it from a code list §4 only gives
  as an illustrative pattern ("A*/V*"), not an exhaustive one.
- `mod_risk_pct` (shaded X / "0.2% annual chance", §4/§5.2) uses
  ZONE_SUBTY == MOD_RISK_SUBTY directly (exact string confirmed live), not
  FLD_ZONE=='X' alone, which also includes unshaded/minimal-risk X.
- `fut_pct` is a simple union overlap against the *entire* P4/CAFE layer for
  covered counties. Confirmed live the layer mixes a majority "SLR 5FT" label
  with a minority of retained FEMA zone labels (AE/VE/AO/"A - NO BFE") --
  §5.2 asks for total future-risk overlap here, no sub-breakdown by zone type,
  so nothing is filtered out of this layer.
- Overlap is computed via gpd.overlay(..., how="intersection") + groupby-sum,
  keyed by a synthetic per-row id, *not* 'pin' -- PINs are not guaranteed
  unique within a county (§12.1 uniqueness gate; Phase 1 found 742 statewide
  conflicting-duplicate PINs, kept not merged), so grouping by 'pin' would
  wrongly combine overlap area across two distinct parcels that happen to
  share a PIN.
- This sum-then-clamp approach is correct as long as same-layer zone polygons
  don't overlap each other. §12.1's own "overlap fractions in [0,1]" gate is
  the named defensive backstop for that assumption, not just a formatting
  nicety -- raw overlap >100% of a parcel's own area is clamped to 1.0 *and*
  counted (logged, not silently allowed or silently hidden).
- Sliver rule (§5.2): an overlap is zeroed out (pct=0, flag=False) if EITHER
  it's < 1% of the parcel's own area OR < 10 m^2 in absolute terms -- "either"
  because a small *fraction* of a huge parcel and a small *absolute* overlap
  on a tiny parcel are both meant to be caught, by two different tests.
- `fut_pct`/`fut_flag` are null (not zero/False) for the 6 non-P4-covered
  counties -- `fut_coverage=False` is the field the UI must check first
  (§5.2: "future data n/a here", never "no future risk"); storing False here
  too would make that mistake easy to make by accident downstream.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import nj_parcel_lib as lib  # imported first: sets PROJ env before geopandas init

import geopandas as gpd
import numpy as np
import pandas as pd

PARCEL_MASTER = lib.PROCESSED / "parcel_master"
PARCEL_GEOMS = lib.PROCESSED / "parcel_geoms"
FLOOD_DIR = lib.PROCESSED / "flood_layers"
OUT_DIR = lib.PROCESSED / "parcel_flood"
SUMMARY_REPORT = lib.PROCESSED / "intersect_report.json"
SUMMARY_MD = lib.REPO / "INTERSECT_SUMMARY.md"

SLIVER_PCT = 0.01       # §5.2: overlaps under 1% of parcel area are dropped
SLIVER_AREA_M2 = 10.0   # §5.2: ... or under 10 m^2 in absolute terms
MOD_RISK_SUBTY = "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"  # verified live, §4/§5.2 "shaded X"

SIMPLIFY_TOLERANCE_M = 1.0  # applied to flood-zone layers only, never to parcels.
# Confirmed live (Salem County): NFHL/CAFE polygons following detailed shoreline
# contours are extraordinarily vertex-dense -- Salem's SFHA layer alone (1,478
# features) carries 4,045,728 vertices, ~2,738/polygon. Every geometric op
# (overlay, sjoin's "intersects" predicate, even a plain union_all dissolve)
# was many tens of seconds to minutes on this data regardless of which
# algorithm was used, confirming vertex density -- not algorithm choice -- was
# the actual cost driver. A 1m simplify cuts that to 467,558 vertices (-88%)
# and measured 4.6x faster overlay() on an identical parcel subset, while
# shifting total intersection area by 0.004% (287 m^2 out of 7,013,629 m^2) --
# two orders of magnitude below the sliver thresholds above, and well within
# the inherent modeling uncertainty of a FEMA/NJDEP flood-zone boundary in the
# first place (these aren't surveyed property lines). Without this, the
# statewide run's naive extrapolated cost was ~9-10h; needed real margin
# under the guide's 12h budget (§6.3), not to just barely fit it.

FIPS_TO_COUNTY = {v: k for k, v in lib.COUNTY_FIPS.items()}


def _overlap_pct(parcels_utm: gpd.GeoDataFrame, zones_utm: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (pct, overlap_area_m2, n_clamped) arrays aligned to `parcels_utm`'s
    row order (both already in a projected meters CRS). Keyed internally by a
    synthetic _row_id, not 'pin' -- see module docstring."""
    n = len(parcels_utm)
    parcel_area = parcels_utm.geometry.area.to_numpy()
    overlap_area = np.zeros(n)

    if len(zones_utm):
        left = gpd.GeoDataFrame(
            {"_row_id": np.arange(n), "geometry": parcels_utm.geometry.to_numpy()},
            geometry="geometry", crs=parcels_utm.crs)
        ov = gpd.overlay(left, zones_utm[["geometry"]], how="intersection", keep_geom_type=True)
        if len(ov):
            ov["_area"] = ov.geometry.area
            summed = ov.groupby("_row_id")["_area"].sum()
            overlap_area[summed.index.to_numpy()] = summed.to_numpy()

    raw_pct = np.divide(overlap_area, parcel_area, out=np.zeros(n), where=parcel_area > 0)
    n_clamped = int((raw_pct > 1.0 + 1e-9).sum())
    pct = np.clip(raw_pct, 0.0, 1.0)

    sliver_mask = (pct < SLIVER_PCT) | (overlap_area < SLIVER_AREA_M2)
    pct = np.where(sliver_mask, 0.0, pct)
    return pct, overlap_area, n_clamped


def process_county(fips: str, force: bool) -> dict:
    county_upper = FIPS_TO_COUNTY.get(fips, fips)
    out_path = OUT_DIR / f"{fips}.parquet"
    if out_path.exists() and not force:
        return {"county": county_upper, "fips": fips, "skipped_cached": True}

    master_path = PARCEL_MASTER / f"{fips}.parquet"
    geoms_path = PARCEL_GEOMS / f"{fips}.gpkg"
    if not master_path.exists() or not geoms_path.exists():
        return {"county": county_upper, "fips": fips, "skipped_missing_phase1": True}

    geoms = gpd.read_file(geoms_path)  # pin, geometry -- WGS84, from Phase 1

    # §12.1 geometry gate, re-verified here rather than trusted from Phase 1's
    # own repair (this is a fresh load in a new stage, not the same in-memory
    # object) -- should already be clean; repaired again defensively if not.
    n_invalid_before = int((~geoms.geometry.is_valid).sum())
    if n_invalid_before:
        geoms["geometry"] = geoms.geometry.buffer(0)
    n_empty = int(geoms.geometry.is_empty.sum())

    geoms_utm = geoms.to_crs(lib.UTM18N)
    n_zero_area = int((geoms_utm.geometry.area <= 0).sum())

    nfhl_path = FLOOD_DIR / "nfhl" / f"{fips}.gpkg"
    if nfhl_path.exists():
        nfhl = gpd.read_file(nfhl_path).to_crs(lib.UTM18N)
        nfhl["geometry"] = nfhl.geometry.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
    else:
        nfhl = gpd.GeoDataFrame({"SFHA_TF": [], "ZONE_SUBTY": []}, geometry=[], crs=lib.UTM18N)
    sfha_zones = nfhl[nfhl["SFHA_TF"] == "T"]
    mod_zones = nfhl[nfhl["ZONE_SUBTY"] == MOD_RISK_SUBTY]

    sfha_pct, _, n_clamp_sfha = _overlap_pct(geoms_utm, sfha_zones)
    mod_pct, _, n_clamp_mod = _overlap_pct(geoms_utm, mod_zones)

    fut_coverage = county_upper in lib.P4_COASTAL_COUNTIES
    n_clamp_fut = 0
    if fut_coverage:
        cafe_path = FLOOD_DIR / "cafe_slr5" / f"{fips}.gpkg"
        if cafe_path.exists():
            cafe = gpd.read_file(cafe_path).to_crs(lib.UTM18N)
            cafe["geometry"] = cafe.geometry.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
        else:
            cafe = gpd.GeoDataFrame(geometry=[], crs=lib.UTM18N)
        fut_pct, _, n_clamp_fut = _overlap_pct(geoms_utm, cafe)
        fut_pct_col = fut_pct
        fut_flag_col = pd.array(fut_pct > 0, dtype="boolean")
    else:
        fut_pct_col = np.full(len(geoms_utm), np.nan)
        fut_flag_col = pd.array([pd.NA] * len(geoms_utm), dtype="boolean")

    out = pd.DataFrame({
        "pin": geoms["pin"].to_numpy(),
        "sfha_pct": sfha_pct, "sfha_flag": sfha_pct > 0,
        "mod_risk_pct": mod_pct, "mod_risk_flag": mod_pct > 0,
        "fut_coverage": fut_coverage,
        "fut_pct": fut_pct_col, "fut_flag": fut_flag_col,
    })
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    # §12.1 consistency gate, checked here rather than deferred to 09_validate.py
    # entirely -- flags are derived directly from the stored pct (`sfha_pct > 0`,
    # not a separately-computed boolean), so flag<=>overlap holds by
    # construction; the only thing worth actively checking is the [0,1] bound.
    assert out["sfha_pct"].between(0, 1).all()
    assert out["mod_risk_pct"].between(0, 1).all()
    assert out.loc[out["fut_coverage"], "fut_pct"].between(0, 1).all()

    return {
        "county": county_upper, "fips": fips, "n_parcels": len(out),
        "n_invalid_repaired": n_invalid_before, "n_empty_geom": n_empty, "n_zero_area": n_zero_area,
        "n_sfha": int(out["sfha_flag"].sum()), "n_mod_risk": int(out["mod_risk_flag"].sum()),
        "fut_coverage": fut_coverage,
        "n_fut_risk": int(out["fut_flag"].sum()) if fut_coverage else None,
        "n_clamped": {"sfha": n_clamp_sfha, "mod_risk": n_clamp_mod, "fut": n_clamp_fut},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--county", help="Comma-separated county names, or omit for ALL.")
    args = ap.parse_args()

    if args.county:
        wanted = {c.strip().upper() for c in args.county.split(",")}
        fips_list = [lib.COUNTY_FIPS[c] for c in sorted(wanted) if c in lib.COUNTY_FIPS]
    else:
        fips_list = sorted(lib.COUNTY_FIPS.values())

    results = []
    for fips in fips_list:
        county_upper = FIPS_TO_COUNTY.get(fips, fips)
        print(f"\n--- {county_upper} ({fips}) ---")
        t0 = time.time()
        r = process_county(fips, args.force)
        dt = time.time() - t0
        results.append(r)
        if r.get("skipped_cached"):
            print("  [cached] already done, use --force to redo")
        elif r.get("skipped_missing_phase1"):
            print("  [SKIP] parcel_master/parcel_geoms not found for this county")
        else:
            print(f"  {r['n_parcels']} parcels in {dt:.1f}s -- SFHA {r['n_sfha']}, "
                  f"moderate {r['n_mod_risk']}, future "
                  f"{r['n_fut_risk'] if r['fut_coverage'] else 'n/a (no P4 coverage)'}")
            if r["n_invalid_repaired"] or r["n_empty_geom"] or r["n_zero_area"]:
                print(f"  [WARN] geometry issues found at Phase 3 load time: "
                      f"{r['n_invalid_repaired']} invalid (repaired), "
                      f"{r['n_empty_geom']} empty, {r['n_zero_area']} zero-area")
            total_clamped = sum(r["n_clamped"].values())
            if total_clamped:
                print(f"  [WARN] {total_clamped} overlap-fraction clamp(s) (raw >100%, "
                      f"likely overlapping source zone polygons): {r['n_clamped']}")

    lib.PROCESSED.mkdir(parents=True, exist_ok=True)
    SUMMARY_REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    done = [r for r in results if not r.get("skipped_missing_phase1")]
    lines = [
        "# NJ Parcel Flood Risk Dashboard — Parcel/Flood Intersection Summary",
        "",
        "Auto-written by `pipeline/03_intersect.py` (§11 Phase 3 exit criterion: "
        "all counties complete, sliver rule applied, §12.1 geometry gates pass).",
        "",
        "## Per-county summary",
        "",
        "| County | FIPS | Parcels | SFHA | Moderate (shaded X) | Future coverage | Future at-risk |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(done, key=lambda r: r["county"]):
        if r.get("skipped_cached"):
            lines.append(f"| {r['county']} | {r['fips']} | (cached, rerun with --force for fresh stats) | | | | |")
            continue
        fut_cell = str(r["n_fut_risk"]) if r["fut_coverage"] else "n/a"
        lines.append(f"| {r['county']} | {r['fips']} | {r['n_parcels']} | {r['n_sfha']} | "
                     f"{r['n_mod_risk']} | {'✅' if r['fut_coverage'] else '❌ no data'} | {fut_cell} |")
    missing = [r for r in results if r.get("skipped_missing_phase1")]
    lines += ["", f"**{len(done)}/{len(results)} counties processed.**", ""]
    if missing:
        lines.append(f"**[WARN] {len(missing)} county(s) skipped -- Phase 1 input not found:** " +
                     ", ".join(r["county"] for r in missing))
        lines.append("")
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {SUMMARY_REPORT.relative_to(lib.REPO)} and INTERSECT_SUMMARY.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
