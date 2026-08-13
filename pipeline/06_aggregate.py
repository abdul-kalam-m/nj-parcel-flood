#!/usr/bin/env python3
"""06 — Geography x class-group x risk-lens aggregates (§5.5) via DuckDB into
JSON summary artifacts, plus the ranked-municipality table (§7.2).

Note on phase numbering: the guide's own §11 phase table bundles
`04_claims.py`+`05_score.py` as one phase ("4. Claims + scores") and lists
this script alone as "5. Aggregates" -- `06_aggregate.py` does not mean
"phase 6" the way `0N_x.py` mapped cleanly to phase N through Phase 3. See
PROGRESS.md 2026-08-13 for the correction (this session's own prior entries
mislabeled 04/05 as separate phases).

Geography levels: state (1), county (21), muni (564 -- `mun_code`, not
`mun_name`, is the grouping key: §5.1's own MOD-IV-join dependency means
~11.7% of parcels statewide have a blank `mun_name` but a populated
`mun_code`/PCL_MUN, same root cause as Phase 1's join-rate finding. A
mun_code -> mun_name lookup is derived by majority vote among the matched
parcels sharing each code -- verified live that all 564 codes have a
derivable name this way, with only one single-record naming inconsistency
statewide, resolved correctly by the majority vote).

Risk lenses (current | future | either, §5.5) map onto §5.2's already-defined
flags: current = sfha_pct>0, future = fut_pct>0 (only where fut_coverage is
true), either = current OR future. The "future" lens's aggregate is computed
only among fut_coverage=true parcels -- both its numerator AND denominator
exclude non-covered parcels entirely, never counting "no future data" as "no
future risk" (§5.2's explicit warning) by silently padding the denominator.
`either`'s overlap fraction (for the overlap-based value-at-risk companion
metric) is defined as GREATEST(sfha_pct, fut_pct) where covered, else just
sfha_pct -- the more severe of the two applicable overlaps; the guide doesn't
spell this out explicitly for a unioned lens, so this is a documented
interpretation choice (§13.2), not a literal spec quote.

Row alignment between `parcel_master` (Phase 1) and `parcel_scores` (Phase
4b/05_score.py) is by row position, verified per county (exact pin-sequence
equality asserted), same reasoning as Phase 5 -- PINs aren't guaranteed
unique within a county.
"""
from __future__ import annotations

import argparse
import json
import sys

import nj_parcel_lib as lib  # imported first: sets PROJ env before any geo import

import duckdb
import pandas as pd

PARCEL_MASTER = lib.PROCESSED / "parcel_master"
PARCEL_SCORES = lib.PROCESSED / "parcel_scores"
SUMMARIES_DIR = lib.ARTIFACTS / "summaries"
RANKED_MUNI_PATH = lib.ARTIFACTS / "ranked_municipalities.json"
AGGREGATE_SUMMARY_MD = lib.REPO / "AGGREGATE_SUMMARY.md"

CLASS_GROUPS_ALL = [
    "Residential", "Commercial", "Industrial", "Farm/Agricultural",
    "Vacant", "Public/Institutional/Exempt", "Other",
]
ROLLUP_TOLERANCE_PCT = 0.1  # §11 Phase 5/Aggregates gate: muni sums = county = state (+-0.1%)


def load_combined() -> pd.DataFrame:
    """Per-county, position-verified combine of parcel_master + parcel_scores,
    concatenated statewide. Same duplicate-PIN-safe pattern as 05_score.py."""
    frames = []
    for fips in sorted(lib.COUNTY_FIPS.values()):
        master_path = PARCEL_MASTER / f"{fips}.parquet"
        scores_path = PARCEL_SCORES / f"{fips}.parquet"
        if not (master_path.exists() and scores_path.exists()):
            continue
        master = pd.read_parquet(
            master_path, columns=["pin", "county", "mun_code", "mun_name", "class_group", "net_value"])
        scores = pd.read_parquet(
            scores_path, columns=["pin", "sfha_pct", "fut_pct", "fut_coverage", "score", "band"])
        if len(master) != len(scores):
            raise ValueError(f"{fips}: row count mismatch (master={len(master)}, scores={len(scores)})")
        if not (master["pin"].to_numpy() == scores["pin"].to_numpy()).all():
            raise ValueError(f"{fips}: pin sequence mismatch, parcel_master vs parcel_scores")
        combined = pd.concat(
            [master.reset_index(drop=True), scores.drop(columns="pin").reset_index(drop=True)], axis=1)
        frames.append(combined)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_mun_name_lookup(df: pd.DataFrame) -> dict[str, str]:
    """mun_code -> mun_name by majority vote among non-blank rows -- mun_name
    is blank for the ~11.7% of parcels with no MOD-IV match (same root cause
    as Phase 1's join-rate finding), but mun_code (PCL_MUN) is always
    populated, so this recovers a name for every code from the parcels that
    *did* match."""
    named = df[df["mun_name"] != ""]
    return named.groupby("mun_code")["mun_name"].agg(lambda s: s.value_counts().idxmax()).to_dict()


