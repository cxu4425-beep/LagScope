"""Prove, on a real machine, that every probe actually works.

Every Bilibili code path in this project - the playurl response, the HLS
server clock, the FLV key frame, the CDN comparison and the edge switch - was
written and tested against fixtures, because the machine it was written on
cannot reach Bilibili at all. The unit tests say the parsing is right *given
that shape of input*. They cannot say the input still has that shape.

This closes that gap by running each probe once against the real thing and
printing what came back. Nothing is asserted: the output is evidence, meant
to be read by a person and pasted into a bug report.

What it deliberately leaves out of the output: the Wi-Fi network name, any
public IP address, and anything about what else is running on the machine.
The addresses in it are the private ones inside the home plus the servers
being measured, and the room id is one the user chose.
"""

from __future__ import annotations

import platform
import re
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import APP_NAME, __version__
from .probes.cdninfo import describe, summary

OK = "ok"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"

MARKS = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]", SKIP: "[skip]"}


@dataclass
class CheckResult:
    """One thing that was tried, and what came back."""

    name: str
    status: str = OK
    lines: List[str] = field(default_factory=list)

    def add(self, line: str) -> "CheckResult":
        self.lines.append(str(line))
        return self

    @property
    def failed(self) -> bool:
        return self.status == FAIL


def _check(name: str, run: Callable[[CheckResult], None]) -> CheckResult:
    """Run one check; an unexpected exception is a failure, never a crash."""
    result = CheckResult(name=name)
    started = time.perf_counter()
    try:
        run(result)
    except Exception as exc:                      # noqa: BLE001 - report anything
        result.status = FAIL
        result.add(f"{type(exc).__name__}: {exc}")
    result.add(f"({(time.perf_counter() - started) * 1000:.0f} ms)")
    return result


# ------------------------------------------------------------------ checks
def check_environment(result: CheckResult) -> None:
    result.add(f"{APP_NAME} {__version__}")
    result.add(f"python {platform.python_version()} on {sys.platform} "
               f"({platform.machine()})")
    result.add(f"frozen executable: {'yes' if getattr(sys, 'frozen', False) else 'no'}")


def check_dns(result: CheckResult) -> None:
    from .probes.path import dns_ms

    for host in ("api.live.bilibili.com", "www.bilibili.com"):
        elapsed = dns_ms(host)
        if elapsed is None:
            result.status = FAIL
            result.add(f"{host}: no answer")
        else:
            result.add(f"{host}: {elapsed:.0f} ms")


def check_api_reachable(result: CheckResult, client, timeout_s: float = 6.0) -> None:
    """Reach the API for real, not just the first hop towards it.

    A TCP handshake alone is not evidence: behind a proxy it succeeds against
    the proxy while every request to Bilibili is refused. So this asks the API
    an actual question and reports what came back.
    """
    from .probes.network import tcp_rtt_ms

    rtt = tcp_rtt_ms("api.live.bilibili.com", 443, timeout_s)
    result.add(f"TCP handshake: {f'{rtt:.0f} ms' if rtt is not None else 'refused'}")

    try:
        payload = client.get_json(
            "https://api.live.bilibili.com/room/v1/Room/get_info", params={"room_id": 1}
        )
    except Exception as exc:                      # noqa: BLE001 - report anything
        result.status = FAIL
        result.add(f"the API itself did not answer: {type(exc).__name__}: {exc}")
        result.add("every Bilibili check below will fail for the same reason")
        return
    result.add(f"API answered, code={payload.get('code')}")


def check_room(result: CheckResult, stream, room: str) -> None:
    """Room info: proves the public API still answers in the expected shape."""
    if not room:
        result.status = SKIP
        result.add("no room id - pass one: --selftest 21452505")
        return
    info = stream.fetch_room_info(room)
    result.add(f"room {info.room_id}: {'live' if info.is_live else 'offline'}")
    result.add(f"title: {info.title[:60] or '(empty)'}")
    result.add(f"area: {info.area or '(empty)'}   viewers: {info.online}")
    if not info.is_live:
        result.status = WARN
        result.add("the room is offline, so the stream checks below will be skipped")
        result.add("try again with a room that is actually streaming")


