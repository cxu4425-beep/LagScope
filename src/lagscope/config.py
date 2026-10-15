"""Per-user configuration.

The config lives in the current user's own config directory, so several people
can use the same machine (or the same portable copy of the .exe) without
sharing settings. Nothing here requires a Bilibili account or a cookie.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any, Optional

from . import APP_ID, APP_NAME, LEGACY_APP_ID, LEGACY_APP_NAME
from .i18n import LANGUAGES
from .probes.video import parse_video_id, parse_video_page

CONFIG_VERSION = 1

_ROOM_URL_RE = re.compile(r"live\.bilibili\.com/(?:blanc/|h5/)?(\d+)", re.IGNORECASE)
_DIGITS_RE = re.compile(r"^\d{1,12}$")


def _config_dir_for(app_name: str, app_id: str) -> Path:
    """Where a per-user config folder lives on this platform."""
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / app_id


def app_config_dir() -> Path:
    """Return (and create) this user's config directory."""
    override = os.environ.get("LAGSCOPE_CONFIG_DIR")
    if override:
        base = Path(override).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        return base
    base = _config_dir_for(APP_NAME, APP_ID)
    if not base.exists():
        _migrate_legacy_config(base)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _migrate_legacy_config(target: Path) -> None:
    """Carry settings over from the pre-rename folder, once.

    The app was called "Bilibili Latency Monitor" up to 1.1.1; an upgrade should
    not silently reset someone's overlay position and room.
    """
    source = _config_dir_for(LEGACY_APP_NAME, LEGACY_APP_ID)
    if not source.is_dir() or source == target:
        return
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "titles.json"):
            old = source / name
            if old.is_file():
                shutil.copy2(old, target / name)
    except OSError:
        # A failed migration just means starting from defaults, never a crash.
        pass


def config_path() -> Path:
    return app_config_dir() / "config.json"


def title_memory_path() -> Path:
    """Where learned "window title -> room/video" pairs are kept."""
    return app_config_dir() / "titles.json"


def log_dir() -> Path:
    path = app_config_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_room_id(text: str) -> str:
    """Accept a room id, a live URL, or a pasted address bar; return the id."""
    text = (text or "").strip()
    if not text:
        return ""
    match = _ROOM_URL_RE.search(text)
    if match:
        return match.group(1)
    if _DIGITS_RE.match(text):
        return text
    return ""


@dataclass
class OverlayConfig:
    enabled: bool = True
    # "free"    - wherever you dragged it
    # "screen"  - pinned to a corner of a chosen screen
    # "window"  - follows the Bilibili window (Windows only, falls back to screen)
    anchor_mode: str = "free"
    x: int = 80
    y: int = 80
    screen_name: str = ""
    corner: str = "top-right"      # top-left | top-right | bottom-left | bottom-right
    offset_x: int = 24
    offset_y: int = 24
    opacity: float = 0.88
    scale: float = 1.0
    always_on_top: bool = True
    click_through: bool = False
    locked: bool = False
    compact: bool = False
    show_breakdown: bool = True
    # Where the serving CDN edge is: what the hostname says, plus how far
    # away the round trip proves it cannot be past.
    show_server: bool = True
    show_sparkline: bool = True
    show_stats: bool = True
    theme: str = "dark"            # dark | light | pink
    follow_window_keyword: str = "哔哩哔哩"


@dataclass
class TrayConfig:
    enabled: bool = True
    show_value_in_icon: bool = True


@dataclass
class ProbeConfig:
    interval_ms: int = 2000
    timeout_ms: int = 4000
    playurl_refresh_s: int = 240
    rtt_host: str = "api.live.bilibili.com"
    rtt_port: int = 443
    prefer_hls: bool = True
    player_buffer_segments: float = 1.0
    max_backoff_multiplier: int = 8
    # Bilibili offers the same room from several CDN edges and the player just
    # takes the first one. When a clearly faster edge exists, move to it.
    auto_cdn: bool = True


@dataclass
class DisplayConfig:
    # Frames the compositor keeps in flight before a frame is lit up.
    frames_in_flight: float = 2.0
    # Panel input lag you measured yourself (e.g. from a review site), in ms.
    manual_offset_ms: float = 0.0
    include_in_total: bool = True


