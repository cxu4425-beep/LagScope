"""Application wiring: overlay + tray + settings + monitoring thread."""

from __future__ import annotations

import copy
import json
import logging
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QMenu, QMessageBox, QProgressDialog,
    QSystemTrayIcon,
)

from . import APP_NAME, REPO_URL, __version__
from .autostart import get_autostart, is_supported as autostart_supported, set_autostart
from .config import Config, parse_room_id, app_config_dir
from .i18n import set_language, tr
from .events import STALL, EventLog, Notifier
from .history import History
from .models import (
    KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, LatencySample, RollingStats,
    WatchTarget,
)
from .monitor import (
    MonitorWorker, STATUS_ERROR, STATUS_NO_ROOM, STATUS_OFFLINE, STATUS_OK, STATUS_PAUSED,
)
from .probes.display import DisplayProbe
from .recording import CsvRecorder
from .report import (
    build_html, build_text, default_report_path, write_report,
)
from .single_instance import SingleInstance
from .update import RELEASES_PAGE, UpdateInfo, check as check_for_update
from .web import DashboardServer
from .ui.icons import app_icon
from .probes.speed import tier_key
from .ui.theme import format_mbps, format_ms, level_for
from .ui.overlay import OverlayWindow
from .ui.history_window import HistoryWindow
from .ui.settings import SettingsDialog
from .ui.wizard import SetupWizard
from .ui.tray import TrayIcon

LOG = logging.getLogger(__name__)

DISPLAY_PUSH_INTERVAL_MS = 1000
CONFIG_SAVE_DEBOUNCE_MS = 1500
CLIPBOARD_POLL_INTERVAL_MS = 1500
HISTORY_FLUSH_INTERVAL_MS = 60_000
# Probe error codes that have a sentence a person can act on.
ERROR_MESSAGES = {
    "no-connections": "status.no_connections",
    "no-reply": "status.no_reply",
    "unreachable": "status.unreachable",
    "no-app": "status.no_app",
    "no-video": "status.no_video",
    "no-room": "status.no_room",
}
MAX_CLIPBOARD_CHARS = 4096


