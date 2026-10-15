"""How a sample is shown: the scale it is coloured on, the rows under it, the
tray's hover text.

The failure these guard against was quiet: every surface used the stream
thresholds (green up to two seconds), so a 300 ms ping was shown green, and a
DNS side watch at 180 ms looked as healthy as one at 8 ms.
"""

from __future__ import annotations

from lagscope import presentation
from lagscope.config import Config
from lagscope.history import Bucket
from lagscope.i18n import tr
from lagscope.models import (
    KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, LatencySample, RollingStats,
)


def _thresholds():
    return Config().thresholds


def test_a_bad_ping_is_not_green():
    t = _thresholds()
    for kind in (KIND_NETWORK, KIND_APP, KIND_TARGET):
        assert presentation.level(20.0, t, kind) == "good"
        assert presentation.level(120.0, t, kind) == "warn"
        assert presentation.level(300.0, t, kind) == "bad"


def test_a_stream_keeps_its_own_scale():
    t = _thresholds()
    assert presentation.level(1500.0, t, KIND_LIVE) == "good"
    assert presentation.level(4000.0, t, KIND_VIDEO) == "warn"
    assert presentation.level(9000.0, t, KIND_LIVE) == "bad"


def test_nothing_measured_is_unknown_not_green():
    assert presentation.level(None, _thresholds(), KIND_NETWORK) == "unknown"


def test_the_network_scale_is_saved_and_sanitised():
    config = Config()
    config.thresholds.net_good_ms = 200.0
    config.thresholds.net_warn_ms = 50.0          # below green: impossible
    config.sanitized()
    assert config.thresholds.net_warn_ms >= config.thresholds.net_good_ms


def test_a_chart_is_coloured_by_what_it_mostly_shows():
    net = [Bucket(start=60.0 * i, kind=KIND_NETWORK) for i in range(8)]
    live = [Bucket(start=60.0 * i, kind=KIND_LIVE) for i in range(3)]
    assert presentation.dominant_kind(net + live) == KIND_NETWORK
    # Minutes from before the kind was recorded can only have been live.
    assert presentation.dominant_kind([Bucket(start=0.0)]) == KIND_LIVE
    assert presentation.dominant_kind([]) == KIND_NETWORK


def _stats(*oks):
    stats = RollingStats(50)
    for ok in oks:
        stats.append(LatencySample(ok=ok, total_ms=20.0 if ok else None, kind=KIND_NETWORK))
    return stats


def test_internet_rows_are_speed_and_loss_not_a_display_estimate():
    sample = LatencySample(ok=True, total_ms=14.0, network_ms=14.0, display_ms=33.0,
                           down_mbps=48.3, up_mbps=1.9, kind=KIND_NETWORK)
    rows = dict(presentation.breakdown_rows(sample, _stats(True, True, True, False)))
    assert rows[tr("label.down")] == "48.3 Mbps"
    assert rows[tr("label.up")] == "1.9 Mbps"
    assert rows[tr("label.loss")] == "25%"
    assert tr("label.display") not in rows


def test_an_app_also_says_how_many_connections_it_has():
    sample = LatencySample(ok=True, total_ms=30.0, kind=KIND_APP, connections=6)
    labels = [label for label, _ in presentation.breakdown_rows(sample)]
    assert labels[0] == tr("label.connections")
    assert tr("label.down") in labels and tr("label.loss") in labels


def test_a_stream_still_shows_where_its_delay_comes_from():
    sample = LatencySample(ok=True, total_ms=2500.0, network_ms=40.0, stream_ms=2400.0,
                           display_ms=33.0, kind=KIND_LIVE)
    labels = [label for label, _ in presentation.breakdown_rows(sample, None, 150.0)]
    assert labels == [tr("label.network"), tr("label.stream"), tr("label.display"),
                      tr("label.audio")]


def test_no_samples_yet_is_dashes_not_zero_loss():
    rows = dict(presentation.breakdown_rows(None, RollingStats(10)))
    assert rows[tr("label.loss")] == "--"


def test_the_tray_tooltip_for_the_internet_says_speed_and_loss():
    sample = LatencySample(ok=True, total_ms=14.0, title="Cloudflare 1.1.1.1",
                           down_mbps=48.3, up_mbps=1.9, kind=KIND_NETWORK)
    text = presentation.tooltip(sample, "", _stats(True, True), "LagScope")
    assert "Cloudflare 1.1.1.1" in text and "14 ms" in text
    assert "48.3 Mbps" in text and "1.9 Mbps" in text and "0%" in text


def test_the_tray_tooltip_for_a_stream_keeps_its_breakdown():
    sample = LatencySample(ok=True, total_ms=2500.0, network_ms=40.0, stream_ms=2400.0,
                           display_ms=33.0, kind=KIND_LIVE, title="Room 1")
    text = presentation.tooltip(sample, "", None, "LagScope")
    assert "2.50 s" in text and "40 ms" in text


def test_the_internet_anchor_is_named_not_shown_as_an_address_and_port():
    sample = LatencySample(ok=True, total_ms=14.0, network_ms=14.0, kind=KIND_NETWORK,
                           host="1.1.1.1:443", title="Cloudflare 1.1.1.1", rtt_to_edge=True)
    line = presentation.server_line(sample)
    assert line.startswith("Cloudflare 1.1.1.1") and ":443" not in line


def test_an_app_server_is_still_shown_by_address():
    sample = LatencySample(ok=True, total_ms=30.0, network_ms=30.0, kind=KIND_APP,
                           host="203.0.113.9:27015", title="game.exe", rtt_to_edge=True)
    assert presentation.server_line(sample).startswith("203.0.113.9:27015")