# C:\Users\<name>, /home/<name>, /Users/<name> - the account name sits in the
# same place in all three.
_HOME_PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]:[\\/]Users[\\/]|/home/|/Users/)(?P<user>[^\\/]+)")


def redact_home(path) -> str:
    """A path with the account name taken out of it.

    The report ends its own output by promising it carries no account details,
    and then printed C:\\Users\\<name>\\AppData\\... two lines above. The
    output exists to be pasted into a forum thread or sent to a helpdesk, so
    the promise has to be true rather than nearly true.
    """
    text = str(path)
    try:
        home = str(Path.home())
    except Exception:
        home = ""
    placeholder = "%USERPROFILE%" if sys.platform.startswith("win") else "~"
    if home and text.lower().startswith(home.lower()):
        return placeholder + text[len(home):]
    # A redirected or roaming profile will not match Path.home(); the shape of
    # the path still gives the account name away, so take it out anyway.
    match = _HOME_PATTERN.match(text)
    if match:
        return placeholder + text[match.end():]
    return text


def distinct_hosts(endpoints) -> list:
    """The distinct edges in a list of endpoints, first seen first.

    Derived from the endpoints in hand rather than asked of the probe. The
    probe has a method for this, but it reads a cache that only the monitoring
    path fills - and this check fetches directly, so that cache is empty here.
    Reading it reported "0 distinct edges" beside six visibly distinct
    hostnames, and, far worse, silently skipped the PCDN detection below.
    """
    seen = []
    for endpoint in endpoints or ():
        host = getattr(endpoint, "host", "")
        if host and host not in seen:
            seen.append(host)
    return seen


def check_endpoints(result: CheckResult, stream, room: str) -> None:
    """playurl: the response shape this project has never seen for real."""
    if not room:
        result.status = SKIP
        result.add("needs a room id")
        return
    endpoints = stream.fetch_endpoints(room)
    if not endpoints:
        result.status = FAIL
        result.add("no playable endpoints came back")
        return
    hosts = distinct_hosts(endpoints)
    result.add(f"{len(endpoints)} endpoint(s), {len(hosts)} distinct edge(s)")
    for endpoint in endpoints[:6]:
        result.add(f"  {endpoint.protocol:<12} {endpoint.fmt:<5} qn={endpoint.qn:<5} "
                   f"{endpoint.host}")
    # What those hostnames say about the machines. This is the part a reader
    # can act on: which CDN they were assigned, and whether any of it is a
    # peer-assisted node rather than a datacentre.
    peers = []
    for host in hosts[:6]:
        described = describe(host)
        if described.operator_key or described.located:
            result.add(f"  {host}  ->  {summary(host)}")
        if described.is_peer:
            peers.append(host)
    if peers:
        result.status = WARN
        result.add(f"peer-assisted (PCDN) node(s) offered: {', '.join(peers)}")
        result.add("  those are home connections reselling upstream, and a common")
        result.add("  cause of stuttering on a line that otherwise tests fine")
    chosen = stream.choose_endpoint(endpoints)
    if chosen is None:
        result.status = FAIL
        result.add("none of them was chosen, which should be impossible")
        return
    result.add(f"chosen: {chosen.fmt} on {chosen.host}")
    if describe(chosen.host).operator_key or describe(chosen.host).located:
        result.add(f"  that edge is: {summary(chosen.host)}")
    if chosen.fmt != "fmp4":
        result.status = WARN
        # Not a promise that fmp4 gets a measurement: a real overseas edge has
        # served fmp4 with no PROGRAM-DATE-TIME in it, which estimates anyway.
        # fmp4 is the only format that *can* be measured exactly, not the one
        # that always is.
        result.add("not fmp4 - exact measurement is not possible for this format")


