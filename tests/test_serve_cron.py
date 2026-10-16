"""Cron matching for the EC2 worker scheduler (no network)."""
from datetime import datetime

from applyforme.serve import _cron_match, _parse_cron, _should_fire


def test_parse_and_match_every_four_hours():
    parts = _parse_cron("0 */4 * * *")
    assert parts is not None
    assert _should_fire(parts, datetime(2026, 10, 17, 0, 0))
    assert _should_fire(parts, datetime(2026, 10, 17, 4, 0))
    assert _should_fire(parts, datetime(2026, 10, 17, 16, 0))
    assert not _should_fire(parts, datetime(2026, 10, 17, 4, 1))
    assert not _should_fire(parts, datetime(2026, 10, 17, 5, 0))


def test_disabled_cron():
    assert _parse_cron("off") is None
    assert _parse_cron("") is None


def test_cron_match_lists_and_ranges():
    assert _cron_match("1,15,30", 15)
    assert _cron_match("10-12", 11)
    assert not _cron_match("10-12", 13)
