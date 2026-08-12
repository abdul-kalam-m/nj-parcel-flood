"""Tests for 01_parcel_core.py -- pure logic offline, plus checks against the
committed mini-state fixture (no network needed, real small-scale data)."""
import geopandas as gpd
import pandas as pd

import importlib
core = importlib.import_module("01_parcel_core")

FIXTURES = ("atlantic-city", "bound-brook", "mendham-boro")


def test_class_group_known_codes():
    assert core.class_group("2") == ("Residential", False)
    assert core.class_group("4C") == ("Residential", False)
    assert core.class_group("4A") == ("Commercial", False)
    assert core.class_group("4B") == ("Industrial", False)
    assert core.class_group("3A") == ("Farm/Agricultural", False)
    assert core.class_group("1") == ("Vacant", False)
    assert core.class_group("15D") == ("Public/Institutional/Exempt", False)


def test_class_group_unmapped_goes_to_other_and_is_flagged():
    # §5.4: unmapped codes go to Other with a logged count, never silently dropped --
    # the "unmapped" flag is what 01_parcel_core.py uses to actually log them.
    group, unmapped = core.class_group("99Z")
    assert group == "Other"
    assert unmapped is True


def test_class_group_blank_code_treated_as_unmapped():
    group, unmapped = core.class_group("")
    assert group == "Other"
    assert unmapped is True
    group, unmapped = core.class_group(None)
    assert unmapped is True


def test_exempt_codes_match_class_group_public_institutional():
    # §5.1 wants an "exempt flag" -- must line up with the same 15A-15F set §5.4
    # maps to Public/Institutional/Exempt, not a separately-drifting list.
    for code in core.EXEMPT_CODES:
        assert core.CLASS_GROUPS[code] == "Public/Institutional/Exempt"


def test_fixture_files_exist_and_are_privacy_clean():
    forbidden = {"owner_name", "owner_mailing", "st_address", "city_state",
                 "zip_code", "zip5", "zip_plus4"}
    for label in FIXTURES:
        master = pd.read_parquet(f"tests/fixtures/parcel_master/{label}.parquet")
        assert len(master) > 0
        cols = {c.lower() for c in master.columns}
        assert not (cols & forbidden), f"{label}: privacy-forbidden column present: {cols & forbidden}"
        assert master["pin"].duplicated().sum() == 0, f"{label}: duplicate PINs"


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
