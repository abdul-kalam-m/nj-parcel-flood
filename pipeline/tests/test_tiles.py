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


# --- the 11-of-564 boundary gap closed this session --------------------------

def test_normalize_handles_newly_added_abbreviations():
    # Each pair is a real TIGER-vs-MOD-IV mismatch that left a municipality
    # with no boundary geometry (and so no choropleth fill) before these
    # _WORD_CANON/_TYPE_CANON entries were added.
    assert tiles._normalize_name("East Rutherford borough") == tiles._normalize_name("E RUTHERFORD BORO")
    assert tiles._normalize_name("Parsippany-Troy Hills township") == \
        tiles._normalize_name("PARSIPPANY TR HLS TWP")
    assert tiles._normalize_name("Point Pleasant Beach borough") == \
        tiles._normalize_name("PT PLEASANT BEACH BORO")
    assert tiles._normalize_name("South Orange Village township") == \
        tiles._normalize_name("SOUTH ORANGE VILLAGE TW")
    assert tiles._normalize_name("Spring Lake Heights borough") == \
        tiles._normalize_name("SPRING LAKE HEIGHTS BOR")


def test_normalize_does_not_generalize_river_abbreviation():
    # Regression guard for the fix's own near-miss: a general RIVER->RIV word
    # rule was tried and reverted because it broke River Vale/River Edge
    # (MOD-IV stores them as one fused word, "RIVERVALE"/"RIVEREDGE") --
    # "RIVER" must normalize as a literal word, unabbreviated.
    assert tiles._normalize_name("River Vale township") == tiles._normalize_name("RIVERVALE TWP")
    assert tiles._normalize_name("River Edge borough") == tiles._normalize_name("RIVEREDGE BORO")


def test_match_rescues_known_overrides_not_resolvable_by_normalization_alone():
    # Caldwell/North Caldwell/Essex Fells (TIGER says borough, this project's
    # own mun_name says TWP), City of Orange (word order), Lower Alloway(s)
    # Creek (spelling), Upper Saddle River (the one abbreviation gap that
    # isn't safe as a general word rule, see _WORD_CANON's comment) -- none
    # of these are closeable by the general normalizer alone.
    cousub = gpd.GeoDataFrame({
        "NAME": ["Caldwell borough", "North Caldwell borough", "Essex Fells borough",
                 "City of Orange township", "Lower Alloways Creek township",
                 "Upper Saddle River borough"],
        "COUNTY": ["013", "013", "013", "013", "033", "003"],
        "geometry": [_square(i, 0) for i in range(6)],
    }, crs=lib.UTM18N)
    mun_lookup = pd.DataFrame({
        "mun_code": ["0703", "0715", "0706", "0717", "1705", "0263"],
        "mun_name": ["CALDWELL BORO TWP", "NORTH CALDWELL TWP", "ESSEX FELLS TWP",
                     "ORANGE CITY TWP", "LOWER ALLOWAY CREEK TWP", "UPPER SADDLE RIV BORO"],
        "county": ["ESSEX", "ESSEX", "ESSEX", "ESSEX", "SALEM", "BERGEN"],
    })
    result = tiles.match_cousub_to_mun_code(cousub, mun_lookup)
    assert len(result) == 6
    assert set(result["mun_code"]) == {"0703", "0715", "0706", "0717", "1705", "0263"}


def test_match_still_preserves_boro_twp_distinction_after_override_fallback():
    # Regression guard: adding the override fallback must not weaken the
    # general type-word rule for places that aren't in the override table.
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
    assert len(result) == 2
    assert set(result["mun_code"]) == {"0405", "0406"}
