"""Tests for 03_intersect.py -- pure geometry logic offline (no files, no
network). All synthetic squares/rectangles in a projected (meters) CRS, since
_overlap_pct only ever calls .area on already-projected geometry -- the exact
coordinate values don't need to be real NJ locations for the area math to be
meaningful."""
import importlib

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

import nj_parcel_lib as lib

intersect = importlib.import_module("03_intersect")


def _rect(x0, y0, w, h):
    return Polygon([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)])


def _square(x0, y0, size):
    return _rect(x0, y0, size, size)


def _parcels(*polys, pins=None):
    return gpd.GeoDataFrame(
        {"pin": pins or [f"P{i}" for i in range(len(polys))], "geometry": list(polys)},
        geometry="geometry", crs=lib.UTM18N)


def _zones(*polys):
    return gpd.GeoDataFrame({"geometry": list(polys)}, geometry="geometry", crs=lib.UTM18N)


def test_full_overlap():
    parcels = _parcels(_square(0, 0, 10))          # 100 m^2 parcel
    zones = _zones(_square(-5, -5, 20))             # zone fully covers it
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert pct[0] == pytest.approx(1.0)
    assert area[0] == pytest.approx(100.0)
    assert n_clamped == 0


def test_partial_overlap():
    parcels = _parcels(_square(0, 0, 10))           # (0,0)-(10,10), 100 m^2
    zones = _zones(_square(5, 0, 10))                # covers x in [5,15] -- half the parcel
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert pct[0] == pytest.approx(0.5)
    assert area[0] == pytest.approx(50.0)


def test_no_overlap():
    parcels = _parcels(_square(0, 0, 10))
    zones = _zones(_square(100, 100, 10))
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert pct[0] == 0.0
    assert area[0] == 0.0
    assert n_clamped == 0


def test_empty_zones_returns_zero():
    parcels = _parcels(_square(0, 0, 10))
    zones = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=lib.UTM18N)
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert pct[0] == 0.0
    assert n_clamped == 0


def test_sliver_below_1pct_of_large_parcel_dropped():
    parcels = _parcels(_square(0, 0, 100))           # 10,000 m^2
    zones = _zones(_rect(95, 0, 15, 15))              # overlap: 5 x 15 = 75 m^2
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert area[0] == pytest.approx(75.0)
    assert area[0] > intersect.SLIVER_AREA_M2         # not an absolute-area sliver...
    assert area[0] / 10_000 < intersect.SLIVER_PCT    # ...but is under 1% of the parcel
    assert pct[0] == 0.0                              # dropped anyway


def test_sliver_below_10m2_absolute_dropped_even_when_pct_alone_would_pass():
    # 10x10 parcel (100 m^2) with a 3x3=9 m^2 overlap: 9% of the parcel (would
    # NOT be dropped by the 1% test alone) but 9 m^2 < 10 m^2 absolute -- the
    # rule drops on *either* test, so this must still be zeroed.
    parcels = _parcels(_square(0, 0, 10))             # 100 m^2
    zones = _zones(_rect(7, 0, 3, 3))                  # 3x3 = 9 m^2 overlap
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert area[0] == pytest.approx(9.0)
    assert area[0] < intersect.SLIVER_AREA_M2
    assert (area[0] / 100.0) >= intersect.SLIVER_PCT  # confirms the pct test alone would NOT drop it
    assert pct[0] == 0.0                               # but the absolute-area test does


def test_multiple_nonoverlapping_zones_sum_correctly():
    parcels = _parcels(_square(0, 0, 10))              # 100 m^2, x&y in [0,10]
    zones = _zones(_rect(0, 0, 5, 10), _rect(5, 0, 5, 10))  # two halves, no overlap w/ each other
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert area[0] == pytest.approx(100.0)
    assert pct[0] == pytest.approx(1.0)
    assert n_clamped == 0


def test_overlapping_source_zones_clamped_to_one_and_counted():
    parcels = _parcels(_square(0, 0, 10))               # 100 m^2
    # two identical zones, each fully covering the parcel and overlapping
    # each other -- raw summed overlap = 200 m^2, double the parcel's own area
    zones = _zones(_square(-5, -5, 20), _square(-5, -5, 20))
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert area[0] == pytest.approx(200.0)   # raw, pre-clamp
    assert pct[0] == pytest.approx(1.0)      # clamped into range
    assert n_clamped == 1


def test_overlap_correctness_unaffected_by_duplicate_pin_values():
    # two DIFFERENT parcels sharing the same 'pin' (a real, confirmed scenario
    # -- Phase 1 found 742 statewide conflicting-duplicate PINs, kept not
    # merged) must each get their own correct, independent overlap, never
    # merged just because they share a pin. _overlap_pct keys internally by
    # row position, not by the 'pin' column, precisely to guarantee this.
    parcels = _parcels(_square(0, 0, 10), _square(1000, 1000, 10), pins=["DUPE", "DUPE"])
    zones = _zones(_square(-5, -5, 20))  # only covers the first parcel
    pct, area, n_clamped = intersect._overlap_pct(parcels, zones)
    assert pct[0] == pytest.approx(1.0)
    assert pct[1] == pytest.approx(0.0)


def test_all_pcts_stay_within_zero_one_bound_property():
    # §12.1 consistency gate, exercised directly: no combination tested above
    # (or their union) should ever leave [0,1].
    parcels = _parcels(_square(0, 0, 10))
    zones = _zones(_square(-5, -5, 20), _square(-3, -3, 20), _square(2, 2, 3))
    pct, _, _ = intersect._overlap_pct(parcels, zones)
    assert ((pct >= 0.0) & (pct <= 1.0)).all()
