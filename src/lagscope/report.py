"""One button that turns hours of measurements into something you can send.

"My internet is bad" is not a report. What gets a helpdesk ticket moving, or
an answer on a forum, is a page that says *when* it was bad, *how* bad, and
*which segment of the path* it happened on - with the numbers attached.

So this builds a single self-contained HTML file: the chart is inline SVG, the
styles are inline, nothing is fetched from the network when it is opened. It
can be mailed, attached to a ticket or opened offline three weeks later and it
still renders. A plain-text version comes with it for pasting into a forum
post, where an attachment is no use.

What it deliberately does *not* contain: any public IP address, any account,
any cookie, any URL you visited. The addresses in it are the private ones
inside your own home (192.168.x.x) plus whatever server was being measured.
"""

from __future__ import annotations

import html
import math
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Sequence

from . import APP_NAME, REPO_URL, __version__
from .config import app_config_dir
from .history import Bucket
from .i18n import tr
from .actions import has_local_cause
from .probes.cdninfo import summary as cdn_summary
from .probes.speed import tier_key
from .textfmt import pad as text_pad, width as text_width
from .ui.theme import format_mbps, format_ms

CHART_WIDTH = 960
CHART_HEIGHT = 260
CHART_PAD_LEFT = 56
CHART_PAD_RIGHT = 16
CHART_PAD_TOP = 14
CHART_PAD_BOTTOM = 28

GOOD = "#1f9d55"
WARN = "#c98a00"
BAD = "#d93636"
INK = "#1a1d24"
MUTED = "#5c6474"
LINE = "#d8dde7"
ACCENT = "#0b7fab"

# Smaller than this either way is not a change anyone would notice.
CHANGE_MS = 10.0


