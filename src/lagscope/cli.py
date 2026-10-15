"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from . import APP_NAME, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lagscope",
        description=f"{APP_NAME} - measure Bilibili live delay from server to client to screen.",
    )
    parser.add_argument("--room", metavar="ID_OR_URL", help="live room id or URL to monitor")
    parser.add_argument("--video", metavar="ID_OR_URL", help="video (BV/av id or URL) to monitor")
    parser.add_argument("--app", metavar="NAME", help="measure any application by process name")
    parser.add_argument("--app-foreground", action="store_true",
                        help="measure whichever application is in the foreground")
    parser.add_argument("--ping", metavar="HOST", help="measure a server address directly")
    parser.add_argument("--ping-port", type=int, default=None, metavar="PORT",
                        help="port to use with --ping (default 443)")
    parser.add_argument("--list-apps", action="store_true",
                        help="list the applications that currently hold connections, then exit")
    parser.add_argument("--detect", dest="detect", action="store_true",
                        help="follow whatever Bilibili page you are watching")
    parser.add_argument("--no-detect", dest="detect", action="store_false",
                        help="never auto-detect; use --room / --video only")
    parser.set_defaults(detect=None)
    # Imported here rather than at module scope: --help must not pay for Qt.
    from .i18n import LANGUAGES

    parser.add_argument("--lang", choices=["auto", *LANGUAGES], help="interface language")
    parser.add_argument("--config-dir", metavar="PATH", help="use this folder for config and logs")
    parser.add_argument("--reset-config", action="store_true", help="start from default settings")
    parser.add_argument("--no-tray", action="store_true", help="do not create a tray icon")
    parser.add_argument("--no-overlay", action="store_true", help="start with the overlay hidden")
    parser.add_argument(
        "--probe-once", action="store_true",
        help="run a single measurement, print it as JSON and exit (no window)",
    )
    parser.add_argument(
        "--diagnose", nargs="?", const="", metavar="HOST",
        help="check each segment of the path (router / ISP / server) and say where the "
             "delay is; defaults to whatever is being monitored",
    )
    parser.add_argument(
        "--report", nargs="?", const="", metavar="FILE",
        help="write a shareable health report (chart + segment check) from the recorded "
             "history and print where it went; defaults to the reports folder",
    )
    parser.add_argument(
        "--history", nargs="?", const="24", metavar="HOURS",
        help="print a summary of the recorded history (default: the last 24 hours; "
             "'all' for everything kept)",
    )
    parser.add_argument(
        "--speedtest", action="store_true",
        help="download flat out for a few seconds and report the speed; this "
             "saturates the line while it runs",
    )
    parser.add_argument(
        "--selftest", nargs="?", const="", metavar="ROOM",
        help="run every probe once against the real world and print what came back; "
             "pass a room id that is currently streaming to cover the Bilibili paths",
    )
    parser.add_argument(
        "--why-ping", nargs="?", const="", metavar="HOST",
        help="time ICMP and a TCP handshake against the same address and explain "
             "why they differ; defaults to the host currently being measured",
    )
    parser.add_argument(
        "--detect-report", action="store_true",
        help="print what each detection source can see on this machine, then exit",
    )
    parser.add_argument(
        "--client-dir", action="append", metavar="PATH", default=None,
        help="extra folder to search for the desktop client's data (repeatable)",
    )
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="logging verbosity")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.config_dir:
        os.environ["LAGSCOPE_CONFIG_DIR"] = args.config_dir

    # Imported after the config dir override so paths resolve correctly.
    from .config import Config, parse_room_id
    from .i18n import set_language
    from .logging_setup import setup_logging

    setup_logging(getattr(logging, args.log_level, logging.INFO))
    log = logging.getLogger(__name__)

    config = Config() if args.reset_config else Config.load()
    if args.room:
        room = parse_room_id(args.room)
        if not room:
            print(f"not a room id or live URL: {args.room}", file=sys.stderr)
            return 2
        config.room_id = room
        config.manual_kind = "live"
        config.detect.enabled = False
    if args.video:
        from .probes.video import parse_video_target

        video, page = parse_video_target(args.video)
        if not video:
            print(f"not a video id or URL: {args.video}", file=sys.stderr)
            return 2
        config.video_id = video
        config.video_page = page
        config.manual_kind = "video"
        config.detect.enabled = False
    if args.app or args.app_foreground:
        config.manual_kind = "app"
        config.app_name = args.app or ""
        config.app_follow_foreground = bool(args.app_foreground)
        config.detect.enabled = False
    if args.ping:
        config.manual_kind = "target"
        config.target_host = args.ping
        if args.ping_port:
            config.target_port = args.ping_port
        config.detect.enabled = False
    if args.detect is not None:
        config.detect.enabled = args.detect
    if args.client_dir:
        config.detect.client_dirs = list(dict.fromkeys(config.detect.client_dirs + args.client_dir))
    if args.lang:
        config.language = args.lang
    if args.no_tray:
        config.tray.enabled = False
    if args.no_overlay:
        config.overlay.enabled = False
    config = config.sanitized()
    set_language(config.language)

    if args.diagnose is not None:
        return _diagnose(config, args.diagnose)

    if args.speedtest:
        return _speedtest(config)

    if args.why_ping is not None:
        return _why_ping(config, args.why_ping)

    if args.selftest is not None:
        return _selftest(config, args.selftest)

    if args.report is not None:
        return _write_report(config, args.report)

    if args.history is not None:
        return _print_history(config, args.history)

    if args.list_apps:
        return _list_apps()

    if args.detect_report:
        return _detect_report(config)

    if args.probe_once:
        return _probe_once(config)

    from PySide6.QtWidgets import QApplication  # noqa: F401  (imported for side effects)

    from .app import MonitorApplication, create_application
    from .single_instance import SingleInstance

    app = create_application(sys.argv[:1])

    # Checked before anything is built, so a second launch never flashes a
    # second tray icon - it just brings the running copy back into view.
    guard = SingleInstance()
    if guard.notify_running_instance():
        log.info("another instance is already running; asked it to show itself")
        print(f"{APP_NAME} is already running.", file=sys.stderr)
        return 0
    guard.listen()

    monitor = MonitorApplication(app, config, guard)
    # A fresh install answers three questions before the overlay appears; an
    # existing one never sees this.
    monitor.run_setup_if_needed()
    monitor.start()
    return app.exec()


