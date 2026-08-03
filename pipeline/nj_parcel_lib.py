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
# FEMA coastal SFHA. NAVD88 (ftUS) height reference. Coastal-only: 14 of NJ's 21
# counties (Atlantic, Bergen, Burlington, Camden, Cape May, Cumberland, Essex,
# Hudson, Mercer, Middlesex, Monmouth, Ocean, Salem, Union) -- the other 7
# (Gloucester, Hunterdon, Morris, Passaic, Somerset, Sussex, Warren) get
# fut_coverage=false per §5.2, exactly as the guide's own partial-coverage
# contingency anticipated. An ArcGIS *item* pointing at this same URL is flagged
# "deprecated" in its metadata, but the underlying MapServer layer itself is live
# and is what NJDEP's own current DCAT catalog (gisdata-njdep.opendata.arcgis.com)
# points to -- treated as a stale item-level label, not a real service issue.
P4_CAFE_SLR5_URL = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Hydrography/MapServer/48"
P4_COASTAL_COUNTIES = [
    "ATLANTIC", "BERGEN", "BURLINGTON", "CAMDEN", "CAPE MAY", "CUMBERLAND",
    "ESSEX", "HUDSON", "MERCER", "MIDDLESEX", "MONMOUTH", "OCEAN", "SALEM", "UNION",
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
             retries: int = 3, timeout: int = 60) -> dict:
    cpath = _cache_path(url, params)
    if cpath.exists() and not force:
        return json.loads(cpath.read_text(encoding="utf-8"))
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
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