def check_measure(result: CheckResult, stream, room: str) -> None:
    """The headline number, and whether the server clock was really there."""
    if not room:
        result.status = SKIP
        result.add("needs a room id")
        return
    measurement = stream.measure(room)
    if measurement.error:
        result.status = FAIL if measurement.error != "offline" else WARN
        result.add(f"no measurement: {measurement.error}")
        return
    result.add(f"method: {measurement.method}   "
               f"{'measured' if not measurement.estimated else 'ESTIMATED'}")
    result.add(f"stream: {measurement.stream_ms:.0f} ms   host: {measurement.host}")
    if measurement.edge_lag_ms is not None:
        result.add(f"distance from the live edge: {measurement.edge_lag_ms:.0f} ms")
    if measurement.buffer_ms is not None:
        result.add(f"player buffer allowance: {measurement.buffer_ms:.0f} ms")
    detail = measurement.detail or {}
    for key in ("segments", "target_duration_s", "window_s", "codec", "quality"):
        if detail.get(key) not in (None, ""):
            result.add(f"{key}: {detail[key]}")
    if measurement.estimated:
        result.status = WARN
        result.add("no EXT-X-PROGRAM-DATE-TIME in the playlist, so this is an estimate")
        if "rejected_edge_lag_ms" in detail:
            result.add(f"a date tag was present but implausible: "
                       f"{detail['rejected_edge_lag_ms']:.0f} ms - check the system clock")


def check_cdn(result: CheckResult, stream, room: str) -> None:
    """The comparison, and what the automatic switch would decide about it."""
    if not room:
        result.status = SKIP
        result.add("needs a room id")
        return
    lines = stream.compare_lines()
    if not lines:
        result.status = WARN
        result.add("no edges to compare")
        return
    for line in lines:
        result.add(f"  {line.host:<44} "
                   f"{f'{line.rtt_ms:.0f} ms' if line.reachable else 'no answer'}")
    switches = stream.switches
    if switches:
        last = switches[-1]
        result.add(f"it moved: {last.from_host} -> {last.to_host}"
                   f"{f' (saving {last.saved_ms:.0f} ms)' if last.saved_ms else ''}")
    else:
        result.add("it stayed put - either already on the best edge, or the "
                   "difference was below the switching threshold")


def check_wireless(result: CheckResult) -> None:
    """What the Wi-Fi reading actually got, or why it got nothing.

    This failed silently on a real machine for two days: the history recorded
    no wireless at all and the report concluded the connection was wired, on a
    laptop that has never been plugged in. Nothing anywhere said so. The
    reading is best-effort by design, but "best effort" has to be visible when
    it comes back empty, or it is indistinguishable from having no Wi-Fi.

    The network's name is never printed - the report says it carries no Wi-Fi
    name and that has to stay true - so what is shown is which labels the
    tool's output contained, which is what a parsing failure looks like.
    """
    from .probes.path import _run, parse_wifi, wifi_info

    info = wifi_info()
    if info is not None:
        result.add(f"signal: {info.signal_pct if info.signal_pct is not None else '?'}%"
                   f"   band: {info.resolved_band() or 'unknown'}"
                   f"   radio: {info.radio or '?'}")
        result.add(f"channel: {info.channel or '?'}   "
                   f"access point: {'yes' if info.bssid else 'not read'}")
        result.add("network name: read, and deliberately not printed here")
        if not info.resolved_band():
            result.status = WARN
            result.add("the band could not be established, so links cannot be "
                       "told apart by it")
        return

    # Nothing came back. Say what the tool actually produced, without the
    # values - the labels alone show whether it answered and whether the
    # parsing understood it.
    result.status = WARN
    result.add("no wireless reading - this machine will look wired in reports")
    if sys.platform.startswith("win"):
        raw = _run(["netsh", "wlan", "show", "interfaces"], 6.0)
    elif sys.platform == "darwin":
        raw = _run(["/System/Library/PrivateFrameworks/Apple80211.framework/"
                    "Versions/Current/Resources/airport", "-I"], 6.0)
    else:
        raw = _run(["iw", "dev"], 4.0)

    if raw is None:
        result.add("the tool could not be run at all")
        return
    if not raw.strip():
        result.add("the tool ran but printed nothing")
        return
    labels = [line.split(":", 1)[0].strip() for line in raw.splitlines()
              if ":" in line and line.split(":", 1)[0].strip()]
    result.add(f"the tool printed {len(raw.splitlines())} line(s)")
    result.add("labels seen: " + (", ".join(labels[:14]) or "(none)"))
    result.add("if a label above is the local word for signal or channel and "
               "the reading still failed, that is the bug - send this list")


