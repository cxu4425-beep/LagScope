"""Monitoring any application: throughput, per-app peers, stalls and spikes."""

import time

import pytest

from lagscope.events import SPIKE, STALL, EventLog, Notifier
from lagscope.models import KIND_APP, LatencySample
from lagscope.probes import appnet
from lagscope.probes.appnet import AppNetProbe, Peer, list_apps, peers_for
from lagscope.probes.netspeed import NetSpeedProbe


# ------------------------------------------------------------------- netspeed
class FakeCounters:
    def __init__(self, values):
        self.values = values
        self.calls = 0

    def __call__(self, pernic=True):
        entry = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return entry


def _nic(sent, recv):
    class Entry:
        bytes_sent = sent
        bytes_recv = recv
    return Entry()


def test_first_sample_only_sets_the_baseline(monkeypatch):
    probe = NetSpeedProbe()
    monkeypatch.setattr(appnet.psutil, "net_io_counters",
                        FakeCounters([{"eth0": _nic(1000, 2000)}]))
    assert probe.sample().ok is False


def test_speed_is_the_delta_over_the_interval(monkeypatch):
    probe = NetSpeedProbe()
    counters = FakeCounters([
        {"eth0": _nic(0, 0)},
        {"eth0": _nic(125_000, 1_250_000)},     # 1 Mbit up, 10 Mbit down in 1 s
    ])
    monkeypatch.setattr(appnet.psutil, "net_io_counters", counters)

    probe.sample()
    probe._last_ts -= 1.0                        # pretend a second has passed
    speed = probe.sample()

    assert speed.ok
    assert speed.up_mbps == pytest.approx(1.0, abs=0.02)
    assert speed.down_mbps == pytest.approx(10.0, abs=0.2)


def test_loopback_and_virtual_adapters_are_ignored(monkeypatch):
    probe = NetSpeedProbe()
    counters = FakeCounters([
        {"lo": _nic(0, 0), "docker0": _nic(0, 0), "eth0": _nic(0, 0)},
        {"lo": _nic(10 ** 9, 10 ** 9), "docker0": _nic(10 ** 9, 10 ** 9), "eth0": _nic(125_000, 0)},
    ])
    monkeypatch.setattr(appnet.psutil, "net_io_counters", counters)

    probe.sample()
    probe._last_ts -= 1.0
    speed = probe.sample()

    assert speed.up_mbps == pytest.approx(1.0, abs=0.02)   # only eth0 counted
    assert speed.down_mbps == pytest.approx(0.0, abs=0.01)


def test_a_counter_reset_does_not_report_a_negative_speed(monkeypatch):
    probe = NetSpeedProbe()
    counters = FakeCounters([{"eth0": _nic(10_000, 10_000)}, {"eth0": _nic(5, 5)}])
    monkeypatch.setattr(appnet.psutil, "net_io_counters", counters)

    probe.sample()
    probe._last_ts -= 1.0
    assert probe.sample().ok is False        # re-baselined instead


def test_missing_counters_are_reported_not_raised(monkeypatch):
    probe = NetSpeedProbe()

    def boom(pernic=True):
        raise OSError("no such device")

    monkeypatch.setattr(appnet.psutil, "net_io_counters", boom)
    assert probe.sample().error == "counters unavailable"


# --------------------------------------------------------------------- peers
class FakeConn:
    def __init__(self, pid, ip, port, udp=False):
        import socket as _socket

        self.pid = pid
        self.type = _socket.SOCK_DGRAM if udp else _socket.SOCK_STREAM
        self.raddr = type("Addr", (), {"ip": ip, "port": port})() if ip else None


def _patch_conns(monkeypatch, conns, names):
    monkeypatch.setattr(appnet.psutil, "net_connections", lambda kind="inet": conns)
    monkeypatch.setattr(appnet, "_process_names", lambda: names)


