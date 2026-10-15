"""Latency to "the internet", for someone who has not named anything to watch.

Most people who open a network monitor want one answer before any other: is my
connection all right, right now? That needs a target, and asking a new user to
type one in is asking them to already know the answer to a question they came
here with.

So the target is chosen automatically, from a short list of anycast services -
addresses that are answered by whichever of the operator's sites is nearest,
on every continent. Measured against one of them, the round trip says how far
this machine is from the well-connected core of the internet, which is the
honest meaning of "my ping".

Why a list rather than one: no single address is good everywhere. 8.8.8.8 is
blocked in mainland China; 223.5.5.5 is a long way from Europe; a corporate
network may filter any of them. Each is timed once, the nearest is kept, and the
choice is reconsidered every half hour - a laptop moves between networks - and
straight away after a run of failures, because a filtered anchor looks exactly
like a dead connection from here.

TCP on 443 first (every one of these serves DNS-over-HTTPS there, so a
handshake is answered without sending a single query), the system ``ping`` when
TCP is blocked.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from .network import icmp_ping_ms, tcp_rtt_ms

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Anchor:
    """One well-known address to measure the internet against."""

    host: str
    port: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} {self.host}"

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


# Anycast resolvers that also serve HTTPS on 443. Order is only a tie-break.
ANCHORS: Sequence[Anchor] = (
    Anchor("1.1.1.1", 443, "Cloudflare"),
    Anchor("8.8.8.8", 443, "Google"),
    Anchor("223.5.5.5", 443, "AliDNS"),
    Anchor("9.9.9.9", 443, "Quad9"),
)

RECHOOSE_S = 30 * 60.0
# Consecutive failures on the chosen anchor before trying the others again.
# Low enough that a filtered address is abandoned within seconds; not one,
# because a single lost handshake is ordinary packet loss and should be
# reported as such rather than hidden by quietly switching targets.
FAILURES_BEFORE_RECHOOSE = 3
# With no network at all every anchor times out, so re-choosing is the most
# expensive thing a round can do. It is tried at most this often while nothing
# answers; in between, each round costs one timeout against one address.
RETRY_S = 120.0
# Choosing is a survey, not the measurement: an anchor slower than this to
# answer is not going to be the nearest one anyway.
CHOOSE_TIMEOUT_S = 1.5


@dataclass(frozen=True)
class InternetResult:
    rtt_ms: Optional[float]
    method: str                 # "tcp" | "icmp" | "none"
    anchor: Optional[Anchor]

    @property
    def ok(self) -> bool:
        return self.rtt_ms is not None


class InternetProbe:
    """Picks the nearest anchor and keeps measuring it."""

    def __init__(self, anchors: Sequence[Anchor] = ANCHORS,
                 connect: Callable[..., Optional[float]] = tcp_rtt_ms,
                 ping: Callable[..., Optional[float]] = icmp_ping_ms,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not anchors:
            raise ValueError("at least one anchor is needed")
        self._anchors = tuple(anchors)
        self._connect = connect
        self._ping = ping
        self._clock = clock
        self._chosen: Optional[Anchor] = None
        self._chosen_at = 0.0
        self._tried_at: Optional[float] = None
        self._failures = 0

    @property
    def anchor(self) -> Optional[Anchor]:
        return self._chosen

    def reset(self) -> None:
        """Forget the choice, e.g. after the network changed."""
        self._chosen = None
        self._chosen_at = 0.0
        self._tried_at = None
        self._failures = 0

    def _time(self, anchor: Anchor, timeout_s: float, icmp: bool = True) -> tuple:
        rtt = self._connect(anchor.host, anchor.port, timeout_s)
        if rtt is not None:
            return rtt, "tcp"
        if icmp:
            rtt = self._ping(anchor.host, timeout_s)
            if rtt is not None:
                return rtt, "icmp"
        return None, "none"

    def choose(self, timeout_s: float = CHOOSE_TIMEOUT_S) -> Optional[Anchor]:
        """Time every anchor and keep the nearest that answered.

        Twice each and the better of the two, because the first handshake to a
        new address can include a cold route that has nothing to do with
        distance. TCP for everyone first; ping only if no anchor answered TCP
        at all, since a network that filters handshakes filters them for every
        address alike. Returns the new choice, or None - in which case the
        previous choice, if any, is kept to go on measuring.
        """
        now = self._clock()
        self._tried_at = now
        best: Optional[Anchor] = None
        best_rtt = float("inf")
        for icmp in (False, True):
            for anchor in self._anchors:
                first, _ = self._time(anchor, timeout_s, icmp=icmp)
                if first is None:
                    continue
                second, _ = self._time(anchor, timeout_s, icmp=icmp)
                rtt = first if second is None else min(first, second)
                if rtt < best_rtt:
                    best, best_rtt = anchor, rtt
            if best is not None:
                break
        if best is None:
            LOG.info("no internet anchor answered")
            return None
        if best != self._chosen:
            LOG.info("internet anchor: %s (%.1f ms)", best.label, best_rtt)
        self._chosen = best
        self._chosen_at = now
        self._failures = 0
        return best

    def _should_choose(self, now: float) -> bool:
        recently_tried = (self._tried_at is not None
                          and now - self._tried_at < RETRY_S)
        if self._chosen is None:
            return not recently_tried
        if self._failures >= FAILURES_BEFORE_RECHOOSE:
            return not recently_tried
        return now - self._chosen_at >= RECHOOSE_S

    def measure(self, timeout_s: float = 4.0) -> InternetResult:
        """One round trip to the internet, choosing where to first if due."""
        if self._should_choose(self._clock()):
            self.choose(min(timeout_s, CHOOSE_TIMEOUT_S))
        # Before anything has ever answered there is no choice to measure, but
        # the round still has to say whether the internet is reachable.
        anchor = self._chosen or self._anchors[0]
        rtt, method = self._time(anchor, timeout_s)
        if rtt is None:
            self._failures += 1
        else:
            self._failures = 0
        return InternetResult(rtt, method, anchor)
