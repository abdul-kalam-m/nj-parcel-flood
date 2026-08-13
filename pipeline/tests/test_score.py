"""Tests for 05_score.py -- pure formula logic offline (no network, no files)."""
import importlib

import numpy as np
import pytest

score_mod = importlib.import_module("05_score")


# --- compute_c_cur -----------------------------------------------------------

def test_c_cur_zero_when_untouched():
    c = score_mod.compute_c_cur(np.array([0.0]), np.array([False]), np.array([0.0]))
    assert c[0] == 0.0


def test_c_cur_presence_floor_applies_below_030():
    # touched but tiny sfha_pct -> floor of 0.3 dominates
    c = score_mod.compute_c_cur(np.array([0.05]), np.array([True]), np.array([0.0]))
    assert c[0] == pytest.approx(0.3)


def test_c_cur_uses_actual_pct_when_above_floor():
    c = score_mod.compute_c_cur(np.array([0.6]), np.array([True]), np.array([0.0]))
    assert c[0] == pytest.approx(0.6)


def test_c_cur_adds_moderate_risk_term():
    c = score_mod.compute_c_cur(np.array([0.6]), np.array([True]), np.array([0.4]))
    assert c[0] == pytest.approx(0.6 + 0.15 * 0.4)


def test_c_cur_moderate_term_alone_no_sfha_floor():
    # not touched by SFHA at all -> no 0.3 floor, just the moderate term
    c = score_mod.compute_c_cur(np.array([0.0]), np.array([False]), np.array([0.4]))
    assert c[0] == pytest.approx(0.15 * 0.4)


def test_c_cur_capped_at_one():
    c = score_mod.compute_c_cur(np.array([1.0]), np.array([True]), np.array([1.0]))
    assert c[0] == 1.0


# --- compute_c_fut -------------------------------------------------------------

def test_c_fut_covered_presence_floor():
    c_cur = np.array([0.5])
    c = score_mod.compute_c_fut(c_cur, np.array([True]), np.array([0.05]))
    assert c[0] == pytest.approx(0.3)


def test_c_fut_covered_uses_actual_pct_above_floor():
    c_cur = np.array([0.5])
    c = score_mod.compute_c_fut(c_cur, np.array([True]), np.array([0.7]))
    assert c[0] == pytest.approx(0.7)


def test_c_fut_covered_capped_at_one():
    c_cur = np.array([0.5])
    c = score_mod.compute_c_fut(c_cur, np.array([True]), np.array([1.0]))
    assert c[0] == 1.0


def test_c_fut_uncovered_is_half_of_c_cur_regardless_of_fut_pct():
    c_cur = np.array([0.8])
    c = score_mod.compute_c_fut(c_cur, np.array([False]), np.array([np.nan]))
    assert c[0] == pytest.approx(0.4)


# --- compute_score / weight redistribution ------------------------------------

def test_score_standard_weights_when_loss_available():
    c_cur, c_fut, tract_pctile = np.array([1.0]), np.array([1.0]), np.array([1.0])
    scores, c_loss, redist = score_mod.compute_score(c_cur, c_fut, tract_pctile)
    assert scores[0] == 100  # 100*(0.45+0.30+0.25) = 100
    assert c_loss[0] == 1.0
    assert redist[0] == False  # noqa: E712


def test_score_redistributed_weights_when_loss_missing():
    c_cur, c_fut, tract_pctile = np.array([1.0]), np.array([1.0]), np.array([np.nan])
    scores, c_loss, redist = score_mod.compute_score(c_cur, c_fut, tract_pctile)
    # 100*(0.60*1 + 0.40*1 + 0*anything) = 100, weights still sum correctly
    assert scores[0] == 100
    assert c_loss[0] == 0.0  # stored as a clean 0, never raw NaN
    assert redist[0] == True  # noqa: E712


