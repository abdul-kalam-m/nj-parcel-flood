"""Tests for 04_claims.py -- pure logic offline (no network, no files)."""
import importlib

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

import nj_parcel_lib as lib

claims = importlib.import_module("04_claims")


def _square(x0, y0, size):
    return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])


def _tracts(geoids_and_squares):
    return gpd.GeoDataFrame(
        {"GEOID": [g for g, _ in geoids_and_squares]},
        geometry=[s for _, s in geoids_and_squares], crs=lib.UTM18N)


# --- compute_tract_summary ---------------------------------------------------

def test_compute_tract_summary_basic_formula_and_ranking():
    all_geoids = ["T1", "T2", "T3"]
    parcels_per_tract = pd.Series({"T1": 100, "T2": 100, "T3": 50})
    claims_per_tract = pd.Series({"T1": 5, "T2": 1})  # T3 has 0 claims (absent), T1 has more claims/parcel
    summary = claims.compute_tract_summary(all_geoids, parcels_per_tract, claims_per_tract)
    s = summary.set_index("tract_geoid")
    assert s.loc["T1", "claims_per_1000_parcels"] == pytest.approx(50.0)   # 5/100*1000
    assert s.loc["T2", "claims_per_1000_parcels"] == pytest.approx(10.0)   # 1/100*1000
    assert s.loc["T3", "claims_per_1000_parcels"] == pytest.approx(0.0)    # no claims mapped
    # T1 has the highest rate -> highest percentile among the 3 populated tracts
    assert s.loc["T1", "tract_loss_pctile"] > s.loc["T2", "tract_loss_pctile"] > s.loc["T3", "tract_loss_pctile"]
    assert s.loc["T1", "tract_loss_pctile"] == pytest.approx(1.0)


def test_compute_tract_summary_zero_parcel_tract_gets_zero_pctile_and_excluded_from_ranking():
    # A tract with no scored parcels (e.g., entirely water/marsh) must not
    # dilute the ranked population with an artificial tie at the bottom.
    all_geoids = ["T1", "T2", "EMPTY"]
    parcels_per_tract = pd.Series({"T1": 10, "T2": 10})  # EMPTY absent -> 0 parcels
    claims_per_tract = pd.Series({"T1": 0, "T2": 0})
    summary = claims.compute_tract_summary(all_geoids, parcels_per_tract, claims_per_tract)
    s = summary.set_index("tract_geoid")
    assert s.loc["EMPTY", "n_parcels"] == 0
    assert s.loc["EMPTY", "tract_loss_pctile"] == 0.0
    # T1/T2 both have 0 claims too, but ARE populated -- ranked only against
    # each other (not dragged down by EMPTY's 0 parcels), where a 2-way tie
    # at the top under average-rank gives both (1+2)/2/2 = 0.75, not 1.0
    # (matching the same average-tie convention as the ties test below).
    assert s.loc["T1", "tract_loss_pctile"] == pytest.approx(0.75)
    assert s.loc["T2", "tract_loss_pctile"] == pytest.approx(0.75)


def test_compute_tract_summary_ties_use_average_rank():
    all_geoids = ["T1", "T2", "T3", "T4"]
    parcels_per_tract = pd.Series({g: 100 for g in all_geoids})
    claims_per_tract = pd.Series({"T1": 0, "T2": 0, "T3": 0, "T4": 4})  # 3-way tie at 0, one clear top
    summary = claims.compute_tract_summary(all_geoids, parcels_per_tract, claims_per_tract)
    s = summary.set_index("tract_geoid")
    assert s.loc["T4", "tract_loss_pctile"] == pytest.approx(1.0)
    tied = s.loc[["T1", "T2", "T3"], "tract_loss_pctile"]
    assert tied.nunique() == 1  # all three tied ranks are identical
    assert tied.iloc[0] == pytest.approx(0.5)  # average of ranks 1,2,3 out of 4 = 2/4


# --- assign_tracts ------------------------------------------------------------

def test_assign_tracts_basic_containment():
    tracts = _tracts([("A", _square(0, 0, 10)), ("B", _square(20, 0, 10))])
    pins = ["P1", "P2"]
    centroids = gpd.GeoSeries([Point(5, 5), Point(25, 5)], crs=lib.UTM18N)
    df, n_unmatched, n_tie = claims.assign_tracts(pins, centroids, tracts)
    assert df.set_index("pin")["tract_geoid"].to_dict() == {"P1": "A", "P2": "B"}
    assert n_unmatched == 0
    assert n_tie == 0


def test_assign_tracts_point_outside_all_tracts_is_unmatched_not_dropped():
    tracts = _tracts([("A", _square(0, 0, 10))])
    pins = ["P1", "P2"]
    centroids = gpd.GeoSeries([Point(5, 5), Point(500, 500)], crs=lib.UTM18N)
    df, n_unmatched, n_tie = claims.assign_tracts(pins, centroids, tracts)
    assert len(df) == 2  # unmatched parcel is kept, not silently dropped
    by_pin = df.set_index("pin")["tract_geoid"]
    assert by_pin["P1"] == "A"
    assert pd.isna(by_pin["P2"])
    assert n_unmatched == 1


def test_assign_tracts_overlapping_tracts_produce_a_counted_tie_not_a_duplicate_row():
    # Real tracts don't overlap, but this construction deterministically
    # forces the multi-match code path so it's actually exercised: two
    # overlapping "tracts" both containing the same point.
    tracts = _tracts([("A", _square(0, 0, 10)), ("B", _square(5, 0, 10))])
    pins = ["P1"]
    centroids = gpd.GeoSeries([Point(7, 5)], crs=lib.UTM18N)  # inside both A and B
    df, n_unmatched, n_tie = claims.assign_tracts(pins, centroids, tracts)
    assert len(df) == 1  # exactly one row for the one physical parcel, not two
    assert n_tie == 1
    assert df.iloc[0]["tract_geoid"] in ("A", "B")  # resolved to one, not left ambiguous


def test_assign_tracts_duplicate_pin_values_resolved_independently():
    # Two DIFFERENT parcels sharing the same 'pin' (a real, confirmed scenario
    # -- Phase 1 found 742 statewide conflicting-duplicate PINs) must each
    # get their own correct tract assignment.
    tracts = _tracts([("A", _square(0, 0, 10)), ("B", _square(20, 0, 10))])
    pins = ["DUPE", "DUPE"]
    centroids = gpd.GeoSeries([Point(5, 5), Point(25, 5)], crs=lib.UTM18N)
    df, n_unmatched, n_tie = claims.assign_tracts(pins, centroids, tracts)
    assert len(df) == 2
    assert list(df["tract_geoid"]) == ["A", "B"]
