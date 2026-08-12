"""Shared helpers for the NJ Parcel Flood Risk Dashboard pipeline (OPERATING_GUIDE.md §6).

Cached, retried HTTP so every stage is idempotent -- same discipline as the FloodOps
projects' pipelines.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

for _v in ("PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

import requests

# --- paths -------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
REPO = PIPELINE_DIR.parent
RAW = REPO / "data" / "raw"
PROCESSED = REPO / "data" / "processed"
MANIFEST = REPO / "data" / "MANIFEST.json"
ARTIFACTS = REPO / "artifacts"

# --- CRS -----------------------------------------------------------------
WGS84 = 4326
UTM18N = 26918  # working CRS (meters), §4

UA = "nj-parcel-flood/1.0 (portfolio project; ar.abdulkalam.mustaq@gmail.com)"
HEADERS = {"User-Agent": UA}

# --- data sources (verified live 2026-08-02, Phase 0 -- see RECON.md for detail) ---

# P1: statewide parcel + MOD-IV composite. The bulk .gdb.zip on geoapps.nj.gov is
# behind Incapsula bot protection (403 to a plain requests call) -- use the
# NJOGIS-owned hosted FeatureServer instead (query-based ingest, county by county).
# NOT one of the several unofficial re-hosted copies that also show up in ArcGIS
# search results -- this one is owner="NJOGIS", contentStatus="public_authoritative".
P1_PARCELS_ITEM_ID = "533599bbfbaa4748bf39faf1375a8a9c"
P1_PARCELS_URL = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
    "Parcels_Composite_NJ_WM/FeatureServer/0"
)
P1_MAX_RECORD_COUNT = 2000  # server-enforced page size, confirmed via ?f=json

# P3: FEMA NFHL. The guide's originally-assumed hazards.fema.gov/gis/nfhl/rest/...
# path 404s (WebSEAL error page) -- corrected path found 2026-08-02.
P3_NFHL_BASE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
P3_NFHL_FLOOD_ZONES_LAYER = 28  # "Flood Hazard Zones" -- confirmed by full layer list

# P4: NJDEP Tidal Climate Adjusted Flood Elevation (CAFE SLR 5ft) -- confirmed live,
# 54,571 features, single scenario (not multiple SLR increments): +5 ft added to the
# FEMA coastal SFHA. NAVD88 (ftUS) height reference. Coastal-only: 15 of NJ's 21
# counties (Atlantic, Bergen, Burlington, Camden, Cape May, Cumberland, Essex,
# Gloucester, Hudson, Mercer, Middlesex, Monmouth, Ocean, Salem, Union) -- the other
# 6 (Hunterdon, Morris, Passaic, Somerset, Sussex, Warren) get fut_coverage=false
# per §5.2, exactly as the guide's own partial-coverage contingency anticipated.
# CORRECTION 2026-08-03 (Phase 2): the Phase 0 list (14 counties, no Gloucester) was
# transcribed from the ArcGIS item's own description text, which is wrong/stale --
# querying the layer's actual COUNTY field directly shows Gloucester present, and
# substantially so (2,000 features returned for Gloucester alone, hitting the
# pagination cap -- not a sliver). Lesson: prefer querying the data itself over
# trusting a provider's prose description, even for something that sounds like a
# simple factual list. An ArcGIS *item* pointing at this same URL is flagged
# "deprecated" in its metadata, but the underlying MapServer layer itself is live
# and is what NJDEP's own current DCAT catalog (gisdata-njdep.opendata.arcgis.com)
# points to -- treated as a stale item-level label, not a real service issue.
P4_CAFE_SLR5_URL = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Hydrography/MapServer/48"
P4_COASTAL_COUNTIES = [
    "ATLANTIC", "BERGEN", "BURLINGTON", "CAMDEN", "CAPE MAY", "CUMBERLAND",
    "ESSEX", "GLOUCESTER", "HUDSON", "MERCER", "MIDDLESEX", "MONMOUTH", "OCEAN",
    "SALEM", "UNION",
]

# P6: OpenFEMA FIMA NFIP Redacted Claims. CONFIRMED UNAVAILABLE 2026-08-02: the
# live query endpoint returns HTTP 503 ("FEMA.gov is experiencing technical
# difficulties"); the dataset-metadata endpoint (a different, working endpoint)
# confirms lastRefresh 2025-12-19 and describes bulk CSV/parquet exports as the
# distribution mechanism, but those bulk URLs 403 (Akamai) to a plain requests
# call too. Independently corroborated by public reporting that FimaNfipClaims/
# FimaNfipPolicies access was suspended. Treat as unavailable until Phase 1/2
# re-check -- guide's own fallback applies (§5.3: redistribute C_loss's weight,
# record the variant in meta.json). Do not build around a retry-until-it-works
# assumption; this needs a human check-in if it matters before launch.
P6_CLAIMS_METADATA_URL = "https://www.fema.gov/api/open/v1/OpenFemaDataSets"
P6_CLAIMS_QUERY_URL = "https://www.fema.gov/api/open/v2/FimaNfipClaims"
P6_STATUS_KNOWN_UNAVAILABLE = True

# NJ county name (as stored in the parcel composite's COUNTY field) -> standard FIPS
# code, for {fips}.parquet/{fips}.gpkg file naming (§6.3/§6.5). Standard, stable
# public reference data -- not independently re-verified per-county the way the live
# services above were, but low risk of drift.
# NJ's standard 2-digit municipal-code county prefix (01=Atlantic .. 21=Warren,
# alphabetical -- confirmed empirically against real records, 2026-08-03, not just
# assumed from the well-known convention). Load-bearing: the parcel composite's own
# COUNTY/MUN_NAME text fields are NULL for any parcel that never matched a MOD-IV
# record (confirmed live: 405,573 statewide, ~11.7% -- these are real parcel
# geometries with real PIN/block/lot, just no assessment data joined, plausibly
# condo sub-units and new construction not yet on the tax roll given the block/lot
# patterns observed). Filtering by COUNTY='X' silently drops all of them, which
# would have made the join-rate QA gate (§12.1.2, >=97%) tautologically read 100%
# (only ever measuring completeness among records that already required a
# successful join to be found at all) while the true statewide rate was ~88%.
# PCL_MUN is populated from the base parcel layer, before/independent of any MOD-IV
# join, so filtering on its prefix instead is what actually captures every parcel.
COUNTY_PREFIX: dict[str, str] = {
    "ATLANTIC": "01", "BERGEN": "02", "BURLINGTON": "03", "CAMDEN": "04",
    "CAPE MAY": "05", "CUMBERLAND": "06", "ESSEX": "07", "GLOUCESTER": "08",
    "HUDSON": "09", "HUNTERDON": "10", "MERCER": "11", "MIDDLESEX": "12",
    "MONMOUTH": "13", "MORRIS": "14", "OCEAN": "15", "PASSAIC": "16",
    "SALEM": "17", "SOMERSET": "18", "SUSSEX": "19", "UNION": "20", "WARREN": "21",
}

COUNTY_FIPS: dict[str, str] = {
    "ATLANTIC": "001", "BERGEN": "003", "BURLINGTON": "005", "CAMDEN": "007",
    "CAPE MAY": "009", "CUMBERLAND": "011", "ESSEX": "013", "GLOUCESTER": "015",
    "HUDSON": "017", "HUNTERDON": "019", "MERCER": "021", "MIDDLESEX": "023",
    "MONMOUTH": "025", "MORRIS": "027", "OCEAN": "029", "PASSAIC": "031",
    "SALEM": "033", "SOMERSET": "035", "SUSSEX": "037", "UNION": "039",
    "WARREN": "041",
}

# P7: Census TIGERweb -- same service family as the FloodOps projects.
TIGERWEB_STATE_COUNTY = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer"
TIGERWEB_TRACTS = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer"
STATE_FIPS = "34"  # New Jersey

# P8: NJ statewide geocoder. Note the *_cascade variant some pages advertise
# (Addr_NJ_cascade) 404s -- this is the real, live service name.
P8_GEOCODER_URL = "https://geo.nj.gov/arcgis/rest/services/Tasks/NJ_Geocode/GeocodeServer"

# P9: OpenFreeMap vector basemap tiles (same as the FloodOps V2 web app pattern).
P9_BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"


# --- cached HTTP ---------------------------------------------------------
def _cache_path(url: str, params: dict | None) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    h = hashlib.sha256(key.encode()).hexdigest()[:24]
    return RAW / "_http_cache" / f"{h}.json"


def get_json(url: str, params: dict | None = None, force: bool = False,
             retries: int = 3, timeout: int = 60, backoff_base: float = 1.5) -> dict:
    """backoff_base controls retry spacing (backoff_base * attempt seconds).
    Some hosts (e.g. mapsdep.nj.gov -- confirmed live, §4 P4 note: an older,
    ArcGIS-item-flagged-deprecated NJDEP server) return HTTP 200 with an HTML
    bot-challenge page instead of JSON once a request budget is exceeded, which
    looks the same as a transient error here but needs a much longer cooldown
    than the default 1.5/3/4.5s backoff to actually clear -- pass a larger
    backoff_base for those, rather than raising the default for every source."""
    cpath = _cache_path(url, params)
    if cpath.exists() and not force:
        return json.loads(cpath.read_text(encoding="utf-8"))
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # ArcGIS REST commonly reports its own server-side errors as a
            # {"error": {...}} JSON body under an HTTP 200 status (confirmed live,
            # 2026-08-03, P4 note in 02_flood_layers.py) -- raise_for_status() never
            # catches this since the status code itself is fine. Found via a real,
            # silent data-loss bug: a batch that failed this way produced 0 rows and
            # 0 exceptions, so a caller's own bisection/retry logic never triggered.
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(f"ArcGIS error payload (HTTP {r.status_code}): {data['error']}")
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(backoff_base * (attempt + 1))
    raise RuntimeError(f"GET JSON failed after {retries}: {url} params={params}: {last}")


def check_url(url: str, params: dict | None = None, timeout: int = 30) -> dict:
    """Non-raising status probe for recon -- returns status info instead of throwing,
    since Phase 0's whole job is to find out what's actually reachable right now."""
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        ok = r.status_code == 200
        is_json = False
        detail = None
        if ok:
            try:
                r.json()
                is_json = True
            except Exception:  # noqa: BLE001
                detail = f"200 but not JSON (len={len(r.content)})"
        return {"ok": ok and is_json, "status_code": r.status_code, "detail": detail}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "detail": str(e)}


def esri_rings_to_geom(rings: list):
    """Convert an esri-JSON polygon's `rings` array to a shapely (Multi)Polygon.

    Needed for FEMA's NFHL service (§4 P3): its Flood Hazard Zones layer 500s on
    `f=geojson` (confirmed live, 2026-08-03 -- an older federal ArcGIS server that
    doesn't support the same output formats as the modern NJOGIS/Esri-hosted
    services this pipeline otherwise uses), so P3 must be fetched as `f=json` and
    converted manually rather than relying on shapely.geometry.shape(). Standard
    esri convention: a clockwise ring starts a new exterior polygon; a
    counter-clockwise ring is a hole in the preceding exterior.
    """
    from shapely.geometry import MultiPolygon, Polygon
    polys = []
    exterior, holes = None, []
    for ring in rings:
        area = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
                   for i in range(len(ring) - 1))
        if area < 0:  # clockwise = new exterior
            if exterior is not None:
                polys.append(Polygon(exterior, holes))
            exterior, holes = ring, []
        else:
            holes.append(ring)
    if exterior is not None:
        polys.append(Polygon(exterior, holes))
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def manifest_add(name: str, source_url: str, local_path: Path | None,
                  license_note: str, extra: dict | None = None) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    entry = {
        "source_url": source_url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "license_note": license_note,
    }
    if local_path is not None and local_path.exists():
        entry["sha256"] = hashlib.sha256(local_path.read_bytes()).hexdigest()
        entry["local_path"] = str(local_path.relative_to(REPO))
    if extra:
        entry.update(extra)
    data[name] = entry
    MANIFEST.write_text(json.dumps(data, indent=2), encoding="utf-8")
