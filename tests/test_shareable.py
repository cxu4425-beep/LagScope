"""Nothing that is made to be pasted somewhere may carry the Wi-Fi name, the
access point's hardware address or the Windows account name.

Found on a real dump: the diagnostics copied from the tray menu carried all
three - the network name and band, the router's MAC address, and
C:\\Users\\<account>\\AppData\\... - in a block whose only purpose is to be
pasted into a bug report.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from lagscope.history import Bucket
from lagscope.models import LatencySample
from lagscope.patterns import by_link
from lagscope.probes import appnet
from lagscope.probes.path import (public_link_label, public_link_labels,
                                  split_link_key)

PLANTED_SSID = "Planted-Net-7Q"
PLANTED_BSSID = "d0:ee:47:aa:bb:cc"


# ------------------------------------------------------------------ labels
def test_the_band_is_read_from_the_end_of_the_key():
    assert split_link_key("Home (5 GHz)") == ("Home", "5")
    assert split_link_key("Home (2.4 GHz)") == ("Home", "2.4")
    # A network name can contain anything - including what looks like a band.
    assert split_link_key("My (2.4 GHz) Net (5 GHz)") == ("My (2.4 GHz) Net", "5")
    assert split_link_key("Home2.4") == ("Home2.4", "")
    assert split_link_key("") == ("", "")


def test_one_router_on_two_bands_keeps_one_letter():
    labels = public_link_labels(["Home (5 GHz)", "Home (2.4 GHz)", "Cafe (5 GHz)"])
    assert labels == {"Home (5 GHz)": "Wi-Fi A (5 GHz)",
                      "Home (2.4 GHz)": "Wi-Fi A (2.4 GHz)",
                      "Cafe (5 GHz)": "Wi-Fi B (5 GHz)"}


def test_a_lone_link_keeps_only_its_band():
    assert public_link_label(f"{PLANTED_SSID} (5 GHz)") == "Wi-Fi (5 GHz)"
    assert public_link_label(PLANTED_SSID) == "Wi-Fi"
    assert public_link_label("") == ""


def _minute(link, avg, start):
    return Bucket(start=start, count=30, ok=30, avg_ms=avg, p95_ms=avg,
                  link=link, signal_pct=70)


def test_the_comparison_never_names_a_network_and_the_most_used_is_a():
    buckets = [_minute(f"Other (2.4 GHz)", 90.0, 60.0 * i) for i in range(3)]
    buckets += [_minute(f"{PLANTED_SSID} (5 GHz)", 30.0, 60.0 * (i + 10))
                for i in range(9)]
    stats = by_link(buckets)
    hosts = {item.host for item in stats}
    assert hosts == {"Wi-Fi A (5 GHz)", "Wi-Fi B (2.4 GHz)"}
    assert not any(PLANTED_SSID in host for host in hosts)


def test_the_report_carries_no_network_name(tmp_path):
    from lagscope.report import build_html, build_text

    buckets = [_minute(f"{PLANTED_SSID} (2.4 GHz)", 90.0, 60.0 * i) for i in range(10)]
    buckets += [_minute(f"{PLANTED_SSID} (5 GHz)", 30.0, 60.0 * (i + 20))
                for i in range(10)]
    links = by_link(buckets)
    text = build_text(summary={"hours": 24}, links=links)
    html = build_html(summary={"hours": 24}, links=links, buckets=buckets)
    for output in (text, html):
        assert PLANTED_SSID not in output
        assert "Wi-Fi A (5 GHz)" in output


# -------------------------------------------------------------- diagnostics
def test_the_last_sample_in_the_dump_keeps_the_band_and_nothing_else():
    from lagscope.app import _shareable_sample

    sample = LatencySample(ok=True, total_ms=20.0, link=f"{PLANTED_SSID} (5 GHz)",
                           bssid=PLANTED_BSSID, signal_pct=82)
    data = _shareable_sample(sample)
    flat = json.dumps(data)
    assert PLANTED_SSID not in flat and PLANTED_BSSID not in flat
    assert data["link"] == "Wi-Fi (5 GHz)"
    assert data["signal_pct"] == 82            # how good it is is the useful part
    assert _shareable_sample(None) is None


def test_the_whole_dump_carries_no_name_no_address_and_no_account(monkeypatch):
    """The real method, end to end, with every field it reads stubbed."""
    from lagscope import app as app_module

    account = "PlantedAccount"
    monkeypatch.setattr(app_module, "app_config_dir",
                        lambda: f"C:\\Users\\{account}\\AppData\\Roaming\\LagScope")
    sample = LatencySample(ok=True, total_ms=20.0, link=f"{PLANTED_SSID} (5 GHz)",
                           bssid=PLANTED_BSSID, signal_pct=82)
    fake = SimpleNamespace(
        _stats=type("S", (), {"last": lambda self: sample, "__len__": lambda self: 1,
                              "avg": lambda self: 20.0,
                              "percentile": lambda self, pct: 30.0,
                              "jitter": lambda self: 2.0,
                              "failure_rate": lambda self: 0.0})(),
        _config=SimpleNamespace(language="zh_TW", room_id=0, video_id="",
                                detect=SimpleNamespace(enabled=False),
                                display=SimpleNamespace(frames_in_flight=2.0,
                                                        manual_offset_ms=0.0)),
        _target=None, _status_key="ok", _status_detail="",
        _display=SimpleNamespace(snapshot=lambda *a: {}),
        _events=SimpleNamespace(summary=lambda: {}),
        _ordered_extras=lambda: [], _lines=("", []), _room_info=None,
    )
    dump = app_module.MonitorApplication.diagnostics_text(fake)

    assert PLANTED_SSID not in dump
    assert PLANTED_BSSID not in dump
    assert account not in dump
    payload = json.loads(dump)
    assert "health" in payload            # what is not measured, said up front
    assert payload["last_sample"]["link"] == "Wi-Fi (5 GHz)"


# --------------------------------------------------------- measuring itself
def _conn(pid, ip="203.0.113.9", port=443):
    return SimpleNamespace(pid=pid, raddr=SimpleNamespace(ip=ip, port=port),
                           laddr=None, status="ESTABLISHED", type=1)


def test_the_app_list_does_not_offer_this_program(monkeypatch):
    """Its connections are its own probes, so it sorts near the top of the list
    exactly while it is measuring - which is how it got picked."""
    me = 4242
    monkeypatch.setattr(appnet, "own_process", lambda: ({me}, "LagScope.exe"))
    monkeypatch.setattr(appnet, "_process_names",
                        lambda: {me: "LagScope.exe", 77: "game.exe"})
    monkeypatch.setattr(appnet.psutil, "net_connections",
                        lambda kind="inet": [_conn(me)] * 9 + [_conn(77)])
    names = [app.name for app in appnet.list_apps()]
    assert names == ["game.exe"]


def test_a_saved_target_of_itself_says_so_instead_of_no_connections(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(appnet, "own_process", lambda: ({1}, "LagScope.exe"))
    result = appnet.AppNetProbe().measure("lagscope.exe")
    assert result.error == appnet.SELF_ERROR


def test_running_from_source_does_not_refuse_every_python_program(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(appnet, "own_process", lambda: ({1}, "python.exe"))
    assert appnet.is_self("python.exe") is False


def test_the_self_error_has_a_sentence_in_every_language():
    from lagscope.app import ERROR_MESSAGES
    from lagscope.i18n import STRINGS

    assert ERROR_MESSAGES[appnet.SELF_ERROR] == "status.self"
    assert "status.self" in STRINGS