def build_lensed_view(con: duckdb.DuckDBPyConnection) -> None:
    """Registers a `lensed` view: one row per (parcel, lens) pair, with a
    uniform at_risk flag and overlap_frac column per lens, so a single
    downstream GROUP BY query handles all three lenses identically."""
    con.execute("""
        CREATE OR REPLACE VIEW lensed AS
        SELECT pin, county, mun_code, class_group, net_value,
               'current' AS lens, (sfha_pct > 0) AS at_risk, sfha_pct AS overlap_frac
        FROM combined
        UNION ALL
        SELECT pin, county, mun_code, class_group, net_value,
               'future' AS lens, (fut_pct > 0) AS at_risk, fut_pct AS overlap_frac
        FROM combined
        WHERE fut_coverage = true
        UNION ALL
        SELECT pin, county, mun_code, class_group, net_value,
               'either' AS lens,
               (sfha_pct > 0 OR (fut_coverage AND fut_pct > 0)) AS at_risk,
               GREATEST(sfha_pct, COALESCE(fut_pct, 0)) AS overlap_frac
        FROM combined
    """)


AGG_SELECT = """
    SELECT
        {geo_col} AS geography_id, {class_col}
        COUNT(*) AS parcel_count,
        SUM(CASE WHEN at_risk THEN 1 ELSE 0 END) AS at_risk_count,
        100.0 * SUM(CASE WHEN at_risk THEN 1 ELSE 0 END) / COUNT(*) AS pct_at_risk,
        SUM(net_value) AS total_assessed_value,
        SUM(CASE WHEN at_risk THEN net_value ELSE 0 END) AS value_at_risk_presence,
        SUM(net_value * overlap_frac) AS value_at_risk_overlap,
        100.0 * SUM(CASE WHEN at_risk THEN net_value ELSE 0 END)
            / NULLIF(SUM(net_value), 0) AS value_exposure_pct
    FROM lensed
    WHERE lens = ?
    {group_by}
"""


def aggregate_level(con: duckdb.DuckDBPyConnection, geo_col: str | None, lens: str) -> pd.DataFrame:
    """One geography level x one lens, both per-class-group rows and an 'ALL'
    classes rollup (the guide's "geography-level rollups" -- a total across
    class groups per geography, not just per-class breakdowns). The rollup
    query omits class_group from the SELECT entirely (can't select a
    non-aggregated column outside GROUP BY) and gets it stamped on in pandas
    afterward instead."""
    geo_expr = geo_col if geo_col else "'STATE'"
    per_class = con.execute(
        AGG_SELECT.format(geo_col=geo_expr, class_col="class_group,",
                           group_by=f"GROUP BY {geo_expr}, class_group"),
        [lens]).df()
    rollup = con.execute(
        AGG_SELECT.format(geo_col=geo_expr, class_col="", group_by=f"GROUP BY {geo_expr}"),
        [lens]).df()
    rollup["class_group"] = "ALL"
    out = pd.concat([per_class, rollup], ignore_index=True)
    out["lens"] = lens
    return out


