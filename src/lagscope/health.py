"""What this program currently cannot measure, and what that costs.

Every probe here degrades quietly. When the Wi-Fi state cannot be read the
history simply records no wireless; when ICMP is blocked the network figure
silently becomes a TCP handshake instead; when the frame timing is unavailable
the display estimate disappears from the total. In each case a number changes
meaning - or stops existing - and nothing says so.

That is not a hypothetical. The Wi-Fi reading failed on a real machine for two
days. The report concluded "no wireless recorded (probably a wired
connection)" about a laptop that has never been plugged in, and the only trace
anywhere was a debug-level log line nobody would see. The measurement being
best-effort is a reasonable design; being indistinguishable from *not needing
it* is not.

So a probe that cannot do its job says so here, once, with the reason. Anything
that shows results can then say which of them are missing and why. Recovery is
reported the same way, because a fault that fixed itself should stop being
reported.

Thread-safe because the probes run on the monitor's worker thread while the UI
reads from the main one.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

# What is degraded, as an i18n key, paired with the key that says what it
# costs. Kept together so a new entry cannot be added without saying why it
# matters - a list of faults with no consequences is just noise.
WIFI = "health.wifi"
ICMP = "health.icmp"
DISPLAY = "health.display"
AUDIO = "health.audio"
WINDOW = "health.window"

CONSEQUENCE = {
    WIFI: "health.wifi.cost",
    ICMP: "health.icmp.cost",
    DISPLAY: "health.display.cost",
    AUDIO: "health.audio.cost",
    WINDOW: "health.window.cost",
}


@dataclass(frozen=True)
class Degradation:
    """One thing that is not working, and since when."""

    key: str
    detail: str = ""          # an observed reason, already formatted
    since: float = 0.0

    @property
    def consequence_key(self) -> str:
        return CONSEQUENCE.get(self.key, "")

    def as_dict(self) -> dict:
        return {"key": self.key, "detail": self.detail, "since": self.since,
                "consequence": self.consequence_key}


class Health:
    """Which measurements are currently working, and which are not."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._faults: Dict[str, Degradation] = {}

    def degraded(self, key: str, detail: str = "", now: Optional[float] = None) -> bool:
        """Record that ``key`` cannot be measured. True if this is news.

        Repeated reports keep the original timestamp: "since 14:02" is more
        useful than a clock that resets every thirty seconds. A changed reason
        does replace the old one, because the second reason is the current one.
        """
        stamp = time.time() if now is None else now
        with self._lock:
            existing = self._faults.get(key)
            if existing is not None and existing.detail == detail:
                return False
            self._faults[key] = Degradation(
                key=key, detail=detail[:200],
                since=existing.since if existing is not None else stamp)
            return existing is None

    def working(self, key: str) -> bool:
        """Record that ``key`` is fine. True if it had been reported broken."""
        with self._lock:
            return self._faults.pop(key, None) is not None

    def current(self) -> List[Degradation]:
        """Everything currently degraded, longest-standing first."""
        with self._lock:
            return sorted(self._faults.values(), key=lambda item: item.since)

    def is_degraded(self, key: str) -> bool:
        with self._lock:
            return key in self._faults

    def clear(self) -> None:
        with self._lock:
            self._faults.clear()


# One registry for the process, imported the way LOG is. The probes that fail
# are scattered across modules and threads; handing an instance to each of them
# would be a lot of plumbing for a list of five things.
HEALTH = Health()