def test_public_servers_rank_above_lan_peers(monkeypatch):
    _patch_conns(monkeypatch, [
        FakeConn(10, "192.168.1.5", 445),
        FakeConn(10, "93.184.216.34", 443),
        FakeConn(10, "93.184.216.34", 443),
    ], {10: "game.exe"})

    peers = peers_for("game.exe")

    assert str(peers[0]) == "93.184.216.34:443"
    assert peers[0].connections == 2
    assert peers[0].is_public and not peers[1].is_public


def test_peers_are_matched_on_a_partial_name(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, "93.184.216.34", 443)], {10: "ValorantGame.exe"})
    assert peers_for("valorant")
    assert peers_for("notrunning") == []


def test_connections_without_a_remote_end_are_skipped(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, None, 0)], {10: "game.exe"})
    assert peers_for("game.exe") == []


def test_apps_are_listed_busiest_first(monkeypatch):
    _patch_conns(monkeypatch, [
        FakeConn(10, "93.184.216.34", 443),
        FakeConn(11, "93.184.216.34", 443),
        FakeConn(11, "93.184.216.35", 443),
    ], {10: "quiet.exe", 11: "busy.exe"})

    apps = list_apps()

    assert [app.name for app in apps] == ["busy.exe", "quiet.exe"]
    assert apps[0].connections == 2


def test_an_unreadable_connection_table_is_not_fatal(monkeypatch):
    def boom(kind="inet"):
        raise PermissionError("root required")

    monkeypatch.setattr(appnet.psutil, "net_connections", boom)
    assert list_apps() == []
    assert peers_for("game.exe") == []


# ------------------------------------------------------------------ app probe
def test_the_busiest_peer_is_timed_over_tcp(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, "93.184.216.34", 443)], {10: "game.exe"})
    monkeypatch.setattr(appnet, "tcp_rtt_ms", lambda ip, port, timeout: 24.0)

    result = AppNetProbe().measure("game.exe")

    assert result.rtt_ms == 24.0 and result.method == "tcp"
    assert str(result.peer) == "93.184.216.34:443" and result.connections == 1


def test_a_udp_server_falls_back_to_ping(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, "93.184.216.34", 7000)], {10: "game.exe"})
    monkeypatch.setattr(appnet, "tcp_rtt_ms", lambda ip, port, timeout: None)
    pings = []
    monkeypatch.setattr(appnet, "icmp_ping_ms",
                        lambda ip, timeout: pings.append(ip) or 31.5)

    probe = AppNetProbe()
    first = probe.measure("game.exe")
    second = probe.measure("game.exe")

    assert first.method == "icmp" and first.rtt_ms == 31.5
    assert second.method == "icmp"
    assert len(pings) == 2          # and TCP is not retried for that peer


def test_an_app_with_no_connections_says_so(monkeypatch):
    _patch_conns(monkeypatch, [], {})
    assert AppNetProbe().measure("game.exe").error == "no-connections"


def test_no_app_selected():
    assert AppNetProbe().measure("").error == "no-app"


def test_a_peer_that_answers_nothing_is_reported(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, "93.184.216.34", 7000)], {10: "game.exe"})
    monkeypatch.setattr(appnet, "tcp_rtt_ms", lambda ip, port, timeout: None)
    monkeypatch.setattr(appnet, "icmp_ping_ms", lambda ip, timeout: None)

    result = AppNetProbe().measure("game.exe")

    assert result.rtt_ms is None and result.peers and result.error == "no-reply"


def test_a_games_udp_server_outranks_its_web_connections(monkeypatch):
    """Roblox and friends hold one UDP socket to the game server and several TCP
    ones to web and CDN endpoints; the game server is the interesting one."""
    _patch_conns(monkeypatch, [
        FakeConn(10, "93.184.216.34", 443),                 # web
        FakeConn(10, "93.184.216.34", 443),                 # web
        FakeConn(10, "93.184.216.35", 443),                 # CDN
        FakeConn(10, "128.116.25.7", 53640, udp=True),      # the actual game server
    ], {10: "RobloxPlayerBeta.exe"})

    peers = peers_for("RobloxPlayerBeta.exe")

    assert peers[0].is_udp and str(peers[0]) == "128.116.25.7:53640"
    assert peers[0].connections == 1                        # despite being the quietest


