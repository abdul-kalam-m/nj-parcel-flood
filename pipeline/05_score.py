#!/usr/bin/env python3
"""05 — Composite flood risk score (§5.3): assembles C_cur/C_fut/C_loss from
Phases 1/3/4's outputs into a 0-100 score + band per parcel. Pure computation,
no network -- everything it needs already exists on disk.

§12.1 gate 4 ("score reproducible from stored components") and the guide's own
"drivers" UI requirement ("must show all three component values and the
inputs behind them") both mean this script's output has to carry more than
just the final score: the raw Phase 3/4 inputs, the derived C_cur/C_fut/C_loss
components, and a flag for when the weight-redistribution fallback applied --
not just a single number.

Row alignment: parcel_master (Phase 1), parcel_flood (Phase 3), and
parcel_claims (Phase 4) are combined by *row position*, not a 'pin' join --
PINs aren't guaranteed unique within a county (§12.1 uniqueness gate; Phase 1
found 742 statewide conflicting-duplicate PINs, kept not merged), and all
three files are independently derived from the same parcel_geoms row order by
three separate scripts, so position alignment is correct today but not
self-evidently permanent. Verified explicitly below (exact pin-sequence
equality asserted per county) rather than trusted silently -- a future
refactor that reorders one script's output would fail loudly here instead of
silently fusing the wrong rows together.
"""
from __future__ import annotations

import argparse
import sys

import nj_parcel_lib as lib  # imported first: sets PROJ env before any geo import

import numpy as np
import pandas as pd

PARCEL_MASTER = lib.PROCESSED / "parcel_master"
PARCEL_FLOOD = lib.PROCESSED / "parcel_flood"
PARCEL_CLAIMS = lib.PROCESSED / "parcel_claims"
SCORE_OUT_DIR = lib.PROCESSED / "parcel_scores"
SCORE_SUMMARY_MD = lib.REPO / "SCORE_SUMMARY.md"

# §5.3, LOCKED (§13.3: "Never change without owner approval" lists "Score
# formula, weights, floors, bands").
W_CUR, W_FUT, W_LOSS = 0.45, 0.30, 0.25
PRESENCE_FLOOR = 0.3
MOD_RISK_WEIGHT = 0.15
FUT_FALLBACK_MULT = 0.5
# Redistributed weights when C_loss is unavailable for a row: §5.3 says
# "redistribute its weight proportionally to the other two" -- proportional
# to their existing 0.45:0.30 ratio, i.e. renormalizing them to sum to 1:
# 0.45/(0.45+0.30)=0.60, 0.30/(0.45+0.30)=0.40. (Not the ~0.643/0.357 figure
# noted in this project's very early Phase 0 record -- re-derived here from
# the guide's literal text and it doesn't reconcile under any reading of
# "proportional to the other two"; treating that early figure as a stale
# error, not a second valid interpretation, since 0.60+0.40=1.0 exactly and
# 0.643+0.357=1.0 only by coincidence of rounding, not by construction.)
W_CUR_REDIST = W_CUR / (W_CUR + W_FUT)
W_FUT_REDIST = W_FUT / (W_CUR + W_FUT)

BAND_BINS = [-1, 0, 24, 49, 74, 100]
BAND_LABELS = ["none", "low", "moderate", "high", "severe"]


def compute_c_cur(sfha_pct: np.ndarray, sfha_flag: np.ndarray, mod_risk_pct: np.ndarray) -> np.ndarray:
    """§5.3: C_cur = max(sfha_pct, 0.3*has_sfha) + 0.15*mod_risk_pct, capped at 1."""
    floor = np.where(sfha_flag, PRESENCE_FLOOR, 0.0)
    raw = np.maximum(sfha_pct, floor) + MOD_RISK_WEIGHT * mod_risk_pct
    return np.clip(raw, 0.0, 1.0)


def compute_c_fut(c_cur: np.ndarray, fut_coverage: np.ndarray, fut_pct: np.ndarray) -> np.ndarray:
    """§5.3: where covered, C_fut = max(fut_pct, 0.3*has_fut) capped at 1 --
    has_fut re-derived as fut_pct>0 (matches Phase 3's own fut_flag
    definition exactly, already §12.1-verified consistent, so no need to
    carry the nullable fut_flag column through here). Where fut_coverage is
    false, C_fut = C_cur*0.5 (the documented fallback; the "future estimated
    from current" driver-panel message is a later/UI-phase concern, not
    this script's -- fut_coverage is carried through in the output for
    whichever phase renders that)."""
    fut_pct_filled = np.nan_to_num(fut_pct, nan=0.0)
    has_fut = fut_pct_filled > 0
    floor = np.where(has_fut, PRESENCE_FLOOR, 0.0)
    covered_val = np.clip(np.maximum(fut_pct_filled, floor), 0.0, 1.0)
    fallback_val = c_cur * FUT_FALLBACK_MULT
    return np.where(fut_coverage, covered_val, fallback_val)


