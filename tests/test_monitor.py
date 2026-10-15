"""The rules that decide what ends up in a sample (no Qt event loop needed)."""

import pytest

from lagscope.config import Config
from lagscope.models import (
    KIND_LIVE, KIND_NETWORK, KIND_VIDEO, NetworkMeasurement, StreamMeasurement, WatchTarget,
)
from lagscope import monitor as monitor_module
from lagscope.monitor import STATUS_ERROR, STATUS_NO_ROOM, STATUS_OFFLINE, STATUS_OK, MonitorWorker


class FakeClient:
    def __init__(self):
        self.timeout_s = 4.0

    def measure(self, url, rtt_ms=None):
        return NetworkMeasurement(rtt_ms=30.0, ttfb_ms=40.0, host="api", clock_offset_ms=12.0)

    def recycle(self):
        pass

    def close(self):
        pass


class FakeProbe:
    """Stands in for both StreamProbe and VideoProbe."""

    def __init__(self, measurement=None, rtt_ms=45.0):
        self.measurement = measurement
        self.rtt_ms = rtt_ms
        self.room_info = None
        self.info = None
        self.clock_offset_ms = None
        self.target = None

    def measure(self, ident=None, page=None):
        return self.measurement

    def endpoint_rtt_ms(self, timeout_s=4.0):
        return self.rtt_ms

    def set_clock_offset_ms(self, offset):
        self.clock_offset_ms = offset

    def set_room(self, room_id):
        self.target = (KIND_LIVE, room_id)

    def set_target(self, video_id, page=1):
        self.target = (KIND_VIDEO, video_id, page)


class FakeDetector:
    def __init__(self, target=None):
        self.target = target
        self.polls = 0

    def poll(self, force=False):
        self.polls += 1
        return self.target

    def apply_config(self, config):
        pass

    def close(self):
        pass


def _config(**kwargs):
    config = Config()
    config.room_id = kwargs.get("room_id", "123")
    config.video_id = kwargs.get("video_id", "")
    config.manual_kind = kwargs.get("manual_kind", "live")
    config.display.include_in_total = kwargs.get("include_display", True)
    config.detect.enabled = kwargs.get("detect", False)
    config.detect.follow_videos = kwargs.get("follow_videos", True)
    return config.sanitized()


def _worker(config, live=None, video=None, rtt_ms=45.0, detector=None):
    worker = MonitorWorker(config)
    worker._client = FakeClient()
    worker._stream = FakeProbe(live, rtt_ms)
    worker._video = FakeProbe(video, rtt_ms)
    worker._detector = detector
    return worker


# --------------------------------------------------------------- live samples
def test_total_is_stream_plus_display_without_double_counting_the_network():
    measurement = StreamMeasurement(stream_ms=2500.0, method="hls-pdt", estimated=False,
                                    edge_lag_ms=2000.0, buffer_ms=480.0, host="cdn")
    worker = _worker(_config(), live=measurement)
    worker.setDisplayLatency(33.0)

    sample = worker._run_round()

    assert sample.ok and sample.estimated is False
    assert sample.kind == KIND_LIVE
    assert sample.stream_ms == 2500.0
    assert sample.network_ms == 45.0        # reported, not added
    assert sample.total_ms == pytest.approx(2533.0)
    assert sample.method == "hls-pdt"


def test_display_can_be_left_out_of_the_total():
    measurement = StreamMeasurement(stream_ms=2500.0, method="hls-pdt", estimated=False)
    worker = _worker(_config(include_display=False), live=measurement)
    worker.setDisplayLatency(33.0)

    sample = worker._run_round()

    assert sample.display_ms == 33.0        # still shown in the breakdown
    assert sample.total_ms == pytest.approx(2500.0)


def test_an_offline_room_is_reported_as_offline_not_as_an_error():
    worker = _worker(_config(), live=StreamMeasurement(stream_ms=None, method="none", error="offline"))

    sample = worker._run_round()

    assert not sample.ok and sample.total_ms is None
    assert worker._last_status == STATUS_OFFLINE