def test_a_udp_peer_is_pinged_without_trying_a_handshake(monkeypatch):
    _patch_conns(monkeypatch, [FakeConn(10, "128.116.25.7", 53640, udp=True)],
                 {10: "RobloxPlayerBeta.exe"})
    handshakes = []
    monkeypatch.setattr(appnet, "tcp_rtt_ms",
                        lambda ip, port, timeout: handshakes.append(ip) or 1.0)
    monkeypatch.setattr(appnet, "icmp_ping_ms", lambda ip, timeout: 28.0)

    result = AppNetProbe().measure("RobloxPlayerBeta.exe")

    assert result.method == "icmp" and result.rtt_ms == 28.0
    assert handshakes == []          # no timeout wasted on a UDP port


def test_a_udp_server_that_drops_icmp_falls_through_to_the_next_peer(monkeypatch):
    _patch_conns(monkeypatch, [
        FakeConn(10, "128.116.25.7", 53640, udp=True),
        FakeConn(10, "93.184.216.34", 443),
    ], {10: "game.exe"})
    monkeypatch.setattr(appnet, "icmp_ping_ms", lambda ip, timeout: None)
    monkeypatch.setattr(appnet, "tcp_rtt_ms", lambda ip, port, timeout: 19.0)

    result = AppNetProbe().measure("game.exe")

    assert result.method == "tcp" and str(result.peer) == "93.184.216.34:443"


@pytest.mark.parametrize(
    "ip,public",
    [("93.184.216.34", True), ("192.168.1.4", False), ("127.0.0.1", False),
     ("10.0.0.8", False), ("169.254.1.1", False), ("not-an-ip", False)],
)
def test_public_address_detection(ip, public):
    assert Peer(ip=ip, port=443).is_public is public


# --------------------------------------------------------------------- events
def _ok(total_ms, ts=None):
    return LatencySample(total_ms=total_ms, ok=True, kind=KIND_APP, ts=ts or time.time())


def test_a_failed_probe_is_one_stall_not_one_per_retry():
    log = EventLog()
    first = log.observe(LatencySample(ok=False, error="timeout"))
    second = log.observe(LatencySample(ok=False, error="timeout"))

    assert first is not None and first.kind == STALL
    assert second is None
    assert log.count(STALL) == 1


def test_recovering_then_failing_again_is_a_second_stall():
    log = EventLog()
    log.observe(LatencySample(ok=False))
    log.observe(_ok(40))
    log.observe(LatencySample(ok=False))
    assert log.count(STALL) == 2


def test_a_stretch_above_the_baseline_is_a_spike():
    log = EventLog(min_baseline_samples=5)
    now = time.time()
    for index in range(10):
        assert log.observe(_ok(40, ts=now + index * 2)) is None
    event = None
    for index in range(5):
        event = log.observe(_ok(400, ts=now + 20 + index * 2)) or event

    assert event is not None and event.kind == SPIKE
    assert event.baseline_ms == pytest.approx(40)
    assert log.count(SPIKE) == 1        # one event for the stretch, not five


def test_one_bad_sample_on_its_own_is_not_an_event():
    """A single high reading is what a wireless link does between two good
    ones. Counting them is what turned two days into 1,421 "spikes"."""
    log = EventLog(min_baseline_samples=5)
    now = time.time()
    for index in range(20):
        log.observe(_ok(40, ts=now + index * 2))
    assert log.observe(_ok(900, ts=now + 40)) is None
    assert log.count(SPIKE) == 0


def test_a_spike_does_not_become_the_new_normal():
    log = EventLog(min_baseline_samples=5)
    now = time.time()
    for index in range(30):
        log.observe(_ok(40, ts=now + index * 2))
    for index in range(5):
        log.observe(_ok(400, ts=now + 60 + index * 2))
    assert log.baseline() == pytest.approx(40)


def test_no_spikes_before_there_is_a_baseline():
    log = EventLog(min_baseline_samples=10)
    assert log.observe(_ok(40)) is None
    for _ in range(8):
        assert log.observe(_ok(4000)) is None   # nothing to compare against yet