@dataclass
class AudioConfig:
    """The last hop: screen to ears.

    Everything else the app measures ends at the picture. Anyone listening on
    Bluetooth has one more delay after that, usually a bigger one than the
    display adds, and no operating system will report it - so this is a number
    the person measures once, by ear, with the calibration dialog.

    It is stored rather than guessed from the codec on purpose. A table saying
    "SBC is about 200 ms" would produce a plausible number for the wrong
    headset, and a plausible wrong number is worse here than no number.
    """

    # How much later the sound arrives than the picture, in ms. 0 = not measured.
    offset_ms: float = 0.0
    include_in_total: bool = True
    # What it was measured with, so a later reader knows which headset it is for.
    device_note: str = ""
    # When it was measured (unix seconds); a calibration for headphones you no
    # longer own should be recognisable as stale.
    measured_at: float = 0.0

    @property
    def measured(self) -> bool:
        return self.offset_ms > 0.0


@dataclass
class RecordingConfig:
    csv_enabled: bool = False
    csv_max_bytes: int = 8 * 1024 * 1024
    csv_backups: int = 3


@dataclass
class DetectConfig:
    """Automatic detection of what you are watching (every source optional)."""

    # Off for a fresh install: following Bilibili pages is for people who
    # asked for it, and everyone else would be told "detecting..." forever.
    enabled: bool = False
    use_client: bool = True       # read the official desktop client's own data folder
    use_history: bool = True      # newest bilibili.com URL in the browser history
    use_titles: bool = True       # match it against open window titles (Windows)
    use_bridge: bool = False      # accept reports from the companion userscript
    use_clipboard: bool = True    # a link copied from the desktop client's share menu
    remember_titles: bool = True  # learn which window title belongs to which page
    follow_videos: bool = True    # follow video pages too, not only live rooms
    # Extra folders to look in when the client is installed somewhere unusual.
    client_dirs: list = field(default_factory=list)
    history_window_min: int = 30
    poll_interval_s: int = 5
    bridge_port: int = 23124
    bridge_timeout_s: int = 120


@dataclass
class WebConfig:
    """The read-only dashboard a phone on the same network can open."""

    enabled: bool = False         # off until asked for: it opens a LAN port
    port: int = 23125
    access_code: str = ""         # empty means anyone on the LAN can look
    bind_host: str = "0.0.0.0"    # the phone has to reach it, so not loopback


@dataclass
class HistoryConfig:
    """Minute-by-minute history, kept so the chart and the report have data.

    One row per minute rather than one per sample: a day costs around 130 KB,
    which is what makes keeping two days of it reasonable.
    """

    enabled: bool = True
    keep_hours: int = 168
    bucket_s: int = 60
    # When something breaks, find out why without being asked: a cut-down path
    # check runs in the background and its verdict is filed against that minute.
    auto_check: bool = True
    auto_check_cooldown_s: int = 600


@dataclass
class SpeedConfig:
    """The on-demand speed test. It saturates the line, so nothing is automatic.

    Both caps exist because this costs data: whichever is reached first ends
    the test, so a gigabit line stops at the byte cap rather than pulling down
    a gigabyte to prove a point.
    """

    budget_s: int = 10
    max_mb: int = 80


@dataclass
class UpdateConfig:
    """Checking whether a newer release exists. One request, nothing sent."""

    enabled: bool = True
    last_checked: float = 0.0     # unix time of the last successful check
    skip_version: str = ""        # "remind me about anything newer than this"


@dataclass
class ThresholdConfig:
    """Where green turns yellow and yellow turns red.

    Two scales, because two different things are measured. A Bilibili stream
    is seconds behind live and 3 s is good; a network round trip is tens of
    milliseconds and 300 ms is bad. One pair of numbers cannot serve both, and
    with the stream pair applied to a ping every result would be green.
    """

    good_ms: float = 2000.0         # stream delay (Bilibili live / video)
    warn_ms: float = 5000.0
    net_good_ms: float = 80.0       # network round trip (internet, app, address)
    net_warn_ms: float = 150.0


