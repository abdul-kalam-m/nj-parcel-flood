"""Tests for 01_parcel_core.py -- pure logic offline, plus checks against the
committed mini-state fixture (no network needed, real small-scale data)."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import importlib
core = importlib.import_module("01_parcel_core")

FIXTURES = ("atlantic-city", "bound-brook", "mendham-boro")


def test_class_group_known_codes():
    assert core.class_group("2") == "Residential"
    assert core.class_group("4C") == "Residential"
    assert core.class_group("4A") == "Commercial"
    assert core.class_group("4B") == "Industrial"
    assert core.class_group("3A") == "Farm/Agricultural"
    assert core.class_group("1") == "Vacant"
    assert core.class_group("15D") == "Public/Institutional/Exempt"


def test_class_group_unmapped_and_missing_both_land_in_other():
    # §5.4: unmapped codes go to Other, never silently dropped. class_group() alone
    # doesn't distinguish "a real code we don't recognize" from "no code at all" --
    # that distinction is build_master()'s job (§12.1's two separate gates), tested
    # below via build_master() directly, not here.
    assert core.class_group("99Z") == "Other"
    assert core.class_group("") == "Other"
    assert core.class_group(None) == "Other"
    assert core.class_group(float("nan")) == "Other"


def test_exempt_codes_match_class_group_public_institutional():
    # §5.1 wants an "exempt flag" -- must line up with the same 15A-15F set §5.4
    # maps to Public/Institutional/Exempt, not a separately-drifting list.
    for code in core.EXEMPT_CODES:
        assert core.CLASS_GROUPS[code] == "Public/Institutional/Exempt"


def _synthetic_gdf(rows: list[dict]) -> gpd.GeoDataFrame:
    base = {
        "PAMS_PIN": None, "COUNTY": "ESSEX", "MUN_NAME": "TESTVILLE", "PCL_MUN": "0701",
        "PCLBLOCK": "1", "PCLLOT": "1", "PCLQCODE": None, "PROP_LOC": "1 MAIN ST",
        "PROP_CLASS": None, "LAND_VAL": None, "IMPRVT_VAL": None, "NET_VALUE": None,
        "CALC_ACRE": 0.1, "geometry": Point(-74.0, 40.0),
    }
    return gpd.GeoDataFrame([{**base, **r} for r in rows], geometry="geometry", crs=4326)


def test_build_master_separates_join_rate_from_crosswalk_gap():
    # The bug this guards against: conflating "no PROP_CLASS at all" (a join-rate
    # problem) with "a real PROP_CLASS our crosswalk doesn't recognize" (a
    # crosswalk-completeness problem) made an ordinary MOD-IV-unmatched rate look
    # like a failing crosswalk. 4 rows: 2 matched+mapped, 1 unmatched (no code), 1
    # matched but genuinely unmapped code.
    gdf = _synthetic_gdf([
        {"PAMS_PIN": "A1", "PROP_CLASS": "2"},
        {"PAMS_PIN": "A2", "PROP_CLASS": "4A"},
        {"PAMS_PIN": "A3", "PROP_CLASS": None},   # unmatched -- join-rate issue
        {"PAMS_PIN": "A4", "PROP_CLASS": "99Z"},  # matched but unmapped code
    ])
    master, stats, keep_mask = core.build_master(gdf, "ESSEX")
    assert stats["n_mod_iv_unmatched"] == 1
    assert stats["join_rate"] == 0.75
    assert stats["unmapped_count"] == 1
    assert stats["unmapped_class_codes"] == ["99Z"]
    assert master.loc[master["pin"] == "A3", "mod_iv_matched"].iloc[0] == False  # noqa: E712
    assert master.loc[master["pin"] == "A3", "class_group"].iloc[0] == "Other"
    assert master.loc[master["pin"] == "A4", "class_group"].iloc[0] == "Other"


def test_build_master_collapses_exact_duplicates_but_keeps_conflicting_ones():
    # §12.1: "PIN unique statewide (dupes logged + resolved by composite key)" --
    # an exact-duplicate row (same PIN, identical everywhere else, confirmed live
    # in Mendham Boro's real data) is collapsed since it adds nothing; a PIN
    # collision with genuinely different data is kept and counted, not silently
    # merged.
    gdf = _synthetic_gdf([
        {"PAMS_PIN": "B1", "PROP_CLASS": "2", "LAND_VAL": 100},
        {"PAMS_PIN": "B1", "PROP_CLASS": "2", "LAND_VAL": 100},  # exact dupe of B1
        {"PAMS_PIN": "B2", "PROP_CLASS": "2", "LAND_VAL": 200},
        {"PAMS_PIN": "B2", "PROP_CLASS": "4A", "LAND_VAL": 300},  # conflicting dupe
    ])
    master, stats, keep_mask = core.build_master(gdf, "ESSEX")
    assert stats["n_exact_dupes_dropped"] == 1
    assert stats["n_dupe_pin"] == 1  # the B2 conflict, not resolved away
    assert len(master) == 3
    assert keep_mask.sum() == 3


def test_fixture_files_exist_and_are_privacy_clean():
    forbidden = {"owner_name", "owner_mailing", "st_address", "city_state",
                 "zip_code", "zip5", "zip_plus4"}
    for label in FIXTURES:
        master = pd.read_parquet(f"tests/fixtures/parcel_master/{label}.parquet")
        assert len(master) > 0
        cols = {c.lower() for c in master.columns}
        assert not (cols & forbidden), f"{label}: privacy-forbidden column present: {cols & forbidden}"
        assert master["pin"].duplicated().sum() == 0, f"{label}: unexpected duplicate PINs"


def test_fixture_join_rates_are_plausible():
    # Real-world join rates are never exactly 100% (some parcels -- ROW, easements,
    # new construction -- legitimately have no MOD-IV match yet), but should still
    # be high. Sanity bounds, not a re-assertion of the exact numbers (those will
    # drift as NJOGIS's composite is updated).
    for label in FIXTURES:
        master = pd.read_parquet(f"tests/fixtures/parcel_master/{label}.parquet")
        join_rate = master["mod_iv_matched"].mean()
        assert 0.90 <= join_rate <= 1.0, f"{label}: implausible join rate {join_rate}"
        # class_group must be "Other" for every unmatched row, and only for rows
        # that are either unmatched or genuinely unmapped -- never left blank/NaN.
        assert master["class_group"].notna().all()


def test_fixture_geometries_valid():
    for label in FIXTURES:
        geoms = gpd.read_file(f"tests/fixtures/parcel_geoms/{label}.gpkg")
        assert len(geoms) > 0
        assert geoms.geometry.is_valid.all(), f"{label}: invalid geometry present"
        assert not geoms.geometry.is_empty.any(), f"{label}: empty geometry present"
        assert str(geoms.crs) == "EPSG:4326"


def test_fixture_master_and_geoms_pin_counts_match():
    for label in FIXTURES:
        master = pd.read_parquet(f"tests/fixtures/parcel_master/{label}.parquet")
        geoms = gpd.read_file(f"tests/fixtures/parcel_geoms/{label}.gpkg")
        assert len(master) == len(geoms), f"{label}: master/geoms row count mismatch"
        assert set(master["pin"]) == set(geoms["pin"]), f"{label}: PIN sets differ between master/geoms"