def test_old_events_fall_out_of_the_window():
    log = EventLog(window_s=60)
    log.observe(LatencySample(ok=False, ts=time.time() - 3600))
    assert log.count() == 0
    assert log.summary()["stalls"] == 0


def test_summary_reports_what_happened():
    log = EventLog(min_baseline_samples=3)
    now = time.time()
    for index in range(20):
        log.observe(_ok(50, ts=now + index * 2))
    for index in range(5):
        log.observe(_ok(500, ts=now + 40 + index * 2))

    summary = log.summary()

    assert summary["spikes"] == 1 and summary["stalls"] == 0
    assert summary["baseline_ms"] == pytest.approx(50)
    assert summary["last"]["kind"] == SPIKE


def test_notifications_are_rate_limited():
    notifier = Notifier(cooldown_s=300)
    now = time.time()

    assert notifier.should_notify(now)
    assert not notifier.should_notify(now + 10)
    assert notifier.should_notify(now + 400)


# ------------------------------------------------- one place decides the target
def test_the_gui_and_the_cli_agree_on_the_target():
    """The rule lived in two places once and drifted; it must stay shared."""
    from lagscope.config import Config
    from lagscope.models import KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO
    from lagscope.targets import manual_target

    config = Config()
    config.detect.enabled = False

    config.manual_kind = "app"
    config.app_name = "game.exe"
    assert manual_target(config).kind == KIND_APP

    config.manual_kind = "target"
    config.target_host = "8.8.8.8"
    config.target_port = 53
    target = manual_target(config)
    assert target.kind == KIND_TARGET and target.page == 53

    config.manual_kind = "video"
    config.video_id = "BV1"
    config.video_page = 3
    assert manual_target(config).page == 3

    config.manual_kind = "live"
    config.room_id = "123"
    assert manual_target(config).kind == KIND_LIVE

    empty = Config()
    empty.detect.enabled = False
    assert manual_target(empty).kind == KIND_NETWORK


def test_follow_foreground_uses_the_frontmost_process():
    from lagscope.config import Config
    from lagscope.targets import manual_target

    config = Config()
    config.manual_kind = "app"
    config.app_follow_foreground = True
    config.app_name = "fallback.exe"

    assert manual_target(config, lambda: "Discord.exe").ident == "Discord.exe"
    # nothing in the foreground: the configured name still applies
    assert manual_target(config, lambda: "").ident == "fallback.exe"


def test_a_configured_app_is_used_even_when_the_kind_says_live():
    from lagscope.config import Config
    from lagscope.models import KIND_APP
    from lagscope.targets import manual_target

    config = Config()
    config.manual_kind = "live"
    config.app_name = "game.exe"
    assert manual_target(config).kind == KIND_APP


# ------------------------------------------------- watching several at once
def _extra_worker(extras):
    from lagscope.config import Config
    from lagscope.monitor import MonitorWorker

    config = Config()
    config.detect.enabled = False
    config.watch_extras = extras
    worker = MonitorWorker(config.sanitized())
    return worker


def test_side_watches_are_measured_one_per_round(monkeypatch):
    """All of them every round would cost more than the round itself."""
    from lagscope import monitor as monitor_module

    pinged = []
    monkeypatch.setattr(monitor_module, "tcp_rtt_ms",
                        lambda host, port, timeout: pinged.append(host) or 10.0)
    worker = _extra_worker([
        {"kind": "target", "ident": "a.example", "port": 443, "label": "A"},
        {"kind": "target", "ident": "b.example", "port": 443, "label": "B"},
    ])
    seen = []
    worker.extraUpdated.connect(seen.append)

    worker._measure_next_extra()
    worker._measure_next_extra()
    worker._measure_next_extra()

    assert pinged == ["a.example", "b.example", "a.example"]   # round robin
    assert [result.label for result in seen] == ["A", "B", "A"]
    assert all(result.ok and result.rtt_ms == 10.0 for result in seen)