def _probe_once(config) -> int:
    """Headless single measurement - handy for troubleshooting and scripting."""
    from .models import KIND_APP, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, LatencySample
    from .probes.network import HttpClient, tcp_rtt_ms
    from .probes.stream import StreamProbe
    from .probes.video import VideoProbe

    target = _probe_target(config)
    timeout_s = config.probe.timeout_ms / 1000.0
    client = HttpClient(timeout_s=timeout_s)
    try:
        if target.kind == KIND_APP:
            from .probes.appnet import AppNetProbe

            result = AppNetProbe().measure(target.ident, timeout_s)
            sample = LatencySample(
                network_ms=result.rtt_ms, total_ms=result.rtt_ms, ok=result.rtt_ms is not None,
                kind=KIND_APP, method=result.method, title=target.ident,
                host=str(result.peer) if result.peer else "",
                connections=result.connections, error=result.error,
            )
            print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
            return 0 if sample.ok else 1

        if target.kind == KIND_TARGET:
            from .probes.network import icmp_ping_ms

            port = int(target.page or 443)
            rtt = tcp_rtt_ms(target.ident, port, timeout_s)
            method = "tcp" if rtt is not None else "icmp"
            if rtt is None:
                rtt = icmp_ping_ms(target.ident, timeout_s)
            sample = LatencySample(
                network_ms=rtt, total_ms=rtt, ok=rtt is not None, kind=KIND_TARGET,
                method=method if rtt is not None else "none",
                host=f"{target.ident}:{port}", title=target.ident,
                error=None if rtt is not None else "unreachable",
            )
            print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
            return 0 if sample.ok else 1

        if target.kind == KIND_NETWORK:
            from .probes.internet import InternetProbe

            result = InternetProbe().measure(timeout_s)
            anchor = result.anchor
            sample = LatencySample(
                network_ms=result.rtt_ms, total_ms=result.rtt_ms, ok=result.ok,
                kind=KIND_NETWORK, method=result.method,
                host=anchor.endpoint if anchor else "",
                title=anchor.label if anchor else "",
                error=None if result.ok else "offline-net",
            )
        else:
            rtt = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)
            if target.kind == KIND_VIDEO:
                probe = VideoProbe(client, playurl_refresh_s=config.probe.playurl_refresh_s)
                result = probe.measure(target.ident, target.page)
            else:
                probe = StreamProbe(
                    client,
                    prefer_hls=config.probe.prefer_hls,
                    player_buffer_segments=config.probe.player_buffer_segments,
                    playurl_refresh_s=config.probe.playurl_refresh_s,
                )
                measurement = client.measure(
                    "https://api.live.bilibili.com/room/v1/Room/get_info?room_id=1"
                )
                probe.set_clock_offset_ms(measurement.clock_offset_ms)
                result = probe.measure(target.ident)
            sample = LatencySample(
                network_ms=probe.endpoint_rtt_ms(timeout_s) or rtt,
                stream_ms=result.stream_ms,
                total_ms=result.stream_ms,
                ok=result.stream_ms is not None,
                estimated=result.estimated,
                kind=target.kind,
                method=result.method,
                host=result.host,
                title=result.title or target.title,
                source=target.source,
                throughput_mbps=result.throughput_mbps,
                required_mbps=result.required_mbps,
                error=result.error,
            )
        print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
        return 0 if sample.ok else 1
    finally:
        client.close()


