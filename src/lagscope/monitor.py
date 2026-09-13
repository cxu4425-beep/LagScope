"""The monitoring loop.

Runs in its own QThread so that a slow network never freezes the overlay. One
round performs: work out what is being watched -> TCP RTT -> live-stream or
video probe -> combine with the display estimate the UI thread keeps updated ->
emit a LatencySample.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .config import Config, title_memory_path
from .detect import AutoDetector
from .health import HEALTH, ICMP, WIFI
from .models import (
    KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, ExtraResult, LatencySample,
    WatchTarget,
)
from .probes.appnet import AppNetProbe
from .probes.netspeed import NetSpeedProbe
from .probes.network import HttpClient, icmp_ping_ms, tcp_rtt_ms
from .probes.path import WifiInfo, wifi_info
from .probes.stream import RoomInfo, StreamProbe
from .probes.video import VideoProbe
from .targets import resolve_target

LOG = logging.getLogger(__name__)

# The radio does not change second to second, and asking for it costs a
# subprocess, so it is read on its own slower clock.
WIFI_REFRESH_S = 30.0

CLOCK_SYNC_INTERVAL_S = 60.0
LINE_COMPARE_INTERVAL_S = 120.0
CLOCK_SYNC_URL = "https://api.live.bilibili.com/room/v1/Room/get_info?room_id=1"

STATUS_OK = "ok"
STATUS_OFFLINE = "offline"
STATUS_NO_ROOM = "no_room"
STATUS_ERROR = "error"
STATUS_PAUSED = "paused"


class MonitorWorker(QObject):
    """Lives in the worker thread; owns the HTTP client, probes and detector."""

    sampleReady = Signal(object)      # LatencySample
    statusChanged = Signal(str, str)  # status key, detail text
    roomInfoChanged = Signal(object)  # RoomInfo | None
    targetChanged = Signal(object)    # WatchTarget
    linesChanged = Signal(object)     # list[CdnLine] - CDN edges, fastest first
    diagnosisReady = Signal(object)   # (PathReport, verdict key, detail)
    quickCheckReady = Signal(object)  # (timestamp, verdict key, detail) - unattended
    lineSwitched = Signal(object)     # LineSwitch - moved to a faster CDN edge
    speedTestReady = Signal(object)   # SpeedResult - the on-demand speed test
    extraUpdated = Signal(object)     # ExtraResult - one side watch, refreshed

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._lock = threading.Lock()
        self._display_ms: Optional[float] = None
        self._paused = False
        self._running = False
        self._failures = 0
        self._last_clock_sync = 0.0
        self._last_status = ""
        self._target: Optional[WatchTarget] = None
        self._client: Optional[HttpClient] = None
        self._stream: Optional[StreamProbe] = None
        self._video: Optional[VideoProbe] = None
        self._app = AppNetProbe()
        self._last_switch = None
        self._extra_app = AppNetProbe()   # separate state: different target
        self._netspeed = NetSpeedProbe()
        self._extra_index = 0
        # Reading the Wi-Fi state shells out; it also barely changes between
        # rounds, so it is cached and refreshed on WIFI_REFRESH_S.
        self._wifi: Optional[WifiInfo] = None
        self._wifi_at = 0.0
        self._detector: Optional[AutoDetector] = None
        self._timer: Optional[QTimer] = None

    # ------------------------------------------------------------- lifecycle
    @Slot()
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._build_probes()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._timer.start(0)
        LOG.info("monitor started")

    @Slot()
    def stop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            # Destroy it here, inside its own thread: a QTimer torn down from
            # another thread at interpreter exit warns on stderr.
            self._timer.deleteLater()
            self._timer = None
        if self._detector is not None:
            self._detector.close()
        if self._client is not None:
            self._client.close()
        LOG.info("monitor stopped")

    @Slot(object)
    def applyConfig(self, config: Config) -> None:
        with self._lock:
            self._config = config
        self._build_probes()
        self._failures = 0
        if self._running and self._timer is not None:
            self._timer.start(0)

    @Slot(bool)
    def setPaused(self, paused: bool) -> None:
        self._paused = bool(paused)
        if not paused and self._running and self._timer is not None:
            self._timer.start(0)
        if paused:
            self._emit_status(STATUS_PAUSED, "")

    def setDisplayLatency(self, display_ms: Optional[float]) -> None:
        """Thread-safe hand-off of the UI thread's display estimate."""
        with self._lock:
            self._display_ms = display_ms

    @Slot(str)
    def submitClipboard(self, text: str) -> None:
        """Clipboard text handed over by the UI thread (it owns the clipboard).

        Resolving a b23.tv share link needs the network, which is why this runs
        here rather than in the UI thread.
        """
        if self._detector is None:
            return
        try:
            target = self._detector.submit_clipboard(text)
        except Exception:  # a odd clipboard must never break the loop
            LOG.exception("clipboard detection failed")
            return
        if target is not None and self._running and self._timer is not None:
            self._timer.start(0)      # switch over immediately

    @Slot()
    def runDiagnosis(self) -> None:
        """Measure each segment of the path; several seconds of subprocesses."""
        from .probes.path import analyse, verdict

        with self._lock:
            config = self._config
        host = self._diagnosis_host(config)
        try:
            report = analyse(host)
        except Exception:
            LOG.exception("diagnosis failed")
            self.diagnosisReady.emit(None)
            return
        key, detail = verdict(report)
        self.diagnosisReady.emit((report, key, detail))

    @Slot()
    def runQuickCheck(self) -> None:
        """A cut-down path check, run unattended the moment something breaks.

        Three pings and no traceroute: this fires while the connection is
        already in trouble, so it has to be over in a couple of seconds and
        must not add load of its own. Nobody is watching a dialog for it - the
        answer is filed against the minute it happened, and shows up later in
        the history and the report.
        """
        from .probes.path import analyse, verdict

        with self._lock:
            config = self._config
        host = self._diagnosis_host(config)
        try:
            report = analyse(host, count=3, timeout_s=1.0, include_trace=False)
        except Exception:
            LOG.exception("automatic check failed")
            return
        key, detail = verdict(report)
        self.quickCheckReady.emit((time.time(), key, detail))

    @Slot()
    def runSpeedTest(self) -> None:
        """Download flat out for a few seconds, from the most relevant server.

        Deliberately never automatic: it saturates the line, so the latency
        figure it runs alongside will spike and the stream may stutter. The
        app marks the minutes it covers so that spike is not read later as a
        fault of the connection.
        """
        from .probes.speed import measure_download, public_url

        with self._lock:
            config = self._config
        budget_s = float(config.speed.budget_s)
        max_bytes = int(config.speed.max_mb) * 1024 * 1024

        url, source = self._bulk_url()
        if not url:
            url, source = public_url(max_bytes), "public"

        if self._client is None:
            # The menu item is available before the first probe cycle has run,
            # and while monitoring is stopped. Neither should crash the worker.
            self._client = HttpClient(timeout_s=config.probe.timeout_ms / 1000.0)
        result = measure_download(self._client.session, url, budget_s=budget_s,
                                  max_bytes=max_bytes, source=source)
        if not result.ok and source == "stream":
            # The CDN refused a long read; the public endpoint still answers
            # the question, so say so rather than reporting a failure.
            LOG.debug("speed test on the stream CDN failed (%s); using the public one",
                      result.error)
            result = measure_download(self._client.session, public_url(max_bytes),
                                      budget_s=budget_s, max_bytes=max_bytes,
                                      source="public")
        self.speedTestReady.emit(result)

    def _bulk_url(self) -> tuple:
        """Somewhere worth downloading from: what is being watched, ideally."""
        target = self._target
        if target is not None and self._video is not None and target.kind == KIND_VIDEO:
            url = self._video.bulk_url()
            if url:
                return url, "stream"
        if target is not None and self._stream is not None and target.kind == KIND_LIVE:
            url = self._stream.bulk_url()
            if url:
                return url, "stream"
        return "", "public"

    def _diagnosis_host(self, config: Config) -> str:
        """Diagnose the path to whatever is being watched right now."""
        target = self._target
        if target is not None:
            if target.kind == KIND_TARGET:
                return target.ident
            if target.kind == KIND_APP and self._app is not None:
                peer = getattr(self._app.measure(target.ident, 2.0), "peer", None)
                if peer is not None:
                    return peer.ip
            if target.kind in (KIND_LIVE, KIND_VIDEO):
                sample_host = ""
                if self._stream is not None:
                    sample_host = self._stream.current_host
                if sample_host:
                    return sample_host
        return config.probe.rtt_host

    def _resolve_url(self, url: str) -> Optional[str]:
        """Follow a short link to the page it points at."""
        if self._client is None:
            return None
        try:
            response = self._client.session.get(
                url, timeout=self._client.timeout_s, allow_redirects=True, stream=True
            )
            final_url = response.url
            response.close()
            return final_url
        except Exception as exc:
            LOG.debug("short link %s did not resolve: %s", url, exc)
            return None

    # ---------------------------------------------------------------- helpers
    def _build_probes(self) -> None:
        with self._lock:
            config = self._config
        timeout_s = config.probe.timeout_ms / 1000.0
        if self._client is None:
            self._client = HttpClient(timeout_s=timeout_s)
        else:
            self._client.timeout_s = timeout_s
            self._client.recycle()
        self._stream = StreamProbe(
            self._client,
            prefer_hls=config.probe.prefer_hls,
            player_buffer_segments=config.probe.player_buffer_segments,
            playurl_refresh_s=config.probe.playurl_refresh_s,
            auto_cdn=config.probe.auto_cdn,
        )
        self._video = VideoProbe(self._client, playurl_refresh_s=config.probe.playurl_refresh_s)
        self._netspeed.reset()
        if self._detector is None:
            self._detector = AutoDetector(config.detect, memory_path=title_memory_path())
        else:
            self._detector.apply_config(config.detect)
        self._detector.set_url_resolver(self._resolve_url)
        self._target = None
        self._last_clock_sync = 0.0

    def _schedule_next(self, failed: bool) -> None:
        if not self._running or self._timer is None:
            return
        with self._lock:
            config = self._config
        interval = config.probe.interval_ms
        if failed:
            self._failures = min(self._failures + 1, 16)
            multiplier = min(2 ** self._failures, config.probe.max_backoff_multiplier)
            interval = int(interval * multiplier)
        else:
            self._failures = 0
        self._timer.start(max(200, interval))

    def _emit_status(self, status: str, detail: str) -> None:
        if status != self._last_status or detail:
            self._last_status = status
            self.statusChanged.emit(status, detail)

    # ----------------------------------------------------------------- target
    def current_target(self, config: Config) -> WatchTarget:
        """What to measure this round: detected first, configured second."""
        return resolve_target(config, self._detector, self._foreground_app)

    def _sync_target(self, target: WatchTarget) -> None:
        if target.same_content(self._target):
            return
        self._target = target
        assert self._stream is not None and self._video is not None
        if target.kind == KIND_LIVE:
            self._stream.set_room(target.ident)
        elif target.kind == KIND_VIDEO:
            self._video.set_target(target.ident, target.page)
        elif target.kind == KIND_APP:
            self._app.set_target(target.ident)
        LOG.info("watching %s %s (source: %s)", target.kind, target.ident or "-", target.source)
        self.targetChanged.emit(target)

    # ------------------------------------------------------------------ round
    @Slot()
    def _tick(self) -> None:
        if not self._running:
            return
        if self._paused:
            self._schedule_next(False)
            return
        try:
            sample = self._with_link(
                self._with_audio(self._with_netspeed(self._run_round())))
        except Exception as exc:  # never let the loop die on a bad round
            LOG.exception("probe round failed")
            sample = LatencySample(ok=False, error=str(exc)[:200])
        self.sampleReady.emit(sample)
        self._measure_next_extra()
        self._schedule_next(failed=not sample.ok)

    def _run_round(self) -> LatencySample:
        with self._lock:
            config = self._config
            display_ms = self._display_ms
        assert self._client is not None and self._stream is not None and self._video is not None

        timeout_s = config.probe.timeout_ms / 1000.0
        self._sync_clock_if_due(timeout_s)

        target = self.current_target(config)
        self._sync_target(target)

        include_display = config.display.include_in_total
        display_component = display_ms if (include_display and display_ms is not None) else None

        if target.kind == KIND_NETWORK:
            return self._network_only_sample(config, display_ms, display_component, timeout_s)

        if target.kind == KIND_APP:
            return self._app_sample(target, display_ms, display_component, timeout_s)
        if target.kind == KIND_TARGET:
            return self._target_sample(target, display_ms, display_component, timeout_s)

        if target.kind == KIND_VIDEO:
            rtt_ms = self._video.endpoint_rtt_ms(timeout_s)
            measurement = self._video.measure(target.ident, target.page)
        else:
            rtt_ms = self._stream.endpoint_rtt_ms(timeout_s)
            measurement = self._stream.measure(target.ident)
            self.roomInfoChanged.emit(self._stream.room_info)
            self._compare_lines_if_due(timeout_s)
        rtt_to_edge = rtt_ms is not None
        if rtt_ms is None:
            # A different machine in a different place: usable as a health
            # number, useless for asking how far away the edge is.
            rtt_ms = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)

        if measurement.stream_ms is None:
            status = STATUS_OFFLINE if measurement.error == "offline" else STATUS_ERROR
            self._emit_status(status, measurement.error or "")
            return LatencySample(
                network_ms=rtt_ms,
                rtt_to_edge=rtt_to_edge,
                display_ms=display_ms,
                total_ms=None,
                ok=False,
                kind=target.kind,
                method=measurement.method,
                host=measurement.host,
                title=measurement.title or target.title,
                source=target.source,
                error=measurement.error,
            )

        # The stream figure is already client-side elapsed time (it contains the
        # network transit), so the network RTT is reported, not added again.
        total = measurement.stream_ms + (display_component or 0.0)
        self._emit_status(STATUS_OK, "")
        return LatencySample(
            network_ms=rtt_ms,
            rtt_to_edge=rtt_to_edge,
            stream_ms=measurement.stream_ms,
            display_ms=display_ms,
            total_ms=total,
            ok=True,
            estimated=measurement.estimated,
            kind=target.kind,
            method=measurement.method,
            host=measurement.host,
            title=measurement.title or target.title,
            source=target.source,
            throughput_mbps=measurement.throughput_mbps,
            required_mbps=measurement.required_mbps,
        )

    def _measure_next_extra(self) -> None:
        """Refresh one side watch per round, in turn.

        Measuring all of them every round would cost more than the round
        itself; taking turns keeps each one fresh enough to answer "is the
        whole line bad?" without slowing the main figure down.
        """
        with self._lock:
            extras = list(self._config.watch_extras)
        if not extras:
            self._extra_index = 0
            return
        self._extra_index %= len(extras)
        entry = extras[self._extra_index]
        self._extra_index = (self._extra_index + 1) % len(extras)

        with self._lock:
            timeout_s = self._config.probe.timeout_ms / 1000.0
        try:
            self.extraUpdated.emit(self._measure_extra(entry, timeout_s))
        except Exception:
            LOG.exception("side watch failed: %s", entry.get("ident"))

    def _measure_extra(self, entry: dict, timeout_s: float) -> ExtraResult:
        kind = entry.get("kind", "target")
        ident = entry.get("ident", "")
        port = int(entry.get("port") or 443)
        label = entry.get("label") or ident
        key = f"{kind}:{ident.lower()}:{port if kind == KIND_TARGET else ''}"

        if kind == KIND_APP:
            result = self._extra_app.measure(ident, timeout_s)
            return ExtraResult(
                key=key, label=label, kind=KIND_APP, ident=ident,
                rtt_ms=result.rtt_ms, method=result.method,
                ok=result.rtt_ms is not None, error=result.error,
            )

        rtt = tcp_rtt_ms(ident, port, timeout_s)
        method = "tcp"
        if rtt is None:
            rtt = icmp_ping_ms(ident, timeout_s)
            method = "icmp" if rtt is not None else "none"
        return ExtraResult(
            key=key, label=label, kind=KIND_TARGET, ident=ident,
            rtt_ms=rtt, method=method, ok=rtt is not None,
            error=None if rtt is not None else "unreachable",
        )

    def _with_netspeed(self, sample: LatencySample) -> LatencySample:
        """Attach the machine's current up/down speed to any sample."""
        with self._lock:
            enabled = self._config.show_netspeed
        if not enabled:
            return sample
        speed = self._netspeed.sample()
        if not speed.ok:
            return sample
        return replace(sample, up_mbps=speed.up_mbps, down_mbps=speed.down_mbps)

    def _current_wifi(self) -> Optional[WifiInfo]:
        """The wireless link, re-read every WIFI_REFRESH_S at most."""
        now = time.monotonic()
        if self._wifi_at and now - self._wifi_at < WIFI_REFRESH_S:
            return self._wifi
        self._wifi_at = now
        try:
            self._wifi = wifi_info()
        except Exception as exc:
            # A machine with no wireless is the normal case, so this is not an
            # error - but it stopped at debug level for two days on a laptop
            # that is always on Wi-Fi, and the report said "probably wired".
            # Recorded where something can say so.
            LOG.debug("wifi state unavailable", exc_info=True)
            HEALTH.degraded(WIFI, f"{type(exc).__name__}: {exc}")
            self._wifi = None
            return None

        if self._wifi is None:
            # Reading nothing is either "no wireless on this machine" or "the
            # reading failed", and the two are indistinguishable from here.
            # Saying which is impossible; saying that it happened is not.
            HEALTH.degraded(WIFI, "the wireless state came back empty")
        else:
            HEALTH.working(WIFI)
        return self._wifi

    def _with_link(self, sample: LatencySample) -> LatencySample:
        """Note which radio carried this sample, so history can group by it.

        Recorded on every sample rather than once, because the answer changes:
        signal drops, and a mesh hands you to a different access point without
        telling anyone. Both are things people feel and cannot see.
        """
        info = self._current_wifi()
        if info is None:
            return sample
        return replace(sample, link=info.link_key, bssid=info.bssid,
                       signal_pct=info.signal_pct)

    def _with_audio(self, sample: LatencySample) -> LatencySample:
        """Add the measured Bluetooth delay, if there is one, to every sample.

        Done here rather than inside each sample builder because the offset is
        a constant that applies to all of them equally: it is a property of the
        headphones, not of what is being watched. The four builders already
        thread ``display_component`` through by hand, and adding a second
        parameter to all of them would be four chances to forget one.

        The number is only added to the total, never invented into it: a round
        that could not produce a total stays without one. "About 170 ms" is not
        a useful answer to "is the stream up?".
        """
        with self._lock:
            audio = self._config.audio
            offset = audio.offset_ms if audio.include_in_total else 0.0
            measured = audio.offset_ms

        if measured <= 0.0:
            return sample
        if not offset or sample.total_ms is None:
            # Still worth reporting what was measured, even when the person has
            # chosen to keep it out of the headline number.
            return replace(sample, audio_ms=measured)
        return replace(sample, audio_ms=measured, total_ms=sample.total_ms + offset)

    def _foreground_app(self) -> str:
        """Process name of the window in front, for "follow whatever I use"."""
        try:
            from .ui.anchor import create_window_finder

            return create_window_finder().foreground_process()
        except Exception as exc:  # pragma: no cover - platform dependent
            LOG.debug("foreground process unavailable: %s", exc)
            return ""

    def _app_sample(self, target: WatchTarget, display_ms: Optional[float],
                    display_component: Optional[float], timeout_s: float) -> LatencySample:
        """Latency of any application, via the servers it is connected to."""
        measurement = self._app.measure(target.ident, timeout_s)
        if measurement.rtt_ms is None:
            self._emit_status(STATUS_ERROR, measurement.error or "")
            return LatencySample(
                ok=False, kind=KIND_APP, method=measurement.method, title=target.ident,
                source=target.source, connections=measurement.connections,
                display_ms=display_ms, error=measurement.error,
            )
        self._emit_status(STATUS_OK, "")
        return LatencySample(
            network_ms=measurement.rtt_ms,
            # Timed against this very peer, so it can carry a distance.
            rtt_to_edge=True,
            display_ms=display_ms,
            total_ms=measurement.rtt_ms + (display_component or 0.0),
            ok=True,
            kind=KIND_APP,
            method=measurement.method,
            host=str(measurement.peer) if measurement.peer else "",
            title=target.ident,
            source=target.source,
            connections=measurement.connections,
        )

    def _target_sample(self, target: WatchTarget, display_ms: Optional[float],
                       display_component: Optional[float], timeout_s: float) -> LatencySample:
        """Latency to a host the user named: game server, DNS, anything."""
        port = int(target.page or 443)
        rtt_ms = tcp_rtt_ms(target.ident, port, timeout_s)
        method = "tcp"
        if rtt_ms is None:
            rtt_ms = icmp_ping_ms(target.ident, timeout_s)
            method = "icmp" if rtt_ms is not None else "none"
        if rtt_ms is None:
            self._emit_status(STATUS_ERROR, "unreachable")
            return LatencySample(ok=False, kind=KIND_TARGET, method="none",
                                 host=f"{target.ident}:{port}", title=target.ident,
                                 source=target.source, display_ms=display_ms,
                                 error="unreachable")
        self._emit_status(STATUS_OK, "")
        return LatencySample(
            network_ms=rtt_ms,
            # Timed against the address named below, so it can carry a distance.
            rtt_to_edge=True,
            display_ms=display_ms,
            total_ms=rtt_ms + (display_component or 0.0),
            ok=True,
            kind=KIND_TARGET,
            method=method,
            host=f"{target.ident}:{port}",
            title=target.ident,
            source=target.source,
        )

    def _network_only_sample(self, config: Config, display_ms: Optional[float],
                             display_component: Optional[float], timeout_s: float) -> LatencySample:
        rtt_ms = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)
        total = None if rtt_ms is None else rtt_ms + (display_component or 0.0)
        self._emit_status(STATUS_NO_ROOM if rtt_ms is not None else STATUS_ERROR, "")
        return LatencySample(
            network_ms=rtt_ms,
            display_ms=display_ms,
            total_ms=total,
            ok=rtt_ms is not None,
            estimated=True,
            kind=KIND_NETWORK,
            method="network-only",
            host=config.probe.rtt_host,
            source="manual",
            error=None if rtt_ms is not None else "network unreachable",
        )

    def _compare_lines_if_due(self, timeout_s: float) -> None:
        """Time the other CDN edges now and then, so a slow one is visible."""
        if self._stream is None:
            return
        try:
            lines = self._stream.lines_if_due(timeout_s, LINE_COMPARE_INTERVAL_S)
        except Exception as exc:  # comparing lines is a bonus, never fatal
            LOG.debug("line comparison failed: %s", exc)
            return
        if lines:
            self.linesChanged.emit((self._stream.current_host, lines))
        # compare_lines() decides on its own whether a move is worth it; this
        # only reports the ones it actually made.
        switches = self._stream.switches
        if switches and switches[-1] is not self._last_switch:
            self._last_switch = switches[-1]
            LOG.info("switched CDN edge: %s -> %s", switches[-1].from_host, switches[-1].to_host)
            self.lineSwitched.emit(switches[-1])

    def _sync_clock_if_due(self, timeout_s: float) -> None:
        now = time.monotonic()
        # "Never synced" is 0.0, and time.monotonic() is uptime on Linux - so
        # comparing the two skipped the very first sync on a machine that had
        # been up for less than the interval. That is not a hypothetical: it
        # is exactly the machine of someone who turned on "start with the
        # system", whose first minute of "measured" latency then ran without
        # a clock offset at all.
        if self._last_clock_sync and now - self._last_clock_sync < CLOCK_SYNC_INTERVAL_S:
            return
        self._last_clock_sync = now
        assert self._client is not None and self._stream is not None
        try:
            measurement = self._client.measure(CLOCK_SYNC_URL)
            if measurement.clock_offset_ms is not None:
                self._stream.set_clock_offset_ms(measurement.clock_offset_ms)
                LOG.debug("clock offset %.0f ms", measurement.clock_offset_ms)
        except Exception as exc:  # a failed sync just keeps the previous offset
            LOG.debug("clock sync failed: %s", exc)


__all__ = [
    "MonitorWorker",
    "RoomInfo",
    "STATUS_ERROR",
    "STATUS_NO_ROOM",
    "STATUS_OFFLINE",
    "STATUS_OK",
    "STATUS_PAUSED",
]