def test_a_failed_probe_keeps_the_network_reading():
    worker = _worker(_config(), live=StreamMeasurement(stream_ms=None, method="none", error="timeout"))

    sample = worker._run_round()

    assert not sample.ok
    assert sample.network_ms == 45.0
    assert sample.error == "timeout"
    assert worker._last_status == STATUS_ERROR


# -------------------------------------------------------------- video samples
def test_a_video_target_uses_the_video_probe_and_carries_throughput():
    measurement = StreamMeasurement(
        stream_ms=900.0, method="video-startup", kind=KIND_VIDEO,
        throughput_mbps=24.0, required_mbps=3.0, host="cdn", title="某某影片",
    )
    worker = _worker(_config(manual_kind="video", video_id="BV1GJ411x7h7"), video=measurement)
    worker.setDisplayLatency(33.0)

    sample = worker._run_round()

    assert sample.ok and sample.kind == KIND_VIDEO
    assert sample.total_ms == pytest.approx(933.0)
    assert sample.throughput_mbps == 24.0 and sample.required_mbps == 3.0
    assert sample.title == "某某影片"
    assert worker._video.target == (KIND_VIDEO, "BV1GJ411x7h7", 1)
    assert worker._stream.target is None    # the live probe stayed idle


def test_a_configured_video_is_used_when_no_room_is_set():
    worker = _worker(_config(room_id="", video_id="BV1GJ411x7h7", manual_kind="live"))
    assert worker.current_target(worker._config).kind == KIND_VIDEO


# ------------------------------------------------------------- network-only
class FakeInternet:
    """Stands in for the anchor probe: one fixed answer, every round."""

    def __init__(self, rtt_ms):
        from lagscope.probes.internet import Anchor

        self.rtt_ms = rtt_ms
        self.anchor = Anchor("1.1.1.1", 443, "Cloudflare")

    def measure(self, timeout_s=4.0):
        from lagscope.probes.internet import InternetResult

        return InternetResult(self.rtt_ms, "tcp" if self.rtt_ms else "none", self.anchor)


def test_network_only_mode_without_a_target():
    """Nothing to watch in Bilibili mode: it still says how the internet is."""
    worker = _worker(_config(room_id=""))
    worker._internet = FakeInternet(21.0)
    worker.setDisplayLatency(16.0)

    sample = worker._run_round()

    assert sample.kind == KIND_NETWORK and sample.method == "tcp"
    # What ping would say: nothing estimated is added to a network number.
    assert sample.ok and sample.total_ms == pytest.approx(21.0)
    assert not sample.estimated
    assert sample.host == "1.1.1.1:443" and "Cloudflare" in sample.title
    # Not chosen on purpose here - a room is what is missing.
    assert worker._last_status == STATUS_NO_ROOM


def test_internet_mode_chosen_on_purpose_is_not_a_missing_room():
    worker = _worker(_config(room_id="555", manual_kind="network"))
    worker._internet = FakeInternet(18.0)

    sample = worker._run_round()

    # The leftover room number does not take over a mode chosen on purpose.
    assert sample.kind == KIND_NETWORK and sample.total_ms == pytest.approx(18.0)
    assert worker._last_status == STATUS_OK


def test_network_only_mode_marks_an_unreachable_network():
    worker = _worker(_config(room_id=""))
    worker._internet = FakeInternet(None)

    sample = worker._run_round()

    assert not sample.ok and sample.total_ms is None
    assert worker._last_status == STATUS_ERROR


# ------------------------------------------------------------ target picking
def test_detection_overrides_the_configured_room():
    detected = WatchTarget(kind=KIND_LIVE, ident="999", source="history")
    worker = _worker(_config(detect=True), detector=FakeDetector(detected))

    target = worker.current_target(worker._config)

    assert target.ident == "999" and target.source == "history"


