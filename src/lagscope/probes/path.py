"""Working out *where* the latency is, not just how much of it there is.

A single number ("180 ms") tells you that something is wrong but not what to
do about it. Splitting the path into segments does:

    you -> router      slow here  =>  Wi-Fi or the local network
    router -> ISP      slow here  =>  your line or your provider
    ISP -> server      slow here  =>  distance, routing, or the server itself

Everything here shells out to the tools that ship with the OS (``ping``,
``tracert``/``traceroute``, ``netsh``/``iw``), so nothing needs administrator
rights and there are no raw sockets. Output formats differ per platform *and*
per language, so parsing never relies on a summary line: reply times are
extracted individually and the statistics computed here, which works the same
in English, Chinese or anything else.
"""

from __future__ import annotations

import ipaddress
import locale
import logging
import re
import socket
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .network import _PING_TIME_RE

LOG = logging.getLogger(__name__)

# Windows: never flash a console window when shelling out from a GUI app.
_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0

_IPV4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

# Where the segments stop being "fine". These are deliberately generous: the
# point is to spot an obvious culprit, not to grade a connection.
GATEWAY_SLOW_MS = 15.0        # a LAN hop should be ~1 ms wired, a few ms on Wi-Fi
GATEWAY_BAD_MS = 40.0
LOSS_WARN_PCT = 2.0
LOSS_BAD_PCT = 8.0
WIFI_WEAK_PCT = 55
# Name resolution above this is felt as "the internet is slow" even when every
# ping is fine: nothing starts until the name is answered.
DNS_SLOW_MS = 300.0


@dataclass(frozen=True)
class PingStats:
    """Result of a burst of pings, computed from the individual replies."""

    host: str
    sent: int = 0
    received: int = 0
    avg_ms: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    error: Optional[str] = None

    @property
    def loss_pct(self) -> Optional[float]:
        if not self.sent:
            return None
        return (self.sent - self.received) * 100.0 / self.sent

    @property
    def ok(self) -> bool:
        return self.received > 0


BAND_24 = "2.4"
BAND_5 = "5"
BAND_6 = "6"


def band_from_mhz(mhz: Optional[float]) -> str:
    """Band from a centre frequency, which is never ambiguous."""
    if not mhz:
        return ""
    value = float(mhz)
    if 2400 <= value <= 2500:
        return BAND_24
    if 5150 <= value <= 5895:
        return BAND_5
    if 5925 <= value <= 7125:
        return BAND_6
    return ""


def band_from_channel(channel: str) -> str:
    """Band from a channel number, which sometimes is ambiguous.

    2.4 GHz uses 1-14 and 5 GHz uses 32-177, so those are safe. Wi-Fi 6E
    restarts its own numbering at 1, so a bare "5" could be either band - and
    a wrong band here would send someone to change a setting that was already
    right. Every adapter that can reach 6 GHz reports the band outright, so
    the ambiguous case is normally resolved before this is consulted; when it
    is not, this says nothing rather than guessing.
    """
    match = re.search(r"\d+", (channel or "").strip())
    if not match:
        return ""
    number = int(match.group())
    if 1 <= number <= 14:
        return BAND_24
    if 32 <= number <= 177:
        return BAND_5
    return ""


def normalise_band(text: str) -> str:
    """Read a band the adapter stated for itself, e.g. "5 GHz"."""
    lowered = (text or "").lower()
    if "2.4" in lowered or "2,4" in lowered:
        return BAND_24
    if "6" in lowered and "ghz" in lowered:
        return BAND_6
    if "5" in lowered:
        return BAND_5
    return ""


