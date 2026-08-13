"""Offline unit tests for nj_parcel_lib.py's pure/constant logic (no network)."""
import nj_parcel_lib as lib


def test_p4_coastal_counties_count():
    # 15 of NJ's 21 counties have CAFE SLR 5ft coverage (verified against the layer's
    # actual COUNTY field, 2026-08-03 -- corrected from an initial 14-county list
    # transcribed from the provider's prose description, which omitted Gloucester).
    # The other 6 must get fut_coverage=false per §5.2, never silently treated as
    # "no future risk".
    assert len(lib.P4_COASTAL_COUNTIES) == 15
    assert "GLOUCESTER" in lib.P4_COASTAL_COUNTIES  # has real coverage, not a sliver
    assert "OCEAN" in lib.P4_COASTAL_COUNTIES  # coastal, correctly included
    assert "HUNTERDON" not in lib.P4_COASTAL_COUNTIES  # inland, correctly excluded


def test_p1_max_record_count_matches_verified_value():
    assert lib.P1_MAX_RECORD_COUNT == 2000


def test_p6_status_reflects_latest_live_recheck():
    # 2026-08-02: confirmed unavailable (old v2 FimaNfipClaims, HTTP 503).
    # 2026-08-13: re-checked live for Phase 4 -- available again, but under a
    # renamed v3 endpoint (`NfipClaims`, no Fima prefix); the old v2 endpoint
    # is deprecated/frozen, not just temporarily down. This constant (and this
    # test) should track whatever was last actually verified live in either
    # direction -- re-verify via 00_recon.py before trusting it further,
    # don't assume today's answer is permanent either.
    assert lib.P6_STATUS_KNOWN_UNAVAILABLE is False
    assert lib.P6_CLAIMS_QUERY_URL.endswith("/v3/NfipClaims")


def test_check_url_handles_unreachable_host_without_raising():
    result = lib.check_url("https://this-host-does-not-exist.invalid/nothing")
    assert result["ok"] is False
    assert result["status_code"] is None