def test_score_redistributed_weights_are_060_040():
    assert score_mod.W_CUR_REDIST == pytest.approx(0.60)
    assert score_mod.W_FUT_REDIST == pytest.approx(0.40)
    assert score_mod.W_CUR_REDIST + score_mod.W_FUT_REDIST == pytest.approx(1.0)


def test_score_matches_hand_computed_example():
    # C_cur=0.5, C_fut=0.2, C_loss=0.8 -> 100*(0.45*0.5+0.30*0.2+0.25*0.8)
    # = 100*(0.225+0.06+0.20) = 100*0.485 = 48.5 -> rounds to 48 or 49
    # depending on convention; just check it lands in {48, 49}, not some
    # unrelated value, and that hand-checking the un-rounded math matches.
    c_cur, c_fut, tract_pctile = np.array([0.5]), np.array([0.2]), np.array([0.8])
    scores, _, _ = score_mod.compute_score(c_cur, c_fut, tract_pctile)
    raw = 100 * (0.45 * 0.5 + 0.30 * 0.2 + 0.25 * 0.8)
    assert raw == pytest.approx(48.5)
    assert scores[0] in (48, 49)


# --- score_to_band: exact boundary values --------------------------------------

@pytest.mark.parametrize("s,expected", [
    (0, "none"),
    (1, "low"), (24, "low"),
    (25, "moderate"), (49, "moderate"),
    (50, "high"), (74, "high"),
    (75, "severe"), (100, "severe"),
])
def test_score_to_band_boundaries(s, expected):
    band = score_mod.score_to_band(np.array([s]))
    assert band[0] == expected


# --- SS12.1 gate 4: score reproducible from stored components -----------------

def test_recompute_check_standard_case():
    sfha_pct, sfha_flag, mod_risk_pct = np.array([0.6]), np.array([True]), np.array([0.2])
    fut_coverage, fut_pct = np.array([True]), np.array([0.4])
    tract_pctile = np.array([0.7])

    c_cur = score_mod.compute_c_cur(sfha_pct, sfha_flag, mod_risk_pct)
    c_fut = score_mod.compute_c_fut(c_cur, fut_coverage, fut_pct)
    scores, c_loss, redist = score_mod.compute_score(c_cur, c_fut, tract_pctile)

    # Recompute purely from the stored components + redistributed flag, as
    # §12.1's gate 4 requires a validator be able to do independently.
    w_cur = score_mod.W_CUR_REDIST if redist[0] else score_mod.W_CUR
    w_fut = score_mod.W_FUT_REDIST if redist[0] else score_mod.W_FUT
    w_loss = 0.0 if redist[0] else score_mod.W_LOSS
    recomputed = round(100 * (w_cur * c_cur[0] + w_fut * c_fut[0] + w_loss * c_loss[0]))
    assert recomputed == scores[0]


def test_recompute_check_redistributed_case_no_nan_propagation():
    # The case this design specifically guards against: C_loss missing (NaN
    # tract percentile) must not poison the recompute check via 0*NaN=NaN.
    sfha_pct, sfha_flag, mod_risk_pct = np.array([0.9]), np.array([True]), np.array([0.0])
    fut_coverage, fut_pct = np.array([True]), np.array([0.5])
    tract_pctile = np.array([np.nan])

    c_cur = score_mod.compute_c_cur(sfha_pct, sfha_flag, mod_risk_pct)
    c_fut = score_mod.compute_c_fut(c_cur, fut_coverage, fut_pct)
    scores, c_loss, redist = score_mod.compute_score(c_cur, c_fut, tract_pctile)

    assert redist[0]
    assert not np.isnan(c_loss[0])  # stored value is safe to multiply by 0
    w_cur, w_fut, w_loss = score_mod.W_CUR_REDIST, score_mod.W_FUT_REDIST, 0.0
    recomputed = round(100 * (w_cur * c_cur[0] + w_fut * c_fut[0] + w_loss * c_loss[0]))
    assert not np.isnan(recomputed)
    assert recomputed == scores[0]