@dataclass(frozen=True)
class WifiInfo:
    ssid: str = ""
    signal_pct: Optional[int] = None
    radio: str = ""               # e.g. 802.11ac
    channel: str = ""
    rx_mbps: Optional[float] = None
    # The access point actually serving you. With a mesh or a repeater the
    # SSID stays the same across all of them, so this is the only way to see
    # a roam - and a roam mid-stream is a stall with no other explanation.
    bssid: str = ""
    freq_mhz: Optional[float] = None
    # "2.4", "5", "6", or "" when it could not be established honestly.
    band: str = ""

    @property
    def weak(self) -> bool:
        return self.signal_pct is not None and self.signal_pct < WIFI_WEAK_PCT

    @property
    def crowded_band(self) -> bool:
        """2.4 GHz: longer range, but shared with everything else in the house."""
        return self.resolved_band() == BAND_24

    def resolved_band(self) -> str:
        """Whatever can be established, preferring the least ambiguous source."""
        return self.band or band_from_mhz(self.freq_mhz) or band_from_channel(self.channel)

    @property
    def link_key(self) -> str:
        """A stable name for "which wireless link was I on", for grouping.

        The SSID alone is not enough: many routers give both bands the same
        name, and those two are very different links to be sitting on.
        """
        if not self.ssid:
            return ""
        band = self.resolved_band()
        return f"{self.ssid} ({band} GHz)" if band else self.ssid


@dataclass
class PathReport:
    target: str = ""
    gateway: Optional[str] = None
    gateway_stats: Optional[PingStats] = None
    hop_host: Optional[str] = None          # first hop beyond the router
    hop_stats: Optional[PingStats] = None
    target_stats: Optional[PingStats] = None
    dns_ms: Optional[float] = None          # how long the name took to resolve
    wifi: Optional[WifiInfo] = None
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        def stats(entry: Optional[PingStats]) -> Optional[dict]:
            if entry is None:
                return None
            return {
                "host": entry.host, "sent": entry.sent, "received": entry.received,
                "loss_pct": entry.loss_pct, "avg_ms": entry.avg_ms,
                "min_ms": entry.min_ms, "max_ms": entry.max_ms,
                "jitter_ms": entry.jitter_ms, "error": entry.error,
            }

        return {
            "target": self.target,
            "gateway": self.gateway,
            "dns_ms": self.dns_ms,
            "segments": {
                "you_to_router": stats(self.gateway_stats),
                "router_to_isp": stats(self.hop_stats),
                "to_target": stats(self.target_stats),
            },
            "wifi": None if self.wifi is None else {
                "ssid": self.wifi.ssid, "signal_pct": self.wifi.signal_pct,
                "radio": self.wifi.radio, "channel": self.wifi.channel,
                "rx_mbps": self.wifi.rx_mbps,
            },
            "verdict": verdict(self)[0],
        }


# --------------------------------------------------------------------- ping
def _console_encodings() -> list:
    """Encodings to try for a Windows command-line tool's output, best first.

    Console tools write in the OEM code page, which is not the one
    ``text=True`` would pick, and on a Chinese Windows the two can differ.
    Getting it wrong used to raise UnicodeDecodeError - which is neither an
    OSError nor a SubprocessError, so it went straight past the handler below
    and was swallowed several frames up as "wifi state unavailable". The
    reading simply vanished, with no error anywhere.
    """
    names = []
    if sys.platform.startswith("win"):
        try:
            import ctypes

            names.append("cp%d" % ctypes.windll.kernel32.GetOEMCP())
            names.append("cp%d" % ctypes.windll.kernel32.GetACP())
        except Exception:
            pass
    names.append(locale.getpreferredencoding(False))
    names.append("utf-8")
    # Never fails, and leaves the ASCII - addresses, numbers, "SSID" - intact
    # even when the labels around them come out as nonsense.
    names.append("latin-1")
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def _decode(raw: bytes) -> str:
    for encoding in _console_encodings():
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", "replace")


def _run(command: list, timeout_s: float) -> Optional[str]:
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=timeout_s,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOG.debug("%s failed: %s", command[0], exc)
        return None
    # A partial answer is still useful: ping exits non-zero on any loss.
    return _decode((completed.stdout or b"") + (completed.stderr or b""))


def parse_ping_times(output: str) -> list:
    """Every round-trip time in a ping transcript, in milliseconds.

    Summary lines are ignored on purpose - they are translated, and the reply
    lines are not.
    """
    times = []
    for match in _PING_TIME_RE.finditer(output or ""):
        try:
            times.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return times