def _diagnose(config, host: str) -> int:
    """Measure each segment of the path and say which one is the problem."""
    from .i18n import tr
    from .probes.path import analyse, verdict

    target = host or _diagnosis_host(config)
    if not target:
        print("nothing to diagnose: pass a host, or set what to monitor first",
              file=sys.stderr)
        return 2

    print(f"{tr('diag.title')}: {target}")
    print(tr("diag.running"), flush=True)
    report = analyse(target)

    rows = [
        (tr("diag.you_router"), report.gateway_stats),
        (tr("diag.router_isp"), report.hop_stats),
        (tr("diag.to_target"), report.target_stats),
    ]
    width = max(len(label) for label, _stats in rows)
    print()
    for label, stats in rows:
        if stats is None:
            print(f"  {label.ljust(width)}   --")
            continue
        if not stats.ok:
            print(f"  {label.ljust(width)}   {stats.error or '--'}  ({stats.host})")
            continue
        loss = stats.loss_pct or 0.0
        print(f"  {label.ljust(width)}   {stats.avg_ms:6.1f} ms   "
              f"{tr('diag.loss')} {loss:4.0f}%   ({stats.host})")

    if report.dns_ms is not None:
        print(f"  {tr('diag.dns').ljust(width)}   {report.dns_ms:6.1f} ms")
    if report.wifi is not None:
        wifi = report.wifi
        signal = f"{wifi.signal_pct}%" if wifi.signal_pct is not None else "--"
        rate = f", {wifi.rx_mbps:.0f} Mbps" if wifi.rx_mbps else ""
        print(f"\n  {tr('diag.wifi')}: {wifi.ssid or '--'}  {signal}  {wifi.radio}{rate}")
    if "gateway-silent" in report.notes:
        print(f"  {tr('diag.gateway_silent')}")
    if not report.gateway:
        print(f"  {tr('diag.no_gateway')}")

    key, detail = verdict(report)
    print(f"\n=> {tr(key)}" + (f"  [{detail}]" if detail else ""))
    return 0


def _diagnosis_host(config) -> str:
    """What to diagnose when the user did not name a host."""
    from .models import KIND_APP, KIND_TARGET

    target = _probe_target(config)
    if target.kind == KIND_TARGET:
        return target.ident
    if target.kind == KIND_APP:
        from .probes.appnet import peers_for

        peers = peers_for(target.ident)
        if peers:
            return peers[0].ip
    # Anything else (a Bilibili room, a video, network-only) is reached through
    # the same line, so the API host is a fair stand-in.
    return config.probe.rtt_host


def _speedtest(config) -> int:
    """Measure the line flat out. No target is known here, so it uses the
    public endpoint - the GUI prefers the CDN you are actually watching."""
    from .i18n import tr
    from .probes.network import HttpClient
    from .probes.speed import measure_download, public_url, tier_key
    from .ui.theme import format_mbps

    max_bytes = int(config.speed.max_mb) * 1024 * 1024
    print(tr("speed.running"), flush=True)

    client = HttpClient(timeout_s=float(config.probe.timeout_ms) / 1000.0)
    try:
        result = measure_download(client.session, public_url(max_bytes),
                                  budget_s=float(config.speed.budget_s),
                                  max_bytes=max_bytes, source="public")
    finally:
        client.close()

    if not result.ok:
        print(f"{tr('speed.failed')}: {result.error}", file=sys.stderr)
        return 1
    print()
    print(tr("speed.result", value=format_mbps(result.mbps)))
    print(tr(tier_key(result.mbps)))
    print(tr("speed.cost", megabytes=f"{result.bytes / 1024 / 1024:.0f}",
             seconds=f"{result.seconds:.0f}"))
    if not result.warmed:
        print(tr("speed.short"))
    return 0


def _selftest(config, room: str) -> int:
    """Evidence that each probe works here, for a person to read and paste."""
    from .selftest import FAIL, format_report, run, worst_status

    print("running the self-test; the Bilibili checks need a few seconds...\n", flush=True)
    results = run(config, room=room)
    print(format_report(results))
    # A non-zero exit lets this be used in a script, but the report is the point.
    return 1 if worst_status(results) == FAIL else 0