def check_path_tools(result: CheckResult) -> None:
    """Whether the OS tools the network check shells out to are usable."""
    from .probes.path import default_gateway, ping_stats

    gateway = default_gateway()
    result.add(f"default gateway: {gateway or 'not found'}")

    stats = ping_stats("8.8.8.8", count=3)
    if stats.error == "ping unavailable":
        result.status = WARN
        result.add("no usable ping command - the segment check cannot run here")
        return
    if not stats.ok:
        result.status = WARN
        result.add(f"8.8.8.8 did not answer ({stats.error}) - it may be filtered")
        return
    result.add(f"8.8.8.8: {stats.avg_ms:.0f} ms avg, {stats.loss_pct:.0f}% loss")


def check_apps(result: CheckResult) -> None:
    """The connection table the any-app mode is built on."""
    from .probes.appnet import list_apps

    apps = list_apps()
    if not apps:
        result.status = WARN
        result.add("no applications with network connections were visible")
        result.add("on macOS this usually means the process list needs permission")
        return
    result.add(f"{len(apps)} program(s) hold connections; busiest:")
    for app in apps[:5]:
        result.add(f"  {app.name}  ({app.connections} connection(s))")


def check_writable(result: CheckResult) -> None:
    """The config folder, which everything else depends on being writable."""
    from .config import app_config_dir
    from .history import History
    from .report import build_html, default_report_path

    folder = app_config_dir()
    result.add(f"config folder: {redact_home(folder)}")

    probe_file = folder / ".selftest"
    probe_file.write_text("ok", encoding="utf-8")
    probe_file.unlink()
    result.add("writable: yes")

    history = History()
    summary = history.summary(24.0)
    result.add(f"history: {summary['buckets']} minute(s) recorded, "
               f"{summary['samples']} sample(s)")
    build_html(buckets=history.buckets(24.0), summary=summary)
    result.add("report renders; it would be written to "
               f"{redact_home(default_report_path().parent)}")


# ------------------------------------------------------------------ runner
def run(config, room: str = "", timeout_s: float = 6.0) -> List[CheckResult]:
    """Every check, in the order a failure would cascade."""
    from .probes.network import HttpClient
    from .probes.stream import StreamProbe

    room = room or config.room_id
    results = [
        _check("environment", check_environment),
        _check("name resolution", check_dns),
    ]

    client = HttpClient(timeout_s=timeout_s)
    stream = StreamProbe(client, prefer_hls=config.probe.prefer_hls,
                         player_buffer_segments=config.probe.player_buffer_segments,
                         auto_cdn=config.probe.auto_cdn)
    try:
        results.append(_check("Bilibili API reachable",
                              lambda r: check_api_reachable(r, client, timeout_s)))
        results.append(_check("room info", lambda r: check_room(r, stream, room)))
        results.append(_check("play URLs", lambda r: check_endpoints(r, stream, room)))
        results.append(_check("live measurement", lambda r: check_measure(r, stream, room)))
        results.append(_check("CDN edges", lambda r: check_cdn(r, stream, room)))
    finally:
        client.close()

    results.append(_check("path tools (ping / gateway)", check_path_tools))
    results.append(_check("wireless", check_wireless))
    results.append(_check("application connections", check_apps))
    results.append(_check("config folder and report", check_writable))
    return results


def format_report(results: List[CheckResult]) -> str:
    """The whole thing as text a person can read and paste somewhere."""
    counts = {status: 0 for status in (OK, WARN, FAIL, SKIP)}
    lines = [
        f"{APP_NAME} {__version__} self-test",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        lines.append(f"{MARKS.get(result.status, '[????]')} {result.name}")
        for line in result.lines:
            lines.append(f"        {line}")
        lines.append("")

    lines.append(f"{counts[OK]} ok, {counts[WARN]} warning(s), "
                 f"{counts[FAIL]} failure(s), {counts[SKIP]} skipped")
    lines.append("")
    lines.append("This output contains addresses inside your own network and the servers")
    lines.append("measured. It has no Wi-Fi name, no public IP and no account details.")
    return "\n".join(lines)


def worst_status(results: List[CheckResult]) -> str:
    for status in (FAIL, WARN, SKIP):
        if any(result.status == status for result in results):
            return status
    return OK