def test_a_side_watch_that_refuses_tcp_is_pinged(monkeypatch):
    from lagscope import monitor as monitor_module

    monkeypatch.setattr(monitor_module, "tcp_rtt_ms", lambda host, port, timeout: None)
    monkeypatch.setattr(monitor_module, "icmp_ping_ms", lambda host, timeout: 22.0)
    worker = _extra_worker([{"kind": "target", "ident": "game.example", "port": 7000,
                             "label": "Game"}])
    seen = []
    worker.extraUpdated.connect(seen.append)

    worker._measure_next_extra()

    assert seen[0].method == "icmp" and seen[0].rtt_ms == 22.0


def test_an_unreachable_side_watch_is_reported_not_dropped(monkeypatch):
    from lagscope import monitor as monitor_module

    monkeypatch.setattr(monitor_module, "tcp_rtt_ms", lambda host, port, timeout: None)
    monkeypatch.setattr(monitor_module, "icmp_ping_ms", lambda host, timeout: None)
    worker = _extra_worker([{"kind": "target", "ident": "down.example", "port": 443,
                             "label": "Down"}])
    seen = []
    worker.extraUpdated.connect(seen.append)

    worker._measure_next_extra()

    assert not seen[0].ok and seen[0].error == "unreachable"
    assert seen[0].label == "Down"        # still shown, so the outage is visible


def test_an_application_side_watch_uses_its_own_probe(monkeypatch):
    from lagscope.probes.appnet import AppMeasurement, Peer

    worker = _extra_worker([{"kind": "app", "ident": "Discord.exe", "port": 443,
                             "label": "Discord"}])
    worker._extra_app = type("P", (), {
        "measure": lambda self, name, timeout: AppMeasurement(
            rtt_ms=44.0, method="icmp", peer=Peer("93.184.216.34", 50000, 1), process=name),
    })()
    seen = []
    worker.extraUpdated.connect(seen.append)

    worker._measure_next_extra()

    assert seen[0].kind == "app" and seen[0].rtt_ms == 44.0


def test_no_side_watches_means_no_work(monkeypatch):
    from lagscope import monitor as monitor_module

    calls = []
    monkeypatch.setattr(monitor_module, "tcp_rtt_ms",
                        lambda host, port, timeout: calls.append(host) or 1.0)
    worker = _extra_worker([])

    worker._measure_next_extra()

    assert calls == []


def test_each_side_watch_keeps_a_stable_key():
    """The UI holds results by key, so it has to survive a re-measure."""
    worker = _extra_worker([{"kind": "target", "ident": "A.Example", "port": 53, "label": "x"}])
    entry = {"kind": "target", "ident": "A.Example", "port": 53, "label": "x"}

    first = worker._measure_extra(entry, 0.01)
    second = worker._measure_extra(entry, 0.01)

    assert first.key == second.key == "target:a.example:53"


# ------------------------------------------------- connections nobody owns
class _Addr:
    def __init__(self, ip, port):
        self.ip, self.port = ip, port


class _Conn:
    """Enough of a psutil connection for these two functions."""

    def __init__(self, pid, ip="1.2.3.4", port=443):
        import socket as _socket

        self.pid = pid
        self.raddr = _Addr(ip, port)
        self.laddr = _Addr("0.0.0.0", 1)
        self.type = _socket.SOCK_STREAM


def test_connections_windows_cannot_attribute_are_left_out(monkeypatch):
    """Windows reports an unowned socket as pid 0, which psutil names
    "System Idle Process". Hundreds of those sort to the top of a list whose
    purpose is picking a program to measure - naming something that is not a
    program and cannot be measured. Seen on a real machine: 317 of them.
    """
    from lagscope.probes import appnet

    monkeypatch.setattr(appnet.psutil, "net_connections",
                        lambda kind="inet": [_Conn(0) for _ in range(317)]
                        + [_Conn(1234), _Conn(1234)])
    monkeypatch.setattr(appnet, "_process_names",
                        lambda: {0: "System Idle Process", 1234: "chrome.exe"})

    apps = appnet.list_apps()
    assert [app.name for app in apps] == ["chrome.exe"]
    assert apps[0].connections == 2


