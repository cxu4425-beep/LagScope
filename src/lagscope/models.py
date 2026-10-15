"""Data structures shared by the probes, the monitor and the UI."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Deque, Iterable, Optional


KIND_LIVE = "live"
KIND_VIDEO = "video"
KIND_APP = "app"          # any application, measured through its own connections
KIND_TARGET = "target"    # a host the user named (game server, DNS, anything)
KIND_NETWORK = "network"

WATCHABLE_KINDS = (KIND_LIVE, KIND_VIDEO, KIND_APP, KIND_TARGET)


@dataclass(frozen=True)
class WatchTarget:
    """What the monitor is currently measuring.

    ``kind`` is one of ``live`` (a room), ``video`` (a VOD) or ``network``
    (nothing selected, network-only mode). ``source`` records where the target
    came from: ``manual``, ``history``, ``bridge`` or ``title``.
    """

    kind: str = KIND_NETWORK
    ident: str = ""               # room id for live, BV id for a video
    page: int = 1                 # video part (1-based); ignored for live
    title: str = ""
    source: str = "manual"
    detected_at: float = field(default_factory=time.time)

    @property
    def is_empty(self) -> bool:
        return self.kind == KIND_NETWORK or not self.ident

    def same_content(self, other: Optional["WatchTarget"]) -> bool:
        """True when both point at the same thing, ignoring source and time."""
        if other is None:
            return False
        return (self.kind, self.ident, self.page) == (other.kind, other.ident, other.page)


@dataclass(frozen=True)
class ExtraResult:
    """One of the side-by-side watches shown under the main figure.

    These exist to answer "is it just my game, or is the whole line bad?", so
    they are deliberately cheap: one round trip each, measured in turn rather
    than all at once.
    """

    key: str                      # stable identity, e.g. "target:8.8.8.8:53"
    label: str = ""
    kind: str = KIND_TARGET
    ident: str = ""
    rtt_ms: Optional[float] = None
    method: str = "none"
    ok: bool = False
    ts: float = field(default_factory=time.time)
    error: Optional[str] = None

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.ts)


@dataclass(frozen=True)
class StreamMeasurement:
    """Result of a single live-stream or video probe."""

    stream_ms: Optional[float]
    method: str = "none"          # hls-pdt | hls-window | flv-keyframe | video-startup | none
    estimated: bool = True        # False only when a server wall-clock is available
    kind: str = KIND_LIVE
    edge_lag_ms: Optional[float] = None
    buffer_ms: Optional[float] = None
    throughput_mbps: Optional[float] = None   # measured download speed (video mode)
    required_mbps: Optional[float] = None     # bitrate the chosen quality needs
    host: str = ""
    title: str = ""
    detail: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def headroom(self) -> Optional[float]:
        """How many times the required bitrate the connection can sustain."""
        if not self.throughput_mbps or not self.required_mbps:
            return None
        return self.throughput_mbps / self.required_mbps


@dataclass(frozen=True)
class NetworkMeasurement:
    """Result of a single network probe."""

    rtt_ms: Optional[float]
    ttfb_ms: Optional[float] = None
    host: str = ""
    clock_offset_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class LatencySample:
    """One point on the timeline shown by the UI.

    ``total_ms`` is the end-to-end estimate: how old the picture on your screen
    is compared to what happened in front of the streamer's camera, limited to
    the parts this tool can actually observe (see docs/METHODOLOGY.md).
    """

    ts: float = field(default_factory=time.time)
    network_ms: Optional[float] = None
    stream_ms: Optional[float] = None
    display_ms: Optional[float] = None
    # Screen-to-ears, measured by ear once and reused. Only meaningful for
    # someone listening on Bluetooth; 0/None for anyone on a wired output.
    audio_ms: Optional[float] = None
    total_ms: Optional[float] = None
    ok: bool = True
    estimated: bool = True
    kind: str = KIND_LIVE
    method: str = "none"
    host: str = ""
    title: str = ""
    source: str = "manual"
    throughput_mbps: Optional[float] = None
    required_mbps: Optional[float] = None
    # Whole-machine throughput, attached to every sample whatever is watched.
    up_mbps: Optional[float] = None
    down_mbps: Optional[float] = None
    # Bytes moved since the previous sample, for the daily data-usage totals.
    up_bytes: int = 0
    down_bytes: int = 0
    connections: int = 0          # how many sockets the watched app holds open
    # Which wireless link carried this sample, e.g. "Home (2.4 GHz)". Empty on
    # a wired machine, which is a fact about the machine rather than a gap.
    link: str = ""
    bssid: str = ""               # the access point, for spotting a roam
    signal_pct: Optional[int] = None
    # Whether network_ms was measured against the host named above. When the
    # edge cannot be timed the monitor falls back to the API host, which is a
    # different machine in a different place - so anything that reasons about
    # *where the server is* from the round trip has to know which it got.
    rtt_to_edge: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


class RollingStats:
    """Bounded rolling window over the most recent samples.

    Memory is capped by ``maxlen`` so the process stays flat during multi-day
    sessions.
    """

    def __init__(self, maxlen: int = 180) -> None:
        self.maxlen = max(5, int(maxlen))
        self._samples: Deque[LatencySample] = deque(maxlen=self.maxlen)

    def __len__(self) -> int:
        return len(self._samples)

    def clear(self) -> None:
        self._samples.clear()

    def resize(self, maxlen: int) -> None:
        maxlen = max(5, int(maxlen))
        if maxlen == self.maxlen:
            return
        self.maxlen = maxlen
        self._samples = deque(self._samples, maxlen=maxlen)

    def append(self, sample: LatencySample) -> None:
        self._samples.append(sample)

    @property
    def samples(self) -> list[LatencySample]:
        return list(self._samples)

    def totals(self) -> list[float]:
        return [s.total_ms for s in self._samples if s.ok and s.total_ms is not None]

    def last(self) -> Optional[LatencySample]:
        return self._samples[-1] if self._samples else None

    def avg(self) -> Optional[float]:
        values = self.totals()
        return sum(values) / len(values) if values else None

    def minimum(self) -> Optional[float]:
        values = self.totals()
        return min(values) if values else None

    def maximum(self) -> Optional[float]:
        values = self.totals()
        return max(values) if values else None

    def percentile(self, pct: float) -> Optional[float]:
        return _percentile(self.totals(), pct)

    def jitter(self) -> Optional[float]:
        """Mean absolute difference between consecutive totals (RFC 3550 style)."""
        values = self.totals()
        if len(values) < 2:
            return None
        diffs = [abs(b - a) for a, b in zip(values, values[1:])]
        return sum(diffs) / len(diffs)

    def failure_rate(self) -> float:
        if not self._samples:
            return 0.0
        failed = sum(1 for s in self._samples if not s.ok)
        return failed / len(self._samples)

    def spark_values(self, count: int) -> list[Optional[float]]:
        """Last ``count`` totals, ``None`` where a probe failed (for the sparkline)."""
        recent = list(self._samples)[-count:]
        return [s.total_ms if s.ok else None for s in recent]

    def extend(self, samples: Iterable[LatencySample]) -> None:
        for sample in samples:
            self.append(sample)
