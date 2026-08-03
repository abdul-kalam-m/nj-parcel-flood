"""Offline unit tests for nj_parcel_lib.py's pure/constant logic (no network)."""
import nj_parcel_lib as lib


def test_p4_coastal_counties_count():
    # 14 of NJ's 21 counties have CAFE SLR 5ft coverage (verified live, 2026-08-02) --
    # the other 7 must get fut_coverage=false per §5.2, never silently treated as
    # "no future risk".
    assert len(lib.P4_COASTAL_COUNTIES) == 14
    assert "GLOUCESTER" not in lib.P4_COASTAL_COUNTIES  # inland, correctly excluded
    assert "OCEAN" in lib.P4_COASTAL_COUNTIES  # coastal, correctly included


def test_p1_max_record_count_matches_verified_value():
    assert lib.P1_MAX_RECORD_COUNT == 2000


def test_p6_marked_known_unavailable():
    # Encodes the 2026-08-02 finding so a future session doesn't have to
    # rediscover it from scratch -- re-verify via 00_recon.py before trusting
    # this is still true, don't just trust the constant forever.
    assert lib.P6_STATUS_KNOWN_UNAVAILABLE is True


def test_check_url_handles_unreachable_host_without_raising():
    result = lib.check_url("https://this-host-does-not-exist.invalid/nothing")
    assert result["ok"] is False
    assert result["status_code"] is None
