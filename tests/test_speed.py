"""The speed test, measured against a server whose rate is known exactly.

A real endpoint would only prove that the network works. Serving the bytes
locally at a controlled rate is what makes it possible to assert that the
arithmetic - and in particular throwing away TCP slow start - is right.
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from lagscope.probes import speed
from lagscope.probes.speed import (
    DEFAULT_MAX_BYTES, SpeedResult, measure_download, public_url, tier_key,
)


class _Server:
    """Serves an endless stream of bytes, optionally rate limited."""

    def __init__(self, bytes_per_s=None, total_bytes=None, status=200):
        self.bytes_per_s = bytes_per_s
        self.total_bytes = total_bytes
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):        # noqa: A003 - keep tests quiet
                pass

            def do_GET(self):                    # noqa: N802 - Qt/http naming
                if outer.status != 200:
                    self.send_error(outer.status)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                block = b"x" * 64 * 1024
                sent = 0
                started = time.perf_counter()
                try:
                    while outer.total_bytes is None or sent < outer.total_bytes:
                        if outer.bytes_per_s:
                            # Hold the wire to the requested rate.
                            due = started + (sent / outer.bytes_per_s)
                            delay = due - time.perf_counter()
                            if delay > 0:
                                time.sleep(min(delay, 0.05))
                        piece = block
                        if outer.total_bytes is not None:
                            piece = block[: outer.total_bytes - sent]
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
                        sent += len(piece)
                        if time.perf_counter() - started > 30:
                            break
                    self.wfile.write(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass                          # the client stopped, which is the point

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_address[1]}/data"

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def session():
    with requests.Session() as opened:
        yield opened


# ------------------------------------------------------------------- limits
def test_the_time_budget_ends_the_download(session):
    with _Server() as url:                        # endless stream
        started = time.perf_counter()
        result = measure_download(session, url, budget_s=2.0, max_bytes=10 ** 12)

    assert result.ok
    assert 1.8 <= time.perf_counter() - started <= 6.0
    assert result.seconds == pytest.approx(2.0, abs=0.6)


def test_the_byte_cap_ends_the_download(session):
    with _Server() as url:
        result = measure_download(session, url, budget_s=30.0, max_bytes=512 * 1024)

    assert result.ok
    # It stops on the first chunk that crosses the cap, never far beyond it.
    assert 512 * 1024 <= result.bytes < 512 * 1024 + speed.CHUNK_BYTES * 2


def test_a_data_cap_is_respected_even_on_a_fast_line(session):
    """The point of the byte cap: a gigabit line must not pull a gigabyte."""
    with _Server() as url:
        result = measure_download(session, url, budget_s=20.0, max_bytes=1024 * 1024)

    assert result.bytes < 4 * 1024 * 1024


# ---------------------------------------------------------------- the maths
def test_the_rate_matches_a_server_held_to_a_known_speed(session):
    # 4 MB/s is 32 Mbps; the measured figure should land near that.
    with _Server(bytes_per_s=4 * 1024 * 1024) as url:
        result = measure_download(session, url, budget_s=4.0, max_bytes=10 ** 12)

    assert result.ok
    assert result.mbps == pytest.approx(32.0, rel=0.45)


def test_slow_start_is_thrown_away_not_averaged_in(session, monkeypatch):
    """A run that spends its first second slow must not be dragged down by it."""
    monkeypatch.setattr(speed, "WARMUP_S", 0.5)
    with _Server() as url:
        result = measure_download(session, url, budget_s=2.0, max_bytes=10 ** 12)

    assert result.warmed
    assert result.ramp_mbps is not None
    # The warmed figure ignores the opening stretch, so it cannot be the
    # whole-run average unless they happen to be identical.
    assert result.mbps >= result.ramp_mbps * 0.5


def test_a_download_shorter_than_the_warm_up_says_so(session):
    with _Server(total_bytes=64 * 1024) as url:
        result = measure_download(session, url, budget_s=10.0, max_bytes=10 ** 12)

    assert result.ok
    assert result.warmed is False          # the caller can say "this may read low"
    assert result.mbps == result.ramp_mbps


# ------------------------------------------------------------------- errors
def test_a_refusing_server_is_reported_not_raised(session):
    with _Server(status=503) as url:
        result = measure_download(session, url, budget_s=5.0)

    assert not result.ok and result.error
    assert result.mbps is None


def test_an_unreachable_host_is_reported_not_raised(session):
    result = measure_download(session, "http://127.0.0.1:1/nothing", budget_s=2.0)
    assert not result.ok and result.error


def test_no_url_is_not_an_error_worth_raising(session):
    assert measure_download(session, "", budget_s=2.0).error == "no-url"


def test_the_host_is_reported_so_the_result_can_be_attributed(session):
    with _Server(total_bytes=128 * 1024) as url:
        result = measure_download(session, url, budget_s=5.0, source="stream")

    assert result.host == "127.0.0.1"
    assert result.source == "stream"


# ------------------------------------------------------------------ verdict
@pytest.mark.parametrize(
    "mbps,key",
    [
        (120.0, "speed.tier.4k"),
        (25.0, "speed.tier.4k"),
        (12.0, "speed.tier.1080p60"),
        (6.0, "speed.tier.1080p"),
        (3.0, "speed.tier.720p"),
        (1.0, "speed.tier.low"),
        (0.0, "speed.tier.low"),
        (None, "speed.tier.low"),
    ],
)
def test_a_speed_maps_to_what_it_can_actually_carry(mbps, key):
    assert tier_key(mbps) == key


def test_the_public_endpoint_asks_for_the_size_it_intends_to_read():
    assert str(DEFAULT_MAX_BYTES) in public_url()
    assert "1048576" in public_url(1024 * 1024)


def test_a_result_serialises_for_the_report():
    payload = SpeedResult(mbps=42.0, bytes=100, seconds=2.0, host="h").as_dict()
    assert payload["mbps"] == 42.0 and payload["host"] == "h"


# ------------------------------------------------------- running it too early
def test_a_speed_test_before_the_first_probe_does_not_crash_the_worker(monkeypatch):
    """The menu item exists before any probe cycle has built the client."""
    from lagscope.config import Config
    from lagscope.monitor import MonitorWorker
    from lagscope.probes import speed as speed_module

    # Hermetic: a real run would pull 80 MB through whatever network is there.
    monkeypatch.setattr(speed_module, "measure_download",
                        lambda *a, **k: SpeedResult(mbps=50.0, bytes=1, seconds=1.0))
    monkeypatch.setattr(speed_module, "measure_upload",
                        lambda *a, **k: SpeedResult(mbps=10.0, bytes=1, seconds=1.0))
    worker = MonitorWorker(Config())
    monkeypatch.setattr(worker._internet, "choose", lambda *a, **k: None)
    assert worker._client is None            # nothing has run yet

    seen = []
    worker.speedTestReady.connect(seen.append)
    worker.runSpeedTest()                    # must report, never raise

    assert len(seen) == 1
    assert isinstance(seen[0], speed_module.SpeedReport)
    assert seen[0].mbps == 50.0 and seen[0].up_mbps == 10.0
    assert seen[0].grade == ""               # no anchor, so no latency claim


# ------------------------------------------------------------------ upload
class _UploadServer:
    """Accepts a chunked POST and reads it at a set rate, like a real uplink."""

    def __init__(self, bytes_per_s=None, status=200):
        self.bytes_per_s = bytes_per_s
        self.status = status
        self.received = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):        # noqa: A003
                pass

            def do_POST(self):                   # noqa: N802
                started = time.perf_counter()
                try:
                    while True:
                        size_line = self.rfile.readline()
                        if not size_line:
                            break
                        size = int(size_line.strip().split(b";")[0] or b"0", 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        remaining = size
                        while remaining:
                            piece = self.rfile.read(min(remaining, 16 * 1024))
                            if not piece:
                                return
                            remaining -= len(piece)
                            outer.received += len(piece)
                            if outer.bytes_per_s:
                                due = started + outer.received / outer.bytes_per_s
                                delay = due - time.perf_counter()
                                if delay > 0:
                                    time.sleep(min(delay, 0.05))
                        self.rfile.readline()
                except (ConnectionResetError, OSError, ValueError):
                    return
                self.send_response(outer.status)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_address[1]}/__up"

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()


def test_upload_is_measured_at_roughly_the_rate_the_line_takes(session):
    server = _UploadServer(bytes_per_s=4 * 1024 * 1024)     # ~33.5 Mbps
    with server as url:
        # Long enough that the kernel's send buffer - several MB on Windows and
        # macOS, accepted before the server has read a byte - is a small share
        # of what is measured rather than an inflation of it.
        result = speed.measure_upload(session, url, budget_s=5.0, max_bytes=10 ** 12)

    assert result.ok and result.warmed
    assert result.mbps == pytest.approx(33.5, rel=0.5)
    assert result.bytes > 0


def test_upload_stops_at_its_byte_cap(session):
    with _UploadServer() as url:
        result = speed.measure_upload(session, url, budget_s=20.0, max_bytes=2 * 1024 * 1024)
    assert result.ok
    assert result.bytes <= 2 * 1024 * 1024 + speed.CHUNK_BYTES


def test_an_unreachable_upload_endpoint_is_an_error_not_a_number(session):
    result = speed.measure_upload(session, "http://127.0.0.1:9/__up", budget_s=1.0)
    assert not result.ok and result.error


# ----------------------------------------------------- latency under load
def test_bufferbloat_grades_follow_the_public_scale():
    assert speed.bloat_grade(None) == ""
    assert speed.bloat_grade(2.0) == "A+"
    assert speed.bloat_grade(20.0) == "A"
    assert speed.bloat_grade(45.0) == "B"
    assert speed.bloat_grade(150.0) == "C"
    assert speed.bloat_grade(300.0) == "D"
    assert speed.bloat_grade(900.0) == "F"


def test_pings_run_beside_the_work_and_stop_with_it():
    calls = []

    def ping():
        calls.append(time.perf_counter())
        return 40.0

    result, samples = speed.latency_during(lambda: time.sleep(0.6) or "done", ping,
                                           interval_s=0.05)
    assert result == "done"
    assert len(samples) >= 5 and set(samples) == {40.0}
    count = len(calls)
    time.sleep(0.2)
    assert len(calls) == count, "the ping thread outlived the test"


def test_a_failing_ping_does_not_break_the_test():
    def ping():
        raise OSError("filtered")

    result, samples = speed.latency_during(lambda: 7, ping, interval_s=0.01)
    assert result == 7 and samples == []


def test_the_report_grades_by_the_worse_direction():
    down = SpeedResult(mbps=100.0, bytes=10, seconds=1.0)
    up = SpeedResult(mbps=10.0, bytes=5, seconds=1.0)
    report = speed.SpeedReport(download=down, upload=up, idle_ms=20.0,
                               loaded_down_ms=35.0, loaded_up_ms=260.0)
    assert report.bloat_ms == pytest.approx(240.0)   # uploading is where it hurts
    assert report.grade == "D"
    # Reads like the download for everything written against that.
    assert report.mbps == 100.0 and report.ok and report.up_mbps == 10.0
    assert report.bytes == 15 and report.seconds == pytest.approx(2.0)


def test_without_an_idle_figure_there_is_no_grade():
    report = speed.SpeedReport(download=SpeedResult(mbps=1.0, bytes=1, seconds=1.0),
                               loaded_down_ms=300.0)
    assert report.bloat_ms is None and report.grade == ""


def test_a_whole_run_against_local_servers(session):
    pings = iter([20.0] * 5 + [70.0] * 1000)
    # A wide gap between the directions: an upload's first second can be
    # inflated by whatever the kernel's send buffer swallowed up front.
    with _Server(bytes_per_s=32 * 1024 * 1024) as down_url, \
            _UploadServer(bytes_per_s=2 * 1024 * 1024) as up_url:
        report = speed.run_speed_test(session, down_url, budget_s=2.0,
                                      max_bytes=10 ** 12, ping=lambda: next(pings),
                                      upload_url=up_url)

    assert report.ok and report.upload is not None and report.upload.ok
    assert report.mbps > report.up_mbps > 0
    assert report.idle_ms == pytest.approx(20.0)
    assert report.bloat_ms == pytest.approx(50.0)
    assert report.grade == "B"


def test_upload_is_skipped_when_the_download_failed(session):
    with _Server(status=500) as url:
        report = speed.run_speed_test(session, url, budget_s=1.0, ping=None,
                                      upload_url="http://127.0.0.1:9/__up")
    assert not report.ok and report.upload is None


def test_the_summary_says_both_directions_and_the_grade():
    from lagscope.i18n import tr
    from lagscope.presentation import speed_summary

    report = speed.SpeedReport(
        download=SpeedResult(mbps=94.2, bytes=50 * 1024 * 1024, seconds=10.0),
        upload=SpeedResult(mbps=21.5, bytes=20 * 1024 * 1024, seconds=10.0),
        idle_ms=12.0, loaded_down_ms=180.0, loaded_up_ms=40.0)
    text = speed_summary(report)
    assert "94.2 Mbps" in text and "21.5 Mbps" in text
    assert "12 ms" in text and "180 ms" in text and "C" in text
    assert tr("speed.grade.C") in text