def compute_score(c_cur: np.ndarray, c_fut: np.ndarray, tract_loss_pctile: np.ndarray):
    """§5.3: score = round(100*(0.45*C_cur + 0.30*C_fut + 0.25*C_loss)).
    Returns (score:int array, C_loss:float array [always defined, never NaN],
    loss_redistributed:bool array). C_loss is stored as 0.0 (not NaN) for
    rows where the tract percentile is unavailable, precisely so the §12.1
    recompute check (`score == round(100*(w_cur*C_cur+w_fut*C_fut+w_loss*
    C_loss))`) always reproduces the stored score exactly -- with w_loss=0
    in the redistributed case, 0*NaN would itself be NaN under IEEE float
    rules, silently breaking that exact recompute-check gate; 0*0.0=0.0
    does not."""
    loss_available = ~pd.isna(tract_loss_pctile)
    c_loss = np.nan_to_num(tract_loss_pctile, nan=0.0)
    w_cur = np.where(loss_available, W_CUR, W_CUR_REDIST)
    w_fut = np.where(loss_available, W_FUT, W_FUT_REDIST)
    w_loss = np.where(loss_available, W_LOSS, 0.0)
    raw = w_cur * c_cur + w_fut * c_fut + w_loss * c_loss
    score = np.round(100 * raw).astype(int)
    return score, c_loss, ~loss_available


def score_to_band(score: np.ndarray) -> np.ndarray:
    """§5.3 bands: 0 none; 1-24 low; 25-49 moderate; 50-74 high; 75-100 severe."""
    return pd.cut(score, bins=BAND_BINS, labels=BAND_LABELS).astype(str)


def process_county(fips: str) -> pd.DataFrame | None:
    master_path = PARCEL_MASTER / f"{fips}.parquet"
    flood_path = PARCEL_FLOOD / f"{fips}.parquet"
    claims_path = PARCEL_CLAIMS / f"{fips}.parquet"
    if not (master_path.exists() and flood_path.exists() and claims_path.exists()):
        return None

    master = pd.read_parquet(master_path, columns=["pin"])
    flood = pd.read_parquet(flood_path)
    claims_df = pd.read_parquet(claims_path)

    n = len(master)
    if len(flood) != n or len(claims_df) != n:
        raise ValueError(f"{fips}: row count mismatch across phase outputs "
                          f"(master={n}, flood={len(flood)}, claims={len(claims_df)})")
    if not (master["pin"].to_numpy() == flood["pin"].to_numpy()).all():
        raise ValueError(f"{fips}: pin sequence mismatch, parcel_master vs parcel_flood")
    if not (master["pin"].to_numpy() == claims_df["pin"].to_numpy()).all():
        raise ValueError(f"{fips}: pin sequence mismatch, parcel_master vs parcel_claims")

    sfha_pct = flood["sfha_pct"].to_numpy()
    mod_risk_pct = flood["mod_risk_pct"].to_numpy()
    fut_coverage = flood["fut_coverage"].to_numpy()
    fut_pct = flood["fut_pct"].to_numpy()
    tract_loss_pctile = claims_df["tract_loss_pctile"].to_numpy()

    c_cur = compute_c_cur(sfha_pct, flood["sfha_flag"].to_numpy(), mod_risk_pct)
    c_fut = compute_c_fut(c_cur, fut_coverage, fut_pct)
    score, c_loss, loss_redistributed = compute_score(c_cur, c_fut, tract_loss_pctile)
    band = score_to_band(score)

    return pd.DataFrame({
        "pin": master["pin"].to_numpy(),
        "sfha_pct": sfha_pct, "mod_risk_pct": mod_risk_pct,
        "fut_coverage": fut_coverage, "fut_pct": fut_pct,
        "tract_loss_pctile": tract_loss_pctile,
        "C_cur": c_cur, "C_fut": c_fut, "C_loss": c_loss,
        "loss_redistributed": loss_redistributed,
        "score": score, "band": band,
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", help="Comma-separated county names, or omit for ALL.")
    args = ap.parse_args()

    if args.county:
        wanted = {c.strip().upper() for c in args.county.split(",")}
        fips_list = [lib.COUNTY_FIPS[c] for c in sorted(wanted) if c in lib.COUNTY_FIPS]
    else:
        fips_list = sorted(lib.COUNTY_FIPS.values())

    SCORE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for fips in fips_list:
        out = process_county(fips)
        if out is None:
            print(f"  [SKIP] {fips}: Phase 1/3/4 output not all present")
            continue
        out.to_parquet(SCORE_OUT_DIR / f"{fips}.parquet", index=False)
        n_redist = int(out["loss_redistributed"].sum())
        band_counts = out["band"].value_counts().to_dict()
        print(f"  {fips}: {len(out)} parcels scored"
              + (f", {n_redist} with C_loss redistributed" if n_redist else "")
              + f" -- bands {band_counts}")
        results.append(out)

    if not results:
        print("No counties processed -- nothing to do.")
        return 1

    all_scores = pd.concat(results, ignore_index=True)
    band_totals = all_scores["band"].value_counts().reindex(BAND_LABELS, fill_value=0)
    total_redist = int(all_scores["loss_redistributed"].sum())

    lines = [
        "# NJ Parcel Flood Risk Dashboard — Score Summary",
        "",
        "Auto-written by `pipeline/05_score.py` (§5.3 composite score + bands). "
        "`C_loss` weight redistributed to `C_cur`/`C_fut` (0.60/0.40) for any "
        "parcel without a usable tract percentile -- §5.3's documented "
        "mechanism, applied per-parcel here since the only rows affected are "
        "Phase 4's 31 statewide tract-unmatched parcels, not a P6 outage.",
        "",
        f"- Parcels scored: **{len(all_scores)}**",
        f"- `C_loss` redistributed (no tract match): **{total_redist}**",
        "",
        "## Statewide band distribution",
        "",
        "| Band | Parcels | % |",
        "|---|---|---|",
    ]
    for b in BAND_LABELS:
        n = int(band_totals[b])
        lines.append(f"| {b} | {n} | {100*n/len(all_scores):.2f}% |")
    lines.append("")
    SCORE_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {len(results)} county file(s) and SCORE_SUMMARY.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
