"""Client -> display probe.

Nothing outside the GPU can time the exact moment a pixel lights up, so this
probe measures what a normal application *can* observe:

* how long the UI thread takes to get a scheduled callback (event-loop lag),
* the real interval between two presented frames (the compositor cadence).

From those it estimates the queueing delay between "the client has decoded a
frame" and "that frame is on the panel", using the number of frames the
compositor keeps in flight plus an optional panel offset the user can enter.
See docs/METHODOLOGY.md for why this is an estimate, never a measurement.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from typing import Deque, Optional


class DisplayProbe:
    def __init__(self, window: int = 90, fallback_hz: float = 60.0) -> None:
        self._intervals: Deque[float] = deque(maxlen=max(10, window))
        self._loop_lags: Deque[float] = deque(maxlen=max(10, window))
        self._last_frame_ts: Optional[float] = None
        self.fallback_hz = fallback_hz
        self.refresh_hz: Optional[float] = None

    # ------------------------------------------------------------- collectors
    def record_frame(self, now: Optional[float] = None) -> None:
        """Call once per painted frame of the overlay."""
        now = time.perf_counter() if now is None else now
        if self._last_frame_ts is not None:
            delta_ms = (now - self._last_frame_ts) * 1000.0
            # Ignore stalls: a hidden or occluded window stops painting and
            # would otherwise poison the median with multi-second gaps.
            if 0.5 <= delta_ms <= 200.0:
                self._intervals.append(delta_ms)
        self._last_frame_ts = now

    def record_loop_lag(self, lag_ms: float) -> None:
        """Call with the overshoot of a zero-delay timer, in milliseconds."""
        if lag_ms >= 0.0:
            self._loop_lags.append(min(lag_ms, 1000.0))

    def notify_hidden(self) -> None:
        """The overlay stopped painting; drop the stale frame anchor."""
        self._last_frame_ts = None

    def reset(self) -> None:
        self._intervals.clear()
        self._loop_lags.clear()
        self._last_frame_ts = None

    # ----------------------------------------------------------------- values
    @property
    def frame_ms(self) -> Optional[float]:
        if not self._intervals:
            return None
        return statistics.median(self._intervals)

    @property
    def frame_jitter_ms(self) -> Optional[float]:
        if len(self._intervals) < 2:
            return None
        return statistics.pstdev(self._intervals)

    @property
    def loop_lag_ms(self) -> Optional[float]:
        if not self._loop_lags:
            return None
        return statistics.median(self._loop_lags)

    def frame_period_ms(self) -> float:
        """Best available frame period: measured, then reported refresh rate."""
        from ..health import DISPLAY, HEALTH

        measured = self.frame_ms
        if measured is not None:
            HEALTH.working(DISPLAY)
            return measured
        hz = self.refresh_hz or self.fallback_hz
        if hz:
            # A reported rate rather than a measured one: fine, and worth
            # nobody's attention.
            HEALTH.working(DISPLAY)
            return 1000.0 / hz
        # Neither measured nor reported. 16.67 ms is a guess that 60 Hz is
        # right, and it goes straight into the headline total as if it had
        # been observed.
        HEALTH.degraded(DISPLAY, "assuming 60 Hz: no frame timing, no reported rate")
        return 16.67

    def estimate_ms(self, frames_in_flight: float = 2.0, manual_offset_ms: float = 0.0) -> float:
        """Estimated client -> photons delay in milliseconds."""
        period = self.frame_period_ms()
        queueing = period * max(0.0, frames_in_flight)
        return queueing + max(0.0, manual_offset_ms) + (self.loop_lag_ms or 0.0)

    def snapshot(self, frames_in_flight: float = 2.0, manual_offset_ms: float = 0.0) -> dict:
        return {
            "frame_ms": self.frame_ms,
            "frame_jitter_ms": self.frame_jitter_ms,
            "loop_lag_ms": self.loop_lag_ms,
            "refresh_hz": self.refresh_hz,
            "display_ms": self.estimate_ms(frames_in_flight, manual_offset_ms),
        }