def check_rollup_invariant(state_df: pd.DataFrame, county_df: pd.DataFrame, muni_df: pd.DataFrame) -> list[str]:
    """§11 Phase 5/Aggregates gate: muni sums = county = state (+-0.1%).
    Checked on the additive metrics (counts, value sums) -- pct/exposure-pct
    are derived ratios and aren't expected to sum across geographies.
    `muni_df` must already carry a `county` column (each mun_code belongs to
    exactly one county) -- grouping munis by (class_group, lens) alone here
    would silently sum every municipality *statewide* instead of just the
    ones in the county being checked, which is exactly the bug this
    function's first version had (caught by its own absurd 20-100x-inflated
    "violations" the first time this ran for real)."""
    problems = []
    additive = ["parcel_count", "at_risk_count", "total_assessed_value",
                "value_at_risk_presence", "value_at_risk_overlap"]

    muni_to_county = muni_df.groupby(["county", "class_group", "lens"])[additive].sum().reset_index()
    for _, county_row in county_df.iterrows():
        match = muni_to_county[(muni_to_county["county"] == county_row["geography_id"])
                                & (muni_to_county["class_group"] == county_row["class_group"])
                                & (muni_to_county["lens"] == county_row["lens"])]
        if match.empty:
            continue
        for col in additive:
            county_val, muni_sum = county_row[col], match[col].iloc[0]
            if county_val == 0 and muni_sum == 0:
                continue
            pct_diff = abs(county_val - muni_sum) / max(abs(county_val), 1e-9) * 100
            if pct_diff > ROLLUP_TOLERANCE_PCT:
                problems.append(f"muni->county {county_row['geography_id']}/{county_row['class_group']}/"
                                 f"{county_row['lens']}/{col}: county={county_val}, muni_sum={muni_sum} "
                                 f"({pct_diff:.3f}% diff)")

    county_to_state = county_df.groupby(["class_group", "lens"])[additive].sum().reset_index()
    for _, state_row in state_df.iterrows():
        match = county_to_state[(county_to_state["class_group"] == state_row["class_group"])
                                 & (county_to_state["lens"] == state_row["lens"])]
        if match.empty:
            continue
        for col in additive:
            state_val, county_sum = state_row[col], match[col].iloc[0]
            if state_val == 0 and county_sum == 0:
                continue
            pct_diff = abs(state_val - county_sum) / max(abs(state_val), 1e-9) * 100
            if pct_diff > ROLLUP_TOLERANCE_PCT:
                problems.append(f"county->state {state_row['class_group']}/{state_row['lens']}/{col}: "
                                 f"state={state_val}, county_sum={county_sum} ({pct_diff:.3f}% diff)")
    return problems