# --------------------------------------------------------------------- chart
def nice_ceiling(value: float) -> float:
    """Round a scale top up to something a person would have chosen."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0):
        candidate = step * magnitude
        if candidate >= value:
            return candidate
    return 10.0 * magnitude


def grid_values(top: float, lines: int = 4) -> List[float]:
    """Gridline values that are round in themselves, not quarters of the top.

    Quartering a 750 ms scale gives 187.5 ms labels, which nobody reads. A
    rounded step gives 200 / 400 / 600 and a top edge that may sit slightly
    above the last line - which is what a chart normally looks like.
    """
    if top <= 0:
        return [0.0]
    step = nice_ceiling(top / max(1, lines))
    values = [0.0]
    value = step
    while value < top - step * 0.2:
        values.append(value)
        value += step
    values.append(top)
    return values


def _switch_label(from_host: str, to_host: str) -> str:
    """``a → b``, with each side named when the hostname says who runs it."""
    from .probes.cdninfo import describe, summary

    def one(host):
        if not host:
            return "--"
        info = describe(host)
        return f"{host} ({summary(host)})" if info.operator_key or info.located else host

    return f"{one(from_host)} → {one(to_host)}"


def _where_html(host: str) -> str:
    """What a CDN hostname says about the machine, when it says anything."""
    from .probes.cdninfo import describe, summary

    info = describe(host)
    if not (info.operator_key or info.located):
        return ""
    text = f'<div class="sub" style="margin-top:4px">{html.escape(summary(host))}</div>'
    if info.is_peer:
        text += (f'<div class="sub" style="margin-top:4px;color:#b45309">'
                 f'{html.escape(tr("cdn.peer.warn"))}</div>')
    return text


def chart_svg(buckets: Sequence[Bucket], bucket_s: float = 60.0,
              good_ms: Optional[float] = None, warn_ms: Optional[float] = None,
              markers: Sequence = ()) -> str:
    """The whole history as one inline SVG - no script, no external file."""
    # Sorted rather than assumed sorted: recorded history always is, but a
    # chart that silently draws nonsense for out-of-order input is a bad way
    # to find that out.
    rows = sorted((row for row in buckets if row.avg_ms is not None),
                  key=lambda row: row.start)
    if not rows:
        return (
            f'<svg viewBox="0 0 {CHART_WIDTH} 80" role="img" aria-label="empty">'
            f'<text x="{CHART_WIDTH / 2}" y="46" text-anchor="middle" fill="{MUTED}" '
            f'font-size="14">{html.escape(tr("report.no_data"))}</text></svg>'
        )

    first = rows[0].start
    last = rows[-1].start + bucket_s
    span = max(bucket_s, last - first)
    top = nice_ceiling(max(row.max_ms or row.avg_ms or 0.0 for row in rows) * 1.05)
    plot_w = CHART_WIDTH - CHART_PAD_LEFT - CHART_PAD_RIGHT
    plot_h = CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM

    def x_of(ts: float) -> float:
        return CHART_PAD_LEFT + (ts - first) / span * plot_w

    def y_of(value: float) -> float:
        clamped = max(0.0, min(top, value))
        return CHART_PAD_TOP + plot_h - (clamped / top) * plot_h

    parts: List[str] = [
        f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="{html.escape(tr("report.chart"))}">',
        f'<rect x="{CHART_PAD_LEFT}" y="{CHART_PAD_TOP}" width="{plot_w}" height="{plot_h}" '
        f'fill="#ffffff" stroke="{LINE}"/>',
    ]

    # Horizontal grid, labelled in the same units as everything else.
    for value in grid_values(top):
        y = y_of(value)
        parts.append(
            f'<line x1="{CHART_PAD_LEFT}" y1="{y:.1f}" x2="{CHART_PAD_LEFT + plot_w}" '
            f'y2="{y:.1f}" stroke="{LINE}" stroke-dasharray="2 4"/>'
        )
        parts.append(
            f'<text x="{CHART_PAD_LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{MUTED}">{html.escape(format_ms(value))}</text>'
        )

    # Where "fine" stops - the same thresholds the overlay colours by.
    for threshold, colour in ((good_ms, GOOD), (warn_ms, WARN)):
        if threshold and 0 < threshold < top:
            y = y_of(threshold)
            parts.append(
                f'<line x1="{CHART_PAD_LEFT}" y1="{y:.1f}" x2="{CHART_PAD_LEFT + plot_w}" '
                f'y2="{y:.1f}" stroke="{colour}" stroke-width="1" opacity="0.5"/>'
            )

    # Hour ticks along the bottom.
    for tick in _hour_ticks(first, last):
        x = x_of(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{CHART_PAD_TOP}" x2="{x:.1f}" '
            f'y2="{CHART_PAD_TOP + plot_h}" stroke="{LINE}"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{CHART_HEIGHT - 9}" text-anchor="middle" font-size="11" '
            f'fill="{MUTED}">{time.strftime("%H:%M", time.localtime(tick))}</text>'
        )

    # A gap in time is a gap in the line: joining across it would invent data.
    for run in _runs(rows, bucket_s):
        band_top = " ".join(f"{x_of(r.start + bucket_s / 2):.1f},{y_of(r.max_ms or r.avg_ms):.1f}"
                            for r in run)
        band_bottom = " ".join(
            f"{x_of(r.start + bucket_s / 2):.1f},{y_of(r.min_ms or r.avg_ms):.1f}"
            for r in reversed(run)
        )
        parts.append(
            f'<polygon points="{band_top} {band_bottom}" fill="{ACCENT}" opacity="0.16"/>'
        )
        line = " ".join(f"{x_of(r.start + bucket_s / 2):.1f},{y_of(r.avg_ms):.1f}" for r in run)
        parts.append(
            f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="1.8" '
            f'stroke-linejoin="round"/>'
        )

    # Every stall and spike marked on the floor, so the eye finds the evening.
    for row in buckets:
        if not (row.stalls or row.spikes):
            continue
        x = x_of(row.start + bucket_s / 2)
        colour = BAD if row.stalls else WARN
        parts.append(
            f'<rect x="{x - 1.5:.1f}" y="{CHART_PAD_TOP + plot_h - 6}" width="3" height="6" '
            f'fill="{colour}"/>'
        )

    # The moments the user marked, so the shared report shows the same "I
    # changed something here" line the window does.
    for marker in markers or ():
        stamp = float(marker.get("ts", 0.0))
        if not (first <= stamp <= last):
            continue
        x = x_of(stamp)
        parts.append(
            f'<line x1="{x:.1f}" y1="{CHART_PAD_TOP}" x2="{x:.1f}" '
            f'y2="{CHART_PAD_TOP + plot_h}" stroke="{INK}" stroke-width="1" '
            f'stroke-dasharray="4 3"/>'
        )
        label = str(marker.get("label") or "")
        if label:
            parts.append(
                f'<text x="{x + 4:.1f}" y="{CHART_PAD_TOP + 12}" font-size="11" '
                f'fill="{INK}">{html.escape(label[:28])}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def _runs(rows: Sequence[Bucket], bucket_s: float) -> List[List[Bucket]]:
    """Split buckets into stretches with no missing minutes between them."""
    runs: List[List[Bucket]] = []
    current: List[Bucket] = []
    for row in rows:
        if current and row.start - current[-1].start > bucket_s * 2.5:
            runs.append(current)
            current = []
        current.append(row)
    if current:
        runs.append(current)
    return [run for run in runs if run]


def _hour_ticks(first: float, last: float) -> List[float]:
    """Tick marks on the hour, thinned out so the labels never collide."""
    span_h = (last - first) / 3600.0
    step_h = 1
    for candidate in (1, 2, 3, 6, 12, 24):
        step_h = candidate
        if span_h / candidate <= 12:
            break
    start = math.ceil(first / 3600.0) * 3600
    ticks = []
    tick = start
    while tick <= last:
        hour = int(time.strftime("%H", time.localtime(tick)))
        if hour % step_h == 0:
            ticks.append(float(tick))
        tick += 3600
    return ticks


# -------------------------------------------------------------------- report
# Kept as local names; the implementation is shared with the other text views.
_width = text_width
_pad = text_pad


def _fmt_pct(value: Optional[float]) -> str:
    return "--" if value is None else f"{value:.1f}%"


def _fmt_time(ts: Optional[float]) -> str:
    if not ts:
        return "--"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def summary_rows(summary: dict) -> List[tuple]:
    """The headline table, shared by the HTML and the plain-text versions."""
    uptime = 100.0 - (summary.get("loss_pct") or 0.0)
    return [
        (tr("label.avg"), format_ms(summary.get("avg_ms"))),
        (tr("label.p95"), format_ms(summary.get("p95_ms"))),
        (tr("label.range"),
         f"{format_ms(summary.get('min_ms'))} – {format_ms(summary.get('max_ms'))}"),
        (tr("label.jitter"), format_ms(summary.get("jitter_ms"))),
        (tr("report.uptime"), _fmt_pct(uptime)),
        (tr("report.stalls"), str(summary.get("stalls", 0))),
        (tr("report.spikes"), str(summary.get("spikes", 0))),
        (tr("report.samples"), str(summary.get("samples", 0))),
    ]


def worst_hour_line(worst: Optional[dict]) -> str:
    if not worst:
        return tr("report.no_trouble")
    return tr(
        "report.worst_line",
        time=time.strftime("%m-%d %H:00", time.localtime(worst["start"])),
        avg=format_ms(worst.get("avg_ms")),
        max=format_ms(worst.get("max_ms")),
        stalls=worst.get("stalls", 0) + worst.get("spikes", 0),
    )


def finding_rows(findings: Sequence) -> List[tuple]:
    """(when, what was blamed) for each unattended check, newest first."""
    rows = []
    for entry in findings or ():
        when = time.strftime("%m-%d %H:%M", time.localtime(entry.get("start", 0)))
        events = (entry.get("stalls", 0) or 0) + (entry.get("spikes", 0) or 0)
        rows.append((when, tr(entry.get("verdict", "")), events))
    return rows


def comparison_rows(comparisons: Sequence) -> List[tuple]:
    """(when, what changed, before -> after, verdict) for each marked moment."""
    rows = []
    for entry in comparisons or ():
        compare = entry.get("compare")
        if not compare:
            continue
        before, after = compare["before"], compare["after"]
        delta = compare.get("delta_ms")
        if delta is None:
            verdict = tr("compare.unclear")
        elif delta <= -CHANGE_MS:
            verdict = tr("compare.better", value=format_ms(abs(delta)))
        elif delta >= CHANGE_MS:
            verdict = tr("compare.worse", value=format_ms(abs(delta)))
        else:
            verdict = tr("compare.same")
        rows.append((
            time.strftime("%m-%d %H:%M", time.localtime(compare["ts"])),
            entry.get("label") or "",
            f"{format_ms(before['avg_ms'])} → {format_ms(after['avg_ms'])}",
            verdict,
            _span_text(compare["span_s"]),
        ))
    return rows


def _span_text(span_s: float) -> str:
    minutes = max(1, int(round(span_s / 60.0)))
    if minutes < 90:
        return tr("compare.span_min", n=minutes)
    return tr("compare.span_hour", n=round(span_s / 3600.0, 1))


def switch_rows(switches: Sequence) -> List[tuple]:
    """(when, from -> to, what it saved) for each CDN edge change."""
    rows = []
    for switch in switches or ():
        when = time.strftime("%m-%d %H:%M", time.localtime(getattr(switch, "ts", 0)))
        saved = getattr(switch, "saved_ms", None)
        rows.append((
            when,
            _switch_label(getattr(switch, "from_host", ""),
                          getattr(switch, "to_host", "")),
            f"-{format_ms(saved)}" if saved else "",
        ))
    return rows


def segment_rows(path_report) -> List[tuple]:
    """The three path segments as (label, value) pairs, or [] without a check."""
    if path_report is None:
        return []
    rows = []
    for label, stats in (
        (tr("diag.you_router"), path_report.gateway_stats),
        (tr("diag.router_isp"), path_report.hop_stats),
        (tr("diag.to_target"), path_report.target_stats),
    ):
        if stats is None:
            rows.append((label, "--", ""))
        elif not stats.ok:
            rows.append((label, stats.error or "--", stats.host))
        else:
            rows.append((
                label,
                f"{format_ms(stats.avg_ms)}   {tr('diag.loss')} {stats.loss_pct:.0f}%",
                stats.host,
            ))
    if path_report.dns_ms is not None:
        rows.append((tr("diag.dns"), format_ms(path_report.dns_ms), ""))
    return rows


def build_html(*, buckets: Sequence[Bucket], summary: dict, bucket_s: float = 60.0,
               worst: Optional[dict] = None, path_report=None, verdict_key: str = "",
               verdict_detail: str = "", extras: Sequence = (), target_label: str = "",
               auto_findings: Sequence = (), switches: Sequence = (),
               comparisons: Sequence = (), speed=None,
               edges: Sequence = (), edge_note: str = "", pattern_note: str = "",
               links: Sequence = (), link_note: str = "",
               signals: Sequence = (), signal_note: str = "",
               actions: Sequence = (),
               good_ms: Optional[float] = None, warn_ms: Optional[float] = None) -> str:
    """The whole report as one HTML document with nothing external in it."""
    esc = html.escape
    hours = summary.get("hours")
    window = tr("report.hours", n=int(hours)) if hours else tr("report.all")

    head = [
        "<!doctype html>", '<html lang="zh">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{esc(tr('report.title'))} · {esc(APP_NAME)}</title>",
        "<style>",
        "body{margin:0;padding:28px 20px 48px;background:#f4f5f8;color:" + INK + ";"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
        "'Microsoft YaHei',system-ui,sans-serif;line-height:1.55;}",
        "main{max-width:1000px;margin:0 auto;}",
        "h1{font-size:20px;margin:0 0 4px;}h2{font-size:15px;margin:26px 0 10px;"
        "letter-spacing:.02em;}",
        ".sub{color:" + MUTED + ";font-size:13px;margin:0 0 18px;}",
        ".card{background:#fff;border:1px solid " + LINE + ";border-radius:10px;"
        "padding:16px 18px;margin-bottom:16px;}",
        ".grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px 12px;}",
        "@media (max-width:620px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));}}",
        ".cell .k{font-size:12px;color:" + MUTED + ";}",
        ".cell .v{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap;}",
        "table{border-collapse:collapse;width:100%;font-size:13px;}",
        "td,th{text-align:left;padding:6px 8px;border-bottom:1px solid " + LINE + ";}",
        "th{color:" + MUTED + ";font-weight:500;}",
        "td.n{font-variant-numeric:tabular-nums;}",
        ".verdict{font-size:15px;padding:12px 14px;border-radius:8px;"
        "background:#eef6fb;border:1px solid #cbe4f0;}",
        ".legend{font-size:12px;color:" + MUTED + ";margin-top:8px;}",
        ".sw{display:inline-block;width:10px;height:10px;border-radius:2px;"
        "vertical-align:-1px;margin-right:4px;}",
        "footer{color:" + MUTED + ";font-size:12px;margin-top:28px;}",
        "a{color:" + ACCENT + ";}",
        "@media print{body{background:#fff;padding:0;}.card{break-inside:avoid;}}",
        "</style>", "</head>", "<body>", "<main>",
    ]

    body = [
        f"<h1>{esc(tr('report.title'))}</h1>",
        f'<p class="sub">{esc(tr("report.generated"))} {esc(_fmt_time(time.time()))}'
        f' · {esc(tr("report.window"))} {esc(window)}'
        f' · {esc(_fmt_time(summary.get("from")))} – {esc(_fmt_time(summary.get("to")))}</p>',
    ]

    if target_label or summary.get("label"):
        body.append(
            f'<p class="sub">{esc(tr("report.watching"))}: '
            f'{esc(target_label or summary.get("label", ""))}</p>'
        )

    cells = "".join(
        f'<div class="cell"><div class="k">{esc(key)}</div>'
        f'<div class="v">{esc(value)}</div></div>'
        for key, value in summary_rows(summary)
    )
    body.append(f'<div class="card"><div class="grid">{cells}</div></div>')

    body.append(f"<h2>{esc(tr('report.chart'))}</h2>")
    body.append('<div class="card">')
    chart_marks = [
        {"ts": entry["compare"]["ts"], "label": entry.get("label", "")}
        for entry in (comparisons or ()) if entry.get("compare")
    ]
    body.append(chart_svg(buckets, bucket_s, good_ms, warn_ms, chart_marks))
    body.append(
        f'<div class="legend">'
        f'<span class="sw" style="background:{ACCENT}"></span>{esc(tr("report.legend_avg"))}'
        f'　<span class="sw" style="background:{ACCENT};opacity:.25"></span>'
        f'{esc(tr("report.legend_range"))}'
        f'　<span class="sw" style="background:{BAD}"></span>{esc(tr("report.legend_marks"))}'
        f"</div></div>"
    )

    body.append(f"<h2>{esc(tr('report.worst'))}</h2>")
    body.append(f'<div class="card">{esc(worst_hour_line(worst))}</div>')

    segments = segment_rows(path_report)
    if segments:
        rows = "".join(
            f"<tr><td>{esc(label)}</td><td class=\"n\">{esc(value)}</td>"
            f"<td>{esc(host)}</td></tr>"
            for label, value, host in segments
        )
        body.append(f"<h2>{esc(tr('report.segments'))}</h2>")
        body.append(f'<div class="card"><table>{rows}</table>')
        if path_report is not None and path_report.wifi is not None:
            wifi = path_report.wifi
            signal = f"{wifi.signal_pct}%" if wifi.signal_pct is not None else "--"
            body.append(
                f'<p class="sub" style="margin:10px 0 0">{esc(tr("diag.wifi"))}: '
                f'{esc(wifi.ssid or "--")}　{esc(signal)}　{esc(wifi.radio)}</p>'
            )
        body.append("</div>")
        if verdict_key:
            detail = f"  [{verdict_detail}]" if verdict_detail else ""
            body.append(f'<div class="verdict">{esc(tr(verdict_key) + detail)}</div>')

    findings = finding_rows(auto_findings)
    if findings:
        rows = "".join(
            f'<tr><td class="n">{esc(when)}</td><td>{esc(what)}</td>'
            f'<td class="n">{esc(str(events) if events else "")}</td></tr>'
            for when, what, events in findings
        )
        body.append(f"<h2>{esc(tr('report.findings'))}</h2>")
        body.append(f'<div class="card"><table>{rows}</table></div>')

    if speed is not None and getattr(speed, "ok", False):
        body.append(f"<h2>{esc(tr('speed.title'))}</h2>")
        body.append(
            f'<div class="card"><div class="grid">'
            f'<div class="cell"><div class="k">{esc(tr("label.down"))}</div>'
            f'<div class="v">{esc(format_mbps(speed.mbps))}</div></div>'
            f'<div class="cell"><div class="k">{esc(tr("speed.host"))}</div>'
            f'<div class="v" style="font-size:14px">{esc(speed.host)}</div>'
            f'{_where_html(speed.host)}</div>'
            f'</div><p class="sub" style="margin:10px 0 0">{esc(tr(tier_key(speed.mbps)))}</p>'
            "</div>"
        )

    if edges:
        body.append(f"<h2>{esc(tr('edge.title'))}</h2>")
        rows = "".join(
            f"<tr><td>{esc(stats.host)}<div class='sub'>{esc(cdn_summary(stats.host))}</div></td>"
            f"<td>{esc(format_ms(stats.avg_ms))}</td>"
            f"<td>{stats.share_pct:.0f}%</td>"
            f"<td>{stats.stalls}</td></tr>"
            for stats in edges
        )
        body.append(
            "<table><thead><tr>"
            f"<th>{esc(tr('edge.col_host'))}</th><th>{esc(tr('edge.col_avg'))}</th>"
            f"<th>{esc(tr('edge.col_share'))}</th><th>{esc(tr('edge.col_stalls'))}</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
        if edge_note:
            body.append(f'<p class="sub">{esc(edge_note)}</p>')

    if links:
        body.append(f"<h2>{esc(tr('link.title'))}</h2>")
        rows = "".join(
            f"<tr><td>{esc(stats.host)}</td>"
            f"<td>{esc(format_ms(stats.avg_ms))}</td>"
            f"<td>{'--' if stats.signal_pct is None else f'{stats.signal_pct:.0f}%'}</td>"
            f"<td>{stats.share_pct:.0f}%</td>"
            f"<td>{stats.roams}</td></tr>"
            for stats in links
        )
        body.append(
            "<table><thead><tr>"
            f"<th>{esc(tr('link.col_host'))}</th><th>{esc(tr('edge.col_avg'))}</th>"
            f"<th>{esc(tr('link.col_signal'))}</th><th>{esc(tr('edge.col_share'))}</th>"
            f"<th>{esc(tr('link.col_roams'))}</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if link_note:
        body.append(f'<p class="sub">{esc(link_note)}</p>')

    if len(signals) > 1:
        body.append(f"<h2>{esc(tr('signal.title'))}</h2>")
        rows = "".join(
            f"<tr><td>{esc(tr(stats.host))}</td>"
            f"<td>{esc(format_ms(stats.avg_ms))}</td>"
            f"<td>{'--' if stats.signal_pct is None else f'{stats.signal_pct:.0f}%'}</td>"
            f"<td>{stats.share_pct:.0f}%</td><td>{stats.stalls}</td></tr>"
            for stats in signals
        )
        body.append(
            "<table><thead><tr>"
            f"<th>{esc(tr('signal.col_when'))}</th><th>{esc(tr('edge.col_avg'))}</th>"
            f"<th>{esc(tr('link.col_signal'))}</th><th>{esc(tr('edge.col_share'))}</th>"
            f"<th>{esc(tr('edge.col_stalls'))}</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if signal_note:
        body.append(f'<p class="sub">{esc(signal_note)}</p>')

    if pattern_note:
        body.append(f"<h2>{esc(tr('pattern.title'))}</h2>")
        body.append(f'<div class="card"><p style="margin:0">{esc(pattern_note)}</p></div>')

    if actions:
        body.append(f"<h2>{esc(tr('action.title'))}</h2>")
        items = "".join(
            f"<li>{esc(tr(action.key))}"
            f"<div class='sub'>{esc(tr('action.because'))}: "
            f"{esc(tr(action.because_key, detail=action.detail) if action.because_key else '')}"
            f"</div></li>"
            for action in actions
        )
        body.append(f'<div class="card"><ol style="margin:0;padding-left:20px">{items}</ol>')
        if not has_local_cause(actions):
            body.append(f'<p class="sub" style="margin:10px 0 0">{esc(tr("action.not_yours"))}</p>')
        body.append("</div>")

    changes = comparison_rows(comparisons)
    if changes:
        rows = "".join(
            f'<tr><td class="n">{esc(when)}</td><td>{esc(label)}</td>'
            f'<td class="n">{esc(shift)}</td><td>{esc(verdict)}</td>'
            f'<td class="n">{esc(span)}</td></tr>'
            for when, label, shift, verdict, span in changes
        )
        body.append(f"<h2>{esc(tr('compare.title'))}</h2>")
        body.append(f'<div class="card"><table>{rows}</table>'
                    f'<p class="sub" style="margin:10px 0 0">{esc(tr("compare.hint"))}</p>'
                    "</div>")

    moves = switch_rows(switches)
    if moves:
        rows = "".join(
            f'<tr><td class="n">{esc(when)}</td><td>{esc(hosts)}</td>'
            f'<td class="n">{esc(saved)}</td></tr>'
            for when, hosts, saved in moves
        )
        body.append(f"<h2>{esc(tr('report.switches'))}</h2>")
        body.append(f'<div class="card"><table>{rows}</table>'
                    f'<p class="sub" style="margin:10px 0 0">{esc(tr("report.switches_hint"))}</p>'
                    "</div>")

    live_extras = [entry for entry in extras if entry is not None]
    if live_extras:
        rows = "".join(
            f"<tr><td>{esc(entry.label or entry.ident)}</td>"
            f'<td class="n">{esc(format_ms(entry.rtt_ms) if entry.ok else "--")}</td>'
            f"<td>{esc(entry.ident)}</td></tr>"
            for entry in live_extras
        )
        body.append(f"<h2>{esc(tr('report.extras'))}</h2>")
        body.append(f'<div class="card"><table>{rows}</table></div>')

    body.append(
        f'<footer>{esc(tr("report.privacy"))}<br>'
        f'{esc(APP_NAME)} {esc(__version__)} · <a href="{esc(REPO_URL)}">{esc(REPO_URL)}</a>'
        "</footer>"
    )

    return "\n".join(head + body + ["</main>", "</body>", "</html>", ""])


def build_text(*, summary: dict, worst: Optional[dict] = None, path_report=None,
               verdict_key: str = "", verdict_detail: str = "",
               target_label: str = "", auto_findings: Sequence = (),
               switches: Sequence = (), comparisons: Sequence = (), speed=None,
               edges: Sequence = (), edge_note: str = "", pattern_note: str = "",
               links: Sequence = (), link_note: str = "",
               signals: Sequence = (), signal_note: str = "",
               actions: Sequence = ()) -> str:
    """The same findings as something you can paste into a forum reply."""
    hours = summary.get("hours")
    window = tr("report.hours", n=int(hours)) if hours else tr("report.all")
    lines = [
        f"{tr('report.title')} · {APP_NAME} {__version__}",
        f"{tr('report.window')}: {window}  "
        f"({_fmt_time(summary.get('from'))} – {_fmt_time(summary.get('to'))})",
    ]
    label = target_label or summary.get("label", "")
    if label:
        lines.append(f"{tr('report.watching')}: {label}")
    lines.append("")
    width = max(_width(key) for key, _value in summary_rows(summary))
    for key, value in summary_rows(summary):
        lines.append(f"  {_pad(key, width)}  {value}")
    lines.append("")
    lines.append(f"{tr('report.worst')}: {worst_hour_line(worst)}")

    segments = segment_rows(path_report)
    if segments:
        lines.append("")
        lines.append(f"{tr('report.segments')}:")
        seg_width = max(_width(label) for label, _value, _host in segments)
        for seg_label, value, host in segments:
            suffix = f"  ({host})" if host else ""
            lines.append(f"  {_pad(seg_label, seg_width)}  {value}{suffix}")
    findings = finding_rows(auto_findings)
    if findings:
        lines.append("")
        lines.append(f"{tr('report.findings')}:")
        for when, what, _events in findings:
            lines.append(f"  {when}  {what}")

    if speed is not None and getattr(speed, "ok", False):
        lines.append("")
        lines.append(f"{tr('speed.title')}: {format_mbps(speed.mbps)}"
                     f"   {tr(tier_key(speed.mbps))}")
        lines.append(f"  {tr('speed.host')}: {speed.host}")

    if edges:
        lines.append("")
        lines.append(f"{tr('edge.title')}:")
        for stats in edges:
            lines.append(f"  {_pad(stats.host, 34)} {format_ms(stats.avg_ms):>9}"
                         f"   {stats.share_pct:4.0f}%   {cdn_summary(stats.host)}")
        if edge_note:
            lines.append(f"  {edge_note}")

    if links:
        lines.append("")
        lines.append(f"{tr('link.title')}:")
        for stats in links:
            signal = "--" if stats.signal_pct is None else f"{stats.signal_pct:.0f}%"
            lines.append(f"  {_pad(stats.host, 34)} {format_ms(stats.avg_ms):>9}"
                         f"   {stats.share_pct:4.0f}%   {signal:>5}"
                         f"   {tr('link.col_roams')} {stats.roams}")
    if link_note:
        lines.append(f"  {link_note}")

    if len(signals) > 1:
        lines.append("")
        lines.append(f"{tr('signal.title')}:")
        for stats in signals:
            pct = "--" if stats.signal_pct is None else f"{stats.signal_pct:.0f}%"
            lines.append(f"  {_pad(tr(stats.host), 12)} {format_ms(stats.avg_ms):>9}"
                         f"   {stats.share_pct:4.0f}%   {pct:>5}")
    if signal_note:
        lines.append(f"  {signal_note}")

    if pattern_note:
        lines.append("")
        lines.append(f"{tr('pattern.title')}: {pattern_note}")

    if actions:
        lines.append("")
        lines.append(f"{tr('action.title')}:")
        for index, action in enumerate(actions, 1):
            lines.append(f"  {index}. {tr(action.key)}")
            if action.because_key:
                lines.append(f"       ({tr('action.because')}: "
                             f"{tr(action.because_key, detail=action.detail)})")
        if not has_local_cause(actions):
            lines.append(f"  {tr('action.not_yours')}")

    changes = comparison_rows(comparisons)
    if changes:
        lines.append("")
        lines.append(f"{tr('compare.title')}:")
        for when, label, shift, verdict, span in changes:
            lines.append(f"  {when}  {label}".rstrip())
            lines.append(f"      {shift}   {verdict}   ({span})")

    moves = switch_rows(switches)
    if moves:
        lines.append("")
        lines.append(f"{tr('report.switches')}:")
        for when, hosts, saved in moves:
            lines.append(f"  {when}  {hosts}  {saved}".rstrip())

    if verdict_key:
        lines.append("")
        lines.append(f"=> {tr(verdict_key)}" + (f"  [{verdict_detail}]" if verdict_detail else ""))
    return "\n".join(lines)


def default_report_path(now: Optional[float] = None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now or time.time()))
    folder = app_config_dir() / "reports"
    return folder / f"lagscope-report-{stamp}.html"


def write_report(document: str, path: Optional[Path] = None) -> Path:
    """Write the HTML out, creating the reports folder if it is missing."""
    target = Path(path) if path is not None else default_report_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    return target
