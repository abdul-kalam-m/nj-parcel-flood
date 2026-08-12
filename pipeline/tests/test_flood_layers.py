"""Tests for 02_flood_layers.py -- pure logic + bisection-fallback regression
tests, all offline (no network, no fixture files). Phase 2 doesn't have a small
committed fixture the way Phase 1 does (its real output is per-county
flood-layer .gpkg files under data/processed/, gitignored, not a 3-town mini
state) -- so coverage here focuses on parts that don't need a live service:
esri geometry conversion, zone aggregation, and the OBJECTID-chunk +
bisection-on-failure fallback that both fetch_nfhl_bbox() and fetch_p4_county()
depend on (the exact mechanism that fixed the Cape May NFHL failures, see
PROGRESS.md 2026-08-12)."""
import importlib

import geopandas as gpd
import pytest

import nj_parcel_lib as lib

flood = importlib.import_module("02_flood_layers")


# --- lib.esri_rings_to_geom (load-bearing for this module; untested elsewhere) ---

def test_esri_rings_to_geom_simple_exterior():
    ring = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]  # clockwise -> esri exterior
    geom = lib.esri_rings_to_geom([ring])
    assert geom is not None
    assert geom.is_valid
    assert geom.area == pytest.approx(1.0)


def test_esri_rings_to_geom_exterior_with_hole():
    exterior = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]  # clockwise -> exterior
    hole = [[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]  # counter-clockwise -> hole
    geom = lib.esri_rings_to_geom([exterior, hole])
    assert geom is not None
    assert geom.is_valid
    assert geom.area == pytest.approx(99.0)  # 10x10 minus the 1x1 hole


def test_esri_rings_to_geom_empty_input_returns_none():
    assert lib.esri_rings_to_geom([]) is None


# --- zone_inventory ---------------------------------------------------------

def _square(x0, y0, size):
    from shapely.geometry import Polygon
    return Polygon([(x0, y0), (x0, y0 + size), (x0 + size, y0 + size), (x0 + size, y0)])


def test_zone_inventory_aggregates_by_zone_and_sums_area():
    # built directly in UTM18N (meters) so zone_inventory's internal
    # to_crs(lib.UTM18N) is a no-op and areas are exact, not reprojection-dependent.
    gdf = gpd.GeoDataFrame({
        "FLD_ZONE": ["AE", "AE", "X"],
        "geometry": [_square(0, 0, 1000), _square(2000, 0, 1000), _square(4000, 0, 500)],
    }, geometry="geometry", crs=lib.UTM18N)
    inv = flood.zone_inventory(gdf, "FLD_ZONE")
    assert inv["AE"]["n_features"] == 2
    assert inv["AE"]["area_km2"] == pytest.approx(2.0, abs=0.01)  # two 1km x 1km squares
    assert inv["X"]["n_features"] == 1
    assert inv["X"]["area_km2"] == pytest.approx(0.25, abs=0.01)  # 0.5km x 0.5km


def test_zone_inventory_empty_gdf_returns_empty_dict():
    gdf = gpd.GeoDataFrame(columns=["FLD_ZONE", "geometry"], geometry="geometry", crs=lib.WGS84)
    assert flood.zone_inventory(gdf, "FLD_ZONE") == {}


# --- bisection fallback (the actual Cape May bug fix) -----------------------
# Both _fetch_p4_batch and _fetch_nfhl_batch call lib.get_json through the
# module attribute (`lib.get_json(...)`, not a bare imported name), so
# monkeypatching the attribute on the shared nj_parcel_lib module object is
# visible to both this test file's `lib` and 02_flood_layers.py's `lib` --
# they're the same cached module object.

def _fake_get_json_failing_id(bad_id: int, extra_fields: dict | None = None):
    """Build a fake lib.get_json that raises like a real ArcGIS error payload
    whenever `bad_id` is in the requested objectIds, and otherwise returns a
    minimal-but-valid esri-JSON feature per id."""
    def fake(url, params=None, force=False, timeout=60, retries=3, backoff_base=1.5):
        ids = [int(x) for x in params["objectIds"].split(",")]
        if bad_id in ids:
            raise RuntimeError(f"ArcGIS error payload (HTTP 200): simulated bad record {bad_id}")
        attrs = {"FLD_ZONE": "AE", **(extra_fields or {})}
        return {"features": [
            {"attributes": {"OBJECTID": i, **attrs},
             "geometry": {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}
            for i in ids
        ]}
    return fake


def test_fetch_p4_batch_bisects_on_failure_and_recovers_good_records(monkeypatch):
    monkeypatch.setattr(lib, "get_json", _fake_get_json_failing_id(42))
    n_bad_before = len(flood.P4_BAD_IDS_LOG)
    rows: list[dict] = []
    flood._fetch_p4_batch([40, 41, 42, 43], force=False, rows=rows)
    assert sorted(r["OBJECTID"] for r in rows) == [40, 41, 43]
    assert flood.P4_BAD_IDS_LOG[n_bad_before:] == [42]


def test_fetch_nfhl_batch_bisects_on_failure_and_recovers_good_records(monkeypatch):
    monkeypatch.setattr(lib, "get_json", _fake_get_json_failing_id(99, {"SFHA_TF": "T"}))
    n_bad_before = len(flood.NFHL_BAD_IDS_LOG)
    rows: list[dict] = []
    flood._fetch_nfhl_batch([97, 98, 99, 100], force=False, rows=rows)
    assert sorted(r["OBJECTID"] for r in rows) == [97, 98, 100]
    assert flood.NFHL_BAD_IDS_LOG[n_bad_before:] == [99]


def test_fetch_p4_batch_all_good_records_no_bisection_needed(monkeypatch):
    monkeypatch.setattr(lib, "get_json", _fake_get_json_failing_id(bad_id=-1))  # never matches
    rows: list[dict] = []
    flood._fetch_p4_batch([1, 2, 3], force=False, rows=rows)
    assert sorted(r["OBJECTID"] for r in rows) == [1, 2, 3]


def test_fetch_nfhl_bbox_chunks_ids_and_assembles_geodataframe(monkeypatch):
    def fake(url, params=None, force=False, timeout=60, retries=3, backoff_base=1.5):
        if params.get("returnIdsOnly") == "true":
            return {"objectIds": [1, 2, 3]}
        ids = [int(x) for x in params["objectIds"].split(",")]
        return {"features": [
            {"attributes": {"OBJECTID": i, "FLD_ZONE": "AE", "SFHA_TF": "T"},
             "geometry": {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}
            for i in ids
        ]}

    monkeypatch.setattr(lib, "get_json", fake)
    gdf = flood.fetch_nfhl_bbox((-75.0, 39.0, -74.9, 39.1), force=False)
    assert len(gdf) == 3
    assert set(gdf["OBJECTID"]) == {1, 2, 3}
    assert str(gdf.crs) == "EPSG:4326"


def test_fetch_nfhl_bbox_returns_empty_gdf_when_no_ids(monkeypatch):
    monkeypatch.setattr(lib, "get_json", lambda *a, **k: {"objectIds": []})
    gdf = flood.fetch_nfhl_bbox((-75.0, 39.0, -74.9, 39.1), force=False)
    assert len(gdf) == 0