def test_detection_falls_back_to_the_configured_room_when_idle():
    worker = _worker(_config(detect=True), detector=FakeDetector(None))
    target = worker.current_target(worker._config)
    assert target.ident == "123" and target.source == "manual"


def test_a_detected_video_is_ignored_when_following_videos_is_off():
    detected = WatchTarget(kind=KIND_VIDEO, ident="BV1GJ411x7h7", source="history")
    worker = _worker(_config(detect=True, follow_videos=False), detector=FakeDetector(detected))

    target = worker.current_target(worker._config)

    assert target.kind == KIND_LIVE and target.ident == "123"


def test_switching_target_reprograms_the_right_probe():
    worker = _worker(_config())
    emitted = []
    worker.targetChanged.connect(emitted.append)

    worker._sync_target(WatchTarget(kind=KIND_LIVE, ident="7"))
    worker._sync_target(WatchTarget(kind=KIND_LIVE, ident="7", source="history"))  # same content
    worker._sync_target(WatchTarget(kind=KIND_VIDEO, ident="BV1", page=2))

    assert worker._stream.target == (KIND_LIVE, "7")
    assert worker._video.target == (KIND_VIDEO, "BV1", 2)
    assert [t.ident for t in emitted] == ["7", "BV1"]


# ------------------------------------------------------------------- clock
def test_clock_offset_is_handed_to_the_stream_probe():
    worker = _worker(_config(), live=StreamMeasurement(stream_ms=1000.0, method="hls-pdt", estimated=False))
    worker._run_round()
    assert worker._stream.clock_offset_ms == 12.0
    assert worker._last_status == STATUS_OK


def test_the_first_clock_sync_happens_on_a_freshly_booted_machine(monkeypatch):
    """time.monotonic() is uptime on Linux, and "never synced" was 0.0.

    Comparing the two skipped the first sync entirely on a machine up for
    less than the interval - which is precisely the machine of someone who
    enabled "start with the system".
    """
    monkeypatch.setattr(monitor_module.time, "monotonic", lambda: 3.0)   # just booted
    worker = _worker(_config(), live=StreamMeasurement(stream_ms=1000.0, method="hls-pdt",
                                                       estimated=False))
    worker._run_round()

    assert worker._stream.clock_offset_ms == 12.0


def test_clock_sync_is_rate_limited():
    worker = _worker(_config(), live=StreamMeasurement(stream_ms=1000.0, method="hls-pdt"))
    worker._run_round()
    worker._stream.clock_offset_ms = None
    worker._run_round()                     # second round is inside the window
    assert worker._stream.clock_offset_ms is None


# --------------------------------------------------- any app / custom target
def test_an_app_target_is_measured_through_its_own_connections(monkeypatch):
    from lagscope.models import KIND_APP
    from lagscope.probes.appnet import AppMeasurement, Peer

    config = _config(room_id="")
    config.manual_kind = "app"
    config.app_name = "game.exe"
    worker = _worker(config)
    worker._app = type("P", (), {
        "measure": lambda self, name, timeout: AppMeasurement(
            rtt_ms=24.0, method="tcp", peer=Peer("93.184.216.34", 443, 4),
            connections=4, process=name),
        "set_target": lambda self, name: None,
    })()
    worker.setDisplayLatency(16.0)

    sample = worker._run_round()

    assert sample.ok and sample.kind == KIND_APP
    assert sample.network_ms == 24.0
    # What ping would print: the display estimate stays out of a network number.
    assert sample.total_ms == pytest.approx(24.0) and not sample.estimated
    assert sample.display_ms == pytest.approx(16.0)   # still reported
    assert sample.host == "93.184.216.34:443" and sample.connections == 4
    assert sample.title == "game.exe"