def ping_stats(host: str, count: int = 5, timeout_s: float = 1.0) -> PingStats:
    """Ping a host ``count`` times and summarise loss and timing."""
    if not host:
        return PingStats(host=host, error="no-host")
    count = max(1, min(30, int(count)))
    if sys.platform.startswith("win"):
        command = ["ping", "-n", str(count), "-w", str(int(timeout_s * 1000)), host]
    elif sys.platform == "darwin":
        # macOS refuses sub-second intervals to non-root users.
        command = ["ping", "-c", str(count), "-W", str(int(timeout_s * 1000)), host]
    else:
        command = ["ping", "-c", str(count), "-W", str(max(1, int(timeout_s))),
                   "-i", "0.25", host]

    budget = timeout_s * count + 5.0
    output = _run(command, budget)
    if output is None:
        return PingStats(host=host, sent=count, error="ping unavailable")

    times = parse_ping_times(output)
    if not times:
        return PingStats(host=host, sent=count, received=0, error="no reply")
    jitter = None
    if len(times) > 1:
        jitter = sum(abs(b - a) for a, b in zip(times, times[1:])) / (len(times) - 1)
    return PingStats(
        host=host, sent=count, received=len(times),
        avg_ms=statistics.fmean(times), min_ms=min(times), max_ms=max(times),
        jitter_ms=jitter,
    )


# ---------------------------------------------------------------------- DNS
def dns_ms(host: str, timeout_s: float = 3.0) -> Optional[float]:
    """How long this machine takes to turn a name into an address.

    A slow resolver is one of the most common causes of "everything feels
    slow" while every ping looks healthy - nothing can start until the name
    comes back. An address that needs no lookup returns 0.0, and a name that
    cannot be resolved returns ``None``.
    """
    host = (host or "").strip()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return 0.0                       # already an address: nothing to resolve
    except ValueError:
        pass

    previous = socket.getdefaulttimeout()
    started = time.perf_counter()
    try:
        socket.setdefaulttimeout(timeout_s)
        socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return None
    finally:
        socket.setdefaulttimeout(previous)
    return (time.perf_counter() - started) * 1000.0


# ------------------------------------------------------------------ gateway
def parse_gateway(output: str, platform: str = "") -> Optional[str]:
    """Pull the default gateway out of a routing table dump."""
    platform = platform or sys.platform
    text = output or ""

    if platform.startswith("win"):
        # "  0.0.0.0    0.0.0.0   192.168.1.1   192.168.1.20     25"
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("0.0.0.0"):
                addresses = _IPV4_RE.findall(stripped)
                # network, netmask, gateway, interface, ...
                if len(addresses) >= 3 and addresses[2] != "0.0.0.0":
                    return addresses[2]
        return None

    if platform == "darwin":
        # "   gateway: 192.168.1.1"
        for line in text.splitlines():
            if "gateway" in line.lower():
                found = _IPV4_RE.search(line)
                if found:
                    return found.group(1)
        return None

    # Linux: "default via 192.168.1.1 dev wlan0 proto dhcp metric 600"
    for line in text.splitlines():
        if line.strip().startswith("default"):
            found = _IPV4_RE.search(line)
            if found:
                return found.group(1)
    return None


def default_gateway() -> Optional[str]:
    """The router this machine sends its traffic to."""
    if sys.platform.startswith("win"):
        output = _run(["route", "print", "-4", "0.0.0.0"], 6.0)
    elif sys.platform == "darwin":
        output = _run(["route", "-n", "get", "default"], 6.0)
    else:
        output = _run(["ip", "-4", "route", "show", "default"], 6.0)
    if output is None:
        return None
    return parse_gateway(output)


