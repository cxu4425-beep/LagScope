"""The always-on-top overlay window.

It is a frameless translucent widget that can sit anywhere: dragged freely,
pinned to a screen corner, or following the Bilibili window. It also doubles as
the display probe's frame source - every painted frame is timed, and short
bursts of frames are requested periodically to sample the compositor cadence
without repainting at 60 fps all day long.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from ..config import Config
from ..health import HEALTH, WINDOW
from ..i18n import tr
from ..models import KIND_APP, KIND_LIVE, KIND_TARGET, KIND_VIDEO, LatencySample, RollingStats
from ..probes.cdninfo import locate_line
from ..probes.display import DisplayProbe
from .anchor import (
    WindowFinder, WindowRect, clamp_to_rect, compute_anchor_position, create_window_finder,
)
from .theme import (
    Palette, color_for_level, format_mbps, format_mbps_short, format_ms, level_for,
    palette_for,
)

FRAME_BURST_INTERVAL_MS = 30_000
FRAME_BURST_COUNT = 24
FOLLOW_INTERVAL_MS = 500


class OverlayWindow(QWidget):
    positionChanged = Signal(int, int)
    contextMenuRequested = Signal(QPoint)
    doubleClicked = Signal()

    def __init__(self, config: Config, display_probe: DisplayProbe,
                 finder: Optional[WindowFinder] = None) -> None:
        super().__init__(None)
        self._config = config
        self._display = display_probe
        self._finder = finder or create_window_finder()
        self._sample: Optional[LatencySample] = None
        self._stats: Optional[RollingStats] = None
        self._status_text: str = tr("status.connecting")
        self._extras: list = []
        self._room_label: str = ""
        self._drag_offset: Optional[QPoint] = None
        self._burst_remaining = 0
        self._burst_started_at = 0.0

        self.setWindowTitle(tr("app.title"))
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        self.setContextMenuPolicy(Qt.PreventContextMenu)

        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._follow_window)

        self._burst_timer = QTimer(self)
        self._burst_timer.timeout.connect(self._start_frame_burst)
        self._burst_timer.start(FRAME_BURST_INTERVAL_MS)

        self.apply_config(config)

    # ------------------------------------------------------------------ config
    def apply_config(self, config: Config) -> None:
        self._config = config
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        if config.overlay.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        if config.overlay.click_through:
            flags |= Qt.WindowTransparentForInput
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setWindowOpacity(config.overlay.opacity)
        self._relayout()
        self.reposition()
        if was_visible:
            self.show()
        if config.overlay.anchor_mode == "window" and self._finder.available:
            self._follow_timer.start(FOLLOW_INTERVAL_MS)
        else:
            self._follow_timer.stop()
        self.update()

    def _scale(self) -> float:
        return max(0.6, min(3.0, self._config.overlay.scale))

    def _relayout(self) -> None:
        scale = self._scale()
        overlay = self._config.overlay
        width = 132 if overlay.compact else 226
        height = 56 if overlay.compact else 78
        if not overlay.compact:
            if overlay.show_server:
                height += 15
            if overlay.show_breakdown:
                height += 54
                # The headset row only exists once it has been calibrated, and
                # the box has to grow with it or the last line is clipped.
                # Driven from the config rather than the current sample so the
                # reserved height cannot disagree with what gets painted.
                if self._config.audio.measured:
                    height += 17
            if overlay.show_sparkline:
                height += 34
            if overlay.show_stats:
                height += 20
            if self._extras:
                height += 6 + 15 * len(self._extras)
        self.setFixedSize(int(width * scale), int(height * scale))

    # --------------------------------------------------------------- placement
    def reposition(self) -> None:
        overlay = self._config.overlay
        if overlay.anchor_mode == "window" and self._finder.available:
            self._follow_window()
            return
        if overlay.anchor_mode == "screen":
            rect = self._target_screen_rect()
            x, y = compute_anchor_position(
                rect, (self.width(), self.height()), overlay.corner, overlay.offset_x, overlay.offset_y
            )
            self.move(x, y)
            return
        x, y = clamp_to_rect((overlay.x, overlay.y), (self.width(), self.height()), self._nearest_screen_rect())
        self.move(x, y)

    def _target_screen_rect(self) -> WindowRect:
        name = self._config.overlay.screen_name
        for screen in QApplication.screens():
            if name and screen.name() == name:
                geo = screen.availableGeometry()
                return WindowRect(geo.x(), geo.y(), geo.width(), geo.height())
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        return WindowRect(geo.x(), geo.y(), geo.width(), geo.height())

    def _nearest_screen_rect(self) -> WindowRect:
        point = QPoint(self._config.overlay.x, self._config.overlay.y)
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        return WindowRect(geo.x(), geo.y(), geo.width(), geo.height())

    def _follow_window(self) -> None:
        overlay = self._config.overlay
        if not getattr(self._finder, "available", False):
            # Follow mode is on but this platform cannot list windows, so the
            # card will sit in a corner no matter what the setting says.
            HEALTH.degraded(WINDOW, "no window list on this platform")
            return
        rect = self._finder.find(overlay.follow_window_keyword)
        if rect is None:
            # Target not on screen right now: hold the last position.
            return
        x, y = compute_anchor_position(
            rect, (self.width(), self.height()), overlay.corner, overlay.offset_x, overlay.offset_y
        )
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ------------------------------------------------------------------- data
    def update_sample(self, sample: LatencySample, stats: RollingStats) -> None:
        self._sample = sample
        self._stats = stats
        self.update()

    def set_status(self, text: str) -> None:
        self._status_text = text
        self.update()

    def set_extras(self, extras: list) -> None:
        """The side watches shown under the main figure."""
        changed = len(extras) != len(self._extras)
        self._extras = list(extras)
        if changed:
            self._relayout()          # the card grows and shrinks with them
        self.update()

    def set_room_label(self, text: str) -> None:
        self._room_label = text
        self.update()

    # ------------------------------------------------------------ frame timing
    def _start_frame_burst(self) -> None:
        if not self.isVisible() or self._burst_remaining > 0:
            return
        self._burst_remaining = FRAME_BURST_COUNT
        self._queue_burst_frame()

    def _queue_burst_frame(self) -> None:
        if self._burst_remaining <= 0:
            return
        self._burst_started_at = time.perf_counter()
        QTimer.singleShot(0, self._burst_frame)

    def _burst_frame(self) -> None:
        lag_ms = (time.perf_counter() - self._burst_started_at) * 1000.0
        self._display.record_loop_lag(lag_ms)
        self._burst_remaining -= 1
        self.update()
        if self._burst_remaining > 0:
            self._queue_burst_frame()

    def _refresh_hz(self) -> Optional[float]:
        handle = self.windowHandle()
        screen = handle.screen() if handle is not None else QApplication.primaryScreen()
        if screen is None:
            return None
        rate = screen.refreshRate()
        return rate if rate and rate > 1 else None

    # ----------------------------------------------------------------- events
    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._display.refresh_hz = self._refresh_hz()
        QTimer.singleShot(300, self._start_frame_burst)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._burst_remaining = 0
        self._display.notify_hidden()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.RightButton:
            self.contextMenuRequested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._config.overlay.locked:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is None:
            return
        target = event.globalPosition().toPoint() - self._drag_offset
        self.move(target)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self.positionChanged.emit(self.x(), self.y())
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
            event.accept()

    # ---------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        self._display.record_frame()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        palette = palette_for(self._config.overlay.theme)
        scale = self._scale()

        self._paint_background(painter, palette, scale)
        if self._config.overlay.compact:
            self._paint_compact(painter, palette, scale)
        else:
            self._paint_full(painter, palette, scale)
        painter.end()

    def _paint_background(self, painter: QPainter, palette: Palette, scale: float) -> None:
        radius = 10.0 * scale
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QBrush(QColor(palette.background)))
        painter.setPen(QPen(QColor(palette.border), 1.0))
        painter.drawPath(path)

    def _total_level(self) -> str:
        value = self._sample.total_ms if (self._sample and self._sample.ok) else None
        return level_for(value, self._config.thresholds.good_ms, self._config.thresholds.warn_ms)

    def _font(self, size: float, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(6.0, size))
        font.setBold(bold)
        return font

    def _paint_compact(self, painter: QPainter, palette: Palette, scale: float) -> None:
        level = self._total_level()
        color = QColor(color_for_level(palette, level))
        value = self._sample.total_ms if (self._sample and self._sample.ok) else None
        painter.setFont(self._font(16 * scale, bold=True))
        painter.setPen(QPen(color))
        text_rect = QRect(0, int(6 * scale), self.width(), int(30 * scale))
        painter.drawText(text_rect, Qt.AlignCenter, format_ms(value))
        painter.setFont(self._font(7.5 * scale))
        painter.setPen(QPen(QColor(palette.muted)))
        painter.drawText(
            QRect(0, int(32 * scale), self.width(), int(18 * scale)),
            Qt.AlignCenter,
            self._subtitle(),
        )

    def _paint_full(self, painter: QPainter, palette: Palette, scale: float) -> None:
        pad = 12.0 * scale
        y = pad
        level = self._total_level()
        color = QColor(color_for_level(palette, level))

        # Header: status dot + app label + room
        dot = 7.0 * scale
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(pad, y + 2 * scale, dot, dot))
        painter.setPen(QPen(QColor(palette.muted)))
        painter.setFont(self._font(8 * scale, bold=True))
        header = self._header_text()
        painter.drawText(QRectF(pad + dot + 6 * scale, y - 2 * scale, self.width(), 16 * scale),
                         Qt.AlignLeft | Qt.AlignVCenter, header)
        if self._room_label:
            header_width = QFontMetrics(painter.font()).horizontalAdvance(header)
            painter.setFont(self._font(7.5 * scale))
            metrics = QFontMetrics(painter.font())
            # Video titles can be long; keep them inside the card.
            available = int(self.width() - pad * 2 - dot - header_width - 12 * scale)
            label = metrics.elidedText(self._room_label, Qt.ElideRight, max(24, available))
            painter.drawText(QRectF(0, y - 2 * scale, self.width() - pad, 16 * scale),
                             Qt.AlignRight | Qt.AlignVCenter, label)
        y += 16 * scale

        # Big number
        value = self._sample.total_ms if (self._sample and self._sample.ok) else None
        painter.setPen(QPen(color))
        painter.setFont(self._font(19 * scale, bold=True))
        painter.drawText(QRectF(pad, y, self.width() - pad * 2, 30 * scale),
                         Qt.AlignLeft | Qt.AlignVCenter, format_ms(value))
        painter.setPen(QPen(QColor(palette.muted)))
        painter.setFont(self._font(7.5 * scale))
        painter.drawText(QRectF(pad, y, self.width() - pad * 2, 30 * scale),
                         Qt.AlignRight | Qt.AlignVCenter, self._subtitle())
        y += 34 * scale

        if self._config.overlay.show_server:
            y = self._paint_server(painter, palette, scale, pad, y)
        if self._config.overlay.show_breakdown:
            y = self._paint_breakdown(painter, palette, scale, pad, y)
        if self._config.overlay.show_sparkline:
            y = self._paint_sparkline(painter, palette, scale, pad, y)
        if self._config.overlay.show_stats:
            y = self._paint_stats(painter, palette, scale, pad, y)
        if self._extras:
            self._paint_extras(painter, palette, scale, pad, y)

    def _subtitle(self) -> str:
        if self._sample is None:
            return self._status_text
        if not self._sample.ok:
            return self._status_text
        return tr("label.estimated") if self._sample.estimated else tr("label.measured")

    def _header_text(self) -> str:
        """The app is general purpose now: only say "B站" when that is what it is."""
        kind = self._sample.kind if self._sample else KIND_LIVE
        if kind in (KIND_LIVE, KIND_VIDEO):
            return tr("app.short")
        return tr("app.short_generic")

    def _breakdown_rows(self) -> list:
        """The detail lines, which say different things per target kind."""
        sample = self._sample
        kind = sample.kind if sample else KIND_LIVE
        network = format_ms(sample.network_ms if sample else None)
        display = format_ms(sample.display_ms if sample else None)
        # Screen to ears. Absent for everyone on a wired output rather than
        # shown as a permanent "--", which would be a row that never says
        # anything to most people.
        tail = ([(tr("label.audio"), format_ms(self._config.audio.offset_ms))]
                if self._config.audio.measured else [])

        if kind == KIND_APP:
            peers = str(sample.connections) if (sample and sample.connections) else "--"
            return [
                (tr("label.latency"), network),
                (tr("label.connections"), peers),
                (tr("label.display"), display),
            ] + tail
        if kind == KIND_TARGET:
            return [
                (tr("label.latency"), network),
                (tr("label.display"), display),
            ] + tail
        second = tr("label.startup") if kind == KIND_VIDEO else tr("label.stream")
        return [
            (tr("label.network"), network),
            (second, format_ms(sample.stream_ms if sample else None)),
            (tr("label.display"), display),
        ] + tail

    def _paint_server(self, painter: QPainter, palette: Palette, scale: float,
                      pad: float, y: float) -> float:
        """One line naming where the stream is coming from.

        Two sources, because neither covers everything: the hostname is exact
        when it says anything, and a cloud-rented node or a PCDN peer says
        nothing; the round trip sets a ceiling for every server alive. The
        ceiling only appears when it was measured against the edge itself and
        when it is narrow enough to be worth reading.
        """
        sample = self._sample
        row_height = 15 * scale
        painter.setFont(self._font(7.5 * scale))
        painter.setPen(QPen(QColor(palette.muted)))
        painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                         Qt.AlignLeft | Qt.AlignVCenter, tr("label.server"))

        text = ""
        if sample is not None and sample.host:
            text = locate_line(sample.host, sample.network_ms, sample.rtt_to_edge)
        if not text:
            text = tr("server.unknown")
        metrics = QFontMetrics(painter.font())
        label_width = metrics.horizontalAdvance(tr("label.server"))
        available = int(self.width() - pad * 2 - label_width - 10 * scale)
        painter.setPen(QPen(QColor(palette.foreground)))
        painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                         Qt.AlignRight | Qt.AlignVCenter,
                         metrics.elidedText(text, Qt.ElideMiddle, max(40, available)))
        return y + row_height

    def _paint_breakdown(self, painter: QPainter, palette: Palette, scale: float,
                         pad: float, y: float) -> float:
        painter.setFont(self._font(8 * scale))
        row_height = 17 * scale
        for label, value in self._breakdown_rows():
            painter.setPen(QPen(QColor(palette.muted)))
            painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.setPen(QPen(QColor(palette.foreground)))
            painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                             Qt.AlignRight | Qt.AlignVCenter, value)
            y += row_height
        return y + 3 * scale

    def _paint_sparkline(self, painter: QPainter, palette: Palette, scale: float,
                         pad: float, y: float) -> float:
        height = 26 * scale
        width = self.width() - pad * 2
        rect = QRectF(pad, y, width, height)
        painter.setPen(QPen(QColor(palette.border), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        points = self._stats.spark_values(48) if self._stats else []
        values = [v for v in points if v is not None]
        if len(values) >= 2:
            low, high = min(values), max(values)
            span = max(1.0, high - low)
            step = width / max(1, len(points) - 1)
            path = QPainterPath()
            started = False
            for index, value in enumerate(points):
                if value is None:
                    started = False
                    continue
                px = rect.left() + index * step
                py = rect.bottom() - ((value - low) / span) * (height - 2 * scale)
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            painter.setPen(QPen(QColor(palette.accent), max(1.0, 1.4 * scale)))
            painter.drawPath(path)
        return y + height + 4 * scale

    def _paint_stats(self, painter: QPainter, palette: Palette, scale: float,
                     pad: float, y: float) -> None:
        if self._stats is None:
            return
        parts = [
            f"{tr('label.avg')} {format_ms(self._stats.avg())}",
            f"{tr('label.p95')} {format_ms(self._stats.percentile(95))}",
            f"{tr('label.jitter')} {format_ms(self._stats.jitter())}",
        ]
        sample = self._sample
        if sample is not None and sample.throughput_mbps:
            # For a video, download speed is what decides whether it stalls.
            parts = parts[:2] + [f"{tr('label.speed')} {format_mbps(sample.throughput_mbps)}"]
        elif sample is not None and (sample.down_mbps is not None or sample.up_mbps is not None):
            # Otherwise show what the whole machine is pushing through the line.
            parts = parts[:1] + [
                f"↓{format_mbps_short(sample.down_mbps)}",
                f"↑{format_mbps_short(sample.up_mbps)}",
            ]
        text = "   ".join(parts)
        painter.setFont(self._font(7 * scale))
        painter.setPen(QPen(QColor(palette.muted)))
        metrics = QFontMetrics(painter.font())
        elided = metrics.elidedText(text, Qt.ElideRight, int(self.width() - pad * 2))
        painter.drawText(QRectF(pad, y, self.width() - pad * 2, 16 * scale),
                         Qt.AlignLeft | Qt.AlignVCenter, elided)
        return y + 16 * scale

    def _paint_extras(self, painter: QPainter, palette: Palette, scale: float,
                      pad: float, y: float) -> None:
        """One line per side watch: name on the left, its own colour on the right."""
        row_height = 15 * scale
        y += 4 * scale
        painter.setPen(QPen(QColor(palette.border), 1.0))
        painter.drawLine(pad, y, self.width() - pad, y)
        y += 2 * scale

        painter.setFont(self._font(7.5 * scale))
        metrics = QFontMetrics(painter.font())
        for extra in self._extras[:4]:
            value = format_ms(extra.rtt_ms) if extra.ok else "--"
            level = level_for(extra.rtt_ms if extra.ok else None,
                              self._config.thresholds.good_ms,
                              self._config.thresholds.warn_ms)
            value_width = metrics.horizontalAdvance(value)
            label = metrics.elidedText(
                extra.label, Qt.ElideRight,
                max(24, int(self.width() - pad * 2 - value_width - 10 * scale)),
            )
            painter.setPen(QPen(QColor(palette.muted)))
            painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.setPen(QPen(QColor(color_for_level(palette, level))))
            painter.drawText(QRectF(pad, y, self.width() - pad * 2, row_height),
                             Qt.AlignRight | Qt.AlignVCenter, value)
            y += row_height
