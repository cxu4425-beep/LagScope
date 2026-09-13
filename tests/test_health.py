"""The registry of things that are not working, and the probes that report to it.

This exists because of a real two-day failure: `netsh wlan show interfaces`
returned nothing a LagScope build could parse, so every sample was recorded
with no wireless information. The report then said the machine was "probably a
wired connection" - about a laptop that has never had a cable in it - and the
only evidence anywhere was a debug log line. These tests are about that class
of bug: a probe allowed to fail, but never allowed to fail silently.
"""

from __future__ import annotations

import subprocess

import pytest

from lagscope.health import (AUDIO, CONSEQUENCE, DISPLAY, HEALTH, ICMP, WIFI,
                             WINDOW, Degradation, Health)
from lagscope.i18n import tr


def _worker(monitor_module):
    """A worker with only the fields ``_current_wifi`` touches.

    Constructing a real one starts threads and network probes; the wireless
    cache is three attributes.
    """
    worker = monitor_module.MonitorWorker.__new__(monitor_module.MonitorWorker)
    worker._wifi = None
    worker._wifi_at = 0.0
    return worker


@pytest.fixture(autouse=True)
def _clean_registry():
    """The module-level registry is shared; no test may leak into another."""
    HEALTH.clear()
    yield
    HEALTH.clear()


# --------------------------------------------------------------- the registry
def test_a_fault_is_remembered_with_its_reason_and_its_time():
    health = Health()
    assert health.degraded(WIFI, "empty output", now=1000.0) is True
    (item,) = health.current()
    assert item.key == WIFI
    assert item.detail == "empty output"
    assert item.since == 1000.0
    assert health.is_degraded(WIFI)


def test_repeating_the_same_fault_is_not_news_and_does_not_reset_the_clock():
    """The Wi-Fi probe runs every thirty seconds. "Since 14:02" is useful;
    "since a moment ago", forever, is not."""
    health = Health()
    health.degraded(WIFI, "empty output", now=1000.0)
    assert health.degraded(WIFI, "empty output", now=9999.0) is False
    assert health.current()[0].since == 1000.0


def test_a_changed_reason_replaces_the_old_one_but_keeps_the_start_time():
    health = Health()
    health.degraded(WIFI, "OSError: no such file", now=1000.0)
    assert health.degraded(WIFI, "empty output", now=2000.0) is False
    (item,) = health.current()
    assert item.detail == "empty output"     # the current reason, not the first
    assert item.since == 1000.0              # but it has been broken since then


def test_recovery_removes_it_and_a_later_failure_starts_a_new_clock():
    health = Health()
    health.degraded(WIFI, "empty output", now=1000.0)
    assert health.working(WIFI) is True
    assert health.current() == []
    assert health.working(WIFI) is False     # nothing to report the second time
    health.degraded(WIFI, "empty output", now=5000.0)
    assert health.current()[0].since == 5000.0


def test_the_longest_standing_fault_is_listed_first():
    health = Health()
    health.degraded(DISPLAY, "", now=2000.0)
    health.degraded(WIFI, "", now=1000.0)
    health.degraded(AUDIO, "", now=3000.0)
    assert [item.key for item in health.current()] == [WIFI, DISPLAY, AUDIO]


def test_a_runaway_reason_cannot_grow_without_limit():
    """A detail is a line in a report, not a traceback."""
    health = Health()
    health.degraded(WIFI, "x" * 5000)
    assert len(health.current()[0].detail) <= 200


def test_every_declared_fault_says_what_it_costs_in_every_language():
    from lagscope.i18n import STRINGS

    for key, consequence in CONSEQUENCE.items():
        assert key in STRINGS, key
        assert consequence in STRINGS, consequence
        assert Degradation(key=key).consequence_key == consequence
        assert tr(consequence).strip(), consequence


def test_the_serialised_form_carries_everything_a_renderer_needs():
    item = Degradation(key=WIFI, detail="empty output", since=1000.0)
    assert item.as_dict() == {"key": WIFI, "detail": "empty output",
                              "since": 1000.0, "consequence": CONSEQUENCE[WIFI]}