def rows_to_geo_json(df: pd.DataFrame) -> dict:
    """One geography's rows (all class_groups x all lenses) -> the nested
    dict a summary JSON file holds: {lens: {class_group: {metrics...}}}."""
    out: dict = {}
    for _, r in df.iterrows():
        out.setdefault(r["lens"], {})[r["class_group"]] = {
            "parcel_count": int(r["parcel_count"]), "at_risk_count": int(r["at_risk_count"]),
            "pct_at_risk": round(float(r["pct_at_risk"]), 3),
            "total_assessed_value": float(r["total_assessed_value"]) if pd.notna(r["total_assessed_value"]) else 0.0,
            "value_at_risk_presence": float(r["value_at_risk_presence"]) if pd.notna(r["value_at_risk_presence"]) else 0.0,
            "value_at_risk_overlap": round(float(r["value_at_risk_overlap"]), 2) if pd.notna(r["value_at_risk_overlap"]) else 0.0,
            "value_exposure_pct": round(float(r["value_exposure_pct"]), 3) if pd.notna(r["value_exposure_pct"]) else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args()

    print("Loading + combining parcel_master + parcel_scores (position-verified per county)...")
    combined = load_combined()
    if combined.empty:
        print("No counties available -- nothing to do.")
        return 1
    print(f"  {len(combined)} parcels combined")
    mun_lookup = build_mun_name_lookup(combined)
    # Each mun_code belongs to exactly one county (PCL_MUN encodes county in
    # its own prefix) -- built once, reused for both the rollup-invariant
    # check below and the ranked-municipality table.
    mun_to_county = combined.drop_duplicates("mun_code").set_index("mun_code")["county"].to_dict()

    con = duckdb.connect()
    con.register("combined", combined)
    build_lensed_view(con)

    lenses = ["current", "future", "either"]
    state_df = pd.concat([aggregate_level(con, None, lens) for lens in lenses], ignore_index=True)
    county_df = pd.concat([aggregate_level(con, "county", lens) for lens in lenses], ignore_index=True)
    muni_df = pd.concat([aggregate_level(con, "mun_code", lens) for lens in lenses], ignore_index=True)
    muni_df["county"] = muni_df["geography_id"].map(mun_to_county)

    print("Checking §11 rollup invariant (muni sums = county = state, ±0.1%)...")
    problems = check_rollup_invariant(state_df, county_df, muni_df)
    if problems:
        print(f"  [FAIL] {len(problems)} rollup invariant violation(s):")
        for p in problems[:20]:
            print("   -", p)
        return 2
    print("  [PASS]")

    # §7.1 artifact naming is FIPS-keyed (`summaries/county/{fips}.json`,
    # `summaries/muni/{fips}{mun}.json`), but the aggregation above groups by
    # `combined`'s own `county` column, which holds the county *name*
    # (Phase 1's schema, always populated regardless of MOD-IV match status)
    # -- translated to FIPS only at file-write time via the existing
    # COUNTY_FIPS lookup, so the aggregation SQL itself doesn't need to care.
    # Muni filenames use {county FIPS}{mun_code's own 2-digit suffix} --
    # verified live that this suffix is unique *within* every county (no
    # collisions), so the concatenation is a safe, globally-unique key.
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARIES_DIR / "state.json").write_text(
        json.dumps(rows_to_geo_json(state_df), indent=2), encoding="utf-8")

    county_dir = SUMMARIES_DIR / "county"
    county_dir.mkdir(exist_ok=True)
    for county_name in sorted(county_df["geography_id"].unique()):
        fips = lib.COUNTY_FIPS[county_name]
        sub = county_df[county_df["geography_id"] == county_name]
        payload = rows_to_geo_json(sub)
        payload["county_name"] = county_name
        (county_dir / f"{fips}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    muni_dir = SUMMARIES_DIR / "muni"
    muni_dir.mkdir(exist_ok=True)
    for mun_code in sorted(muni_df["geography_id"].unique()):
        sub = muni_df[muni_df["geography_id"] == mun_code]
        county_name = mun_to_county[mun_code]
        fips_mun = f"{lib.COUNTY_FIPS[county_name]}{mun_code[-2:]}"
        payload = rows_to_geo_json(sub)
        payload["mun_name"] = mun_lookup.get(mun_code, "")
        payload["county_name"] = county_name
        (muni_dir / f"{fips_mun}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Ranked-municipality table (§7.2): either-lens, all-classes rollup --
    # the broadest "which towns are most at risk" view; per-county rank by
    # both % at risk and value at risk, since the UI view wants both.
    either_all = muni_df[(muni_df["lens"] == "either") & (muni_df["class_group"] == "ALL")].copy()
    either_all["mun_name"] = either_all["geography_id"].map(mun_lookup)
    ranked = []
    for county, grp in either_all.groupby("county"):
        by_pct = grp.sort_values("pct_at_risk", ascending=False)["geography_id"].tolist()
        by_value = grp.sort_values("value_at_risk_presence", ascending=False)["geography_id"].tolist()
        ranked.append({
            "county": county,
            "rank_by_pct_at_risk": by_pct,
            "rank_by_value_at_risk": by_value,
        })
    RANKED_MUNI_PATH.parent.mkdir(parents=True, exist_ok=True)
    RANKED_MUNI_PATH.write_text(json.dumps(ranked, indent=2), encoding="utf-8")

    state_either_all = state_df[(state_df["lens"] == "either") & (state_df["class_group"] == "ALL")].iloc[0]
    lines = [
        "# NJ Parcel Flood Risk Dashboard — Aggregate Summary",
        "",
        "Auto-written by `pipeline/06_aggregate.py` (§5.5; §11 \"Phase 5: "
        "Aggregates\" exit criterion -- rollup invariant muni=county=state "
        "±0.1%, independently checked above: **PASS**).",
        "",
        f"- Parcels aggregated: **{len(combined)}**",
        f"- Municipalities: **{muni_df['geography_id'].nunique()}**",
        f"- Statewide, either lens, all classes: **{int(state_either_all['at_risk_count'])}/"
        f"{int(state_either_all['parcel_count'])} parcels at risk "
        f"({state_either_all['pct_at_risk']:.2f}%)**, value exposure "
        f"**{state_either_all['value_exposure_pct']:.2f}%**",
        "",
        "## Statewide by class group (either lens)",
        "",
        "| Class group | Parcels | At risk | % at risk | Value exposure % |",
        "|---|---|---|---|---|",
    ]
    state_either = state_df[(state_df["lens"] == "either") & (state_df["class_group"] != "ALL")]
    for _, r in state_either.sort_values("pct_at_risk", ascending=False).iterrows():
        lines.append(f"| {r['class_group']} | {int(r['parcel_count'])} | {int(r['at_risk_count'])} | "
                     f"{r['pct_at_risk']:.2f}% | {r['value_exposure_pct']:.2f}% |")
    lines.append("")
    AGGREGATE_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nWrote summaries/state.json, {county_df['geography_id'].nunique()} county file(s), "
          f"{muni_df['geography_id'].nunique()} muni file(s), ranked_municipalities.json, "
          f"AGGREGATE_SUMMARY.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
