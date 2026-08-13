"""Tests for 09_validate.py -- pure gate logic offline, synthetic data
(no network, no full statewide processed data required)."""
import importlib

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon
import geopandas as gpd

validate = importlib.import_module("09_validate")


# --- gate 1: uniqueness -------------------------------------------------------

def test_gate1_passes_when_composite_key_resolves_pin_dupes():
    master = pd.DataFrame({
        "pin": ["A", "A", "B"],
        "composite_key": ["A_1", "A_2", "B_1"],  # PIN dupe resolved by distinct composite_key
    })
    r = validate.gate_1_uniqueness(master)
    assert r["n_dupe_pin_statewide"] == 1
    assert r["n_dupe_composite_key_statewide"] == 0
    assert r["passed"] is True


def test_gate1_fails_when_rows_genuinely_differ_but_composite_key_still_collides():
    # composite_key collides too, but the underlying rows are NOT identical
    # (land_val differs) -- composite_key isn't doing its job here even
    # though the records are genuinely distinct, a real, fixable problem
    # (unlike the fully-identical case below, which no attribute-only key
    # could ever resolve).
    master = pd.DataFrame({
        "pin": ["A", "A", "B"],
        "composite_key": ["X", "X", "Y"],
        "land_val": [100, 200, 300],
    })
    r = validate.gate_1_uniqueness(master)
    assert r["n_unresolved_but_fixable"] == 2
    assert r["n_unresolved_full_row_identical"] == 0
    assert r["passed"] is False


def test_gate1_categorizes_full_row_identical_separately_and_still_passes():
    # composite_key collides, AND the rows are genuinely identical across
    # every column -- an attribute-only key structurally cannot resolve
    # this (it isn't a dedup bug), so it's counted in a distinct category
    # rather than failing the gate outright.
    master = pd.DataFrame({
        "pin": ["A", "A", "B"],
        "composite_key": ["X", "X", "Y"],
        "land_val": [100, 100, 300],
    })
    r = validate.gate_1_uniqueness(master)
    assert r["n_unresolved_full_row_identical"] == 2
    assert r["n_unresolved_but_fixable"] == 0
    assert r["passed"] is True


# --- gate 2: completeness ------------------------------------------------------

def test_gate2_reuses_real_crosswalk_and_separates_join_rate_from_unmapped():
    master = pd.DataFrame({
        "mod_iv_matched": [True, True, True, False],
        "prop_class": ["2", "4A", "99Z", None],  # 99Z: matched but not in the real crosswalk
    })
    r = validate.gate_2_completeness(master)
    assert r["join_rate"] == 0.75
    assert r["join_rate_gate_ok"] is False  # 0.75 < 0.97
    assert r["unmapped_class_pct"] == pytest.approx(25.0)  # 1/4 matched-but-unmapped
    assert r["passed"] is False


def test_gate2_passes_when_both_thresholds_met():
    master = pd.DataFrame({
        "mod_iv_matched": [True] * 97 + [False] * 3,
        "prop_class": ["2"] * 100,
    })
    r = validate.gate_2_completeness(master)
    assert r["join_rate"] == 0.97
    assert r["join_rate_gate_ok"] is True
    assert r["unmapped_class_pct"] == 0.0
    assert r["passed"] is True


# --- gate 3: geometry ----------------------------------------------------------

def _valid_square():
    return Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])


def test_gate3_passes_on_clean_geometry():
    gdf = gpd.GeoDataFrame({"geometry": [_valid_square(), _valid_square()]}, crs="EPSG:26918")
    r = validate.gate_3_geometry(gdf)
    assert r["passed"] is True
    assert r["n_invalid"] == 0 and r["n_empty"] == 0 and r["n_zero_area"] == 0


def test_gate3_fails_on_invalid_geometry():
    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])  # self-intersecting
    gdf = gpd.GeoDataFrame({"geometry": [_valid_square(), bowtie]}, crs="EPSG:26918")
    r = validate.gate_3_geometry(gdf)
    assert r["passed"] is False
    assert r["n_invalid"] == 1


def test_gate3_fails_on_zero_area_geometry():
    point_like = Polygon([(0, 0), (0, 0), (0, 0)])
    gdf = gpd.GeoDataFrame({"geometry": [_valid_square(), Point(1, 1).buffer(0.0)]}, crs="EPSG:26918")
    r = validate.gate_3_geometry(gdf)
    assert r["passed"] is False
    assert r["n_empty"] >= 1 or r["n_zero_area"] >= 1


# --- gate 4: consistency (mirrors 05_score.py's own recompute-check tests) ----

def _make_combined(n=3):
    return pd.DataFrame({
        "sfha_pct": [0.5, 0.0, 1.0][:n], "sfha_flag": [True, False, True][:n],
        "mod_risk_pct": [0.0, 0.2, 0.0][:n], "mod_risk_flag": [False, True, False][:n],
        "fut_pct": [0.3, np.nan, np.nan][:n], "fut_coverage": [True, False, False][:n],
        "C_cur": [0.5, 0.15, 1.0][:n], "C_fut": [0.3, 0.0075, 0.5][:n],
        "C_loss": [0.4, 0.0, 0.0][:n], "loss_redistributed": [False, False, True][:n],
    })


