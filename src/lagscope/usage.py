"""How much data this machine moved: today, this month, the last few days.

Next to "how fast", the question a network monitor gets asked most is "how
much" - on a phone hotspot, a capped plan, a dorm network that throttles after
50 GB. The interface counters already pass through every sample to work out
the speed; this keeps their deltas instead of throwing them away.

One line per day, kept for a bit over a year, in a small JSON file of its own.
Not in the minute-by-minute history: that keeps a week, and a month's total
needs a month. Counted while this program runs, which is said wherever the
numbers are shown - traffic while it was closed is not known and is not
estimated.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOG = logging.getLogger(__name__)

KEEP_DAYS = 400
FILE_NAME = "usage.json"


def _day_key(ts: Optional[float] = None) -> str:
    """Local calendar day: a month rolls over at local midnight, not UTC's."""
    return datetime.fromtimestamp(time.time() if ts is None else ts).strftime("%Y-%m-%d")


def format_bytes(value: Optional[float]) -> str:
    """``0 B`` / ``820 KB`` / ``14.2 MB`` / ``3.41 GB`` (1000-based, as ISPs bill)."""
    if value is None:
        return "--"
    value = max(0.0, float(value))
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if value >= size:
            number = value / size
            return f"{number:.2f} {unit}" if number < 10 else (
                f"{number:.1f} {unit}" if number < 100 else f"{number:.0f} {unit}")
    return f"{value:.0f} B"


class UsageLedger:
    """Bytes down and up per local day, persisted, thread-safe."""

    def __init__(self, path: Optional[Path] = None, keep_days: int = KEEP_DAYS) -> None:
        self.path = path
        self.keep_days = max(31, int(keep_days))
        self._lock = threading.Lock()
        self._days: Dict[str, List[int]] = {}
        self._dirty = False
        if path is not None:
            self.load()

    # ------------------------------------------------------------------ input
    def add(self, down_bytes: int, up_bytes: int, ts: Optional[float] = None) -> None:
        down = max(0, int(down_bytes or 0))
        up = max(0, int(up_bytes or 0))
        if not down and not up:
            return
        key = _day_key(ts)
        with self._lock:
            entry = self._days.setdefault(key, [0, 0])
            entry[0] += down
            entry[1] += up
            self._dirty = True

    # ----------------------------------------------------------------- output
    def day(self, when: Optional[date] = None) -> Tuple[int, int]:
        key = (when or date.today()).strftime("%Y-%m-%d")
        with self._lock:
            down, up = self._days.get(key, (0, 0))
        return down, up

    def today(self) -> Tuple[int, int]:
        return self.day()

    def month(self, when: Optional[date] = None) -> Tuple[int, int]:
        """This calendar month so far (or the month containing ``when``)."""
        prefix = (when or date.today()).strftime("%Y-%m-")
        down = up = 0
        with self._lock:
            for key, (d, u) in self._days.items():
                if key.startswith(prefix):
                    down += d
                    up += u
        return down, up

    def recent(self, days: int = 7, until: Optional[date] = None) -> List[Tuple[str, int, int]]:
        """``[(YYYY-MM-DD, down, up), ...]`` oldest first, missing days as zero."""
        end = until or date.today()
        out = []
        with self._lock:
            for offset in range(days - 1, -1, -1):
                key = (end - timedelta(days=offset)).strftime("%Y-%m-%d")
                down, up = self._days.get(key, (0, 0))
                out.append((key, down, up))
        return out

    def clear(self) -> None:
        with self._lock:
            self._days.clear()
            self._dirty = True
        self.flush()

    # ------------------------------------------------------------- persistence
    def _trim(self) -> None:
        cutoff = (date.today() - timedelta(days=self.keep_days)).strftime("%Y-%m-%d")
        for key in [key for key in self._days if key < cutoff]:
            del self._days[key]

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            LOG.warning("usage ledger unreadable, starting over: %s", exc)
            return
        days = raw.get("days", {}) if isinstance(raw, dict) else {}
        loaded: Dict[str, List[int]] = {}
        for key, value in days.items():
            try:
                datetime.strptime(key, "%Y-%m-%d")
                down, up = int(value[0]), int(value[1])
            except (TypeError, ValueError, IndexError):
                continue
            loaded[key] = [max(0, down), max(0, up)]
        with self._lock:
            # Anything counted before the file was read is kept, not replaced.
            for key, (down, up) in loaded.items():
                entry = self._days.setdefault(key, [0, 0])
                entry[0] += down
                entry[1] += up
            self._trim()

    def flush(self, force: bool = False) -> bool:
        """Write to disk if anything changed. Atomic: a crash leaves the old file."""
        if self.path is None:
            return False
        with self._lock:
            if not (self._dirty or force):
                return False
            self._trim()
            payload = {"version": 1, "days": dict(sorted(self._days.items()))}
            self._dirty = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, self.path)
            return True
        except OSError as exc:
            LOG.warning("could not save usage: %s", exc)
            with self._lock:
                self._dirty = True
            return False