# --------------------------------------------------------------------- hops
def parse_trace_hops(output: str) -> list:
    """``(hop_number, address, rtt_ms)`` for each hop that answered."""
    hops = []
    for line in (output or "").splitlines():
        stripped = line.strip()
        match = re.match(r"^(\d{1,2})\b", stripped)
        if not match:
            continue
        address = _IPV4_RE.search(stripped)
        if not address:
            continue          # a hop that timed out ("* * *")
        times = parse_ping_times(stripped)
        # Windows writes "1 ms" with a space and no "time=" prefix.
        if not times:
            times = [float(value) for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*ms", stripped)]
        hops.append((int(match.group(1)), address.group(1), min(times) if times else None))
    return hops


def first_external_hop(target: str, timeout_s: float = 1.0) -> Optional[tuple]:
    """The hop just past the router, i.e. the way into the ISP's network."""
    if not target:
        return None
    if sys.platform.startswith("win"):
        command = ["tracert", "-d", "-h", "3", "-w", str(int(timeout_s * 1000)), target]
    else:
        command = ["traceroute", "-n", "-m", "3", "-w", str(max(1, int(timeout_s))), target]
    output = _run(command, timeout_s * 12 + 6.0)
    if output is None:
        return None
    hops = parse_trace_hops(output)
    for number, address, rtt in hops:
        if number >= 2:
            return address, rtt
    return None


# --------------------------------------------------------------------- Wi-Fi
def _mac(text: str) -> str:
    """A MAC address in one lowercase form, or nothing at all."""
    match = re.search(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", text or "")
    return match.group().lower().replace("-", ":") if match else ""


def parse_wifi(output: str, platform: str = "") -> Optional[WifiInfo]:
    """Read the current Wi-Fi quality out of the platform's tool."""
    platform = platform or sys.platform
    text = output or ""
    if not text.strip():
        return None

    def field_value(*names) -> str:
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if any(name in key for name in names):
                return value.strip()
        return ""

    if platform.startswith("win"):
        # netsh wlan show interfaces - labels are translated, values are not.
        signal = field_value("signal", "信号", "訊號")
        percent = re.search(r"(\d{1,3})\s*%", signal)
        rate = field_value("receive rate", "接收速率", "接收速度")
        rate_value = re.search(r"(\d+(?:[.,]\d+)?)", rate)
        ssid = field_value("ssid")
        # "BSSID" also contains "ssid"; a MAC address is not a network name.
        if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", ssid.lower()):
            ssid = ""
        # Windows says 通道 in Traditional Chinese and 信道 in Simplified;
        # 頻道 is the word for a television channel and was never right.
        channel = field_value("channel", "通道", "信道", "频道", "頻道")
        # Windows 11 states the band outright. Prefer it: 6 GHz reuses the low
        # channel numbers, so inferring from the channel can be wrong there.
        band = normalise_band(field_value("band", "频带", "頻帶"))
        return WifiInfo(
            ssid=ssid,
            signal_pct=int(percent.group(1)) if percent else None,
            radio=field_value("radio type", "无线电类型", "無線電類型"),
            channel=channel,
            rx_mbps=float(rate_value.group(1).replace(",", ".")) if rate_value else None,
            bssid=_mac(field_value("bssid")),
            band=band or band_from_channel(channel),
        )

    if platform == "darwin":
        ssid = field_value(" ssid")
        rssi = field_value("agrctlrssi")
        rate = field_value("lastxrate", "maxrate")
        signal = None
        if rssi:
            try:
                # dBm to a rough percentage: -50 or better is full, -100 is nothing.
                signal = max(0, min(100, int(round((int(rssi) + 100) * 2))))
            except ValueError:
                signal = None
        channel = field_value("channel")
        return WifiInfo(ssid=ssid, signal_pct=signal, radio=field_value("phy mode"),
                        channel=channel,
                        rx_mbps=float(rate) if rate.replace(".", "").isdigit() else None,
                        bssid=_mac(field_value("bssid")),
                        band=band_from_channel(channel))

    # Linux: iw dev <if> link
    ssid_match = re.search(r"SSID:\s*(.+)", text)
    signal_match = re.search(r"signal:\s*(-?\d+)\s*dBm", text)
    rate_match = re.search(r"rx bitrate:\s*([\d.]+)", text)
    # "Connected to a4:2b:8c:11:22:33 (on wlan0)" - the AP, not the interface.
    bssid_match = re.search(r"Connected to\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", text)
    freq_match = re.search(r"freq:\s*(\d+)", text)
    signal = None
    if signal_match:
        signal = max(0, min(100, int(round((int(signal_match.group(1)) + 100) * 2))))
    freq = float(freq_match.group(1)) if freq_match else None
    return WifiInfo(
        ssid=ssid_match.group(1).strip() if ssid_match else "",
        signal_pct=signal,
        rx_mbps=float(rate_match.group(1)) if rate_match else None,
        bssid=_mac(bssid_match.group(1)) if bssid_match else "",
        freq_mhz=freq,
        # A frequency settles the band outright, with no channel-numbering
        # ambiguity to work around.
        band=band_from_mhz(freq),
    )


def wifi_info() -> Optional[WifiInfo]:
    if sys.platform.startswith("win"):
        output = _run(["netsh", "wlan", "show", "interfaces"], 6.0)
    elif sys.platform == "darwin":
        output = _run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/"
             "Current/Resources/airport", "-I"], 6.0)
    else:
        output = _run(["iw", "dev"], 4.0)
        if output:
            interface = re.search(r"Interface\s+(\S+)", output)
            output = _run(["iw", "dev", interface.group(1), "link"], 4.0) if interface else None
    if not output:
        return None
    info = parse_wifi(output)
    # No SSID and no signal means "not on Wi-Fi", which is not a failure.
    if info is not None and not info.ssid and info.signal_pct is None:
        return None
    return info


