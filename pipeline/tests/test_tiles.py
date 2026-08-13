"""Tests for 07_tiles.py -- offline (no network, no Docker, no files)."""
import importlib

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

import nj_parcel_lib as lib

tiles = importlib.import_module("07_tiles")


# --- _normalize_name: the actual bug this project hit -------------------------

def test_normalize_handles_formatting_differences():
    # hyphen vs space vs nothing, TIGER's full words vs MOD-IV's abbreviations
    assert tiles._normalize_name("Ho-Ho-Kus borough") == tiles._normalize_name("HOHOKUS BORO")
    assert tiles._normalize_name("Peapack and Gladstone borough") == \
        tiles._normalize_name("PEAPACK GLADSTONE BORO")
    assert tiles._normalize_name("Avon-by-the-Sea borough") == \
        tiles._normalize_name("AVON BY THE SEA BORO")
    assert tiles._normalize_name("Mount Laurel township") == tiles._normalize_name("MT LAUREL TWP")
    assert tiles._normalize_name("South Hackensack township") == \
        tiles._normalize_name("SO HACKENSACK TWP")


def test_normalize_dedupes_redundant_doubled_type_suffix():
    # TIGER's "Ventnor City city" -- a real live example, not hypothetical
    assert tiles._normalize_name("Ventnor City city") == tiles._normalize_name("VENTNOR CITY")


def test_normalize_preserves_borough_vs_township_distinction():
    # The actual bug: an earlier version stripped the type word entirely and
    # silently collapsed genuinely distinct, separately-incorporated NJ
    # municipalities (Berlin Boro != Berlin Twp) onto the same key.
    assert tiles._normalize_name("Berlin borough") != tiles._normalize_name("Berlin township")
    assert tiles._normalize_name("Egg Harbor City city") != tiles._normalize_name("Egg Harbor township")
    assert tiles._normalize_name("BERLIN BORO") != tiles._normalize_name("BERLIN TWP")


# --- match_cousub_to_mun_code: no fan-out, unmatched logged not forced --------

def _square(x0, y0, size=1):
    return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])


def test_match_produces_no_fan_out_for_distinct_boro_twp_pairs():
    # Regression test for the exact collision bug: two genuinely distinct
    # municipalities sharing a base name (Boro + Twp) must each get exactly
    # one matched row, never a many-to-many blowup.
    cousub = gpd.GeoDataFrame({
        "NAME": ["Berlin borough", "Berlin township"],
        "COUNTY": ["007", "007"],
        "geometry": [_square(0, 0), _square(1, 0)],
    }, crs=lib.UTM18N)
    mun_lookup = pd.DataFrame({
        "mun_code": ["0405", "0406"],
        "mun_name": ["BERLIN BORO", "BERLIN TWP"],
        "county": ["CAMDEN", "CAMDEN"],
    })
    result = tiles.match_cousub_to_mun_code(cousub, mun_lookup)
    assert len(result) == 2  # not 4 (which a collision-fan-out would produce)
    assert set(result["mun_code"]) == {"0405", "0406"}


def test_match_logs_unmatched_without_dropping_the_matched_rows():
    cousub = gpd.GeoDataFrame({
        "NAME": ["Berlin borough", "Nonexistent Place township"],
        "COUNTY": ["007", "007"],
        "geometry": [_square(0, 0), _square(1, 0)],
    }, crs=lib.UTM18N)
    mun_lookup = pd.DataFrame({
        "mun_code": ["0405"], "mun_name": ["BERLIN BORO"], "county": ["CAMDEN"],
    })
    result = tiles.match_cousub_to_mun_code(cousub, mun_lookup)
    assert len(result) == 1  # the unmatched row is dropped from the *output*...
    assert result.iloc[0]["mun_code"] == "0405"  # ...but the real match still comes through