# ------------------------------------------------- the probes that report in
def test_the_wifi_probe_reports_when_it_cannot_read_anything(monkeypatch):
    """The actual two-day bug: a reading that comes back empty."""
    from lagscope import monitor as monitor_module

    monkeypatch.setattr(monitor_module, "wifi_info", lambda: None)
    assert _worker(monitor_module)._current_wifi() is None
    assert HEALTH.is_degraded(WIFI)
    assert "empty" in HEALTH.current()[0].detail


def test_the_wifi_probe_reports_the_exception_it_hit(monkeypatch):
    from lagscope import monitor as monitor_module

    def explode():
        raise OSError("netsh is not on PATH")

    monkeypatch.setattr(monitor_module, "wifi_info", explode)
    assert _worker(monitor_module)._current_wifi() is None
    assert HEALTH.is_degraded(WIFI)
    assert "netsh is not on PATH" in HEALTH.current()[0].detail


def test_a_working_wifi_probe_clears_an_earlier_report(monkeypatch):
    from lagscope import monitor as monitor_module
    from lagscope.probes.path import WifiInfo

    HEALTH.degraded(WIFI, "empty output")
    monkeypatch.setattr(monitor_module, "wifi_info",
                        lambda: WifiInfo(ssid="x", signal_pct=70))
    assert _worker(monitor_module)._current_wifi() is not None
    assert not HEALTH.is_degraded(WIFI)


def test_the_display_probe_reports_when_it_is_guessing_60hz():
    """Nothing measured and nothing reported: 16.67 ms goes into the headline
    total looking exactly like an observation."""
    from lagscope.probes.display import DisplayProbe

    probe = DisplayProbe(fallback_hz=0.0)
    assert probe.frame_period_ms() == 16.67
    assert HEALTH.is_degraded(DISPLAY), "a guessed refresh rate went unreported"
    assert "60" in HEALTH.current()[0].detail


def test_a_reported_refresh_rate_is_nobody_s_business():
    """Not measured but reported by the system is fine, not a fault."""
    from lagscope.probes.display import DisplayProbe

    probe = DisplayProbe()
    probe.refresh_hz = 144.0
    probe.frame_period_ms()
    assert not HEALTH.is_degraded(DISPLAY)


def test_a_measured_period_clears_an_earlier_guess():
    from lagscope.probes.display import DisplayProbe

    probe = DisplayProbe(fallback_hz=0.0)
    probe.frame_period_ms()
    assert HEALTH.is_degraded(DISPLAY)
    probe.refresh_hz = 60.0
    probe.frame_period_ms()
    assert not HEALTH.is_degraded(DISPLAY)


def test_ping_being_missing_is_reported_but_a_filtered_host_is_not(monkeypatch):
    """A host that drops ICMP is normal. `ping` not existing is not."""
    from lagscope.probes import network

    monkeypatch.setattr(network.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            FileNotFoundError("ping")))
    assert network.icmp_ping_ms("1.1.1.1") is None
    assert HEALTH.is_degraded(ICMP)

    HEALTH.clear()
    monkeypatch.setattr(
        network.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", ""))
    assert network.icmp_ping_ms("1.1.1.1") is None
    assert not HEALTH.is_degraded(ICMP), "a host filtering ICMP is not a fault"


def test_a_successful_ping_clears_an_earlier_report(monkeypatch):
    from lagscope.probes import network

    HEALTH.degraded(ICMP, "ping: FileNotFoundError")
    monkeypatch.setattr(
        network.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.3 ms", ""))
    assert network.icmp_ping_ms("1.1.1.1") == pytest.approx(12.3)
    assert not HEALTH.is_degraded(ICMP)


def test_window_following_reports_when_the_platform_cannot_list_windows():
    """Follow mode set on a machine that cannot do it is a silently ignored
    setting: the card sits in a corner and the checkbox still looks on."""
    from lagscope.ui import anchor

    finder = anchor.WindowFinder()
    assert finder.available is False
    assert WINDOW in CONSEQUENCE
    assert tr(CONSEQUENCE[WINDOW]).strip()