def test_an_unowned_socket_is_not_attributed_to_a_named_program(monkeypatch):
    from lagscope.probes import appnet

    monkeypatch.setattr(appnet.psutil, "net_connections",
                        lambda kind="inet": [_Conn(0), _Conn(1234)])
    monkeypatch.setattr(appnet, "_process_names",
                        lambda: {0: "System Idle Process", 1234: "chrome.exe"})

    assert sum(peer.connections for peer in appnet.peers_for("chrome.exe")) == 1


def test_an_ipv6_peer_brackets_its_address():
    """"2607:6bc0::10:443" cannot be told apart from an address whose last
    group is 443 - one reader took it for a MAC address. RFC 3986 brackets."""
    assert str(Peer("2607:6bc0::10", 443)) == "[2607:6bc0::10]:443"
    assert str(Peer("::1", 80)) == "[::1]:80"


def test_an_ipv4_peer_is_left_exactly_as_it_was():
    assert str(Peer("93.184.216.34", 443)) == "93.184.216.34:443"


def test_a_wobbly_connection_does_not_report_its_own_wobble_as_events():
    """Two real days produced 1,421 spikes - one every twenty-two samples.

    The old rule compared each value against the median of the last two
    minutes and flagged anything twice as large. On a wireless link that
    normally moves between 30 and 90 ms, that fires constantly and none of it
    is an event: the connection is doing what it always does.
    """
    import random

    log = EventLog(min_baseline_samples=10)
    rng = random.Random(20260913)
    now = time.time()
    for index in range(1200):
        log.observe(_ok(rng.uniform(30, 90), ts=now + index * 2))

    assert log.count(SPIKE) == 0, f"{log.count(SPIKE)} events in ordinary noise"


def test_the_same_connection_still_reports_a_real_one():
    """The point is not to report less; it is to report what is unusual."""
    import random

    log = EventLog(min_baseline_samples=10)
    rng = random.Random(20260913)
    now = time.time()
    for index in range(1200):
        log.observe(_ok(rng.uniform(30, 90), ts=now + index * 2))

    event = None
    for step in range(5):
        event = log.observe(_ok(400, ts=now + 2400 + step * 2)) or event
    assert event is not None and event.kind == SPIKE
    assert event.threshold_ms is not None and event.threshold_ms < 400


def test_the_bar_follows_the_connection_rather_than_a_constant():
    """A steady link and a jittery one at the same average are not the same."""
    import random

    steady = EventLog(min_baseline_samples=10)
    jittery = EventLog(min_baseline_samples=10)
    rng = random.Random(4)
    now = time.time()
    for index in range(200):
        steady.observe(_ok(60 + rng.uniform(-1, 1), ts=now + index * 2))
        jittery.observe(_ok(rng.uniform(20, 140), ts=now + index * 2))

    assert steady.threshold() < jittery.threshold()
    # 130 ms is remarkable on the steady link and routine on the other one.
    steady_event = jittery_event = None
    for step in range(5):
        at = now + 400 + step * 2
        steady_event = steady.observe(_ok(130, ts=at)) or steady_event
        jittery_event = jittery.observe(_ok(130, ts=at)) or jittery_event
    assert steady_event is not None
    assert jittery_event is None


def test_a_small_absolute_jump_is_never_an_event():
    """18 ms to 37 ms doubles and nobody on earth notices."""
    log = EventLog(min_baseline_samples=5)
    now = time.time()
    for index in range(20):
        log.observe(_ok(18, ts=now + index * 2))
    for step in range(5):
        assert log.observe(_ok(37, ts=now + 60 + step * 2)) is None
    event = None
    for step in range(5):
        event = log.observe(_ok(300, ts=now + 80 + step * 2)) or event
    assert event is not None


