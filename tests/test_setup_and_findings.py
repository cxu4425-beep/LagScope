"""The first-run answers, the DNS segment, and "why did it break".

The wizard is a Qt dialog, but the part worth testing is the translation from
four radio buttons into a config, which is plain data.
"""

import math
import time

from lagscope.config import Config
from lagscope.history import History
from lagscope.i18n import tr
from lagscope.models import LatencySample
from lagscope.probes import path
from lagscope.probes.path import DNS_SLOW_MS, PathReport, PingStats, dns_ms, verdict
from lagscope.report import build_html, build_text, finding_rows


# ------------------------------------------------------------------ DNS
def test_an_address_needs_no_lookup():
    assert dns_ms("8.8.8.8") == 0.0
    assert dns_ms("2001:4860:4860::8888") == 0.0


def test_no_host_and_no_answer_are_both_none():
    assert dns_ms("") is None
    assert dns_ms("this-name-does-not-exist.invalid") is None


def test_a_name_that_resolves_is_timed(monkeypatch):
    monkeypatch.setattr(path.socket, "getaddrinfo", lambda *args, **kwargs: [])
    elapsed = dns_ms("example.com")
    assert elapsed is not None and elapsed >= 0.0


def test_a_slow_resolver_is_named_when_the_path_is_otherwise_fine():
    report = PathReport(
        target="example.com",
        gateway="192.168.1.1",
        gateway_stats=PingStats(host="192.168.1.1", sent=5, received=5, avg_ms=2.0),
        target_stats=PingStats(host="example.com", sent=5, received=5, avg_ms=30.0),
        dns_ms=DNS_SLOW_MS + 50,
    )
    assert verdict(report)[0] == "verdict.dns"


def test_a_broken_path_outranks_a_slow_lookup():
    """A slow lookup is a symptom of a bad line, so the line is reported first."""
    report = PathReport(
        target="example.com",
        gateway="192.168.1.1",
        gateway_stats=PingStats(host="192.168.1.1", sent=5, received=5, avg_ms=90.0),
        target_stats=PingStats(host="example.com", sent=5, received=5, avg_ms=200.0),
        dns_ms=DNS_SLOW_MS + 500,
    )
    assert verdict(report)[0] in ("verdict.home", "verdict.wifi")


def test_a_quick_lookup_is_not_worth_mentioning():
    report = PathReport(
        target="example.com",
        gateway="192.168.1.1",
        gateway_stats=PingStats(host="192.168.1.1", sent=5, received=5, avg_ms=2.0),
        target_stats=PingStats(host="example.com", sent=5, received=5, avg_ms=30.0),
        dns_ms=12.0,
    )
    assert verdict(report)[0] == "verdict.ok"


