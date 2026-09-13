"""Network-level probes: TCP round trip, HTTP time-to-first-byte, clock offset."""

from __future__ import annotations

import email.utils
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

from ..health import HEALTH, ICMP
from ..models import NetworkMeasurement

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://live.bilibili.com/",
    "Origin": "https://live.bilibili.com",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def host_port_from_url(url: str, default_port: int = 443) -> Tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else default_port)
    return host, port


@dataclass(frozen=True)
class ConnectTiming:
    """A TCP handshake, with the name lookup billed separately.

    ``socket.create_connection`` takes a hostname, so the obvious way to time a
    handshake quietly folds the DNS lookup into the answer. That is why this
    app's latency could read tens of milliseconds above ``ping`` for the same
    server: it was not measuring the same thing. Resolving first, then timing
    the connection to the address, keeps the two apart.
    """

    rtt_ms: Optional[float] = None
    dns_ms: Optional[float] = None
    address: str = ""           # the IP actually connected to
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.rtt_ms is not None


def _is_ip_literal(host: str) -> bool:
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, host)
            return True
        except (OSError, ValueError):
            continue
    return False


def connect_timing(host: str, port: int = 443, timeout_s: float = 4.0) -> ConnectTiming:
    """Resolve, then time the handshake to the address that came back.

    Reported separately because they fail and drift for different reasons: a
    slow resolver is not a slow path to the server, and only one of them is
    something the viewer can do anything about.
    """
    if not host:
        return ConnectTiming(error="no-host")

    dns_ms = None
    if _is_ip_literal(host):
        infos = [(socket.AF_INET6 if ":" in host else socket.AF_INET,
                  socket.SOCK_STREAM, 0, "", (host, int(port)))]
    else:
        started = time.perf_counter()
        try:
            infos = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
        except (OSError, ValueError) as exc:
            return ConnectTiming(dns_ms=(time.perf_counter() - started) * 1000.0,
                                 error=_short_error(exc))
        dns_ms = (time.perf_counter() - started) * 1000.0

    last_error = ""
    for family, socktype, proto, _canonical, address in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(timeout_s)
            started = time.perf_counter()
            sock.connect(address)
            rtt_ms = (time.perf_counter() - started) * 1000.0
            return ConnectTiming(rtt_ms=rtt_ms, dns_ms=dns_ms, address=str(address[0]))
        except (OSError, ValueError) as exc:
            last_error = _short_error(exc)
        finally:
            try:
                sock.close()
            except OSError:
                pass
    return ConnectTiming(dns_ms=dns_ms, error=last_error or "unreachable")


def tcp_rtt_ms(host: str, port: int = 443, timeout_s: float = 4.0) -> Optional[float]:
    """Time a TCP handshake, which is one round trip to the edge server.

    Returns ``None`` when the host is unreachable within ``timeout_s``. The
    name lookup is excluded - see :func:`connect_timing`, which reports it.
    """
    return connect_timing(host, port, timeout_s).rtt_ms


# ``ping`` prints the time in the console's own language.
_PING_TIME_RE = re.compile(
    r"(?:time|時間|时间|tempo|Zeit|temps)\s*[=<]\s*([\d.,]+)\s*m?s", re.IGNORECASE
)


def icmp_ping_ms(host: str, timeout_s: float = 2.0) -> Optional[float]:
    """Round trip via the system ``ping``, for servers that ignore TCP (UDP games).

    No raw sockets, so no administrator rights are needed. Returns ``None`` when
    the host does not answer or ping is unavailable.
    """
    if not host:
        return None
    timeout_ms = max(200, int(timeout_s * 1000))
    if sys.platform.startswith("win"):
        command = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        creationflags = 0x08000000  # CREATE_NO_WINDOW: never flash a console
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), host]
        creationflags = 0
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_s + 2.0,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # ping itself could not be run - that is the tool, not the host, so it
        # is worth saying out loud. A host that merely filters ICMP comes back
        # with a non-zero exit code below and is nobody's fault.
        HEALTH.degraded(ICMP, f"ping: {type(exc).__name__}: {exc}")
        return None
    if completed.returncode != 0:
        return None
    match = _PING_TIME_RE.search(completed.stdout or "")
    if match is None:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    HEALTH.working(ICMP)
    return value


def clock_offset_ms(server_date_header: str, local_recv_epoch: float, rtt_ms: Optional[float]) -> Optional[float]:
    """Estimate ``server_clock - local_clock`` from an HTTP ``Date`` header.

    The header only has one-second resolution, so the result carries roughly
    +/-500 ms of quantisation error. It is good enough to keep a wall-clock
    stream measurement from drifting when the user's clock is minutes off.
    """
    if not server_date_header:
        return None
    try:
        server_epoch = email.utils.parsedate_to_datetime(server_date_header).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    one_way_ms = (rtt_ms or 0.0) / 2.0
    return (server_epoch - local_recv_epoch) * 1000.0 + one_way_ms


class HttpClient:
    """Small wrapper around :class:`requests.Session` with timing helpers.

    A single session is reused so keep-alive connections make repeated probes
    cheap; :meth:`recycle` drops the pool after a network change.
    """

    def __init__(self, timeout_s: float = 4.0) -> None:
        self.timeout_s = timeout_s
        self._session = self._new_session()

    @staticmethod
    def _new_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        session.trust_env = True  # honour the user's proxy settings
        return session

    @property
    def session(self) -> requests.Session:
        return self._session

    def recycle(self) -> None:
        self.close()
        self._session = self._new_session()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # pragma: no cover - defensive, close must never raise
            pass

    def get_json(self, url: str, params: Optional[dict] = None,
                 headers: Optional[dict] = None) -> dict:
        response = self._session.get(url, params=params, headers=headers, timeout=self.timeout_s)
        response.raise_for_status()
        return response.json()

    def get_text_timed(self, url: str) -> Tuple[str, float, requests.Response]:
        """GET a small text body; returns ``(text, ttfb_ms, response)``."""
        started = time.perf_counter()
        response = self._session.get(url, timeout=self.timeout_s, stream=True)
        ttfb_ms = (time.perf_counter() - started) * 1000.0
        try:
            response.raise_for_status()
            text = response.text
        finally:
            response.close()
        return text, ttfb_ms, response

    def measure(self, url: str, rtt_ms: Optional[float] = None) -> NetworkMeasurement:
        """Measure TTFB (and clock offset) for a URL, plus a TCP RTT if absent."""
        host, port = host_port_from_url(url)
        if rtt_ms is None:
            rtt_ms = tcp_rtt_ms(host, port, self.timeout_s)
        try:
            started = time.perf_counter()
            response = self._session.get(url, timeout=self.timeout_s, stream=True)
            ttfb_ms = (time.perf_counter() - started) * 1000.0
            recv_epoch = time.time()
            date_header = response.headers.get("Date", "")
            response.close()
        except requests.RequestException as exc:
            return NetworkMeasurement(rtt_ms=rtt_ms, host=host, error=_short_error(exc))
        return NetworkMeasurement(
            rtt_ms=rtt_ms,
            ttfb_ms=ttfb_ms,
            host=host,
            clock_offset_ms=clock_offset_ms(date_header, recv_epoch, rtt_ms),
        )


def _short_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:200]