def test_normal_means_the_last_half_hour_not_the_last_two_minutes():
    """An evening that degrades slowly used to register as nothing at all:
    every value looked fine next to the two minutes before it."""
    log = EventLog(min_baseline_samples=10)
    now = time.time()
    for index in range(300):            # ten minutes at 2 s, steady and good
        log.observe(_ok(40, ts=now + index * 2))
    assert log.baseline() == pytest.approx(40)
    # Climbing gently: each step is small, but the half hour remembers 40 ms.
    event = None
    for step in range(1, 30):
        event = log.observe(_ok(40 + step * 8, ts=now + 600 + step * 2)) or event
    assert event is not None and event.kind == SPIKE


def test_the_baseline_forgets_what_is_older_than_its_horizon():
    log = EventLog(min_baseline_samples=5, baseline_s=600)
    now = time.time()
    for index in range(20):
        log.observe(_ok(500, ts=now + index * 2))
    for index in range(20):
        log.observe(_ok(40, ts=now + 1200 + index * 2))
    assert log.baseline() == pytest.approx(40)


def test_a_connection_that_gets_worse_and_stays_worse_becomes_the_new_normal():
    """Otherwise the bar never moves: the first bad sample is an event and
    every sample after it is "still spiking", forever, against a baseline
    frozen at how good things used to be."""
    log = EventLog(min_baseline_samples=10, level_shift_s=120)
    now = time.time()
    for index in range(60):
        log.observe(_ok(40, ts=now + index * 2))
    for index in range(200):                    # it moved to 300 ms and stayed
        log.observe(_ok(300, ts=now + 120 + index * 2))

    assert log.baseline() > 100, "the baseline never learned the new normal"
    assert log.count(SPIKE) == 1, "one event for the change, not one per sample"
    # And from the new normal, a jump is measured against that.
    for step in range(5):
        assert log.observe(_ok(320, ts=now + 600 + step * 2)) is None
    event = None
    for step in range(5):
        event = log.observe(_ok(2000, ts=now + 640 + step * 2)) or event
    assert event is not None


def test_a_brief_hiccup_is_still_thrown_away():
    """The level-shift rule must not let a two-second outlier into the normal."""
    log = EventLog(min_baseline_samples=10, level_shift_s=120)
    now = time.time()
    for index in range(60):
        log.observe(_ok(40, ts=now + index * 2))
    before = log.baseline()
    log.observe(_ok(900, ts=now + 120))
    log.observe(_ok(41, ts=now + 122))
    assert log.baseline() == pytest.approx(before, abs=1.0)


def test_an_outage_does_not_fake_a_run_of_bad_latency_around_it():
    """A spike, then the probe fails for an hour, then one more bad sample:
    the two are not a one-hour bad stretch, and must not be read as one."""
    log = EventLog(min_baseline_samples=10, level_shift_s=120)
    now = time.time()
    for index in range(60):
        log.observe(_ok(40, ts=now + index * 2))
    good = log.baseline()
    for step in range(5):                       # a real spike starts
        log.observe(_ok(900, ts=now + 120 + step * 2))
    for step in range(200):                     # then it goes down entirely
        log.observe(LatencySample(ok=False, error="timeout",
                                  ts=now + 140 + step * 2))
    bar = log.threshold()
    log.observe(_ok(900, ts=now + 700))         # back, still bad, ten minutes on

    # The bar is the sensitive part: folding six 900 ms samples into fifty-odd
    # 40 ms ones barely moves the median, but it moves the 99th percentile all
    # the way up to 900 - and nothing would ever be reported again.
    assert log.threshold() == pytest.approx(bar, abs=1.0), \
        "an outage was mistaken for a sustained run of bad latency"
    assert log.baseline() == pytest.approx(good, abs=1.0)


def test_after_a_long_enough_outage_there_is_no_recent_normal_to_compare_to():
    """Nothing measured for over half an hour means nothing to call normal,
    and the honest answer is to report no spikes until it is rebuilt."""
    log = EventLog(min_baseline_samples=10)
    now = time.time()
    for index in range(60):
        log.observe(_ok(40, ts=now + index * 2))
    assert log.threshold() is not None
    for step in range(5):
        assert log.observe(_ok(900, ts=now + 3600 + step * 2)) is None
    assert log.baseline() is None
