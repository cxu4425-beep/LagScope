"""Spotting the moments that matter: stalls, spikes and recoveries.

A number that is bad *right now* is easy to see on the overlay. What people
actually remember is "it hiccuped four times this evening", so every failed
probe and every sudden jump is recorded as an event, counted over a rolling
window, and optionally announced once (never once per sample).
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .models import LatencySample

STALL = "stall"        # the probe failed outright: stream down, app unreachable
SPIKE = "spike"        # latency jumped far above this connection's own normal

# Below this, a jump is arithmetic rather than experience. Nobody notices 18 ms
# becoming 37 - it doubled, but it is still instant - and a rule that counts it
# buries the 200 ms jump that ruined a stream.
SPIKE_FLOOR_MS = 30.0

# Where the bar sits in this connection's own recent distribution. A high
# percentile rather than a multiple of the average, because latency is not
# symmetrical: the middle is tight and the tail is long, so anything built on
# the spread around the middle lands well inside ordinary traffic.
SPIKE_PERCENTILE = 0.99

# How many samples in a row have to be bad. This is the part that matters. One
# sample above any bar is not something a person experiences - a wireless link
# produces those all day - and counting them is what turned two days into 1,421
# "spikes". Judging the median of the last few samples instead asks whether the
# connection is *staying* bad, which is the thing that ruins a stream.
#
# Measured rather than guessed: against two simulated days at jitter from mild
# to severe, with twenty bad stretches planted, one sample reported between 185
# and 5,047 events. A five-sample window reported 18 to 19 of the 20 at every
# jitter level, and stayed flat out to nine samples - so this sits in the
# middle of a wide plateau rather than on a lucky value.
SPIKE_RUN = 5

# How much history counts as "normal". The old rule compared against the last
# sixty samples - about two minutes - so an evening of slowly worsening latency
# never registered at all: every value looked normal next to the two minutes
# before it. Half an hour is long enough to have an opinion.
BASELINE_S = 1800.0

# A spike is kept out of the baseline so it cannot raise the bar it was
# measured against. Left at that, a connection that simply gets worse and
# stays worse would be compared against its old self forever: the first bad
# sample is an event, every one after it is "still spiking", and the baseline
# never moves. So once a run of bad samples lasts this long it stops being an
# event and becomes the new normal, which is what it is.
LEVEL_SHIFT_S = 120.0


@dataclass(frozen=True)
class Event:
    kind: str
    ts: float
    value_ms: Optional[float] = None
    baseline_ms: Optional[float] = None
    # What it had to beat, so a notification can say "220 ms, and 105 would
    # have been unusual" rather than leaving the reader to trust the label.
    threshold_ms: Optional[float] = None
    detail: str = ""


class EventLog:
    """Rolling record of stalls and spikes over the last ``window_s`` seconds."""

    def __init__(self, window_s: float = 3600.0,
                 percentile: float = SPIKE_PERCENTILE,
                 run: int = SPIKE_RUN,
                 floor_ms: float = SPIKE_FLOOR_MS,
                 baseline_s: float = BASELINE_S,
                 level_shift_s: float = LEVEL_SHIFT_S,
                 min_baseline_samples: int = 10, maxlen: int = 500) -> None:
        self.window_s = max(60.0, float(window_s))
        self.percentile = min(0.999, max(0.5, float(percentile)))
        self.run = max(1, int(run))
        self.floor_ms = max(0.0, float(floor_ms))
        self.baseline_s = max(60.0, float(baseline_s))
        self.level_shift_s = max(30.0, float(level_shift_s))
        self.min_baseline_samples = max(3, int(min_baseline_samples))
        self._events: Deque[Event] = deque(maxlen=maxlen)
        # (timestamp, value): trimmed by age rather than by count, so the
        # horizon is half an hour whatever the probe interval happens to be.
        self._recent: Deque[tuple] = deque(maxlen=4000)
        self._in_stall = False
        self._in_spike = False
        self._run: list = []            # samples inside an episode, held aside
        # The last few samples, whose median is what gets judged. They are also
        # what delays admission to the baseline: a sample only counts as normal
        # once the window it sat in has passed without an episode, so the start
        # of a bad stretch can never be learned as normal on its way in.
        self._window: Deque[tuple] = deque(maxlen=self.run)

    # ------------------------------------------------------------------ input
    def observe(self, sample: LatencySample) -> Optional[Event]:
        """Feed one sample; returns a new event when this sample starts one."""
        now = sample.ts or time.time()
        event: Optional[Event] = None

        if not sample.ok:
            # Only the first failure of a run is an event, not every retry.
            if not self._in_stall:
                event = Event(kind=STALL, ts=now, detail=(sample.error or "")[:120])
                self._events.append(event)
            self._in_stall = True
            self._in_spike = False
            # The stretch of bad samples is over - it ended in a failure. Left
            # in place, its first timestamp would later be measured against a
            # sample from after the outage, and a gap of any length would look
            # like a two-minute run of bad latency that never happened.
            self._run = []
            return event

        self._in_stall = False
        value = sample.total_ms
        if value is None:
            return None

        self._trim(now)
        self._window.append((now, value))
        threshold = self.threshold()
        level = statistics.median([item[1] for item in self._window])

        if threshold is not None and level > threshold:
            if not self._in_spike:
                # Reported as the worst value in the window rather than the
                # median, so the number in the notification is one that
                # actually happened.
                event = Event(kind=SPIKE, ts=now,
                              value_ms=max(item[1] for item in self._window),
                              baseline_ms=self.baseline(), threshold_ms=threshold)
                self._events.append(event)
            self._in_spike = True
            # Held aside rather than dropped: a hiccup is thrown away, but a
            # stretch this long is the connection's new normal and has to be
            # learned, or nothing will ever look normal again.
            self._run.append((now, value))
            if self._run[-1][0] - self._run[0][0] >= self.level_shift_s:
                self._recent.extend(self._run)
                self._run = []
                self._in_spike = False
                self._window.clear()
        else:
            self._in_spike = False
            self._run = []
            if len(self._window) == self._window.maxlen:
                # The sample now leaving the window. Admitting it only once its
                # whole window has passed quietly is what stops the first few
                # samples of a bad stretch being learned as normal before the
                # median notices them - which quietly raises the bar out of
                # reach and makes the episode itself invisible.
                self._recent.append(self._window[0])
        return event

    def _trim(self, now: float) -> None:
        cutoff = now - self.baseline_s
        while self._recent and self._recent[0][0] < cutoff:
            self._recent.popleft()

    def _values(self) -> list:
        return [value for _ts, value in self._recent]

    def baseline(self) -> Optional[float]:
        """What this connection normally does, over the last half hour."""
        if len(self._recent) < self.min_baseline_samples:
            return None
        return statistics.median(self._values())

    def unusual_ms(self) -> Optional[float]:
        """How high this connection gets on an ordinary day.

        The point of the whole exercise: a link that sits at 30 ms and one that
        swings between 30 and 300 do not deserve the same bar, and neither of
        them deserves a bar chosen by whoever wrote the program.
        """
        values = self._values()
        if len(values) < self.min_baseline_samples:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(len(ordered) * self.percentile))
        return ordered[index]

    def threshold(self) -> Optional[float]:
        """What the last few samples have to stay above to be worth reporting."""
        baseline = self.baseline()
        unusual = self.unusual_ms()
        if baseline is None or unusual is None:
            return None
        # The floor keeps arithmetic out of it: on a link that never leaves
        # 18 ms its own 99th percentile might be 21, and nobody has ever
        # noticed three milliseconds.
        return max(unusual, baseline + self.floor_ms)

    # ----------------------------------------------------------------- output
    def _fresh(self) -> list:
        cutoff = time.time() - self.window_s
        return [event for event in self._events if event.ts >= cutoff]

    def count(self, kind: Optional[str] = None) -> int:
        return sum(1 for event in self._fresh() if kind is None or event.kind == kind)

    def last(self) -> Optional[Event]:
        events = self._fresh()
        return events[-1] if events else None

    def summary(self) -> dict:
        events = self._fresh()
        last = events[-1] if events else None
        return {
            "window_min": int(self.window_s / 60),
            "stalls": sum(1 for event in events if event.kind == STALL),
            "spikes": sum(1 for event in events if event.kind == SPIKE),
            "baseline_ms": self.baseline(),
            "threshold_ms": self.threshold(),
            "last": None if last is None else {
                "kind": last.kind,
                "ago_s": round(max(0.0, time.time() - last.ts), 1),
                "value_ms": last.value_ms,
            },
        }

    def clear(self) -> None:
        self._events.clear()
        self._recent.clear()
        self._in_stall = False
        self._in_spike = False
        self._run = []
        self._window.clear()


class Notifier:
    """Rate limit for tray notifications: at most one per ``cooldown_s``."""

    def __init__(self, cooldown_s: float = 300.0) -> None:
        self.cooldown_s = max(30.0, float(cooldown_s))
        self._last_sent = 0.0

    def should_notify(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if now - self._last_sent < self.cooldown_s:
            return False
        self._last_sent = now
        return True

    def reset(self) -> None:
        self._last_sent = 0.0
