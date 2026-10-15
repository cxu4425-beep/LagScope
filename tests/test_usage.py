"""How much data was moved: today, this month, the last week.

The cases that matter: totals land on the local calendar day, survive a
restart, are not lost to a crash mid-write, and are never invented - a gap
while the program was closed stays a gap.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

from lagscope.i18n import tr
from lagscope.models import LatencySample
from lagscope.usage import UsageLedger, format_bytes


def _ts(day: date, hour: int = 12) -> float:
    return datetime(day.year, day.month, day.day, hour).timestamp()


def test_bytes_add_up_per_local_day():
    ledger = UsageLedger()
    today = date.today()
    ledger.add(1_000, 200, _ts(today, 9))
    ledger.add(4_000, 800, _ts(today, 21))
    ledger.add(9_999, 9, _ts(today - timedelta(days=1)))
    assert ledger.today() == (5_000, 1_000)
    assert ledger.day(today - timedelta(days=1)) == (9_999, 9)


def test_the_month_is_the_calendar_month_so_far():
    ledger = UsageLedger()
    first = date.today().replace(day=1)
    ledger.add(100, 10, _ts(first))
    ledger.add(200, 20, _ts(date.today()))
    ledger.add(5_000, 500, _ts(first - timedelta(days=1)))     # last month
    assert ledger.month() == (300, 30)


def test_recent_days_are_listed_oldest_first_with_gaps_as_zero():
    ledger = UsageLedger()
    today = date.today()
    ledger.add(70, 7, _ts(today))
    ledger.add(50, 5, _ts(today - timedelta(days=3)))
    recent = ledger.recent(5)
    assert [entry[0] for entry in recent] == [
        (today - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(4, -1, -1)]
    assert recent[-1][1:] == (70, 7)
    assert recent[1][1:] == (50, 5)
    assert recent[2][1:] == (0, 0)


def test_nothing_negative_or_empty_is_recorded():
    ledger = UsageLedger()
    ledger.add(-500, -1)
    ledger.add(0, 0)
    assert ledger.today() == (0, 0)
    assert not ledger._dirty


def test_it_survives_a_restart(tmp_path):
    path = tmp_path / "usage.json"
    first = UsageLedger(path)
    first.add(123_456, 7_890)
    assert first.flush()
    again = UsageLedger(path)
    assert again.today() == (123_456, 7_890)


def test_counting_before_the_file_is_read_is_kept(tmp_path):
    path = tmp_path / "usage.json"
    saved = UsageLedger(path)
    saved.add(1_000, 100)
    saved.flush()
    ledger = UsageLedger()
    ledger.path = path
    ledger.add(5, 1)
    ledger.load()
    assert ledger.today() == (1_005, 101)


def test_a_damaged_file_starts_over_instead_of_crashing(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("{not json", encoding="utf-8")
    ledger = UsageLedger(path)
    assert ledger.today() == (0, 0)
    path.write_text(json.dumps({"days": {"garbage": [1, 2], "2026-01-01": ["x"]}}),
                    encoding="utf-8")
    assert UsageLedger(path).recent(1)[0][1:] == (0, 0)


def test_a_write_is_atomic(tmp_path):
    path = tmp_path / "usage.json"
    ledger = UsageLedger(path)
    ledger.add(10, 1)
    ledger.flush()
    assert not (tmp_path / "usage.tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_old_days_are_dropped_after_the_retention():
    ledger = UsageLedger(keep_days=40)
    old = date.today() - timedelta(days=60)
    ledger.add(1, 1, _ts(old))
    ledger.add(1, 1)
    ledger._trim()
    assert ledger.day(old) == (0, 0) and ledger.today() == (1, 1)


def test_sizes_read_the_way_an_isp_bills_them():
    assert format_bytes(None) == "--"
    assert format_bytes(0) == "0 B"
    assert format_bytes(820_000) == "820 KB"
    assert format_bytes(14_200_000) == "14.2 MB"
    assert format_bytes(3_412_000_000) == "3.41 GB"


def test_samples_carry_the_bytes_the_speed_probe_saw():
    from lagscope.monitor import MonitorWorker
    from lagscope.config import Config
    from lagscope.probes.netspeed import NetSpeed

    worker = MonitorWorker(Config())
    worker._netspeed.sample = lambda: NetSpeed(up_mbps=1.0, down_mbps=8.0,
                                               up_bytes=250_000, down_bytes=2_000_000,
                                               interval_s=2.0)
    sample = worker._with_netspeed(LatencySample(ok=True, total_ms=10.0))
    assert (sample.down_bytes, sample.up_bytes) == (2_000_000, 250_000)


def test_the_report_shows_today_and_the_month_and_says_what_is_counted():
    from lagscope.report import build_text, usage_rows

    usage = {"today": (1_500_000_000, 200_000_000), "month": (34_000_000_000, 5_100_000_000),
             "recent": [("2026-10-14", 2_000_000_000, 300_000_000)]}
    text = build_text(summary={"hours": 24}, usage=usage)
    assert tr("usage.title") in text and "1.50 GB" in text and "34.0 GB" in text
    assert usage_rows({"today": (0, 0), "month": (0, 0), "recent": []}) == []


def test_the_tray_tooltip_ends_with_todays_usage():
    from lagscope import presentation
    from lagscope.models import KIND_NETWORK

    sample = LatencySample(ok=True, total_ms=12.0, kind=KIND_NETWORK)
    text = presentation.tooltip(sample, "", None, "LagScope", "Today ↓1 GB ↑1 MB")
    assert text.endswith("Today ↓1 GB ↑1 MB")