def _why_ping(config, host: str) -> int:
    """Answer "why doesn't this match ping" with both numbers side by side."""
    from .pingcompare import compare, format_report
    from .probes.network import host_port_from_url

    port = 443
    target = (host or "").strip()
    if target:
        # Accept a pasted URL as readily as a bare hostname.
        if "//" in target or target.startswith(("http:", "https:")):
            target, port = host_port_from_url(target)
    else:
        target = config.probe.rtt_host
        port = config.probe.rtt_port
    if not target:
        print("no host to measure; pass one, e.g. --why-ping cn-gotcha09.bilivideo.com")
        return 2

    print(f"measuring {target} with both tools; this takes a few seconds...\n", flush=True)
    result = compare(target, port)
    print(format_report(result))
    return 0 if result.tcp_samples else 1


def _history_hours(text: str):
    """``24`` -> 24.0, ``all`` -> None (everything kept)."""
    text = (text or "").strip().lower()
    if text in ("", "all", "0"):
        return None if text == "all" else 24.0
    try:
        return max(0.1, float(text))
    except ValueError:
        return 24.0


def _load_history(config):
    from .history import History

    return History(bucket_s=config.history.bucket_s, keep_hours=config.history.keep_hours)


def _print_history(config, window: str) -> int:
    """What the chart shows, as text - useful over SSH and in a bug report."""
    from .i18n import tr
    from .report import build_text

    hours = _history_hours(window)
    history = _load_history(config)
    summary = history.summary(hours)
    if not summary["buckets"]:
        print(tr("history.empty"))
        return 0
    print(build_text(summary=summary, worst=history.worst_hour(hours)))
    return 0


def _write_report(config, path: str) -> int:
    """The one-click report, from the command line: history plus a fresh check."""
    from pathlib import Path

    from .i18n import tr
    from .probes.path import analyse, verdict
    from .report import build_html, default_report_path, write_report

    hours = 24.0
    history = _load_history(config)
    summary = history.summary(hours)

    # A report without the path check is only half of one, so it runs here too.
    target = _diagnosis_host(config)
    print(tr("diag.running"), flush=True)
    path_report = analyse(target) if target else None
    key, detail = verdict(path_report) if path_report is not None else ("", "")

    from .presentation import dominant_kind, thresholds_for

    guides = thresholds_for(config.thresholds, dominant_kind(history.buckets(hours)))
    document = build_html(
        buckets=history.buckets(hours), summary=summary, bucket_s=history.bucket_s,
        worst=history.worst_hour(hours), path_report=path_report,
        verdict_key=key, verdict_detail=detail,
        target_label=summary.get("label", ""),
        good_ms=guides[0], warn_ms=guides[1],
    )
    # Said before the path is printed: the two streams interleave otherwise.
    if not summary["buckets"]:
        print(tr("history.empty"), file=sys.stderr)

    destination = Path(path).expanduser() if path else default_report_path()
    try:
        written = write_report(document, destination)
    except OSError as exc:
        print(f"{tr('report.failed')}: {exc}", file=sys.stderr)
        return 1
    print(f"{tr('report.saved')} {written}")
    return 0


def _list_apps() -> int:
    """Show which programs are on the network, so one can be named with --app."""
    from .probes.appnet import list_apps

    apps = list_apps()
    if not apps:
        print("No application with open connections was found.", file=sys.stderr)
        return 1
    width = max(len(app.name) for app in apps)
    print(f"{'APPLICATION'.ljust(width)}  SOCKETS  PIDS")
    for app in apps:
        pids = ",".join(str(pid) for pid in app.pids[:4])
        print(f"{app.name.ljust(width)}  {app.connections:>7}  {pids}")
    return 0


def _detect_report(config) -> int:
    """Show what each detection source finds here - the first thing to run when
    auto-detection is not picking up the desktop client."""
    from .config import title_memory_path
    from .detect import AutoDetector

    detector = AutoDetector(config.detect, memory_path=title_memory_path())
    try:
        report = detector.report()
    finally:
        detector.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["client"]["folders"]:
        print(
            "\nNo desktop-client data folder found. If the client is installed, pass its\n"
            "folder with --client-dir (e.g. --client-dir \"%APPDATA%\\bilibili\") and\n"
            "report the path so it can be added to the defaults.",
            file=sys.stderr,
        )
    return 0 if report.get("result") else 1


def _with_target(sample, target) -> dict:
    payload = sample.to_dict()
    payload["target"] = {"kind": target.kind, "id": target.ident, "page": target.page,
                         "source": target.source}
    return payload


def _probe_target(config):
    """Same rules the GUI uses, with detection resolved right now."""
    from .detect import AutoDetector
    from .targets import resolve_target

    def foreground_app() -> str:
        from .ui.anchor import create_window_finder

        return create_window_finder().foreground_process()

    detector = None
    if config.detect.enabled:
        detector = AutoDetector(config.detect)
    try:
        return resolve_target(config, detector, foreground_app, force_detect=True)
    finally:
        if detector is not None:
            detector.close()