def test_gate4_passes_on_internally_consistent_data():
    combined = _make_combined()
    w_cur = np.where(combined["loss_redistributed"], 0.6, 0.45)
    w_fut = np.where(combined["loss_redistributed"], 0.4, 0.30)
    w_loss = np.where(combined["loss_redistributed"], 0.0, 0.25)
    combined["score"] = np.round(100 * (w_cur * combined["C_cur"] + w_fut * combined["C_fut"]
                                         + w_loss * combined["C_loss"])).astype(int)
    r = validate.gate_4_consistency(combined)
    assert r["passed"] is True
    assert r["n_score_recompute_mismatches"] == 0


def test_gate4_catches_flag_overlap_inconsistency():
    combined = _make_combined()
    combined["score"] = 0
    combined.loc[0, "sfha_flag"] = False  # contradicts sfha_pct=0.5 > 0
    r = validate.gate_4_consistency(combined)
    assert r["passed"] is False
    assert any("sfha_flag" in p for p in r["problems"])


def test_gate4_catches_score_recompute_mismatch():
    combined = _make_combined()
    combined["score"] = 999  # deliberately wrong, won't match any real recompute
    r = validate.gate_4_consistency(combined)
    assert r["passed"] is False
    assert r["n_score_recompute_mismatches"] == len(combined)


# --- gate 5: distribution sanity -----------------------------------------------

def test_gate5_flags_bound_brook_and_manville_when_not_high_risk():
    # Construct a world where Bound Brook/Manville are NOT high-risk outliers
    # -- the gate must fail, per §12.1's explicit "stop and investigate"
    # framing. Deterministic (fraction-of-10-rows), not sampled, and uses the
    # real mun_code constants directly -- an earlier draft generated "M{i}"
    # munis and compared against the real constants, which could never match,
    # making the assertion pass for the wrong reason (NaN >= 0.75 -> False).
    # Ranking is band-based (moderate/high/severe), not flag-based -- see
    # gate_5's own docstring/comments for why (Bound Brook is the real-world
    # example that forced this design: low on a flag-only metric, high on
    # the band that's what a user actually sees).
    munis = [validate.BOUND_BROOK_MUN_CODE, validate.MANVILLE_MUN_CODE] + [f"M{i}" for i in range(18)]
    rows = []
    for i, mun in enumerate(munis):
        is_target = mun in (validate.BOUND_BROOK_MUN_CODE, validate.MANVILLE_MUN_CODE)
        n_at_risk = 1 if is_target else 5 + (i % 5)  # targets: 10% at risk; others: 50-90%
        for j in range(10):
            rows.append({"mun_code": mun, "county": "SOMERSET",
                         "sfha_flag": j < n_at_risk, "band": "moderate" if j < n_at_risk else "low",
                         "fut_coverage": False, "fut_pct": np.nan})
    combined = pd.DataFrame(rows)
    r = validate.gate_5_distribution_sanity(combined)
    assert r["bound_brook_ranks_high"] is False
    assert r["manville_ranks_high"] is False
    assert r["passed"] is False


def test_gate5_passes_when_named_towns_and_coastal_counties_are_elevated():
    munis = [validate.BOUND_BROOK_MUN_CODE, validate.MANVILLE_MUN_CODE] + [f"M{i}" for i in range(18)]
    rows = []
    for i, mun in enumerate(munis):
        is_target = mun in (validate.BOUND_BROOK_MUN_CODE, validate.MANVILLE_MUN_CODE)
        county = "ATLANTIC" if i < 3 else "SOMERSET"  # both targets + 1 more are "coastal"
        n_at_risk = 9 if (is_target or county == "ATLANTIC") else 1  # 90% vs 10%, deterministic
        for j in range(10):
            rows.append({"mun_code": mun, "county": county,
                         "sfha_flag": j < n_at_risk, "band": "severe" if j < n_at_risk else "low",
                         "fut_coverage": False, "fut_pct": np.nan})
    combined = pd.DataFrame(rows)
    r = validate.gate_5_distribution_sanity(combined)
    assert r["bound_brook_ranks_high"] is True
    assert r["manville_ranks_high"] is True
    assert r["coastal_elevated_vs_statewide"] is True
    assert r["passed"] is True


# --- gate 7: privacy audit ------------------------------------------------------

def test_gate7_detects_forbidden_pattern_in_artifact(tmp_path, monkeypatch):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    (summaries / "state.json").write_text('{"owner_name": "leaked"}', encoding="utf-8")
    monkeypatch.setattr(validate.lib, "ARTIFACTS", tmp_path)
    r = validate.gate_7_privacy_audit()
    assert r["passed"] is False
    assert len(r["artifact_hits"]) == 1


def test_gate7_passes_on_clean_artifacts(tmp_path, monkeypatch):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    (summaries / "state.json").write_text('{"parcel_count": 100, "band": "low"}', encoding="utf-8")
    monkeypatch.setattr(validate.lib, "ARTIFACTS", tmp_path)
    r = validate.gate_7_privacy_audit()
    assert r["artifact_hits"] == []