@dataclass
class Config:
    version: int = CONFIG_VERSION
    language: str = "auto"          # auto | zh_CN | zh_TW | en
    room_id: str = ""
    video_id: str = ""              # BV id (or avNNN), used when manual_kind is "video"
    video_page: int = 1             # which part (P) of that video
    # network | live | video | app | target - what to watch when Bilibili
    # auto-detection is off. A fresh install watches the internet connection
    # itself, which needs nothing typed in; saved configs keep what they had.
    manual_kind: str = "network"
    app_name: str = ""              # process to follow in "app" mode (e.g. game.exe)
    app_follow_foreground: bool = False   # or just follow whatever app is in front
    target_host: str = ""           # host to ping in "target" mode
    target_port: int = 443
    show_netspeed: bool = True      # attach up/down speed to every sample
    # Extra things to keep an eye on beside the main one: [{kind,ident,port,label}].
    # "Is my game laggy, or is the whole line?" needs more than one number.
    watch_extras: list = field(default_factory=list)
    notify_enabled: bool = True     # tray balloon when a stall or spike happens
    # False until the setup wizard has been through once, on a fresh install.
    setup_done: bool = False
    sample_window: int = 180
    autostart: bool = False
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    updates: UpdateConfig = field(default_factory=UpdateConfig)
    speed: SpeedConfig = field(default_factory=SpeedConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    web: WebConfig = field(default_factory=WebConfig)

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return _build(cls, data or {})

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return cls()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # A corrupt config must never stop the app from starting.
            _quarantine(path)
            return cls()
        if not isinstance(data, dict):
            _quarantine(path)
            return cls()
        return cls.from_dict(data)

    def save(self, path: Optional[Path] = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        # Atomic write: a crash mid-save must not truncate the config.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.replace(tmp_name, path)

    def sanitized(self) -> "Config":
        """Clamp every value into a range the UI and probes can survive."""
        self.probe.interval_ms = int(_clamp(self.probe.interval_ms, 500, 60_000))
        self.probe.timeout_ms = int(_clamp(self.probe.timeout_ms, 1000, 30_000))
        self.probe.playurl_refresh_s = int(_clamp(self.probe.playurl_refresh_s, 30, 3600))
        self.probe.rtt_port = int(_clamp(self.probe.rtt_port, 1, 65535))
        self.probe.player_buffer_segments = _clamp(self.probe.player_buffer_segments, 0.0, 10.0)
        self.probe.max_backoff_multiplier = int(_clamp(self.probe.max_backoff_multiplier, 1, 60))
        self.overlay.opacity = _clamp(self.overlay.opacity, 0.2, 1.0)
        self.overlay.scale = _clamp(self.overlay.scale, 0.6, 3.0)
        self.sample_window = int(_clamp(self.sample_window, 20, 5000))
        self.display.frames_in_flight = _clamp(self.display.frames_in_flight, 0.0, 6.0)
        self.display.manual_offset_ms = _clamp(self.display.manual_offset_ms, 0.0, 500.0)
        # 500 ms is past anything a real headset does; beyond that the
        # number is a mistake rather than a measurement.
        self.audio.offset_ms = _clamp(self.audio.offset_ms, 0.0, 500.0)
        self.audio.device_note = str(self.audio.device_note or "")[:80]
        self.thresholds.net_good_ms = _clamp(self.thresholds.net_good_ms, 1.0, 10_000.0)
        self.thresholds.net_warn_ms = _clamp(
            self.thresholds.net_warn_ms, self.thresholds.net_good_ms, 10_000.0)
        self.thresholds.good_ms = _clamp(self.thresholds.good_ms, 10.0, 600_000.0)
        self.thresholds.warn_ms = _clamp(self.thresholds.warn_ms, self.thresholds.good_ms, 600_000.0)
        if self.overlay.anchor_mode not in ("free", "screen", "window"):
            self.overlay.anchor_mode = "free"
        if self.overlay.corner not in ("top-left", "top-right", "bottom-left", "bottom-right"):
            self.overlay.corner = "top-right"
        if self.overlay.theme not in ("dark", "light", "pink"):
            self.overlay.theme = "dark"
        if self.language not in ("auto", *LANGUAGES):
            self.language = "auto"
        if not isinstance(self.detect.client_dirs, list):
            self.detect.client_dirs = []
        self.detect.client_dirs = [str(path) for path in self.detect.client_dirs if str(path).strip()]
        self.detect.history_window_min = int(_clamp(self.detect.history_window_min, 1, 1440))
        self.detect.poll_interval_s = int(_clamp(self.detect.poll_interval_s, 2, 300))
        self.detect.bridge_port = int(_clamp(self.detect.bridge_port, 1024, 65535))
        self.detect.bridge_timeout_s = int(_clamp(self.detect.bridge_timeout_s, 10, 3600))
        self.history.keep_hours = int(_clamp(self.history.keep_hours, 1, 720))
        self.history.bucket_s = int(_clamp(self.history.bucket_s, 15, 3600))
        self.history.auto_check_cooldown_s = int(
            _clamp(self.history.auto_check_cooldown_s, 60, 86_400))
        self.speed.budget_s = int(_clamp(self.speed.budget_s, 3, 60))
        self.speed.max_mb = int(_clamp(self.speed.max_mb, 5, 2000))
        self.updates.skip_version = str(self.updates.skip_version or "").strip()[:32]
        self.updates.last_checked = float(_clamp(self.updates.last_checked, 0, 4e10))
        self.web.port = int(_clamp(self.web.port, 1024, 65535))
        self.web.access_code = "".join(
            ch for ch in str(self.web.access_code or "") if ch.isalnum()
        )[:32]
        if self.web.bind_host not in ("0.0.0.0", "127.0.0.1"):
            self.web.bind_host = "0.0.0.0"
        self.watch_extras = _clean_extras(self.watch_extras)
        if self.manual_kind not in ("network", "live", "video", "app", "target"):
            self.manual_kind = "network"
        self.target_port = int(_clamp(self.target_port, 1, 65535))
        self.target_host = str(self.target_host or "").strip()
        self.app_name = str(self.app_name or "").strip()
        self.room_id = parse_room_id(self.room_id)
        # A pasted URL carries its own part number; keep it.
        pasted_page = parse_video_page(self.video_id)
        self.video_id = parse_video_id(self.video_id)
        if pasted_page > 1:
            self.video_page = pasted_page
        self.video_page = int(_clamp(self.video_page, 1, 10_000))
        self.version = CONFIG_VERSION
        return self


MAX_EXTRA_WATCHES = 4


def _clean_extras(entries: Any) -> list:
    """Keep the extra watches to things that can actually be measured."""
    if not isinstance(entries, list):
        return []
    cleaned = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "target")
        if kind not in ("target", "app"):
            continue
        ident = str(entry.get("ident") or "").strip()
        if not ident:
            continue
        port = int(_clamp(entry.get("port", 443), 1, 65535))
        key = f"{kind}:{ident.lower()}:{port if kind == 'target' else ''}"
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "kind": kind,
            "ident": ident,
            "port": port,
            "label": str(entry.get("label") or "").strip()[:40] or ident,
        })
        if len(cleaned) >= MAX_EXTRA_WATCHES:
            break
    return cleaned


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _quarantine(path: Path) -> None:
    try:
        path.replace(path.with_suffix(path.suffix + ".broken"))
    except OSError:
        pass


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Instantiate a dataclass from a dict, ignoring unknown keys.

    ``from __future__ import annotations`` makes every field type a string, so
    nested sections are resolved through the explicit ``_NESTED`` table.
    """
    kwargs: dict[str, Any] = {}
    known = {info.name for info in fields(cls)}
    for name, raw in data.items():
        if name not in known:
            continue
        nested_cls = _nested_dataclass(cls, name)
        if nested_cls is not None:
            if isinstance(raw, dict):
                kwargs[name] = _build(nested_cls, raw)
            continue
        kwargs[name] = raw
    return cls(**kwargs)


_NESTED = {
    "overlay": OverlayConfig,
    "tray": TrayConfig,
    "probe": ProbeConfig,
    "display": DisplayConfig,
    "audio": AudioConfig,
    "recording": RecordingConfig,
    "history": HistoryConfig,
    "updates": UpdateConfig,
    "speed": SpeedConfig,
    "thresholds": ThresholdConfig,
    "detect": DetectConfig,
    "web": WebConfig,
}


def _nested_dataclass(cls: type, name: str) -> Optional[type]:
    if cls is Config:
        return _NESTED.get(name)
    return None