# ------------------------------------------------------------------ verdict
def verdict(report: PathReport) -> tuple:
    """``(key, detail)`` naming the segment to blame, for the UI to translate."""
    gateway = report.gateway_stats
    hop = report.hop_stats
    target = report.target_stats
    wifi = report.wifi

    # No ping on this machine at all: say that, rather than blaming the target.
    measured = [entry for entry in (gateway, hop, target) if entry is not None]
    if measured and all(entry.error == "ping unavailable" for entry in measured):
        return "verdict.no_ping", ""

    if target is not None and not target.ok and target.error != "ping unavailable" \
            and (gateway is None or gateway.ok):
        return "verdict.target_down", target.host

    if gateway is not None and gateway.ok:
        loss = gateway.loss_pct or 0.0
        slow = (gateway.avg_ms or 0.0) >= GATEWAY_SLOW_MS
        if loss >= LOSS_BAD_PCT or (gateway.avg_ms or 0.0) >= GATEWAY_BAD_MS:
            return ("verdict.wifi" if (wifi and wifi.weak) else "verdict.home",
                    f"{gateway.avg_ms:.0f} ms / {loss:.0f}%")
        if slow or loss >= LOSS_WARN_PCT:
            return ("verdict.wifi" if (wifi and wifi.weak) else "verdict.home",
                    f"{gateway.avg_ms:.0f} ms / {loss:.0f}%")

    if gateway is not None and not gateway.ok and gateway.error != "ping unavailable":
        # Some routers simply do not answer ICMP; that is not a fault by itself.
        report.notes.append("gateway-silent")

    if hop is not None and hop.ok and gateway is not None and gateway.ok:
        if (hop.avg_ms or 0.0) - (gateway.avg_ms or 0.0) >= 60.0:
            return "verdict.isp", f"{hop.avg_ms:.0f} ms @ {hop.host}"

    if report.dns_ms is not None and report.dns_ms >= DNS_SLOW_MS:
        # Checked after the segments above: a broken path explains a slow
        # lookup, not the other way round.
        return "verdict.dns", f"{report.dns_ms:.0f} ms"

    if target is not None and target.ok:
        loss = target.loss_pct or 0.0
        if loss >= LOSS_WARN_PCT:
            return "verdict.loss", f"{loss:.0f}%"
        reference = hop.avg_ms if (hop and hop.ok) else (gateway.avg_ms if (gateway and gateway.ok) else 0.0)
        if (target.avg_ms or 0.0) - (reference or 0.0) >= 80.0:
            return "verdict.server", f"{target.avg_ms:.0f} ms"
        return "verdict.ok", f"{target.avg_ms:.0f} ms"

    return "verdict.unknown", ""


def analyse(target: str, count: int = 5, timeout_s: float = 1.0,
            include_trace: bool = True) -> PathReport:
    """Measure each segment of the path to ``target``."""
    report = PathReport(target=target)
    report.gateway = default_gateway()
    if report.gateway:
        report.gateway_stats = ping_stats(report.gateway, count, timeout_s)
    if include_trace and target:
        hop = first_external_hop(target, timeout_s)
        if hop is not None:
            report.hop_host = hop[0]
            report.hop_stats = ping_stats(hop[0], count, timeout_s)
    if target:
        report.target_stats = ping_stats(target, count, timeout_s)
        report.dns_ms = dns_ms(target, timeout_s=max(1.0, timeout_s * 3))
    report.wifi = wifi_info()
    return report
