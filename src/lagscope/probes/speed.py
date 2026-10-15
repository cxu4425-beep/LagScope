"""An actual speed test: how fast is this line, really?

Every sample already carries the *passive* throughput - what the machine
happens to be moving right now. That answers "is something else eating my
line", and it cannot answer "how fast could this line go", because nothing
was asking it to go fast.

This does ask. Two things follow from that, and both matter more than the
number itself:

* **It saturates the line while it runs.** Latency will spike, the stream may
  stutter, and the minutes it covers are marked in the history so that spike
  is not later read as a fault.
* **It costs data.** Capped by time *and* bytes, whichever comes first, so a
  fast line stops at the byte cap rather than pulling down a gigabyte.

Where it downloads from is deliberate: the CDN already serving what you are
watching, when there is one. That measures the path that actually matters
rather than a generic test server on the other side of the country.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)

# TCP starts slow. The first stretch understates a fast line badly, so it is
# measured separately and thrown away rather than averaged in.
WARMUP_S = 1.0
DEFAULT_BUDGET_S = 10.0
DEFAULT_MAX_BYTES = 80 * 1024 * 1024
CHUNK_BYTES = 64 * 1024

# A public endpoint for the case where nothing else is being watched. Named
# here rather than buried, because it is a host this app talks to.
PUBLIC_URL = "https://speed.cloudflare.com/__down?bytes={bytes}"

# Roughly what each quality needs, for turning Mbps into a sentence.
QUALITY_TIERS = (
    (25.0, "speed.tier.4k"),
    (10.0, "speed.tier.1080p60"),
    (5.0, "speed.tier.1080p"),
    (2.5, "speed.tier.720p"),
    (0.0, "speed.tier.low"),
)


@dataclass(frozen=True)
class SpeedResult:
    """What one download achieved, and what it cost to find out."""

    mbps: Optional[float] = None
    bytes: int = 0
    seconds: float = 0.0
    host: str = ""
    source: str = "public"          # "stream" when it used the CDN in use
    ramp_mbps: Optional[float] = None   # including slow start, for comparison
    warmed: bool = True             # False when it ended before the ramp did
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.mbps is not None and self.error is None

    def as_dict(self) -> dict:
        return {"mbps": self.mbps, "bytes": self.bytes, "seconds": self.seconds,
                "host": self.host, "source": self.source, "warmed": self.warmed,
                "error": self.error}


def tier_key(mbps: Optional[float]) -> str:
    """The highest quality this speed comfortably carries."""
    if mbps is None:
        return "speed.tier.low"
    for threshold, key in QUALITY_TIERS:
        if mbps >= threshold:
            return key
    return "speed.tier.low"


def measure_download(session, url: str, *, budget_s: float = DEFAULT_BUDGET_S,
                     max_bytes: int = DEFAULT_MAX_BYTES, headers: Optional[dict] = None,
                     source: str = "public",
                     on_progress: Optional[Callable[[float, int], None]] = None
                     ) -> SpeedResult:
    """Download as fast as the line allows, for a bounded time and size.

    The rate is taken from the stretch *after* the warm-up, because TCP slow
    start would otherwise make a fast connection look mediocre. Both figures
    are reported so the difference is visible rather than hidden.
    """
    host = urlparse(url).hostname or ""
    if not url:
        return SpeedResult(source=source, error="no-url")

    started = time.perf_counter()
    total = 0
    warm_start: Optional[float] = None
    warm_bytes = 0

    try:
        response = session.get(url, headers=headers or {}, timeout=budget_s + 5.0,
                               stream=True)
    except Exception as exc:                      # noqa: BLE001 - report anything
        return SpeedResult(host=host, source=source, error=str(exc)[:160])

    try:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
            if not chunk:
                continue
            now = time.perf_counter()
            elapsed = now - started
            total += len(chunk)

            if warm_start is None and elapsed >= WARMUP_S:
                warm_start, warm_bytes = now, 0     # the clock that counts
            elif warm_start is not None:
                warm_bytes += len(chunk)

            if on_progress is not None:
                on_progress(elapsed, total)
            if elapsed >= budget_s or total >= max_bytes:
                break
    except Exception as exc:                      # noqa: BLE001
        if total <= 0:
            return SpeedResult(host=host, source=source, error=str(exc)[:160])
        LOG.debug("speed test ended early: %s", exc)
    finally:
        response.close()

    total_s = max(1e-6, time.perf_counter() - started)
    if total <= 0:
        return SpeedResult(host=host, source=source, seconds=total_s, error="no-data")

    ramp_mbps = (total * 8) / total_s / 1_000_000.0
    if warm_start is not None and warm_bytes > 0:
        warm_s = max(1e-6, time.perf_counter() - warm_start)
        mbps = (warm_bytes * 8) / warm_s / 1_000_000.0
        warmed = True
    else:
        # It finished before slow start was over - a small file or a slow line.
        # The whole-run figure is all there is, and it is honest about being it.
        mbps, warmed = ramp_mbps, False

    return SpeedResult(mbps=mbps, bytes=total, seconds=total_s, host=host,
                       source=source, ramp_mbps=ramp_mbps, warmed=warmed)


def public_url(max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    return PUBLIC_URL.format(bytes=int(max_bytes))


# ------------------------------------------------------------------ upload
# Cloudflare's public speed test accepts a POST of any size and throws it away.
PUBLIC_UP_URL = "https://speed.cloudflare.com/__up"


def measure_upload(session, url: str = PUBLIC_UP_URL, *, budget_s: float = DEFAULT_BUDGET_S,
                   max_bytes: int = DEFAULT_MAX_BYTES // 2,
                   on_progress: Optional[Callable[[float, int], None]] = None
                   ) -> SpeedResult:
    """Send as fast as the line allows, for a bounded time and size.

    The body is generated chunk by chunk, so nothing the size of the test is
    ever held in memory, and the generator is the clock: a chunk is asked for
    once the previous one has been handed to the socket. Same warm-up rule as
    the download, for the same reason.
    """
    host = urlparse(url).hostname or ""
    if not url:
        return SpeedResult(source="public", error="no-url")
    payload = b"\0" * CHUNK_BYTES
    state = {"total": 0, "warm_start": None, "warm_bytes": 0, "last": None}
    started = time.perf_counter()

    def body():
        while True:
            now = time.perf_counter()
            elapsed = now - started
            state["last"] = now
            if state["warm_start"] is None and elapsed >= WARMUP_S:
                state["warm_start"], state["warm_bytes"] = now, 0
            if elapsed >= budget_s or state["total"] >= max_bytes:
                return
            if on_progress is not None:
                on_progress(elapsed, state["total"])
            yield payload
            state["total"] += len(payload)
            if state["warm_start"] is not None:
                state["warm_bytes"] += len(payload)

    try:
        response = session.post(url, data=body(), timeout=budget_s + 10.0,
                                headers={"Content-Type": "application/octet-stream"})
        response.close()
    except Exception as exc:                      # noqa: BLE001
        if state["total"] <= 0:
            return SpeedResult(host=host, source="public", error=str(exc)[:160])
        LOG.debug("upload test ended early: %s", exc)

    ended = state["last"] or time.perf_counter()
    total = state["total"]
    total_s = max(1e-6, ended - started)
    if total <= 0:
        return SpeedResult(host=host, source="public", seconds=total_s, error="no-data")
    ramp_mbps = (total * 8) / total_s / 1_000_000.0
    if state["warm_start"] is not None and state["warm_bytes"] > 0:
        warm_s = max(1e-6, ended - state["warm_start"])
        mbps, warmed = (state["warm_bytes"] * 8) / warm_s / 1_000_000.0, True
    else:
        mbps, warmed = ramp_mbps, False
    return SpeedResult(mbps=mbps, bytes=total, seconds=total_s, host=host,
                       source="public", ramp_mbps=ramp_mbps, warmed=warmed)


# ----------------------------------------------------- latency under load
# How often to time a round trip while the line is full. Fast enough to see a
# queue build; slow enough that the pings are not themselves a load.
LOADED_PING_INTERVAL_S = 0.25
IDLE_PINGS = 5

# Bufferbloat grades by how much the round trip grows under load, the scale
# the well-known public tests use. A queue that adds 300 ms is why a video
# call breaks up the moment someone else in the house starts a download.
BLOAT_GRADES = (
    (5.0, "A+"),
    (30.0, "A"),
    (60.0, "B"),
    (200.0, "C"),
    (400.0, "D"),
)


def bloat_grade(increase_ms: Optional[float]) -> str:
    if increase_ms is None:
        return ""
    for limit, grade in BLOAT_GRADES:
        if increase_ms < limit:
            return grade
    return "F"


def _median(values) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def latency_during(work: Callable[[], object], ping: Callable[[], Optional[float]],
                   interval_s: float = LOADED_PING_INTERVAL_S) -> tuple:
    """Run ``work`` while timing round trips beside it: ``(result, [ms...])``.

    The pings run on their own thread and their own sockets, so they queue
    behind the test traffic exactly as a game's or a call's packets would.
    """
    import threading

    samples: list = []
    done = threading.Event()

    def loop():
        while not done.is_set():
            try:
                value = ping()
            except Exception:                     # noqa: BLE001
                value = None
            if value is not None:
                samples.append(value)
            done.wait(interval_s)

    thread = threading.Thread(target=loop, name="loaded-ping", daemon=True)
    thread.start()
    try:
        result = work()
    finally:
        done.set()
        thread.join(timeout=5.0)
    return result, list(samples)


@dataclass(frozen=True)
class SpeedReport:
    """A whole test: down, up, and what the load did to the round trip.

    Reads like the download result it contains (``mbps``, ``ok``, ``host``...),
    because the report, the advice and the history were all written against
    that and download is still the headline number.
    """

    download: SpeedResult
    upload: Optional[SpeedResult] = None
    idle_ms: Optional[float] = None
    loaded_down_ms: Optional[float] = None
    loaded_up_ms: Optional[float] = None

    # --- the download, as before
    @property
    def mbps(self) -> Optional[float]:
        return self.download.mbps

    @property
    def ok(self) -> bool:
        return self.download.ok

    @property
    def host(self) -> str:
        return self.download.host

    @property
    def source(self) -> str:
        return self.download.source

    @property
    def warmed(self) -> bool:
        return self.download.warmed

    @property
    def error(self) -> Optional[str]:
        return self.download.error

    @property
    def seconds(self) -> float:
        return self.download.seconds + (self.upload.seconds if self.upload else 0.0)

    @property
    def bytes(self) -> int:
        return self.download.bytes + (self.upload.bytes if self.upload else 0)

    # --- what is new
    @property
    def up_mbps(self) -> Optional[float]:
        return self.upload.mbps if (self.upload and self.upload.ok) else None

    @property
    def bloat_ms(self) -> Optional[float]:
        """How much the round trip grew at its worst while the line was full."""
        loaded = [v for v in (self.loaded_down_ms, self.loaded_up_ms) if v is not None]
        if self.idle_ms is None or not loaded:
            return None
        return max(0.0, max(loaded) - self.idle_ms)

    @property
    def grade(self) -> str:
        return bloat_grade(self.bloat_ms)

    def as_dict(self) -> dict:
        return {
            "download": self.download.as_dict(),
            "upload": self.upload.as_dict() if self.upload else None,
            "idle_ms": self.idle_ms,
            "loaded_down_ms": self.loaded_down_ms,
            "loaded_up_ms": self.loaded_up_ms,
            "bloat_ms": self.bloat_ms,
            "grade": self.grade,
        }


def run_speed_test(session, download_url: str, *, source: str = "public",
                   budget_s: float = DEFAULT_BUDGET_S, max_bytes: int = DEFAULT_MAX_BYTES,
                   ping: Optional[Callable[[], Optional[float]]] = None,
                   upload_url: Optional[str] = PUBLIC_UP_URL,
                   fallback_url: Optional[str] = None) -> SpeedReport:
    """Idle round trip, then download, then upload, each with pings beside it.

    ``ping`` times one round trip somewhere near (the internet anchor); without
    it the latency half is skipped and the report says nothing about it rather
    than guessing. Upload uses half the byte cap: on most lines it is the
    slower direction, and on a metered one it is paid for just the same.
    """
    idle = None
    if ping is not None:
        idle = _median(ping() for _ in range(IDLE_PINGS))

    def down():
        result = measure_download(session, download_url, budget_s=budget_s,
                                  max_bytes=max_bytes, source=source)
        if not result.ok and fallback_url:
            LOG.debug("speed test on %s failed (%s); using the public one",
                      source, result.error)
            result = measure_download(session, fallback_url, budget_s=budget_s,
                                      max_bytes=max_bytes, source="public")
        return result

    if ping is not None:
        download, down_pings = latency_during(down, ping)
    else:
        download, down_pings = down(), []

    upload = None
    up_pings: list = []
    if upload_url and download.ok:
        def up():
            return measure_upload(session, upload_url, budget_s=budget_s,
                                  max_bytes=max(1, max_bytes // 2))
        if ping is not None:
            upload, up_pings = latency_during(up, ping)
        else:
            upload = up()

    return SpeedReport(download=download, upload=upload, idle_ms=idle,
                       loaded_down_ms=_median(down_pings),
                       loaded_up_ms=_median(up_pings) if upload else None)