def test_an_app_with_no_connections_is_a_failed_sample(monkeypatch):
    from lagscope.probes.appnet import AppMeasurement

    config = _config(room_id="")
    config.manual_kind = "app"
    config.app_name = "game.exe"
    worker = _worker(config)
    worker._app = type("P", (), {
        "measure": lambda self, name, timeout: AppMeasurement(
            process=name, error="no-connections"),
        "set_target": lambda self, name: None,
    })()

    sample = worker._run_round()

    assert not sample.ok and sample.error == "no-connections"


def test_a_custom_target_is_pinged(monkeypatch):
    from lagscope.models import KIND_TARGET

    config = _config(room_id="")
    config.manual_kind = "target"
    config.target_host = "8.8.8.8"
    config.target_port = 53
    worker = _worker(config)
    monkeypatch.setattr("lagscope.monitor.tcp_rtt_ms", lambda host, port, timeout: 12.0)
    worker.setDisplayLatency(16.0)

    sample = worker._run_round()

    assert sample.ok and sample.kind == KIND_TARGET
    assert sample.host == "8.8.8.8:53" and sample.method == "tcp"
    assert sample.total_ms == pytest.approx(12.0) and not sample.estimated


def test_a_custom_target_falls_back_to_ping(monkeypatch):
    config = _config(room_id="")
    config.manual_kind = "target"
    config.target_host = "game.example.com"
    worker = _worker(config)
    monkeypatch.setattr("lagscope.monitor.tcp_rtt_ms", lambda host, port, timeout: None)
    monkeypatch.setattr("lagscope.monitor.icmp_ping_ms", lambda host, timeout: 30.0)

    sample = worker._run_round()

    assert sample.ok and sample.method == "icmp" and sample.network_ms == 30.0


def test_an_unreachable_target_is_reported(monkeypatch):
    config = _config(room_id="")
    config.manual_kind = "target"
    config.target_host = "nowhere.invalid"
    worker = _worker(config)
    monkeypatch.setattr("lagscope.monitor.tcp_rtt_ms", lambda host, port, timeout: None)
    monkeypatch.setattr("lagscope.monitor.icmp_ping_ms", lambda host, timeout: None)

    sample = worker._run_round()

    assert not sample.ok and sample.error == "unreachable"


def test_machine_speed_is_stamped_onto_any_sample(monkeypatch):
    from lagscope.probes.netspeed import NetSpeed

    worker = _worker(_config(), live=StreamMeasurement(stream_ms=1000.0, method="hls-pdt"))
    worker._netspeed = type("S", (), {
        "sample": lambda self: NetSpeed(up_mbps=2.0, down_mbps=50.0, interval_s=2.0),
        "reset": lambda self: None,
    })()

    sample = worker._with_netspeed(worker._run_round())

    assert sample.down_mbps == 50.0 and sample.up_mbps == 2.0


def test_machine_speed_can_be_turned_off():
    from lagscope.probes.netspeed import NetSpeed

    config = _config()
    config.show_netspeed = False
    worker = _worker(config, live=StreamMeasurement(stream_ms=1000.0, method="hls-pdt"))
    worker._netspeed = type("S", (), {
        "sample": lambda self: NetSpeed(up_mbps=2.0, down_mbps=50.0),
        "reset": lambda self: None,
    })()

    sample = worker._with_netspeed(worker._run_round())

    assert sample.down_mbps is None


def test_watching_an_application_can_say_how_far_away_the_server_is():
    """The round trip in app mode is measured against that very peer, so it
    carries a distance. Without the flag the overlay showed a bare address and
    no location at all - which is the case where an address says least."""
    from dataclasses import replace as _replace

    from lagscope.models import KIND_APP, LatencySample

    sample = LatencySample(kind=KIND_APP, network_ms=58.0, rtt_to_edge=True,
                           host="[2607:6bc0::10]:443", ok=True)
    assert sample.rtt_to_edge is True
    # and the round trip is the one to that host, not to some fallback
    assert sample.network_ms == 58.0
    assert _replace(sample, rtt_to_edge=False).rtt_to_edge is False
