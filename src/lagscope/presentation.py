"""What a sample looks like to a person: the rows, the colour, the tooltip.

The overlay, the tray, the phone dashboard and the report all show the same
sample, and each used to decide on its own which rows to show and which
thresholds to colour it by. They drifted - the dashboard kept a display row the
overlay had dropped, the side watches were coloured on the stream scale - so the
decisions live here, once, with no Qt in sight.

Two families of number go through this, and they are not on the same scale:

* **Network latency** (the internet, an app's server, an address): a round
  trip, tens of milliseconds, the number ``ping`` prints. Shown as measured and
  coloured on a ping scale.
* **Stream delay** (a Bilibili live room or video): how far behind live the
  picture is, seconds, plus the estimated display and headphone delay because
  that is the delay a viewer actually experiences.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .i18n import tr
from .models import KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO
from .ui.theme import format_mbps, format_ms

NETWORK_KINDS = (KIND_NETWORK, KIND_APP, KIND_TARGET)
STREAM_KINDS = (KIND_LIVE, KIND_VIDEO)


def is_network_kind(kind: Optional[str]) -> bool:
    return kind in NETWORK_KINDS


def thresholds_for(thresholds, kind: Optional[str]) -> Tuple[float, float]:
    """``(good_ms, warn_ms)`` on the scale this kind of number lives on."""
    if kind in STREAM_KINDS:
        return float(thresholds.good_ms), float(thresholds.warn_ms)
    return float(thresholds.net_good_ms), float(thresholds.net_warn_ms)


def dominant_kind(buckets: Sequence) -> str:
    """The kind most of these recorded minutes were, for colouring a chart.

    Minutes recorded before the kind was kept count as live, which is the only
    thing they could have been.
    """
    counts: dict = {}
    for bucket in buckets or ():
        kind = getattr(bucket, "kind", "") or KIND_LIVE
        counts[kind] = counts.get(kind, 0) + 1
    if not counts:
        return KIND_NETWORK
    return max(counts.items(), key=lambda item: item[1])[0]


def level(value: Optional[float], thresholds, kind: Optional[str]) -> str:
    """``good`` / ``warn`` / ``bad`` / ``unknown`` on the right scale."""
    if value is None:
        return "unknown"
    good, warn = thresholds_for(thresholds, kind)
    if value <= good:
        return "good"
    if value <= warn:
        return "warn"
    return "bad"


def format_pct(value: Optional[float]) -> str:
    if value is None:
        return "--"
    if 0 < value < 1:
        return f"{value:.1f}%"
    return f"{value:.0f}%"


def loss_pct(stats) -> Optional[float]:
    """Share of recent rounds that got no answer at all, in percent."""
    if stats is None or not len(stats):
        return None
    return stats.failure_rate() * 100.0


def server_line(sample) -> str:
    """Which server the number is measured against, and how far away at most.

    The internet anchor is named ("Cloudflare 1.1.1.1") rather than shown as an
    address and port: "1.1.1.1:443" means nothing to most people, and the
    company running it is the part they would recognise. It gets no distance
    ceiling either: an anycast address is answered by whichever site is
    nearest, so "within 1,400 km" says nothing anyone would act on - and on a
    small card it pushed the name itself off the end.
    """
    from .probes.cdninfo import locate_line

    if sample is None or not sample.host:
        return ""
    if sample.kind == KIND_NETWORK and sample.title:
        return sample.title
    return locate_line(sample.host, sample.network_ms, sample.rtt_to_edge)


def breakdown_rows(sample, stats=None, audio_offset_ms: float = 0.0) -> List[tuple]:
    """The detail lines under the big number, per kind of target."""
    kind = sample.kind if sample else KIND_NETWORK
    if is_network_kind(kind):
        rows = []
        if kind == KIND_APP:
            peers = str(sample.connections) if (sample and sample.connections) else "--"
            rows.append((tr("label.connections"), peers))
        rows += [
            (tr("label.down"), format_mbps(sample.down_mbps if sample else None)),
            (tr("label.up"), format_mbps(sample.up_mbps if sample else None)),
            (tr("label.loss"), format_pct(loss_pct(stats))),
        ]
        return rows

    network = format_ms(sample.network_ms if sample else None)
    display = format_ms(sample.display_ms if sample else None)
    second = tr("label.startup") if kind == KIND_VIDEO else tr("label.stream")
    rows = [
        (tr("label.network"), network),
        (second, format_ms(sample.stream_ms if sample else None)),
        (tr("label.display"), display),
    ]
    # Screen to ears. Absent for everyone on a wired output rather than shown
    # as a permanent "--", a row that would never say anything to most people.
    if audio_offset_ms and audio_offset_ms > 0:
        rows.append((tr("label.audio"), format_ms(audio_offset_ms)))
    return rows


def tooltip(sample, status_text: str, stats=None, app_name: str = "",
            usage_line: str = "") -> str:
    """The tray icon's hover text, with today's data usage under it."""
    text = _tooltip(sample, status_text, stats, app_name)
    return f"{text}\n{usage_line}" if usage_line else text


def _tooltip(sample, status_text: str, stats=None, app_name: str = "") -> str:
    value = sample.total_ms if (sample and sample.ok) else None
    title = sample.title if (sample and sample.title) else app_name
    kind = sample.kind if sample else KIND_NETWORK
    if is_network_kind(kind):
        return tr(
            "tray.tooltip_net",
            title=title,
            total=format_ms(value),
            down=format_mbps(sample.down_mbps if sample else None),
            up=format_mbps(sample.up_mbps if sample else None),
            loss=format_pct(loss_pct(stats)),
            status=status_text,
        ).rstrip()
    fields = {
        "title": title,
        "total": format_ms(value),
        "network": format_ms(sample.network_ms if sample else None),
        "stream": format_ms(sample.stream_ms if sample else None),
        "display": format_ms(sample.display_ms if sample else None),
        "status": status_text,
    }
    if kind == KIND_VIDEO:
        fields["speed"] = format_mbps(sample.throughput_mbps if sample else None)
        return tr("tray.tooltip_video", **fields).rstrip()
    return tr("tray.tooltip", **fields).rstrip()


def speed_summary(report) -> str:
    """A speed test as plain lines - the CLI prints it, the dialog shows it."""
    from .probes.speed import tier_key

    lines = [tr("speed.result", value=format_mbps(report.mbps))]
    if report.upload is not None:
        lines.append(tr("speed.result_up", value=format_mbps(report.up_mbps))
                     if report.up_mbps is not None else tr("speed.up_failed"))
    if report.idle_ms is not None:
        lines.append(tr("speed.idle", value=format_ms(report.idle_ms)))
    if report.grade:
        lines.append(tr("speed.loaded", value=format_ms(report.idle_ms + report.bloat_ms),
                        grade=report.grade))
        lines.append(tr(f"speed.grade.{report.grade.replace('+', 'plus')}"))
    lines += ["", tr(tier_key(report.mbps)), "",
              tr("speed.source_stream") if report.source == "stream"
              else tr("speed.source_public"),
              tr("speed.cost", megabytes=f"{report.bytes / 1024 / 1024:.0f}",
                 seconds=f"{report.seconds:.0f}")]
    if not report.warmed:
        lines.append(tr("speed.short"))
    return "\n".join(lines)
