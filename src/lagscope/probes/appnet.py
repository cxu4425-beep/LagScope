"""Latency for any application, not just Bilibili.

Given a process (picked by name, or whatever is in the foreground), this finds
the servers it is actually talking to and times the round trip to the busiest
one. Nothing is injected into the process and no packets are captured: the
connection table is public information about the user's own processes, and the
round trip is measured by connecting to the same endpoint the app uses.

Games and voice apps often sit on UDP, where a TCP handshake proves nothing, so
the probe falls back to ICMP (the system ``ping`` command) for those.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import sys
from dataclasses import dataclass, field
from typing import Optional

from .network import icmp_ping_ms, tcp_rtt_ms

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dependency
    psutil = None  # type: ignore

LOG = logging.getLogger(__name__)

MAX_PEERS = 8


@dataclass(frozen=True)
class Peer:
    ip: str
    port: int
    connections: int = 1
    protocol: str = "tcp"         # tcp | udp - decides how it can be timed

    @property
    def is_udp(self) -> bool:
        return self.protocol == "udp"

    @property
    def is_public(self) -> bool:
        try:
            address = ipaddress.ip_address(self.ip)
        except ValueError:
            return False
        return not (address.is_private or address.is_loopback or address.is_link_local
                    or address.is_multicast or address.is_reserved)

    def __str__(self) -> str:
        # IPv6 is written in colons too, so "2607:6bc0::10:443" cannot be told
        # apart from an address whose last group happens to be 443. Brackets
        # are the standard way out (RFC 3986) and the only reason anyone can
        # see where the address stops and the port starts.
        if ":" in self.ip:
            return f"[{self.ip}]:{self.port}"
        return f"{self.ip}:{self.port}"


@dataclass(frozen=True)
class AppInfo:
    name: str
    pids: tuple = ()
    connections: int = 0


@dataclass(frozen=True)
class AppMeasurement:
    rtt_ms: Optional[float] = None
    method: str = "none"          # tcp | icmp | none
    peer: Optional[Peer] = None
    peers: tuple = ()
    connections: int = 0
    process: str = ""
    error: Optional[str] = None


def _process_names() -> dict:
    """pid -> process name, tolerating processes that vanish mid-scan."""
    names = {}
    if psutil is None:
        return names
    for process in psutil.process_iter(["name"]):
        try:
            names[process.pid] = process.info.get("name") or ""
        except Exception:  # pragma: no cover - race with process exit
            continue
    return names


# Windows reports a connection whose owning process it cannot name as pid 0,
# which psutil renders as "System Idle Process". Those are usually sockets in
# TIME_WAIT and there are often hundreds of them, so left in they sort to the
# top of a list whose whole purpose is "pick the program to measure" - naming
# something that is not a program and cannot be measured.
UNOWNED_PIDS = (0,)


# Measuring this program with itself. Its connections are its own probes - the
# handshakes it makes to time other things - so the "app" is busiest exactly
# while it is measuring, has nothing at all between rounds, and every figure it
# produces is a measurement of the measurement. It also reliably appears near
# the top of the list, for the same reason, which is how it gets picked.
SELF_ERROR = "self"


def own_process() -> tuple:
    """``(pids, name)`` for this program.

    Two pids, when frozen: a PyInstaller one-file build is a small launcher
    process that unpacks and starts the real one, both under the same name, and
    the launcher holds no sockets but is still this program.
    """
    pids = {os.getpid()}
    name = ""
    if psutil is None:
        return pids, name
    try:
        me = psutil.Process()
        name = me.name() or ""
        parent = me.parent()
        if parent is not None and name and parent.name() == name:
            pids.add(parent.pid)
    except Exception:  # pragma: no cover - access denied, process gone
        LOG.debug("could not inspect own process", exc_info=True)
    return pids, name


def is_self(process_name: str) -> bool:
    """Whether ``process_name`` is this program.

    Only for a frozen build. Running from source, this program is "python.exe",
    and refusing every Python program on the machine would be wrong.
    """
    if not process_name or not getattr(sys, "frozen", False):
        return False
    _pids, name = own_process()
    return bool(name) and process_name.lower() == name.lower()


def list_apps(min_connections: int = 1) -> list:
    """Applications that currently hold network connections, busiest first."""
    if psutil is None:
        return []
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception as exc:
        LOG.debug("connection table unavailable: %s", exc)
        return []

    names = _process_names()
    mine, _name = own_process()
    grouped: dict = {}
    for entry in connections:
        if entry.pid is None or entry.pid in UNOWNED_PIDS or not entry.raddr:
            continue
        if entry.pid in mine:
            continue
        name = names.get(entry.pid) or f"pid {entry.pid}"
        pids, count = grouped.get(name, (set(), 0))
        pids.add(entry.pid)
        grouped[name] = (pids, count + 1)

    apps = [
        AppInfo(name=name, pids=tuple(sorted(pids)), connections=count)
        for name, (pids, count) in grouped.items()
        if count >= min_connections
    ]
    apps.sort(key=lambda app: app.connections, reverse=True)
    return apps


def peers_for(process_name: str) -> list:
    """Remote endpoints one application is connected to, busiest first."""
    if psutil is None or not process_name:
        return []
    wanted = process_name.strip().lower()
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception as exc:
        LOG.debug("connection table unavailable: %s", exc)
        return []

    names = _process_names()
    counted: dict = {}
    for entry in connections:
        if entry.pid is None or entry.pid in UNOWNED_PIDS or not entry.raddr:
            continue
        name = (names.get(entry.pid) or "").lower()
        if wanted not in name and wanted != f"pid {entry.pid}":
            continue
        protocol = "udp" if entry.type == socket.SOCK_DGRAM else "tcp"
        key = (entry.raddr.ip, entry.raddr.port, protocol)
        counted[key] = counted.get(key, 0) + 1

    peers = [
        Peer(ip=ip, port=port, connections=count, protocol=protocol)
        for (ip, port, protocol), count in counted.items()
    ]
    # Public first (a LAN peer says nothing about the line), then UDP: a game or
    # voice app carries its real-time traffic over UDP while holding several TCP
    # connections to web and CDN endpoints, and timing those would answer a
    # different question than "how laggy is my game right now".
    peers.sort(key=lambda peer: (peer.is_public, peer.is_udp, peer.connections), reverse=True)
    return peers[:MAX_PEERS]


class AppNetProbe:
    """Times the round trip to the server an application is talking to."""

    def __init__(self) -> None:
        self._process = ""
        self._icmp_only: set = set()

    def set_target(self, process_name: str) -> None:
        if process_name != self._process:
            self._process = process_name
            self._icmp_only.clear()

    @property
    def process(self) -> str:
        return self._process

    def measure(self, process_name: Optional[str] = None, timeout_s: float = 4.0) -> AppMeasurement:
        process_name = process_name or self._process
        if not process_name:
            return AppMeasurement(error="no-app")
        if psutil is None:
            return AppMeasurement(process=process_name, error="psutil unavailable")
        if is_self(process_name):
            # Saved before the list stopped offering it, most likely.
            return AppMeasurement(process=process_name, error=SELF_ERROR)

        peers = peers_for(process_name)
        if not peers:
            return AppMeasurement(process=process_name, peers=(), error="no-connections")

        total = sum(peer.connections for peer in peers)
        for peer in peers:
            rtt, method = self._time_peer(peer, timeout_s)
            if rtt is not None:
                return AppMeasurement(
                    rtt_ms=rtt, method=method, peer=peer, peers=tuple(peers),
                    connections=total, process=process_name,
                )
        return AppMeasurement(
            peers=tuple(peers), connections=total, process=process_name,
            error="no-reply",
        )

    def _time_peer(self, peer: Peer, timeout_s: float) -> tuple:
        """TCP first; ICMP for endpoints that never answer a handshake (UDP)."""
        key = str(peer)
        # A handshake against a UDP port cannot succeed, so do not spend a
        # timeout finding that out.
        if peer.is_udp:
            rtt = icmp_ping_ms(peer.ip, timeout_s)
            return (rtt, "icmp") if rtt is not None else (None, "none")
        if key not in self._icmp_only:
            rtt = tcp_rtt_ms(peer.ip, peer.port, timeout_s)
            if rtt is not None:
                return rtt, "tcp"
            self._icmp_only.add(key)
        rtt = icmp_ping_ms(peer.ip, timeout_s)
        if rtt is not None:
            return rtt, "icmp"
        return None, "none"