class MonitorApplication(QObject):
    """Owns every long-lived object; one instance per process.

    Everything the worker must do is requested through these signals: the
    worker lives in another thread, and touching its timers directly from the
    GUI thread is not allowed by Qt.
    """

    configChanged = Signal(object)
    pauseRequested = Signal(bool)
    stopRequested = Signal()
    clipboardText = Signal(str)
    diagnosisRequested = Signal()
    quickCheckRequested = Signal()
    speedTestRequested = Signal()
    updateFound = Signal(object)      # UpdateInfo, from the checker thread

    def __init__(self, app: QApplication, config: Config,
                 instance: Optional[SingleInstance] = None) -> None:
        super().__init__()
        self._app = app
        self._config = config.sanitized()
        self._stats = RollingStats(self._config.sample_window)
        self._display = DisplayProbe()
        self._recorder: Optional[CsvRecorder] = None
        self._settings_dialog: Optional[SettingsDialog] = None
        self._status_key = STATUS_OK
        self._status_detail = ""
        self._paused = False
        self._room_title = ""
        self._target: Optional[WatchTarget] = None
        self._room_info = None
        self._lines: tuple = ("", [])
        self._events = EventLog()
        self._notifier = Notifier()
        self._extras: dict = {}      # key -> ExtraResult, newest per side watch
        self._dashboard: Optional[DashboardServer] = None
        self._history = History(bucket_s=self._config.history.bucket_s,
                                keep_hours=self._config.history.keep_hours)
        self._history_window: Optional[HistoryWindow] = None
        # Kept so an exported report carries the last check, not a blank section.
        self._last_diagnosis: Optional[tuple] = None
        self._last_auto_check = 0.0
        self._switches: list = []    # CDN edges moved to, newest last
        self._speed_running = False
        self._last_speed = None
        self._update_available: Optional[UpdateInfo] = None
        self._update_manual = False
        self._update_announced = False

        self._overlay = OverlayWindow(self._config, self._display)
        self._overlay.positionChanged.connect(self._on_overlay_moved)
        self._overlay.contextMenuRequested.connect(self._show_menu_at)
        self._overlay.doubleClicked.connect(self._toggle_compact)

        self._tray: Optional[TrayIcon] = None
        self._menu = QMenu()
        self._build_menu()
        self._setup_tray()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_config_now)

        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._push_display_latency)
        self._display_timer.start(DISPLAY_PUSH_INTERVAL_MS)

        # History is written once a minute, not once a sample: a crash costs
        # at most the minute in progress.
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._flush_history)
        self._history_timer.start(HISTORY_FLUSH_INTERVAL_MS)

        self._thread = QThread(self)
        # The worker gets its own copy: the GUI thread keeps mutating settings.
        self._worker = MonitorWorker(copy.deepcopy(self._config))
        self._worker.moveToThread(self._thread)
        self._worker.sampleReady.connect(self._on_sample)
        self._worker.statusChanged.connect(self._on_status)
        self._worker.roomInfoChanged.connect(self._on_room_info)
        self._worker.targetChanged.connect(self._on_target)
        self._worker.linesChanged.connect(self._on_lines)
        self._thread.started.connect(self._worker.start)
        self.configChanged.connect(self._worker.applyConfig)
        self.pauseRequested.connect(self._worker.setPaused)
        self.stopRequested.connect(self._worker.stop)
        self.clipboardText.connect(self._worker.submitClipboard)
        self.diagnosisRequested.connect(self._worker.runDiagnosis)
        self.quickCheckRequested.connect(self._worker.runQuickCheck)
        self._worker.quickCheckReady.connect(self._on_quick_check)
        self._worker.lineSwitched.connect(self._on_line_switch)
        self.speedTestRequested.connect(self._worker.runSpeedTest)
        self._worker.speedTestReady.connect(self._on_speed_test)
        self._worker.diagnosisReady.connect(self._on_diagnosis)
        self._worker.extraUpdated.connect(self._on_extra)

        # The clipboard belongs to the GUI thread, so it is polled here and the
        # text is handed to the worker, which does the parsing and any lookup.
        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.timeout.connect(self._poll_clipboard)
        self._last_clipboard = ""
        if self._config.detect.enabled and self._config.detect.use_clipboard:
            self._clipboard_timer.start(CLIPBOARD_POLL_INTERVAL_MS)

        self._instance = instance or SingleInstance()
        self._instance.setParent(self)
        self._instance.activated.connect(self._on_second_instance)

        self._apply_recording()
        self._apply_dashboard()
        app.aboutToQuit.connect(self._shutdown)

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if self._config.overlay.enabled:
            self._overlay.show()
        self._update_status_text()
        self._thread.start()
        self.updateFound.connect(self._on_update_found)
        self._start_update_check()

    def run_setup_if_needed(self) -> bool:
        """Ask the three first-run questions. True when the wizard ran."""
        if self._config.setup_done:
            return False
        wizard = SetupWizard(copy.deepcopy(self._config))
        wizard.exec()
        # Closing it with the window button still counts as answered: the
        # defaults it was showing are the ones that get saved.
        self.apply_config(wizard.apply_to(copy.deepcopy(self._config)))
        set_language(self._config.language)
        self._build_menu()
        if self._tray is not None:
            self._tray.set_menu(self._menu)
        return True

    def instance_guard(self) -> SingleInstance:
        return self._instance

    # ------------------------------------------------------------------- menu
    def _build_menu(self) -> None:
        self._menu.clear()

        self._action_overlay = QAction(tr("menu.show_overlay"), self._menu, checkable=True)
        self._action_overlay.setChecked(self._config.overlay.enabled)
        self._action_overlay.toggled.connect(self._set_overlay_visible)
        self._menu.addAction(self._action_overlay)

        self._action_lock = QAction(tr("menu.lock"), self._menu, checkable=True)
        self._action_lock.setChecked(self._config.overlay.locked)
        self._action_lock.toggled.connect(self._set_locked)
        self._menu.addAction(self._action_lock)

        self._action_click_through = QAction(tr("menu.click_through"), self._menu, checkable=True)
        self._action_click_through.setChecked(self._config.overlay.click_through)
        self._action_click_through.toggled.connect(self._set_click_through)
        self._menu.addAction(self._action_click_through)

        self._menu.addSeparator()

        self._action_detect = QAction(tr("menu.auto_detect"), self._menu, checkable=True)
        self._action_detect.setChecked(self._config.detect.enabled)
        self._action_detect.toggled.connect(self._set_auto_detect)
        self._menu.addAction(self._action_detect)

        diagnose_action = QAction(tr("menu.diagnose"), self._menu)
        diagnose_action.triggered.connect(self._run_diagnosis)
        self._menu.addAction(diagnose_action)

        history_action = QAction(tr("menu.history"), self._menu)
        history_action.triggered.connect(self.open_history)
        self._menu.addAction(history_action)

        report_action = QAction(tr("menu.report"), self._menu)
        report_action.triggered.connect(self.export_report)
        self._menu.addAction(report_action)

        speed_action = QAction(tr("menu.speedtest"), self._menu)
        speed_action.triggered.connect(self.run_speed_test)
        self._menu.addAction(speed_action)

        mark_action = QAction(tr("menu.mark"), self._menu)
        mark_action.triggered.connect(self.mark_moment)
        self._menu.addAction(mark_action)

        phone_action = QAction(tr("menu.phone"), self._menu)
        phone_action.triggered.connect(self._show_phone_url)
        self._menu.addAction(phone_action)

        clipboard_action = QAction(tr("menu.read_clipboard"), self._menu)
        clipboard_action.triggered.connect(self._read_clipboard_now)
        self._menu.addAction(clipboard_action)

        theme_menu = self._menu.addMenu(tr("overlay.theme"))
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        for theme in ("dark", "light", "pink"):
            action = QAction(tr(f"overlay.theme.{theme}"), theme_menu, checkable=True)
            action.setChecked(self._config.overlay.theme == theme)
            action.triggered.connect(lambda _checked, name=theme: self._set_theme(name))
            theme_group.addAction(action)
            theme_menu.addAction(action)

        self._action_pause = QAction(
            tr("menu.resume") if self._paused else tr("menu.pause"), self._menu, checkable=True
        )
        # Rebuilt on a language change: keep the current state without re-firing.
        self._action_pause.blockSignals(True)
        self._action_pause.setChecked(self._paused)
        self._action_pause.blockSignals(False)
        self._action_pause.toggled.connect(self._set_paused)
        self._menu.addAction(self._action_pause)

        reset_action = QAction(tr("menu.reset_position"), self._menu)
        reset_action.triggered.connect(self._reset_position)
        self._menu.addAction(reset_action)

        self._menu.addSeparator()

        settings_action = QAction(tr("menu.settings"), self._menu)
        settings_action.triggered.connect(self.open_settings)
        self._menu.addAction(settings_action)

        diag_action = QAction(tr("menu.copy_diag"), self._menu)
        diag_action.triggered.connect(self._copy_diagnostics)
        self._menu.addAction(diag_action)

        selftest_action = QAction(tr("menu.selftest"), self._menu)
        selftest_action.triggered.connect(self._run_selftest)
        self._menu.addAction(selftest_action)

        folder_action = QAction(tr("menu.open_config"), self._menu)
        folder_action.triggered.connect(self._open_config_folder)
        self._menu.addAction(folder_action)

        if self._update_available is not None:
            label = tr("update.available", version=self._update_available.version,
                       current=__version__)
        else:
            label = tr("menu.check_update")
        update_action = QAction(label, self._menu)
        update_action.triggered.connect(self._check_updates_now)
        self._menu.addAction(update_action)

        about_action = QAction(tr("menu.about"), self._menu)
        about_action.triggered.connect(self._show_about)
        self._menu.addAction(about_action)

        self._menu.addSeparator()
        quit_action = QAction(tr("menu.quit"), self._menu)
        quit_action.triggered.connect(self._app.quit)
        self._menu.addAction(quit_action)

    def _setup_tray(self) -> None:
        if not self._config.tray.enabled:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            LOG.warning("system tray not available")
            return
        self._tray = TrayIcon(self._config, self)
        self._tray.set_menu(self._menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._set_overlay_visible(not self._overlay.isVisible())
            self._action_overlay.setChecked(self._overlay.isVisible())

    def _show_menu_at(self, position) -> None:
        self._menu.popup(position)

    # ---------------------------------------------------------------- actions
    def _set_overlay_visible(self, visible: bool) -> None:
        self._config.overlay.enabled = bool(visible)
        if visible:
            self._overlay.show()
            self._overlay.reposition()
        else:
            self._overlay.hide()
        self._schedule_save()

    def _set_locked(self, locked: bool) -> None:
        self._config.overlay.locked = bool(locked)
        self._schedule_save()

    def _set_click_through(self, enabled: bool) -> None:
        self._config.overlay.click_through = bool(enabled)
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        self._schedule_save()

    def _set_theme(self, theme: str) -> None:
        self._config.overlay.theme = theme
        self._overlay.apply_config(self._config)
        if self._tray is not None:
            self._tray.apply_config(self._config)
        self._schedule_save()

    def _set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._action_pause.setText(tr("menu.resume") if paused else tr("menu.pause"))
        self.pauseRequested.emit(self._paused)
        self._update_status_text()

    def _set_auto_detect(self, enabled: bool) -> None:
        self._config.detect.enabled = bool(enabled)
        self.configChanged.emit(copy.deepcopy(self._config))
        self._schedule_save()

    def _toggle_compact(self) -> None:
        self._config.overlay.compact = not self._config.overlay.compact
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        self._schedule_save()

    def _reset_position(self) -> None:
        self._config.overlay.anchor_mode = "free"
        self._config.overlay.x = 80
        self._config.overlay.y = 80
        self._overlay.apply_config(self._config)
        self._overlay.show()
        self._schedule_save()

    def _on_overlay_moved(self, x: int, y: int) -> None:
        self._config.overlay.x = int(x)
        self._config.overlay.y = int(y)
        if self._config.overlay.anchor_mode != "free":
            self._config.overlay.anchor_mode = "free"
        self._schedule_save()

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self._config)
            self._settings_dialog.configApplied.connect(self.apply_config)
            self._settings_dialog.openConfigFolderRequested.connect(self._open_config_folder)
        else:
            self._settings_dialog.load_from(self._config)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _run_diagnosis(self) -> None:
        """Kick off the segment-by-segment check and tell the user to wait."""
        if self._tray is not None:
            self._tray.showMessage(tr("diag.title"), tr("diag.running"), app_icon(), 4000)
        self.diagnosisRequested.emit()

    @Slot(object)
    def _on_diagnosis(self, payload) -> None:
        if payload is None:
            QMessageBox.warning(None, tr("diag.title"), tr("verdict.unknown"))
            return
        report, key, detail = payload
        self._last_diagnosis = payload
        QMessageBox.information(None, tr("diag.title"), self._diagnosis_text(report, key, detail))

    def _diagnosis_text(self, report, key: str, detail: str) -> str:
        """The result as something a person can read - and paste to a helpdesk."""
        lines = [f"{tr('diag.title')}: {report.target}", ""]
        rows = [
            (tr("diag.you_router"), report.gateway_stats),
            (tr("diag.router_isp"), report.hop_stats),
            (tr("diag.to_target"), report.target_stats),
        ]
        for label, stats in rows:
            if stats is None:
                lines.append(f"{label}:  --")
            elif not stats.ok:
                lines.append(f"{label}:  {stats.error or '--'}  ({stats.host})")
            else:
                lines.append(
                    f"{label}:  {format_ms(stats.avg_ms)}   "
                    f"{tr('diag.loss')} {stats.loss_pct:.0f}%   ({stats.host})"
                )
        if report.dns_ms is not None:
            lines.append(f"{tr('diag.dns')}:  {format_ms(report.dns_ms)}")
        if report.wifi is not None:
            wifi = report.wifi
            signal = f"{wifi.signal_pct}%" if wifi.signal_pct is not None else "--"
            lines.append(f"\n{tr('diag.wifi')}: {wifi.ssid or '--'}  {signal}  {wifi.radio}")
        if "gateway-silent" in report.notes:
            lines.append(tr("diag.gateway_silent"))
        lines.append("")
        lines.append(tr(key) + (f"  [{detail}]" if detail else ""))
        return "\n".join(lines)

    # -------------------------------------------------------------- history
    def open_history(self) -> None:
        """The chart of everything recorded so far, kept live while it is open."""
        if self._history_window is None:
            self._history_window = HistoryWindow(self._config, self._history)
            self._history_window.exportRequested.connect(self.export_report)
            self._history_window.copyRequested.connect(self._copy_report_summary)
            self._history_window.markRequested.connect(self.mark_moment)
            # The window asks for the analysis rather than being handed a
            # snapshot, so it stays current as the range buttons change.
            self._history_window.set_analysis_provider(self._analysis)
        else:
            self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    # --------------------------------------------------------- speed test
    def run_speed_test(self) -> None:
        """Ask before starting: this one deliberately hurts while it runs."""
        if self._speed_running:
            return
        answer = QMessageBox.question(
            None, tr("speed.title"),
            tr("speed.confirm", seconds=self._config.speed.budget_s,
               megabytes=self._config.speed.max_mb),
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Ok,
        )
        if answer != QMessageBox.Ok:
            return
        self._speed_running = True
        # Marked before it starts: the latency spike it is about to cause is
        # this app's own doing, and the history should say so rather than
        # leaving a mysterious red tick for someone to worry about later.
        if self._config.history.enabled:
            self._history.mark(tr("speed.marker"))
        if self._tray is not None:
            self._tray.showMessage(tr("speed.title"), tr("speed.running"), app_icon(), 4000)
        self.speedTestRequested.emit()

    @Slot(object)
    def _on_speed_test(self, result) -> None:
        self._speed_running = False
        if result is None:
            return
        self._last_speed = result
        self._flush_history()
        if self._history_window is not None and self._history_window.isVisible():
            self._history_window.refresh()
        QMessageBox.information(None, tr("speed.title"), self._speed_text(result))

    def _speed_text(self, result) -> str:
        """The number, what it can carry, and what it cost to find out."""
        if not result.ok:
            return f"{tr('speed.failed')}\n{result.error or ''}".strip()
        lines = [
            f"{tr('speed.result', value=format_mbps(result.mbps))}",
            "",
            tr(tier_key(result.mbps)),
            "",
            tr("speed.source_stream") if result.source == "stream"
            else tr("speed.source_public"),
            tr("speed.cost", megabytes=f"{result.bytes / 1024 / 1024:.0f}",
               seconds=f"{result.seconds:.0f}"),
        ]
        if not result.warmed:
            lines.append(tr("speed.short"))
        return "\n".join(lines)

    def mark_moment(self) -> None:
        """Record "I changed something", so the effect can be measured later."""
        label, accepted = QInputDialog.getText(
            None, tr("compare.dialog"), tr("compare.prompt")
        )
        if not accepted:
            return
        self._history.mark(label)
        self._flush_history()
        if self._history_window is not None and self._history_window.isVisible():
            self._history_window.refresh()
        if self._tray is not None:
            self._tray.showMessage(tr("compare.dialog"), tr("compare.marked"),
                                   app_icon(), 6000)

    def _comparisons(self, hours) -> list:
        """Each marked moment with its before-and-after, newest first."""
        entries = []
        for marker in self._history.markers(hours):
            entries.append({"label": marker["label"],
                            "compare": self._history.compare(marker["ts"])})
        entries.reverse()
        return entries

    def _report_context(self) -> dict:
        """Everything the report needs, gathered from what is already known."""
        hours = 24.0
        if self._history_window is not None:
            hours = self._history_window.hours()
        path_report, verdict_key, verdict_detail = (self._last_diagnosis
                                                    or (None, "", ""))
        return {
            "buckets": self._history.buckets(hours),
            "summary": self._history.summary(hours),
            "bucket_s": self._history.bucket_s,
            "worst": self._history.worst_hour(hours),
            "path_report": path_report,
            "verdict_key": verdict_key,
            "verdict_detail": verdict_detail,
            "extras": self._ordered_extras(),
            "auto_findings": self._history.findings(hours),
            "switches": list(reversed(self._switches)),
            "comparisons": self._comparisons(hours),
            "speed": self._last_speed,
            **self._pattern_context(hours, verdict_key),
            "target_label": self._room_title or self._watch_label(),
            "good_ms": self._config.thresholds.good_ms,
            "warn_ms": self._config.thresholds.warn_ms,
        }

    def _watch_label(self) -> str:
        target = self._target
        if target is None or target.is_empty:
            return ""
        return target.title or target.ident

    def export_report(self) -> None:
        """Write the health report and open it in the browser."""
        self._flush_history()
        context = self._report_context()
        document = build_html(**context)
        try:
            path = write_report(document, default_report_path())
        except OSError as exc:
            LOG.warning("could not write the report: %s", exc)
            QMessageBox.warning(None, tr("report.title"), f"{tr('report.failed')}\n{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if self._tray is not None:
            self._tray.showMessage(tr("report.title"), f"{tr('report.saved')} {path}",
                                   app_icon(), 6000)

    def _copy_report_summary(self) -> None:
        """The same findings as text, for a forum reply or a chat message."""
        context = self._report_context()
        QGuiApplication.clipboard().setText(build_text(
            summary=context["summary"], worst=context["worst"],
            path_report=context["path_report"], verdict_key=context["verdict_key"],
            verdict_detail=context["verdict_detail"], target_label=context["target_label"],
            auto_findings=context["auto_findings"], switches=context["switches"],
            comparisons=context["comparisons"], speed=context["speed"],
            edges=context["edges"], edge_note=context["edge_note"],
            edges_comparable=context["edges_comparable"],
            links=context["links"], link_note=context["link_note"],
            signals=context["signals"], signal_note=context["signal_note"],
            pattern_note=context["pattern_note"], actions=context["actions"],
        ))
        if self._tray is not None:
            self._tray.showMessage(tr("report.title"), tr("report.copied"), app_icon(), 4000)

    def _flush_history(self) -> None:
        if self._config.history.enabled:
            self._history.flush()

    # ------------------------------------------------------------- updates
    def _start_update_check(self, manual: bool = False) -> None:
        """Ask GitHub for the newest tag, off the GUI thread.

        A plain thread rather than the worker: it must not sit in front of a
        measurement, and it has nothing to do with monitoring.
        """
        if not manual and not self._config.updates.enabled:
            return
        config = self._config.updates
        last_checked = 0.0 if manual else config.last_checked
        skip = "" if manual else config.skip_version

        def run() -> None:
            found = check_for_update(__version__, last_checked, skip)
            # Emitted either way: a manual check has to say "you are up to date".
            self.updateFound.emit(found if found is not None else (None if not manual else False))

        threading.Thread(target=run, name="lagscope-update", daemon=True).start()

    @Slot(object)
    def _on_update_found(self, found) -> None:
        if found is None:
            return
        self._config.updates.last_checked = time.time()
        self._schedule_save()
        if found is False:                     # a manual check that found nothing
            QMessageBox.information(None, tr("update.group"), tr("update.none"))
            return
        if not isinstance(found, UpdateInfo):
            return
        self._update_available = found
        self._build_menu()
        if self._tray is not None:
            self._tray.set_menu(self._menu)
        if self._update_manual:
            self._update_manual = False
            self._offer_update(found)
        elif self._tray is not None and not self._update_announced:
            # Never a modal dialog on its own initiative: this app runs behind
            # fullscreen games. A balloon, and a menu entry that stays put.
            self._update_announced = True
            self._tray.showMessage(
                tr("update.group"),
                tr("update.available", version=found.version, current=__version__),
                app_icon(), 8000,
            )

    def _offer_update(self, found: UpdateInfo) -> None:
        """The dialog - with "install it" first, when that is actually safe."""
        from .selfupdate import can_self_update

        asset = found.installer
        installable = can_self_update(asset)

        box = QMessageBox(QMessageBox.Information, tr("update.group"),
                          tr("update.available", version=found.version, current=__version__))
        install_button = None
        if installable:
            box.setInformativeText(tr("update.install_hint", megabytes=max(1, asset.size // (1024 * 1024))))
            install_button = box.addButton(tr("update.install"), QMessageBox.AcceptRole)
        open_button = box.addButton(tr("update.open"), QMessageBox.AcceptRole)
        skip_button = box.addButton(tr("update.skip"), QMessageBox.DestructiveRole)
        box.addButton(tr("update.later"), QMessageBox.RejectRole)
        if install_button is not None:
            box.setDefaultButton(install_button)
        box.exec()
        if install_button is not None and box.clickedButton() is install_button:
            self._install_update(asset)
        elif box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl(found.url))
        elif box.clickedButton() is skip_button:
            self._config.updates.skip_version = found.version
            self._update_available = None
            self._build_menu()
            if self._tray is not None:
                self._tray.set_menu(self._menu)
            self._schedule_save()

    def _install_update(self, asset) -> None:
        """Download it, check it, run it, and get out of its way.

        The progress dialog is modal on purpose: this ends with the app
        quitting, and starting something else in the meantime would only be
        interrupted a few seconds later.
        """
        from .selfupdate import download, launch_installer

        progress = QProgressDialog(tr("update.downloading"), tr("button.cancel"),
                                   0, 100, None)
        progress.setWindowTitle(tr("update.group"))
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setValue(0)

        state = {"result": None, "done": 0, "total": asset.size or 0}

        def work():
            def report(done, total):
                state["done"], state["total"] = done, total

            state["result"] = download(asset, on_progress=report,
                                       cancelled=progress.wasCanceled)

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while thread.is_alive():
            if state["total"]:
                progress.setValue(int(state["done"] * 100 / state["total"]))
            QApplication.processEvents()
            thread.join(0.05)
        progress.close()

        result = state["result"]
        if result is None or not result.ok:
            reason = "" if result is None else result.error
            if reason == "cancelled":
                return
            # Anything that failed verification is a reason to send them to the
            # page, never a reason to run the file anyway.
            QMessageBox.warning(None, tr("update.group"),
                                tr("update.install_failed", reason=reason or "unknown"))
            QDesktopServices.openUrl(QUrl(self._update_available.url
                                          if self._update_available else RELEASES_PAGE))
            return

        if not launch_installer(result.path):
            QMessageBox.warning(None, tr("update.group"),
                                tr("update.install_failed", reason="launch"))
            return
        # Windows cannot replace a running executable, so leaving now is not
        # politeness - it is what makes the install possible.
        # aboutToQuit runs _shutdown, which closes the history file and drops
        # the mutex the installer is about to look for.
        self._app.quit()

    def _check_updates_now(self) -> None:
        """The tray menu asked, so an answer either way is expected."""
        if self._update_available is not None:
            self._offer_update(self._update_available)
            return
        self._update_manual = True
        self._start_update_check(manual=True)

    # ------------------------------------------------- automatic path checks
    @Slot(object)
    def _on_quick_check(self, payload) -> None:
        """File what the unattended check blamed against the minute it ran in."""
        if not payload or not self._config.history.enabled:
            return
        ts, key, detail = payload
        self._history.note_verdict(key, detail, ts)
        if self._history_window is not None and self._history_window.isVisible():
            self._history_window.refresh()

    @Slot(object)
    def _on_line_switch(self, switch) -> None:
        """A faster CDN edge was picked: note it, quietly.

        No balloon: this happens on its own, and a notification for something
        the user did not ask for and cannot act on is just noise. It is not
        filed in the history either - that section answers "why did it stall",
        and a switch is the opposite of a problem. The report lists them
        separately, and the drop it caused is already visible on the chart.
        """
        if switch is None:
            return
        self._switches.append(switch)
        del self._switches[:-20]

    def _maybe_auto_check(self) -> None:
        """Run one background check per cooldown, when something breaks."""
        history = self._config.history
        if not (history.enabled and history.auto_check):
            return
        now = time.monotonic()
        if self._last_auto_check and now - self._last_auto_check < history.auto_check_cooldown_s:
            return
        self._last_auto_check = now
        self.quickCheckRequested.emit()

    def _show_phone_url(self) -> None:
        """Show (and copy) the address to type into a phone browser."""
        if self._dashboard is None:
            QMessageBox.information(None, tr("web.group"), tr("web.off"))
            return
        urls = self._dashboard.urls()
        if not urls:
            QMessageBox.information(None, tr("web.group"), tr("web.off"))
            return
        QGuiApplication.clipboard().setText(urls[0])
        QMessageBox.information(
            None, tr("web.group"),
            f"{tr('web.url_label')}\n\n" + "\n".join(urls) + f"\n\n{tr('web.copied')}",
        )

    def _analysis(self, hours) -> dict:
        """The edge/pattern/action analysis, from wherever it is asked for.

        The window and the exported report go through this same call, so what
        someone reads on screen cannot drift from what they send to support.
        """
        _report, verdict_key, _detail = self._last_diagnosis or (None, "", "")
        return self._pattern_context(hours, verdict_key)

    def _pattern_context(self, hours, verdict_key: str = "") -> dict:
        """Which edges served you, when it was bad, and what to try about it."""
        from .actions import suggest
        from .patterns import (by_edge, by_link, by_period, by_signal,
                               edge_verdict, edges_are_comparable, hour_ranges,
                               signal_note_key)
        from .probes.cdninfo import describe

        buckets = self._history.buckets(hours)
        edges = by_edge(buckets)
        # Watching an application, the hosts are whatever it talked to - not
        # alternatives to one another. Ranking them and advising a reassignment
        # would be advice about a choice nobody has.
        comparable = edges_are_comparable(buckets)
        verdict = edge_verdict(edges) if comparable else None

        note = ""
        if not comparable:
            # With one host there is nothing anyone would have tried to
            # compare, so the explanation would be answering an unasked
            # question.
            note = tr("edge.not_comparable") if len(edges) > 1 else ""
        elif verdict.key == "edge.differs" and verdict.worst and verdict.best:
            note = tr("edge.differs", worst=verdict.worst.host, best=verdict.best.host,
                      diff=f"{verdict.difference_ms:.0f}", share=f"{verdict.worst.share_pct:.0f}")
        elif verdict is not None and verdict.key:
            note = tr(verdict.key)

        # The same comparison for the wireless network. Separate from the edge
        # one because the conclusions differ in kind: which CDN node you were
        # handed is not yours to choose, and which Wi-Fi you are on is.
        links = by_link(buckets)
        link_verdict = edge_verdict(links, prefix="link")
        link_note = ""
        if link_verdict.key == "link.differs" and link_verdict.worst and link_verdict.best:
            link_note = tr("link.differs",
                           worst=link_verdict.worst.host, best=link_verdict.best.host,
                           diff=f"{link_verdict.difference_ms:.0f}",
                           share=f"{link_verdict.worst.share_pct:.0f}")
        elif not links:
            # No wireless recorded at all is a fact about the machine, not a
            # gap in the data - so say which it is rather than "not enough".
            link_note = tr("link.none")
        elif link_verdict.key:
            link_note = tr(link_verdict.key)

        # Most homes have one wireless network, so by_link has nothing to
        # compare - but the same rows still hold a comparison worth making.
        signals = by_signal(buckets)
        signal_verdict = edge_verdict(signals, prefix="signal")
        signal_note = ""
        if signal_verdict.key == "signal.differs" and signal_verdict.worst:
            signal_note = tr("signal.differs",
                             diff=f"{signal_verdict.difference_ms:.0f}",
                             share=f"{signal_verdict.worst.share_pct:.0f}")
        elif signals and signal_verdict.key:
            # "Only one band" means two opposite things - strong throughout is
            # good news, weak throughout is the answer by itself.
            key = signal_note_key(signal_verdict)
            best = signal_verdict.best
            signal_note = (tr(key, pct=f"{(best.signal_pct or 0):.0f}")
                           if key == "signal.always_weak" and best else tr(key))

        pattern = by_period(buckets)
        pattern_note = ""
        if pattern.has_pattern and pattern.worst:
            when = "、".join(
                tr("pattern.range", start=f"{start:02d}", end=f"{end:02d}")
                for start, end in hour_ranges(pattern.worst_hours)
            )
            pattern_note = tr("pattern.found", when=when,
                              bad=f"{pattern.worst.avg_ms:.0f}",
                              overall=f"{pattern.overall_ms:.0f}")
        elif pattern.key:
            pattern_note = tr(pattern.key)

        summary = self._history.summary(hours)
        current = self._monitor_wifi()
        return {
            "edges": edges,
            "edge_note": note,
            "edges_comparable": comparable,
            "links": links,
            "link_note": link_note,
            "signals": signals,
            "signal_note": signal_note,
            "pattern_note": pattern_note,
            "actions": suggest(
                edge_verdict=verdict,   # None when they are not alternatives
                pattern=pattern,
                verdict_key=verdict_key,
                peer_hosts=[stats.host for stats in edges
                            if describe(stats.host).is_peer],
                loss_pct=summary.get("loss_pct"),
                speed_mbps=self._last_speed.mbps if self._last_speed else None,
                switches=len(self._switches or ()),
                link_verdict=link_verdict,
                roams=sum(getattr(b, "roams", 0) for b in buckets),
                band=current,
                bluetooth_ms=self._config.audio.offset_ms,
                signal_verdict=signal_verdict,
            ),
        }

    def _monitor_wifi(self) -> str:
        """The band in use right now, for advice that is about right now.

        Read off the most recent minute rather than by asking the adapter
        again: the history already has it, and a second subprocess to learn
        something already written down would be waste.
        """
        for bucket in reversed(self._history.buckets(1) or ()):
            link = getattr(bucket, "link", "") or ""
            if "2.4" in link:
                return "2.4"
            if link:
                return "5" if "5 GHz" in link else ""
        return ""

    def _run_selftest(self) -> None:
        """The command-line self-test, without the command line.

        Every Bilibili path in this app is tested against fixtures only, so a
        report from a real machine is the only evidence that any of it still
        works. Requiring a terminal to produce that was the reason it never
        got produced.
        """
        from .selftest import format_report, run

        progress = QProgressDialog(tr("selftest.running"), "", 0, 0, None)
        progress.setWindowTitle(tr("selftest.title"))
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.show()

        room = ""
        if self._target is not None and self._target.kind == "room":
            room = str(self._target.ident or "")
        if not room:
            # Without a room, the four checks that matter most - play URLs,
            # the live measurement, the CDN comparison - all skip, and the
            # report then tells a GUI user to go and use a command line. Ask
            # instead; this button exists so that is never the answer.
            entered, accepted = QInputDialog.getText(
                None, tr("selftest.title"), tr("selftest.ask_room"))
            if not accepted:
                return
            room = parse_room_id(entered)
        state = {"text": ""}

        def work():
            try:
                state["text"] = format_report(run(self._config, room=room))
            except Exception as exc:                  # noqa: BLE001 - report it
                state["text"] = f"self-test failed: {exc}"

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while thread.is_alive():
            QApplication.processEvents()
            thread.join(0.05)
        progress.close()

        QGuiApplication.clipboard().setText(state["text"])
        box = QMessageBox(QMessageBox.Information, tr("selftest.title"),
                          tr("selftest.done"))
        box.setInformativeText(tr("selftest.privacy"))
        box.setDetailedText(state["text"])
        box.exec()

    def _copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(self.diagnostics_text())
        if self._tray is not None:
            self._tray.showMessage(APP_NAME, tr("notice.copied"), app_icon(), 3000)

    def _open_config_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_config_dir())))

    def _show_about(self) -> None:
        QMessageBox.information(
            None,
            f"{APP_NAME} {__version__}",
            f"{tr('about.body')}\n\n{REPO_URL}\n{app_config_dir()}",
        )

    # ----------------------------------------------------------------- config
    @Slot(object)
    def apply_config(self, config: Config) -> None:
        previous_language = self._config.language
        previous_autostart = self._config.autostart
        self._config = config.sanitized()

        if self._config.language != previous_language:
            set_language(self._config.language)
            self._build_menu()
            if self._tray is not None:
                self._tray.set_menu(self._menu)
            if self._settings_dialog is not None:
                self._settings_dialog.deleteLater()
                self._settings_dialog = None
            # Its labels are built once, so it is rebuilt in the new language too.
            if self._history_window is not None:
                self._history_window.deleteLater()
                self._history_window = None

        self._stats.resize(self._config.sample_window)
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        else:
            self._overlay.hide()
        self._action_overlay.setChecked(self._config.overlay.enabled)
        self._action_lock.setChecked(self._config.overlay.locked)
        self._action_click_through.setChecked(self._config.overlay.click_through)
        self._action_detect.blockSignals(True)
        self._action_detect.setChecked(self._config.detect.enabled)
        self._action_detect.blockSignals(False)

        if self._config.tray.enabled and self._tray is None:
            self._setup_tray()
        elif self._tray is not None:
            self._tray.apply_config(self._config)
            self._tray.setVisible(self._config.tray.enabled)

        if self._config.autostart != previous_autostart and autostart_supported():
            if not set_autostart(self._config.autostart):
                self._config.autostart = bool(get_autostart())

        if self._config.detect.enabled and self._config.detect.use_clipboard:
            if not self._clipboard_timer.isActive():
                self._clipboard_timer.start(CLIPBOARD_POLL_INTERVAL_MS)
        else:
            self._clipboard_timer.stop()

        self._prune_extras()
        self._overlay.set_extras(self._ordered_extras())
        self._apply_recording()
        self._apply_history()
        self._apply_dashboard()
        self.configChanged.emit(copy.deepcopy(self._config))
        self._save_config_now()
        self._update_status_text()

    def _apply_dashboard(self) -> None:
        """Start, restart or stop the phone dashboard to match the settings."""
        web = self._config.web
        if self._dashboard is not None:
            same = (self._dashboard.port == web.port
                    and self._dashboard.access_code == web.access_code
                    and self._dashboard.bind_host == web.bind_host)
            if web.enabled and same:
                return
            self._dashboard.stop()
            self._dashboard = None
        if not web.enabled:
            return
        server = DashboardServer(web.port, web.access_code, web.bind_host)
        if server.start():
            self._dashboard = server
            self._publish_dashboard()
        else:
            LOG.warning("phone dashboard could not start on port %s", web.port)

    def _publish_dashboard(self) -> None:
        """Hand the current state to the dashboard in ready-to-render form."""
        if self._dashboard is None:
            return
        sample = self._stats.last()
        kind = sample.kind if sample else KIND_LIVE
        value = sample.total_ms if (sample and sample.ok) else None
        level = level_for(value, self._config.thresholds.good_ms,
                          self._config.thresholds.warn_ms)

        if kind == KIND_APP:
            rows = [
                (tr("label.latency"), format_ms(sample.network_ms if sample else None)),
                (tr("label.connections"), str(sample.connections) if sample and sample.connections else "--"),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]
        elif kind == KIND_TARGET:
            rows = [
                (tr("label.latency"), format_ms(sample.network_ms if sample else None)),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]
        else:
            second = tr("label.startup") if kind == KIND_VIDEO else tr("label.stream")
            rows = [
                (tr("label.network"), format_ms(sample.network_ms if sample else None)),
                (second, format_ms(sample.stream_ms if sample else None)),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]

        if self._config.audio.measured:
            rows.append((tr("label.audio"), format_ms(self._config.audio.offset_ms)))
        if sample is not None and sample.host:
            from .probes.cdninfo import locate_line

            rows.append((tr("label.server"),
                         locate_line(sample.host, sample.network_ms, sample.rtt_to_edge)))

        events = self._events.summary()
        stats = [
            (tr("label.avg"), format_ms(self._stats.avg())),
            (tr("label.p95"), format_ms(self._stats.percentile(95))),
            (tr("label.down"), format_mbps(sample.down_mbps if sample else None)),
            (tr("label.up"), format_mbps(sample.up_mbps if sample else None)),
        ]
        self._dashboard.publish({
            "ok": bool(sample and sample.ok),
            "total_ms": value,
            "level": level,
            "status": self._status_line() or (
                tr("label.measured") if (sample and not sample.estimated) else tr("label.estimated")
            ),
            "target": self._room_title or (sample.title if sample else ""),
            "rows": rows,
            "stats": stats,
            "spark": self._stats.spark_values(60),
            "extras": [
                {
                    "label": extra.label,
                    "value": format_ms(extra.rtt_ms) if extra.ok else "--",
                    "level": level_for(extra.rtt_ms if extra.ok else None,
                                       self._config.thresholds.good_ms,
                                       self._config.thresholds.warn_ms),
                }
                for extra in self._ordered_extras()
            ],
            "measured": bool(sample and not sample.estimated),
            "foot": f"{APP_NAME} {__version__} · {tr('label.jitter')} "
                    f"{format_ms(self._stats.jitter())} · "
                    f"{events['stalls'] + events['spikes']} / {events['window_min']}min",
        })

    def _apply_history(self) -> None:
        """Follow a changed retention setting without losing what is stored."""
        history = self._config.history
        if history.keep_hours != self._history.keep_hours or \
                history.bucket_s != self._history.bucket_s:
            self._history.close()
            self._history = History(bucket_s=history.bucket_s, keep_hours=history.keep_hours)
            if self._history_window is not None:
                self._history_window.deleteLater()
                self._history_window = None
        if not history.enabled:
            self._history.flush()
        if self._history_window is not None:
            self._history_window.apply_config(self._config)

    def _apply_recording(self) -> None:
        if self._config.recording.csv_enabled:
            if self._recorder is None:
                self._recorder = CsvRecorder(
                    max_bytes=self._config.recording.csv_max_bytes,
                    backups=self._config.recording.csv_backups,
                )
        elif self._recorder is not None:
            self._recorder.close()
            self._recorder = None

    def _schedule_save(self) -> None:
        self._save_timer.start(CONFIG_SAVE_DEBOUNCE_MS)

    def _save_config_now(self) -> None:
        try:
            self._config.save()
        except OSError as exc:
            LOG.warning("could not save config: %s", exc)

    # ------------------------------------------------------------------ data
    @Slot(object)
    def _on_extra(self, result) -> None:
        self._extras[result.key] = result
        self._prune_extras()
        self._overlay.set_extras(self._ordered_extras())
        self._publish_dashboard()

    def _prune_extras(self) -> None:
        """Forget watches the user has removed from the settings."""
        wanted = {
            f"{entry.get('kind', 'target')}:{str(entry.get('ident', '')).lower()}:"
            f"{entry.get('port') if entry.get('kind', 'target') == KIND_TARGET else ''}"
            for entry in self._config.watch_extras
        }
        for key in list(self._extras):
            if key not in wanted:
                self._extras.pop(key, None)

    def _ordered_extras(self) -> list:
        """In the order the user arranged them, not the order they answered."""
        ordered = []
        for entry in self._config.watch_extras:
            kind = entry.get("kind", "target")
            port = entry.get("port") if kind == KIND_TARGET else ""
            key = f"{kind}:{str(entry.get('ident', '')).lower()}:{port}"
            result = self._extras.get(key)
            if result is not None:
                ordered.append(result)
        return ordered

    @Slot(object)
    def _on_lines(self, payload) -> None:
        self._lines = payload

    @Slot(object)
    def _on_sample(self, sample: LatencySample) -> None:
        event = self._events.observe(sample)
        if event is not None:
            self._announce(event)
        self._stats.append(sample)
        if self._config.history.enabled:
            self._history.add(sample)
            if event is not None:
                self._history.note_event(event.kind)
            if self._history_window is not None and self._history_window.isVisible():
                self._history_window.refresh()
        self._overlay.update_sample(sample, self._stats)
        if self._tray is not None:
            self._tray.update_sample(sample, self._status_line())
        if self._recorder is not None:
            self._recorder.write(sample)
        self._publish_dashboard()

    @Slot(str, str)
    def _on_status(self, status: str, detail: str) -> None:
        self._status_key = status
        self._status_detail = detail
        self._update_status_text()

    def _announce(self, event) -> None:
        """One tray balloon per problem, never one per sample."""
        # Whether or not it is worth interrupting the user, it is worth finding
        # out why while the problem is still happening.
        self._maybe_auto_check()
        if self._tray is None or not self._config.notify_enabled:
            return
        if not self._notifier.should_notify():
            return
        if event.kind == STALL:
            text = tr("notice.stall")
        else:
            text = tr("notice.spike", value=format_ms(event.value_ms),
                      baseline=format_ms(event.baseline_ms))
        self._tray.showMessage(APP_NAME, text, app_icon(), 5000)

    @Slot(object)
    def _on_room_info(self, info) -> None:
        self._room_info = info
        if info is not None and self._target is not None and self._target.kind == KIND_LIVE:
            self._room_title = f"{tr('label.room')} {info.room_id}"
            self._overlay.set_room_label(self._room_title)

    @Slot(object)
    def _on_target(self, target) -> None:
        self._target = target
        if target is None or target.kind == KIND_NETWORK:
            self._room_title = ""
        elif target.kind == KIND_VIDEO:
            self._room_title = f"{tr('label.video')} {target.title or target.ident}"
        elif target.kind == KIND_APP:
            self._room_title = f"{tr('label.app')} {target.ident}"
        elif target.kind == KIND_TARGET:
            self._room_title = f"{tr('label.target')} {target.ident}"
        else:
            # Only a live stream has a room; the branch used to say "Room
            # LagScope.exe", which is three kinds of wrong at once.
            self._room_title = f"{tr('label.room')} {target.ident}"
        self._overlay.set_room_label(self._room_title)

    def _status_line(self) -> str:
        if self._paused:
            return tr("status.paused")
        mapping = {
            STATUS_OK: "",
            STATUS_OFFLINE: tr("status.offline"),
            STATUS_NO_ROOM: tr("status.network_only"),
            STATUS_ERROR: tr("status.error"),
            STATUS_PAUSED: tr("status.paused"),
        }
        if self._status_key == STATUS_OK:
            # Nothing to say once samples are flowing.
            return "" if len(self._stats) else tr("status.connecting")
        if self._status_key == STATUS_NO_ROOM and self._config.detect.enabled:
            # Auto-detection is on but has not found a page yet.
            return tr("status.detecting")
        text = mapping.get(self._status_key, "")
        if self._status_key == STATUS_ERROR and self._status_detail:
            # Probe errors are codes; show the translated sentence where there
            # is one, and the raw detail (a network message) otherwise.
            known = ERROR_MESSAGES.get(self._status_detail)
            return tr(known) if known else f"{text}: {self._status_detail}"
        return text or tr("status.connecting")

    def _update_status_text(self) -> None:
        self._overlay.set_status(self._status_line())
        if self._tray is not None:
            self._tray.update_sample(self._stats.last(), self._status_line())

    def _poll_clipboard(self, force: bool = False) -> None:
        """Hand a freshly copied Bilibili link to the worker.

        Only the text is passed on, and only when it changed; the worker throws
        away anything that is not a Bilibili link.
        """
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return
        try:
            text = clipboard.text() or ""
        except RuntimeError:  # clipboard busy or owned by another app
            return
        text = text.strip()[:MAX_CLIPBOARD_CHARS]
        if not text or (text == self._last_clipboard and not force):
            return
        self._last_clipboard = text
        self.clipboardText.emit(text)

    def _read_clipboard_now(self) -> None:
        self._poll_clipboard(force=True)
        if self._tray is not None:
            self._tray.showMessage(APP_NAME, tr("notice.clipboard_read"), app_icon(), 2500)

    def _push_display_latency(self) -> None:
        if not self._overlay.isVisible():
            # Without a visible overlay there are no frames to time; the
            # configured panel offset is still meaningful.
            manual = self._config.display.manual_offset_ms
            self._worker.setDisplayLatency(manual if manual > 0 else None)
            return
        self._worker.setDisplayLatency(
            self._display.estimate_ms(
                self._config.display.frames_in_flight,
                self._config.display.manual_offset_ms,
            )
        )

    # ---------------------------------------------------------------- helpers
    def diagnostics_text(self) -> str:
        sample = self._stats.last()
        payload = {
            "app": APP_NAME,
            "version": __version__,
            "language": self._config.language,
            "auto_detect": self._config.detect.enabled,
            "target": {
                "kind": self._target.kind if self._target else None,
                "id": self._target.ident if self._target else None,
                "page": self._target.page if self._target else None,
                "source": self._target.source if self._target else None,
            },
            "room_id": self._config.room_id or None,
            "video_id": self._config.video_id or None,
            "status": self._status_key,
            "status_detail": self._status_detail,
            "samples": len(self._stats),
            "avg_ms": self._stats.avg(),
            "p95_ms": self._stats.percentile(95),
            "jitter_ms": self._stats.jitter(),
            "failure_rate": self._stats.failure_rate(),
            "last_sample": sample.to_dict() if sample else None,
            "display": self._display.snapshot(
                self._config.display.frames_in_flight, self._config.display.manual_offset_ms
            ),
            "events": self._events.summary(),
            "extras": [
                {"label": extra.label, "kind": extra.kind, "ident": extra.ident,
                 "rtt_ms": extra.rtt_ms, "method": extra.method, "ok": extra.ok,
                 "age_s": round(extra.age_s, 1), "error": extra.error}
                for extra in self._ordered_extras()
            ],
            "netspeed": {
                "down_mbps": sample.down_mbps if sample else None,
                "up_mbps": sample.up_mbps if sample else None,
            },
            "cdn_lines": {
                "current": self._lines[0],
                "measured": [
                    {"host": line.host, "rtt_ms": line.rtt_ms} for line in (self._lines[1] or [])
                ],
            },
            "room": None if self._room_info is None else {
                "id": self._room_info.room_id,
                "title": self._room_info.title,
                "online": self._room_info.online,
                "area": self._room_info.area,
                "live_seconds": self._room_info.live_seconds(),
            },
            "config_dir": str(app_config_dir()),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @Slot()
    def _on_second_instance(self) -> None:
        """Someone launched the app again: bring the overlay back instead."""
        self._set_overlay_visible(True)
        self._action_overlay.setChecked(True)
        self._overlay.raise_()

    def _shutdown(self) -> None:
        self._display_timer.stop()
        self._clipboard_timer.stop()
        self._history_timer.stop()
        self._history.close()
        if self._save_timer.isActive():
            self._save_timer.stop()
        self._save_config_now()
        # Queued: the worker stops its own timers inside its own thread, then
        # quit() ends that thread's event loop.
        self.stopRequested.emit()
        self._thread.quit()
        if not self._thread.wait(3000):
            LOG.warning("monitor thread did not stop in time")
            self._thread.terminate()
        if self._recorder is not None:
            self._recorder.close()
        if self._dashboard is not None:
            self._dashboard.stop()
        if self._tray is not None:
            self._tray.hide()
        self._instance.close()


def create_application(argv: list[str]) -> QApplication:
    QApplication.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())
    # Closing the settings dialog must not end the process.
    app.setQuitOnLastWindowClosed(False)
    return app
