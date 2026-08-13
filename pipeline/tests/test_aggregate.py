"""Tests for 06_aggregate.py -- offline (in-memory DuckDB + tiny synthetic
data, no real files, no network)."""
import importlib

import duckdb
import numpy as np
import pandas as pd
import pytest

agg = importlib.import_module("06_aggregate")


# --- build_mun_name_lookup ----------------------------------------------------

def test_mun_name_lookup_majority_vote():
    df = pd.DataFrame({
        "mun_code": ["A1", "A1", "A1", "A2", "A2"],
        "mun_name": ["FANWOOD BORO", "FANWOOD BORO", "", "SOMETOWN", ""],
    })
    lookup = agg.build_mun_name_lookup(df)
    assert lookup == {"A1": "FANWOOD BORO", "A2": "SOMETOWN"}


def test_mun_name_lookup_omits_codes_with_no_usable_name():
    df = pd.DataFrame({"mun_code": ["A1", "A1"], "mun_name": ["", ""]})
    lookup = agg.build_mun_name_lookup(df)
    assert lookup == {}


# --- synthetic statewide fixture: 4 parcels, 2 counties, 3 munis --------------
# P1: county A, mun A1, Residential, value 100, sfha=0.5, fut=0.2, covered
# P2: county A, mun A1, Residential, value 200, sfha=0.0, fut=0.0, covered
# P3: county A, mun A2, Commercial,  value 300, sfha=0.0, fut=NaN, NOT covered
# P4: county B, mun B1, Residential, value 400, sfha=1.0, fut=NaN, NOT covered

@pytest.fixture
def con():
    combined = pd.DataFrame({
        "pin": ["P1", "P2", "P3", "P4"],
        "county": ["A", "A", "A", "B"],
        "mun_code": ["A1", "A1", "A2", "B1"],
        "class_group": ["Residential", "Residential", "Commercial", "Residential"],
        "net_value": [100.0, 200.0, 300.0, 400.0],
        "sfha_pct": [0.5, 0.0, 0.0, 1.0],
        "fut_pct": [0.2, 0.0, np.nan, np.nan],
        "fut_coverage": [True, True, False, False],
    })
    c = duckdb.connect()
    c.register("combined", combined)
    agg.build_lensed_view(c)
    yield c
    c.close()


def _row(df, geo, class_group="ALL"):
    match = df[(df["geography_id"] == geo) & (df["class_group"] == class_group)]
    assert len(match) == 1, f"expected exactly one row for {geo}/{class_group}, got {len(match)}"
    return match.iloc[0]


def test_current_lens_county_totals(con):
    county_df = agg.aggregate_level(con, "county", "current")
    a = _row(county_df, "A")
    assert a["parcel_count"] == 3
    assert a["at_risk_count"] == 1  # only P1 (sfha_pct=0.5 > 0)
    assert a["total_assessed_value"] == pytest.approx(600.0)
    assert a["value_at_risk_presence"] == pytest.approx(100.0)  # P1's full value
    assert a["value_at_risk_overlap"] == pytest.approx(100 * 0.5)  # 50.0
    assert a["value_exposure_pct"] == pytest.approx(100 / 600 * 100)

    b = _row(county_df, "B")
    assert b["parcel_count"] == 1
    assert b["at_risk_count"] == 1  # P4 (sfha_pct=1.0)
    assert b["value_at_risk_overlap"] == pytest.approx(400 * 1.0)


def test_future_lens_excludes_uncovered_parcels_entirely(con):
    # Future lens must never treat "no coverage" as "no risk" -- uncovered
    # parcels (P3, P4) must be absent from both numerator AND denominator,
    # not silently counted as not-at-risk.
    county_df = agg.aggregate_level(con, "county", "future")
    a = _row(county_df, "A")
    assert a["parcel_count"] == 2  # only P1, P2 (covered) -- P3 excluded
    assert a["at_risk_count"] == 1  # P1 (fut_pct=0.2 > 0)
    assert a["total_assessed_value"] == pytest.approx(300.0)  # P1+P2 only

    # County B has ZERO covered parcels -- must produce no row at all here,
    # not a misleading 0/0 or a row that silently omits P4.
    assert (county_df["geography_id"] == "B").sum() == 0


def test_either_lens_uses_greatest_overlap_and_or_of_flags(con):
    county_df = agg.aggregate_level(con, "county", "either")
    a = _row(county_df, "A")
    assert a["parcel_count"] == 3  # either lens includes uncovered parcels (unlike future alone)
    assert a["at_risk_count"] == 1  # P1: sfha 0.5>0 -> True; P2, P3 both False
    assert a["value_at_risk_overlap"] == pytest.approx(100 * 0.5)  # GREATEST(0.5, 0.2) = 0.5

    b = _row(county_df, "B")
    assert b["at_risk_count"] == 1  # P4: sfha 1.0>0 -> True even though future is unknown
    assert b["value_at_risk_overlap"] == pytest.approx(400 * 1.0)  # GREATEST(1.0, 0) = 1.0


def test_class_group_rollup_and_per_class_both_present(con):
    county_df = agg.aggregate_level(con, "county", "current")
    # County A has both a Residential-only row and an ALL row
    res = _row(county_df, "A", "Residential")
    all_a = _row(county_df, "A", "ALL")
    assert res["parcel_count"] == 2   # P1, P2
    assert all_a["parcel_count"] == 3  # P1, P2, P3 (Commercial included in ALL)


# --- check_rollup_invariant: the actual bug this project hit -----------------

def test_rollup_invariant_passes_on_consistent_data(con):
    state_df = pd.concat([agg.aggregate_level(con, None, lens) for lens in ("current", "future", "either")],
                          ignore_index=True)
    county_df = pd.concat([agg.aggregate_level(con, "county", lens) for lens in ("current", "future", "either")],
                           ignore_index=True)
    muni_df = pd.concat([agg.aggregate_level(con, "mun_code", lens) for lens in ("current", "future", "either")],
                         ignore_index=True)
    muni_df["county"] = muni_df["geography_id"].map({"A1": "A", "A2": "A", "B1": "B"})
    problems = agg.check_rollup_invariant(state_df, county_df, muni_df)
    assert problems == []


def test_rollup_invariant_catches_cross_county_muni_leakage(con):
    # Regression test for the exact bug this script's first version had:
    # summing munis by (class_group, lens) alone -- without county -- lets a
    # municipality's numbers silently bleed into every other county's check.
    # A correct invariant check must catch this, not pass it.
    county_df = agg.aggregate_level(con, "county", "current")
    muni_df = agg.aggregate_level(con, "mun_code", "current")
    muni_df["county"] = muni_df["geography_id"].map({"A1": "A", "A2": "A", "B1": "B"})
    # Corrupt the mapping so B1 (really county B) is mislabeled as county A --
    # simulates/reproduces the original bug's effect (a muni's numbers land
    # in the wrong county's rollup).
    muni_df.loc[muni_df["geography_id"] == "B1", "county"] = "A"

    state_df = agg.aggregate_level(con, None, "current")
    problems = agg.check_rollup_invariant(state_df, county_df, muni_df)
    assert len(problems) > 0
    # county A's muni-sum is now inflated by the mislabeled B1 -> flagged
    assert any(p.startswith("muni->county A/") for p in problems)