# ------------------------------------------------------- automatic findings
def _history(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = math.floor(time.time() / 60) * 60 - 5 * 60
    for index in range(5):
        history.add(LatencySample(ts=base + index * 60, total_ms=100.0, ok=True))
    return history, base


def test_a_verdict_lands_on_the_minute_the_check_ran_in(tmp_path):
    history, base = _history(tmp_path)
    history.note_verdict("verdict.wifi", "38 ms", ts=base + 60)

    rows = {row.start: row for row in history.buckets()}
    assert rows[base + 60].verdict == "verdict.wifi"
    assert rows[base + 60].verdict_detail == "38 ms"
    assert rows[base].verdict == ""


def test_a_check_that_finishes_after_its_minute_still_lands_in_it(tmp_path):
    """Three pings take seconds, so the answer often arrives a minute later."""
    history, base = _history(tmp_path)
    history.note_verdict("verdict.isp", "", ts=base + 120)

    rows = {row.start: row for row in history.buckets()}
    assert rows[base + 120].verdict == "verdict.isp"


def test_an_empty_verdict_is_not_recorded(tmp_path):
    history, base = _history(tmp_path)
    history.note_verdict("", "nothing", ts=base)
    assert all(not row.verdict for row in history.buckets())


def test_findings_survive_a_restart(tmp_path):
    path_ = tmp_path / "h.json"
    history = History(path_, bucket_s=60)
    base = math.floor(time.time() / 60) * 60 - 300
    history.add(LatencySample(ts=base, total_ms=100.0, ok=True))
    history.note_verdict("verdict.loss", "9%", ts=base)
    history.close()

    restored = History(path_, bucket_s=60)
    assert restored.findings()[0]["verdict"] == "verdict.loss"
    assert restored.findings()[0]["detail"] == "9%"


def test_old_rows_without_a_verdict_column_still_load(tmp_path):
    """A history file written by 3.5 has twelve columns, not fourteen."""
    import json

    path_ = tmp_path / "h.json"
    now = math.floor(time.time() / 60) * 60 - 120
    old_row = [now, 3, 3, 100.0, 90.0, 110.0, 108.0, 5.0, 0, 0, "live", "room 42"]
    path_.write_text(json.dumps({"version": 1, "buckets": [old_row]}), encoding="utf-8")

    rows = History(path_).buckets()
    assert len(rows) == 1 and rows[0].verdict == "" and rows[0].label == "room 42"


def test_findings_are_newest_first_and_capped(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = math.floor(time.time() / 60) * 60 - 20 * 60
    for index in range(20):
        history.add(LatencySample(ts=base + index * 60, total_ms=100.0, ok=True))
        history.note_verdict("verdict.wifi", str(index), ts=base + index * 60)

    found = history.findings(limit=5)
    assert len(found) == 5
    assert [entry["detail"] for entry in found] == ["19", "18", "17", "16", "15"]


def test_the_report_shows_what_broke_and_when(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = math.floor(time.time() / 60) * 60 - 120
    history.add(LatencySample(ts=base, total_ms=100.0, ok=True))
    history.note_event("stall")
    history.note_verdict("verdict.wifi", "38 ms", ts=base)

    findings = history.findings()
    document = build_html(buckets=history.buckets(24.0), summary=history.summary(24.0),
                          auto_findings=findings)
    text = build_text(summary=history.summary(24.0), auto_findings=findings)

    assert tr("report.findings") in document and tr("verdict.wifi") in document
    assert tr("report.findings") in text and tr("verdict.wifi") in text


def test_no_automatic_checks_means_no_section(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    history.add(LatencySample(ts=time.time(), total_ms=100.0, ok=True))
    document = build_html(buckets=history.buckets(24.0), summary=history.summary(24.0),
                          auto_findings=history.findings())
    assert tr("report.findings") not in document


def test_finding_rows_are_readable_pairs():
    rows = finding_rows([{"start": 1_700_000_000, "verdict": "verdict.ok",
                          "detail": "", "stalls": 2, "spikes": 1}])
    assert rows[0][1] == tr("verdict.ok")
    assert rows[0][2] == 3                       # stalls and spikes together


# ------------------------------------------------------------------ wizard
def _apply(choice, detail="", corner="free", language="auto", updates=True):
    """Mirror of SetupWizard.apply_to for the data it produces."""
    from lagscope.ui.wizard import SetupWizard

    config = Config()
    dummy = SetupWizard.__new__(SetupWizard)     # no Qt widgets are touched below

    class _Fake:
        def __init__(self, value):
            self._value = value

        def currentData(self):
            return self._value

        def text(self):
            return self._value

        def isChecked(self):
            return bool(self._value)

    dummy.language_combo = _Fake(language)
    dummy.detail_edit = _Fake(detail)
    dummy.corner_combo = _Fake(corner)
    dummy.autostart_check = _Fake(False)
    dummy.update_check = _Fake(updates)
    dummy._selected = lambda: choice
    return SetupWizard.apply_to(dummy, config)


def test_following_what_i_watch_turns_detection_on():
    config = _apply("auto")
    assert config.detect.enabled is True
    assert config.setup_done is True


def test_picking_a_program_switches_to_app_mode():
    config = _apply("app", detail="RobloxPlayerBeta.exe")
    assert config.detect.enabled is False
    assert config.manual_kind == "app"
    assert config.app_name == "RobloxPlayerBeta.exe"
    assert config.app_follow_foreground is False


def test_an_empty_program_name_means_follow_the_foreground():
    config = _apply("app", detail="")
    assert config.app_follow_foreground is True


def test_picking_an_address_switches_to_target_mode():
    config = _apply("target", detail="8.8.8.8")
    assert config.manual_kind == "target" and config.target_host == "8.8.8.8"


def test_a_corner_pins_the_overlay_and_free_leaves_it_draggable():
    assert _apply("auto", corner="free").overlay.anchor_mode == "free"
    pinned = _apply("auto", corner="bottom-left")
    assert pinned.overlay.anchor_mode == "screen"
    assert pinned.overlay.corner == "bottom-left"


def test_the_update_question_is_carried_through():
    assert _apply("auto", updates=False).updates.enabled is False
    assert _apply("auto", updates=True).updates.enabled is True


def test_the_wizard_is_never_shown_twice():
    config = _apply("auto")
    assert config.setup_done is True
    # Reloading a saved config keeps the flag, which is what suppresses it.
    assert Config.from_dict(config.to_dict()).setup_done is True


# ------------------------------------------------------------------ wizard
def test_the_wizard_defaults_to_the_internet_and_adds_the_router(monkeypatch):
    """Pressing Start without reading anything must give a working monitor."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from lagscope.config import Config
    from lagscope.ui import wizard as wizard_module

    QApplication.instance() or QApplication([])
    monkeypatch.setattr("lagscope.probes.path.default_gateway", lambda: "192.168.1.1")
    config = wizard_module.SetupWizard(Config()).apply_to(Config())

    assert config.manual_kind == "network" and not config.detect.enabled
    assert config.setup_done
    assert config.watch_extras[0]["ident"] == "192.168.1.1"


def test_the_router_is_not_added_twice_or_when_there_is_none():
    from lagscope.config import Config
    from lagscope.ui.wizard import add_router

    config = Config()
    assert add_router(config, lambda: "10.0.0.1")
    assert not add_router(config, lambda: "10.0.0.1")
    assert len(config.watch_extras) == 1
    assert not add_router(Config(), lambda: "")
    assert not add_router(Config(), lambda: (_ for _ in ()).throw(OSError("no route")))
