"""Settings dialog: everything is editable here, no config file editing needed."""

from __future__ import annotations

import copy
import time
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, REPO_URL, __version__
from ..autostart import is_supported as autostart_supported
from ..config import Config, app_config_dir, parse_room_id
from ..probes.video import parse_video_target
from ..i18n import LANGUAGE_NAMES, LANGUAGES, tr
from .anchor import create_window_finder
from .icons import app_icon


class ExtraWatchDialog(QDialog):
    """Add one side watch: an address to ping, or an application to follow."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("extras.dialog"))
        form = QFormLayout(self)

        self.kind_combo = QComboBox(self)
        self.kind_combo.addItem(tr("extras.kind.target"), "target")
        self.kind_combo.addItem(tr("extras.kind.app"), "app")
        self.kind_combo.currentIndexChanged.connect(self._sync)
        form.addRow(tr("extras.kind"), self.kind_combo)

        self.ident_edit = QLineEdit(self)
        self.ident_edit.setPlaceholderText("8.8.8.8 / Discord.exe")
        form.addRow(tr("extras.ident"), self.ident_edit)

        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(443)
        form.addRow(tr("general.target_port"), self.port_spin)

        self.label_edit = QLineEdit(self)
        self.label_edit.setMaxLength(40)
        form.addRow(tr("extras.label"), self.label_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.button(QDialogButtonBox.Ok).setText(tr("button.ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("button.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._sync()

    def _sync(self) -> None:
        self.port_spin.setEnabled(self.kind_combo.currentData() == "target")

    def entry(self) -> Optional[dict]:
        ident = self.ident_edit.text().strip()
        if not ident:
            return None
        return {
            "kind": self.kind_combo.currentData() or "target",
            "ident": ident,
            "port": self.port_spin.value(),
            "label": self.label_edit.text().strip() or ident,
        }


def _scrollable(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    # No sideways scrolling: the page follows the viewport width so that the
    # wrapped hint labels reflow instead of pushing the form wider.
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area


class SettingsDialog(QDialog):
    """Edits a copy of the config; emits :attr:`configApplied` on OK/Apply."""

    configApplied = Signal(object)
    openConfigFolderRequested = Signal()

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(config)
        self._window_following_available = create_window_finder().available

        self.setWindowTitle(f"{APP_NAME} - {tr('settings.title')}")
        self.setWindowIcon(app_icon())
        self.setModal(False)
        self.setMinimumWidth(500)
        self.resize(540, 660)

        # Scrollable pages: translations differ in length and a small laptop
        # screen must never cut a setting off.
        tabs = QTabWidget(self)
        tabs.addTab(_scrollable(self._build_general_tab()), tr("settings.tab.general"))
        tabs.addTab(_scrollable(self._build_overlay_tab()), tr("settings.tab.overlay"))
        tabs.addTab(_scrollable(self._build_advanced_tab()), tr("settings.tab.advanced"))
        tabs.addTab(self._build_about_tab(), tr("settings.tab.about"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
            | QDialogButtonBox.RestoreDefaults,
            parent=self,
        )
        buttons.button(QDialogButtonBox.Ok).setText(tr("button.ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("button.cancel"))
        buttons.button(QDialogButtonBox.Apply).setText(tr("button.apply"))
        buttons.button(QDialogButtonBox.RestoreDefaults).setText(tr("button.defaults"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self.load_from(self._config)

    # ------------------------------------------------------------------ build
    def _build_general_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        target_box = QGroupBox(tr("general.target"), page)
        target_form = QFormLayout(target_box)
        self._target_form = target_form

        # The general ones first; Bilibili's three are the specialist case.
        # "network" must be in this list: a mode the dialog cannot show is a
        # mode it silently replaces with whatever is first when OK is pressed.
        self.target_combo = QComboBox(target_box)
        self.target_combo.addItem(tr("general.target.network"), "network")
        self.target_combo.addItem(tr("general.target.app"), "app")
        self.target_combo.addItem(tr("general.target.custom"), "target")
        self.target_combo.addItem(tr("general.target.auto"), "auto")
        self.target_combo.addItem(tr("general.target.live"), "live")
        self.target_combo.addItem(tr("general.target.video"), "video")
        self.target_combo.currentIndexChanged.connect(self._sync_detect_state)
        target_form.addRow(tr("general.target"), self.target_combo)

        self.network_hint = QLabel(tr("wizard.hint.network"), target_box)
        self.network_hint.setWordWrap(True)
        self.network_hint.setStyleSheet("color: palette(mid);")
        target_form.addRow(self.network_hint)

        self.room_edit = QLineEdit(target_box)
        self.room_edit.setPlaceholderText("https://live.bilibili.com/21452505")
        target_form.addRow(tr("general.room"), self.room_edit)
        room_hint = self._room_hint = QLabel(tr("general.room_hint"), target_box)
        room_hint.setWordWrap(True)
        room_hint.setStyleSheet("color: palette(mid);")
        target_form.addRow(room_hint)

        self.video_edit = QLineEdit(target_box)
        self.video_edit.setPlaceholderText("https://www.bilibili.com/video/BV1GJ411x7h7")
        target_form.addRow(tr("general.video"), self.video_edit)
        video_hint = self._video_hint = QLabel(tr("general.video_hint"), target_box)
        video_hint.setWordWrap(True)
        video_hint.setStyleSheet("color: palette(mid);")
        target_form.addRow(video_hint)

        # --- any application -------------------------------------------------
        self.app_combo = QComboBox(target_box)
        self.app_combo.setEditable(True)          # a game that is not running yet
        self.app_refresh_button = QPushButton(tr("general.app_refresh"), target_box)
        self.app_refresh_button.clicked.connect(self._reload_apps)
        app_row = self._app_row = QHBoxLayout()
        app_row.addWidget(self.app_combo, 1)
        app_row.addWidget(self.app_refresh_button)
        target_form.addRow(tr("general.app_name"), app_row)
        self.app_follow_check = QCheckBox(tr("general.app_follow"), target_box)
        self.app_follow_check.toggled.connect(self._sync_target_state)
        target_form.addRow("", self.app_follow_check)
        app_hint = self._app_hint = QLabel(tr("general.app_hint"), target_box)
        app_hint.setWordWrap(True)
        app_hint.setStyleSheet("color: palette(mid);")
        target_form.addRow(app_hint)

        # --- a server address the user types ---------------------------------
        self.target_host_edit = QLineEdit(target_box)
        self.target_host_edit.setPlaceholderText("8.8.8.8")
        target_form.addRow(tr("general.target_host"), self.target_host_edit)
        self.target_port_spin = QSpinBox(target_box)
        self.target_port_spin.setRange(1, 65535)
        target_form.addRow(tr("general.target_port"), self.target_port_spin)
        target_hint = self._target_hint = QLabel(tr("general.target_hint"), target_box)
        target_hint.setWordWrap(True)
        target_hint.setStyleSheet("color: palette(mid);")
        target_form.addRow(target_hint)

        outer.addWidget(target_box)

        outer.addWidget(self._build_detect_box(page))

        general_box = QGroupBox(tr("settings.tab.general"), page)
        form = QFormLayout(general_box)

        self.interval_spin = QSpinBox(page)
        self.interval_spin.setRange(500, 60_000)
        self.interval_spin.setSingleStep(500)
        self.interval_spin.setSuffix(" ms")
        form.addRow(tr("general.interval"), self.interval_spin)

        self.window_spin = QSpinBox(page)
        self.window_spin.setRange(20, 5000)
        self.window_spin.setSingleStep(10)
        form.addRow(tr("general.sample_window"), self.window_spin)

        self.language_combo = QComboBox(page)
        self.language_combo.addItem(tr("general.language_auto"), "auto")
        for code in LANGUAGES:
            self.language_combo.addItem(LANGUAGE_NAMES[code], code)
        form.addRow(tr("general.language"), self.language_combo)

        self.autostart_check = QCheckBox(tr("general.autostart"), page)
        if not autostart_supported():
            self.autostart_check.setEnabled(False)
            self.autostart_check.setToolTip(tr("general.autostart_unsupported"))
        form.addRow("", self.autostart_check)

        self.tray_check = QCheckBox(tr("tray.enabled"), page)
        form.addRow("", self.tray_check)
        self.tray_value_check = QCheckBox(tr("tray.show_value"), page)
        form.addRow("", self.tray_value_check)
        self.netspeed_check = QCheckBox(tr("general.netspeed"), page)
        form.addRow("", self.netspeed_check)
        self.notify_check = QCheckBox(tr("general.notify"), page)
        form.addRow("", self.notify_check)

        outer.addWidget(self._build_extras_box(page))
        outer.addWidget(general_box)
        outer.addWidget(self._build_web_box(page))
        outer.addStretch(1)
        return page

    def _build_extras_box(self, parent: QWidget) -> QWidget:
        box = QGroupBox(tr("extras.group"), parent)
        layout = QVBoxLayout(box)

        self.extras_list = QListWidget(box)
        self.extras_list.setMaximumHeight(110)
        layout.addWidget(self.extras_list)

        buttons = QHBoxLayout()
        add_button = QPushButton(tr("extras.add"), box)
        add_button.clicked.connect(self._add_extra)
        remove_button = QPushButton(tr("extras.remove"), box)
        remove_button.clicked.connect(self._remove_extra)
        router_button = QPushButton(tr("extras.add_router"), box)
        router_button.clicked.connect(self._add_router)
        dns_button = QPushButton(tr("extras.add_dns"), box)
        dns_button.clicked.connect(self._add_dns)
        self._extra_add_buttons = (add_button, router_button, dns_button)
        for button in (add_button, remove_button, router_button, dns_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        hint = QLabel(tr("extras.hint"), box)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        return box

    def _refresh_extras(self) -> None:
        from ..config import MAX_EXTRA_WATCHES

        # At the limit the add buttons simply go grey; interrupting someone with
        # a dialog to say "no" is worse than showing them they cannot.
        full = len(self._extras) >= MAX_EXTRA_WATCHES
        for button in self._extra_add_buttons:
            button.setEnabled(not full)
            button.setToolTip(tr("extras.full") if full else "")

        self.extras_list.clear()
        for entry in self._extras:
            if entry["kind"] == "target":
                detail = f"{entry['ident']}:{entry['port']}"
            else:
                detail = entry["ident"]
            item = QListWidgetItem(f"{entry['label']}  —  {detail}")
            item.setData(Qt.UserRole, entry)
            self.extras_list.addItem(item)

    def _append_extra(self, entry: dict) -> None:
        from ..config import MAX_EXTRA_WATCHES

        if len(self._extras) >= MAX_EXTRA_WATCHES:
            return
        key = (entry["kind"], entry["ident"].lower())
        if any((item["kind"], item["ident"].lower()) == key for item in self._extras):
            return
        self._extras.append(entry)
        self._refresh_extras()

    def _add_extra(self) -> None:
        dialog = ExtraWatchDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        entry = dialog.entry()
        if entry is not None:
            self._append_extra(entry)

    def _remove_extra(self) -> None:
        for item in self.extras_list.selectedItems():
            entry = item.data(Qt.UserRole)
            self._extras = [
                other for other in self._extras
                if not (other["kind"] == entry["kind"] and other["ident"] == entry["ident"])
            ]
        self._refresh_extras()

    def _add_router(self) -> None:
        from ..probes.path import default_gateway

        gateway = default_gateway()
        if not gateway:
            QMessageBox.information(self, tr("extras.group"), tr("extras.no_router"))
            return
        self._append_extra({"kind": "target", "ident": gateway, "port": 80,
                            "label": tr("extras.router")})

    def _add_dns(self) -> None:
        self._append_extra({"kind": "target", "ident": "8.8.8.8", "port": 53,
                            "label": tr("extras.dns")})

    def _build_web_box(self, parent: QWidget) -> QWidget:
        box = QGroupBox(tr("web.group"), parent)
        form = QFormLayout(box)

        self.web_check = QCheckBox(tr("web.enabled"), box)
        self.web_check.toggled.connect(self._sync_web_state)
        form.addRow("", self.web_check)

        self.web_port_spin = QSpinBox(box)
        self.web_port_spin.setRange(1024, 65535)
        form.addRow(tr("web.port"), self.web_port_spin)

        self.web_code_edit = QLineEdit(box)
        self.web_code_edit.setMaxLength(32)
        form.addRow(tr("web.code"), self.web_code_edit)

        self.web_url_label = QLabel("", box)
        self.web_url_label.setWordWrap(True)
        self.web_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(tr("web.url_label"), self.web_url_label)

        hint = QLabel(tr("web.hint"), box)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        form.addRow(hint)
        self._web_box = box
        return box

    def _sync_history_state(self) -> None:
        enabled = self.history_check.isChecked()
        self.history_keep_spin.setEnabled(enabled)
        self.auto_check_check.setEnabled(enabled)

    def _sync_web_state(self) -> None:
        enabled = self.web_check.isChecked()
        self.web_port_spin.setEnabled(enabled)
        self.web_code_edit.setEnabled(enabled)
        self._refresh_web_urls()

    def _refresh_web_urls(self) -> None:
        from ..web import dashboard_urls

        if not self.web_check.isChecked():
            self.web_url_label.setText(tr("web.off"))
            return
        urls = dashboard_urls(self.web_port_spin.value(), self.web_code_edit.text().strip())
        self.web_url_label.setText("\n".join(urls) if urls else tr("web.off"))

    def _build_detect_box(self, parent: QWidget) -> QWidget:
        box = QGroupBox(tr("detect.group"), parent)
        form = QFormLayout(box)

        self.detect_client_check = QCheckBox(tr("detect.client"), box)
        form.addRow("", self.detect_client_check)
        self.detect_clipboard_check = QCheckBox(tr("detect.clipboard"), box)
        form.addRow("", self.detect_clipboard_check)
        self.detect_titles_memory_check = QCheckBox(tr("detect.remember_titles"), box)
        form.addRow("", self.detect_titles_memory_check)
        client_hint = QLabel(tr("detect.client_hint"), box)
        client_hint.setWordWrap(True)
        client_hint.setStyleSheet("color: palette(mid);")
        form.addRow(client_hint)

        self.detect_history_check = QCheckBox(tr("detect.history"), box)
        form.addRow("", self.detect_history_check)
        self.detect_titles_check = QCheckBox(tr("detect.titles"), box)
        form.addRow("", self.detect_titles_check)
        self.detect_videos_check = QCheckBox(tr("detect.follow_videos"), box)
        form.addRow("", self.detect_videos_check)
        self.detect_bridge_check = QCheckBox(tr("detect.bridge"), box)
        self.detect_bridge_check.toggled.connect(self._sync_detect_state)
        form.addRow("", self.detect_bridge_check)

        self.detect_port_spin = QSpinBox(box)
        self.detect_port_spin.setRange(1024, 65535)
        form.addRow(tr("detect.bridge_port"), self.detect_port_spin)

        self.detect_window_spin = QSpinBox(box)
        self.detect_window_spin.setRange(1, 1440)
        self.detect_window_spin.setSuffix(" min")
        form.addRow(tr("detect.window"), self.detect_window_spin)

        self.detect_interval_spin = QSpinBox(box)
        self.detect_interval_spin.setRange(2, 300)
        self.detect_interval_spin.setSuffix(" s")
        form.addRow(tr("detect.interval"), self.detect_interval_spin)

        privacy = QLabel(tr("detect.privacy"), box)
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color: palette(mid);")
        form.addRow(privacy)
        self._detect_box = box
        return box

    def _build_overlay_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        placement = QGroupBox(tr("overlay.anchor"), page)
        form = QFormLayout(placement)

        self.overlay_check = QCheckBox(tr("overlay.enabled"), placement)
        form.addRow("", self.overlay_check)

        self.anchor_combo = QComboBox(placement)
        for mode in ("free", "screen", "window"):
            self.anchor_combo.addItem(tr(f"overlay.anchor.{mode}"), mode)
        self.anchor_combo.currentIndexChanged.connect(self._sync_anchor_state)
        form.addRow(tr("overlay.anchor"), self.anchor_combo)

        self.screen_combo = QComboBox(placement)
        form.addRow(tr("overlay.screen"), self.screen_combo)

        self.corner_combo = QComboBox(placement)
        for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
            self.corner_combo.addItem(tr(f"overlay.corner.{corner}"), corner)
        form.addRow(tr("overlay.corner"), self.corner_combo)

        self.offset_x_spin = QSpinBox(placement)
        self.offset_x_spin.setRange(0, 4000)
        form.addRow(tr("overlay.offset_x"), self.offset_x_spin)
        self.offset_y_spin = QSpinBox(placement)
        self.offset_y_spin.setRange(0, 4000)
        form.addRow(tr("overlay.offset_y"), self.offset_y_spin)

        self.keyword_edit = QLineEdit(placement)
        form.addRow(tr("overlay.follow_keyword"), self.keyword_edit)
        self.window_note = QLabel(tr("overlay.window_unsupported"), placement)
        self.window_note.setWordWrap(True)
        self.window_note.setStyleSheet("color: palette(mid);")
        form.addRow(self.window_note)
        outer.addWidget(placement)

        look = QGroupBox(tr("settings.tab.overlay"), page)
        look_form = QFormLayout(look)

        self.opacity_slider = QSlider(Qt.Horizontal, look)
        self.opacity_slider.setRange(20, 100)
        self.opacity_label = QLabel("", look)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        look_form.addRow(tr("overlay.opacity"), opacity_row)

        self.scale_spin = QDoubleSpinBox(look)
        self.scale_spin.setRange(0.6, 3.0)
        self.scale_spin.setSingleStep(0.1)
        look_form.addRow(tr("overlay.scale"), self.scale_spin)

        self.theme_combo = QComboBox(look)
        for theme in ("dark", "light", "pink"):
            self.theme_combo.addItem(tr(f"overlay.theme.{theme}"), theme)
        look_form.addRow(tr("overlay.theme"), self.theme_combo)

        self.on_top_check = QCheckBox(tr("overlay.on_top"), look)
        look_form.addRow("", self.on_top_check)
        self.click_through_check = QCheckBox(tr("overlay.click_through"), look)
        look_form.addRow("", self.click_through_check)
        self.locked_check = QCheckBox(tr("overlay.lock"), look)
        look_form.addRow("", self.locked_check)
        self.compact_check = QCheckBox(tr("overlay.compact"), look)
        look_form.addRow("", self.compact_check)
        self.server_check = QCheckBox(tr("overlay.show_server"), look)
        look_form.addRow("", self.server_check)
        self.breakdown_check = QCheckBox(tr("overlay.show_breakdown"), look)
        look_form.addRow("", self.breakdown_check)
        self.sparkline_check = QCheckBox(tr("overlay.show_sparkline"), look)
        look_form.addRow("", self.sparkline_check)
        self.stats_check = QCheckBox(tr("overlay.show_stats"), look)
        look_form.addRow("", self.stats_check)
        outer.addWidget(look)
        outer.addStretch(1)
        return page

    def _build_advanced_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.timeout_spin = QSpinBox(page)
        self.timeout_spin.setRange(1000, 30_000)
        self.timeout_spin.setSingleStep(500)
        self.timeout_spin.setSuffix(" ms")
        form.addRow(tr("advanced.timeout"), self.timeout_spin)

        self.playurl_spin = QSpinBox(page)
        self.playurl_spin.setRange(30, 3600)
        self.playurl_spin.setSuffix(" s")
        form.addRow(tr("advanced.playurl_refresh"), self.playurl_spin)

        self.rtt_host_edit = QLineEdit(page)
        form.addRow(tr("advanced.rtt_host"), self.rtt_host_edit)

        self.auto_cdn_check = QCheckBox(tr("advanced.auto_cdn"), page)
        form.addRow("", self.auto_cdn_check)
        auto_cdn_hint = QLabel(tr("advanced.auto_cdn_hint"), page)
        auto_cdn_hint.setWordWrap(True)
        auto_cdn_hint.setStyleSheet("color: palette(mid);")
        form.addRow(auto_cdn_hint)

        self.prefer_hls_check = QCheckBox(tr("advanced.prefer_hls"), page)
        form.addRow("", self.prefer_hls_check)

        self.buffer_spin = QDoubleSpinBox(page)
        self.buffer_spin.setRange(0.0, 10.0)
        self.buffer_spin.setSingleStep(0.5)
        form.addRow(tr("advanced.buffer_segments"), self.buffer_spin)

        self.frames_spin = QDoubleSpinBox(page)
        self.frames_spin.setRange(0.0, 6.0)
        self.frames_spin.setSingleStep(0.5)
        form.addRow(tr("advanced.frames_in_flight"), self.frames_spin)

        self.manual_offset_spin = QDoubleSpinBox(page)
        self.manual_offset_spin.setRange(0.0, 500.0)
        self.manual_offset_spin.setSingleStep(1.0)
        self.manual_offset_spin.setSuffix(" ms")
        form.addRow(tr("advanced.manual_offset"), self.manual_offset_spin)

        self.include_display_check = QCheckBox(tr("advanced.include_display"), page)
        form.addRow("", self.include_display_check)

        # Screen to ears. A spin box alone would be asking someone to type in a
        # number they have no way of knowing, so the calibrate button - which
        # measures it - sits on the same row and is the intended route in.
        audio_row = QHBoxLayout()
        self.audio_offset_spin = QDoubleSpinBox(page)
        self.audio_offset_spin.setRange(0.0, 500.0)
        self.audio_offset_spin.setSingleStep(1.0)
        self.audio_offset_spin.setSuffix(" ms")
        audio_row.addWidget(self.audio_offset_spin, 1)
        self.calibrate_audio_button = QPushButton(tr("advanced.calibrate_audio"), page)
        self.calibrate_audio_button.clicked.connect(self._calibrate_audio)
        audio_row.addWidget(self.calibrate_audio_button)
        form.addRow(tr("advanced.audio_offset"), audio_row)

        self.audio_note_label = QLabel("", page)
        self.audio_note_label.setStyleSheet("color: palette(mid);")
        form.addRow("", self.audio_note_label)

        self.include_audio_check = QCheckBox(tr("advanced.include_audio"), page)
        form.addRow("", self.include_audio_check)

        # Network first: it is what most people watch. The stream pair is on a
        # scale a thousand times larger and would make every ping green.
        self.net_good_spin = QDoubleSpinBox(page)
        self.net_good_spin.setRange(1.0, 10_000.0)
        self.net_good_spin.setSingleStep(10.0)
        self.net_good_spin.setDecimals(0)
        self.net_good_spin.setSuffix(" ms")
        form.addRow(tr("advanced.net_good"), self.net_good_spin)

        self.net_warn_spin = QDoubleSpinBox(page)
        self.net_warn_spin.setRange(1.0, 10_000.0)
        self.net_warn_spin.setSingleStep(10.0)
        self.net_warn_spin.setDecimals(0)
        self.net_warn_spin.setSuffix(" ms")
        form.addRow(tr("advanced.net_warn"), self.net_warn_spin)

        self.good_spin = QDoubleSpinBox(page)
        self.good_spin.setRange(10.0, 600_000.0)
        self.good_spin.setSingleStep(100.0)
        self.good_spin.setSuffix(" ms")
        form.addRow(tr("advanced.good"), self.good_spin)

        self.warn_spin = QDoubleSpinBox(page)
        self.warn_spin.setRange(10.0, 600_000.0)
        self.warn_spin.setSingleStep(100.0)
        self.warn_spin.setSuffix(" ms")
        form.addRow(tr("advanced.warn"), self.warn_spin)

        self.csv_check = QCheckBox(tr("advanced.csv"), page)
        form.addRow("", self.csv_check)
        csv_hint = QLabel(tr("advanced.csv_hint"), page)
        csv_hint.setWordWrap(True)
        csv_hint.setStyleSheet("color: palette(mid);")
        form.addRow(csv_hint)

        history_box = QGroupBox(tr("history.group"), page)
        history_form = QFormLayout(history_box)
        self.history_check = QCheckBox(tr("history.enabled"), history_box)
        self.history_check.toggled.connect(self._sync_history_state)
        history_form.addRow("", self.history_check)
        self.history_keep_spin = QSpinBox(history_box)
        self.history_keep_spin.setRange(1, 720)
        history_form.addRow(tr("history.keep"), self.history_keep_spin)
        self.auto_check_check = QCheckBox(tr("history.auto_check"), history_box)
        history_form.addRow("", self.auto_check_check)
        auto_hint = QLabel(tr("history.auto_check_hint"), history_box)
        auto_hint.setWordWrap(True)
        auto_hint.setStyleSheet("color: palette(mid);")
        history_form.addRow(auto_hint)
        history_hint = QLabel(tr("history.hint"), history_box)
        history_hint.setWordWrap(True)
        history_hint.setStyleSheet("color: palette(mid);")
        history_form.addRow(history_hint)
        form.addRow(history_box)

        speed_box = QGroupBox(tr("speed.group"), page)
        speed_form = QFormLayout(speed_box)
        self.speed_budget_spin = QSpinBox(speed_box)
        self.speed_budget_spin.setRange(3, 60)
        self.speed_budget_spin.setSuffix(" s")
        speed_form.addRow(tr("speed.budget"), self.speed_budget_spin)
        self.speed_mb_spin = QSpinBox(speed_box)
        self.speed_mb_spin.setRange(5, 2000)
        self.speed_mb_spin.setSuffix(" MB")
        speed_form.addRow(tr("speed.max_mb"), self.speed_mb_spin)
        speed_hint = QLabel(tr("speed.hint"), speed_box)
        speed_hint.setWordWrap(True)
        speed_hint.setStyleSheet("color: palette(mid);")
        speed_form.addRow(speed_hint)
        form.addRow(speed_box)

        update_box = QGroupBox(tr("update.group"), page)
        update_layout = QVBoxLayout(update_box)
        self.update_check_box = QCheckBox(tr("update.enabled"), update_box)
        update_layout.addWidget(self.update_check_box)
        update_hint = QLabel(tr("update.hint"), update_box)
        update_hint.setWordWrap(True)
        update_hint.setStyleSheet("color: palette(mid);")
        update_layout.addWidget(update_hint)
        form.addRow(update_box)

        open_button = QPushButton(tr("menu.open_config"), page)
        open_button.clicked.connect(self.openConfigFolderRequested.emit)
        form.addRow("", open_button)
        return page

    def _build_about_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        title = QLabel(f"<b>{APP_NAME}</b>", page)
        body = QLabel(tr("about.body"), page)
        body.setWordWrap(True)
        version = QLabel(f"{tr('about.version')}: {__version__}", page)
        repo = QLabel(f'<a href="{REPO_URL}">{tr("about.repo")}</a>', page)
        repo.setOpenExternalLinks(True)
        folder = QLabel(str(app_config_dir()), page)
        folder.setWordWrap(True)
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for widget in (title, body, version, repo, folder):
            layout.addWidget(widget)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------- data
    def load_from(self, config: Config) -> None:
        self._config = copy.deepcopy(config)
        overlay = self._config.overlay

        mode = "auto" if self._config.detect.enabled else self._config.manual_kind
        self.target_combo.setCurrentIndex(max(0, self.target_combo.findData(mode)))
        self.room_edit.setText(self._config.room_id)
        self.video_edit.setText(self._config.video_id)
        self._reload_apps(self._config.app_name)
        self.app_follow_check.setChecked(self._config.app_follow_foreground)
        self.target_host_edit.setText(self._config.target_host)
        self.target_port_spin.setValue(self._config.target_port)
        self.netspeed_check.setChecked(self._config.show_netspeed)
        self.notify_check.setChecked(self._config.notify_enabled)
        self._extras = [dict(entry) for entry in self._config.watch_extras]
        self._refresh_extras()
        self.web_check.setChecked(self._config.web.enabled)
        self.web_port_spin.setValue(self._config.web.port)
        self.web_code_edit.setText(self._config.web.access_code)
        self.detect_client_check.setChecked(self._config.detect.use_client)
        self.detect_clipboard_check.setChecked(self._config.detect.use_clipboard)
        self.detect_titles_memory_check.setChecked(self._config.detect.remember_titles)
        self.detect_history_check.setChecked(self._config.detect.use_history)
        self.detect_titles_check.setChecked(self._config.detect.use_titles)
        self.detect_bridge_check.setChecked(self._config.detect.use_bridge)
        self.detect_videos_check.setChecked(self._config.detect.follow_videos)
        self.detect_port_spin.setValue(self._config.detect.bridge_port)
        self.detect_window_spin.setValue(self._config.detect.history_window_min)
        self.detect_interval_spin.setValue(self._config.detect.poll_interval_s)

        self.interval_spin.setValue(self._config.probe.interval_ms)
        self.window_spin.setValue(self._config.sample_window)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self._config.language)))
        self.autostart_check.setChecked(self._config.autostart)
        self.tray_check.setChecked(self._config.tray.enabled)
        self.tray_value_check.setChecked(self._config.tray.show_value_in_icon)

        self._reload_screens(overlay.screen_name)
        self.overlay_check.setChecked(overlay.enabled)
        self.anchor_combo.setCurrentIndex(max(0, self.anchor_combo.findData(overlay.anchor_mode)))
        self.corner_combo.setCurrentIndex(max(0, self.corner_combo.findData(overlay.corner)))
        self.offset_x_spin.setValue(overlay.offset_x)
        self.offset_y_spin.setValue(overlay.offset_y)
        self.keyword_edit.setText(overlay.follow_window_keyword)
        self.opacity_slider.setValue(int(round(overlay.opacity * 100)))
        self.opacity_label.setText(f"{self.opacity_slider.value()}%")
        self.scale_spin.setValue(overlay.scale)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(overlay.theme)))
        self.on_top_check.setChecked(overlay.always_on_top)
        self.click_through_check.setChecked(overlay.click_through)
        self.locked_check.setChecked(overlay.locked)
        self.compact_check.setChecked(overlay.compact)
        self.server_check.setChecked(overlay.show_server)
        self.breakdown_check.setChecked(overlay.show_breakdown)
        self.sparkline_check.setChecked(overlay.show_sparkline)
        self.stats_check.setChecked(overlay.show_stats)

        probe = self._config.probe
        self.timeout_spin.setValue(probe.timeout_ms)
        self.playurl_spin.setValue(probe.playurl_refresh_s)
        self.rtt_host_edit.setText(probe.rtt_host)
        self.prefer_hls_check.setChecked(probe.prefer_hls)
        self.buffer_spin.setValue(probe.player_buffer_segments)
        self.frames_spin.setValue(self._config.display.frames_in_flight)
        self.manual_offset_spin.setValue(self._config.display.manual_offset_ms)
        self.include_display_check.setChecked(self._config.display.include_in_total)
        self.audio_offset_spin.setValue(self._config.audio.offset_ms)
        self.include_audio_check.setChecked(self._config.audio.include_in_total)
        self._refresh_audio_note()
        self.net_good_spin.setValue(self._config.thresholds.net_good_ms)
        self.net_warn_spin.setValue(self._config.thresholds.net_warn_ms)
        self.good_spin.setValue(self._config.thresholds.good_ms)
        self.warn_spin.setValue(self._config.thresholds.warn_ms)
        self.csv_check.setChecked(self._config.recording.csv_enabled)
        self.auto_cdn_check.setChecked(self._config.probe.auto_cdn)
        self.history_check.setChecked(self._config.history.enabled)
        self.history_keep_spin.setValue(self._config.history.keep_hours)
        self.auto_check_check.setChecked(self._config.history.auto_check)
        self.update_check_box.setChecked(self._config.updates.enabled)
        self.speed_budget_spin.setValue(self._config.speed.budget_s)
        self.speed_mb_spin.setValue(self._config.speed.max_mb)

        self._sync_history_state()
        self._sync_anchor_state()
        self._sync_detect_state()
        self._sync_web_state()

    def _refresh_audio_note(self) -> None:
        """Say which headphones the stored number was measured with, and when.

        A calibration is only valid for the headset it was taken on, and people
        own more than one pair. Without this the spin box is an anonymous
        number that nobody can decide whether to trust.
        """
        audio = self._config.audio
        if audio.offset_ms <= 0:
            self.audio_note_label.setText(tr("advanced.audio_never"))
            return
        parts = []
        if audio.device_note:
            parts.append(audio.device_note)
        if audio.measured_at > 0:
            parts.append(time.strftime("%Y-%m-%d", time.localtime(audio.measured_at)))
        self.audio_note_label.setText(" \u00b7 ".join(parts))

    def _calibrate_audio(self) -> None:
        from .audiosync import AudioSyncDialog

        dialog = AudioSyncDialog(self._config, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if not dialog.apply_to(self._config):
            return
        # Push what was measured back into the widgets, so Save writes it and
        # Cancel discards it like every other field on this page.
        self.audio_offset_spin.setValue(self._config.audio.offset_ms)
        self.include_audio_check.setChecked(self._config.audio.include_in_total)
        self._refresh_audio_note()

    def _reload_screens(self, selected: str) -> None:
        from PySide6.QtWidgets import QApplication

        self.screen_combo.clear()
        self.screen_combo.addItem(tr("overlay.screen_primary"), "")
        for screen in QApplication.screens():
            geometry = screen.geometry()
            label = f"{screen.name()} ({geometry.width()}x{geometry.height()})"
            self.screen_combo.addItem(label, screen.name())
        index = self.screen_combo.findData(selected)
        self.screen_combo.setCurrentIndex(index if index >= 0 else 0)

    def _sync_anchor_state(self) -> None:
        mode = self.anchor_combo.currentData()
        corner_modes = mode in ("screen", "window")
        self.corner_combo.setEnabled(corner_modes)
        self.offset_x_spin.setEnabled(corner_modes)
        self.offset_y_spin.setEnabled(corner_modes)
        self.screen_combo.setEnabled(mode == "screen")
        self.keyword_edit.setEnabled(mode == "window")
        self.window_note.setVisible(mode == "window" and not self._window_following_available)

    def _sync_detect_state(self) -> None:
        mode = self.target_combo.currentData()
        auto = mode == "auto"
        # Hidden rather than greyed out: a page of disabled Bilibili options is
        # noise to everyone who is not watching Bilibili.
        self._detect_box.setVisible(auto)
        self._detect_box.setEnabled(auto)
        self.detect_port_spin.setEnabled(auto and self.detect_bridge_check.isChecked())
        self._sync_target_state()

    def _sync_target_state(self) -> None:
        """Only show the fields that matter for the chosen mode."""
        mode = self.target_combo.currentData()
        form = self._target_form
        rows = (
            ((self.network_hint,), mode == "network"),
            ((self.room_edit, self._room_hint), mode in ("auto", "live")),
            ((self.video_edit, self._video_hint), mode in ("auto", "video")),
            ((self._app_row, self.app_follow_check, self._app_hint), mode == "app"),
            ((self.target_host_edit, self.target_port_spin, self._target_hint),
             mode == "target"),
        )
        for members, visible in rows:
            for member in members:
                form.setRowVisible(member, visible)
        self.room_edit.setEnabled(mode in ("auto", "live"))
        self.video_edit.setEnabled(mode in ("auto", "video"))
        following = self.app_follow_check.isChecked()
        self.app_combo.setEnabled(mode == "app" and not following)
        self.app_refresh_button.setEnabled(mode == "app" and not following)
        self.app_follow_check.setEnabled(mode == "app")
        self.target_host_edit.setEnabled(mode == "target")
        self.target_port_spin.setEnabled(mode == "target")

    def _chosen_app(self) -> str:
        """The picker shows "name (sockets)"; the process name is the item data."""
        index = self.app_combo.currentIndex()
        text = (self.app_combo.currentText() or "").strip()
        if index >= 0 and text == self.app_combo.itemText(index):
            return (self.app_combo.itemData(index) or text).strip()
        return text

    def _reload_apps(self, selected: str = "") -> None:
        """Fill the picker with the programs that currently hold connections."""
        from ..probes.appnet import list_apps

        current = selected or self.app_combo.currentText()
        self.app_combo.clear()
        try:
            apps = list_apps()
        except Exception:      # a locked-down machine must not break the dialog
            apps = []
        for app in apps:
            self.app_combo.addItem(f"{app.name}  ({app.connections})", app.name)
        if current:
            index = self.app_combo.findData(current)
            if index >= 0:
                self.app_combo.setCurrentIndex(index)
            else:
                self.app_combo.setEditText(current)

    def to_config(self) -> Config:
        config = copy.deepcopy(self._config)
        mode = self.target_combo.currentData() or "network"
        config.detect.enabled = mode == "auto"
        if mode in ("network", "live", "video", "app", "target"):
            config.manual_kind = mode
        config.detect.use_client = self.detect_client_check.isChecked()
        config.detect.use_clipboard = self.detect_clipboard_check.isChecked()
        config.detect.remember_titles = self.detect_titles_memory_check.isChecked()
        config.detect.use_history = self.detect_history_check.isChecked()
        config.detect.use_titles = self.detect_titles_check.isChecked()
        config.detect.use_bridge = self.detect_bridge_check.isChecked()
        config.detect.follow_videos = self.detect_videos_check.isChecked()
        config.detect.bridge_port = self.detect_port_spin.value()
        config.detect.history_window_min = self.detect_window_spin.value()
        config.detect.poll_interval_s = self.detect_interval_spin.value()

        config.room_id = parse_room_id(self.room_edit.text())
        config.video_id, config.video_page = parse_video_target(self.video_edit.text())
        config.app_name = self._chosen_app()
        config.app_follow_foreground = self.app_follow_check.isChecked()
        config.target_host = self.target_host_edit.text().strip()
        config.target_port = self.target_port_spin.value()
        config.show_netspeed = self.netspeed_check.isChecked()
        config.notify_enabled = self.notify_check.isChecked()
        config.watch_extras = [dict(entry) for entry in self._extras]
        config.web.enabled = self.web_check.isChecked()
        config.web.port = self.web_port_spin.value()
        config.web.access_code = self.web_code_edit.text().strip()
        config.probe.interval_ms = self.interval_spin.value()
        config.sample_window = self.window_spin.value()
        config.language = self.language_combo.currentData() or "auto"
        config.autostart = self.autostart_check.isChecked()
        config.tray.enabled = self.tray_check.isChecked()
        config.tray.show_value_in_icon = self.tray_value_check.isChecked()

        overlay = config.overlay
        overlay.enabled = self.overlay_check.isChecked()
        overlay.anchor_mode = self.anchor_combo.currentData() or "free"
        overlay.screen_name = self.screen_combo.currentData() or ""
        overlay.corner = self.corner_combo.currentData() or "top-right"
        overlay.offset_x = self.offset_x_spin.value()
        overlay.offset_y = self.offset_y_spin.value()
        overlay.follow_window_keyword = self.keyword_edit.text().strip() or "哔哩哔哩"
        overlay.opacity = self.opacity_slider.value() / 100.0
        overlay.scale = self.scale_spin.value()
        overlay.theme = self.theme_combo.currentData() or "dark"
        overlay.always_on_top = self.on_top_check.isChecked()
        overlay.click_through = self.click_through_check.isChecked()
        overlay.locked = self.locked_check.isChecked()
        overlay.compact = self.compact_check.isChecked()
        overlay.show_server = self.server_check.isChecked()
        overlay.show_breakdown = self.breakdown_check.isChecked()
        overlay.show_sparkline = self.sparkline_check.isChecked()
        overlay.show_stats = self.stats_check.isChecked()

        config.probe.timeout_ms = self.timeout_spin.value()
        config.probe.playurl_refresh_s = self.playurl_spin.value()
        config.probe.rtt_host = self.rtt_host_edit.text().strip() or "api.live.bilibili.com"
        config.probe.prefer_hls = self.prefer_hls_check.isChecked()
        config.probe.player_buffer_segments = self.buffer_spin.value()
        config.display.frames_in_flight = self.frames_spin.value()
        config.display.manual_offset_ms = self.manual_offset_spin.value()
        config.display.include_in_total = self.include_display_check.isChecked()
        config.audio.offset_ms = self.audio_offset_spin.value()
        config.audio.include_in_total = self.include_audio_check.isChecked()
        config.audio.device_note = self._config.audio.device_note
        config.audio.measured_at = self._config.audio.measured_at
        config.thresholds.net_good_ms = self.net_good_spin.value()
        config.thresholds.net_warn_ms = max(self.net_warn_spin.value(),
                                            self.net_good_spin.value())
        config.thresholds.good_ms = self.good_spin.value()
        config.thresholds.warn_ms = max(self.warn_spin.value(), self.good_spin.value())
        config.recording.csv_enabled = self.csv_check.isChecked()
        config.probe.auto_cdn = self.auto_cdn_check.isChecked()
        config.history.enabled = self.history_check.isChecked()
        config.history.keep_hours = self.history_keep_spin.value()
        config.history.auto_check = self.auto_check_check.isChecked()
        config.updates.enabled = self.update_check_box.isChecked()
        config.speed.budget_s = self.speed_budget_spin.value()
        config.speed.max_mb = self.speed_mb_spin.value()
        return config.sanitized()

    # ---------------------------------------------------------------- actions
    def _apply(self) -> None:
        self.configApplied.emit(self.to_config())

    def _on_accept(self) -> None:
        self._apply()
        self.accept()

    def _restore_defaults(self) -> None:
        # Keep what the user is watching; reset everything else.
        defaults = Config()
        defaults.room_id = parse_room_id(self.room_edit.text())
        defaults.video_id, defaults.video_page = parse_video_target(self.video_edit.text())
        self.load_from(defaults)
