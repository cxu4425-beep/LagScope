"""The three questions worth asking before anything else.

A settings dialog with five tabs is the right tool for someone who already
knows what the app does. It is the wrong first thing to meet. So a fresh
install asks three things - what to watch, where to put the overlay, and
whether it may check for updates - and everything else keeps its default.

The third question exists because the answer is a network request. Turning it
on quietly and mentioning it in a README nobody reads is not consent, so it is
asked out loud, with what it does spelled out next to the box.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..autostart import is_supported as autostart_supported
from ..config import Config
from ..i18n import LANGUAGE_NAMES, LANGUAGES, tr
from .icons import app_icon

# (config value, label key) for the "what should it watch" question.
# First is the default, and the one most people want: it needs nothing typed
# in and nothing installed. Bilibili is last because it is the specialist case.
CHOICES = (
    ("network", "wizard.watch.network"),
    ("app", "wizard.watch.app"),
    ("target", "wizard.watch.target"),
    ("auto", "wizard.watch.auto"),
)

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")


def _wrapped(label: QLabel, min_lines: int = 1) -> QLabel:
    """A word-wrapped label a box layout will actually give room to.

    A wrapped QLabel knows its height only once it knows its width, and a box
    layout ignores that unless the size policy says to ask. Without this the
    second line is simply cut off - which never showed up in Chinese, where
    these hints happen to fit on one line, and did the moment they were
    translated into a language that needs two.
    """
    label.setWordWrap(True)
    policy = label.sizePolicy()
    policy.setHeightForWidth(True)
    policy.setVerticalPolicy(QSizePolicy.MinimumExpanding)
    label.setSizePolicy(policy)
    if min_lines > 1:
        # Reserving the tallest case keeps the dialog from resizing every time
        # a radio button swaps the text underneath it.
        label.setMinimumHeight(label.fontMetrics().lineSpacing() * min_lines)
    return label


def add_router(config: Config, gateway_lookup=None) -> bool:
    """Add the home router as a side watch, unless it is already there.

    Quietly does nothing when the gateway cannot be found - a VPN that owns the
    default route, say - because the wizard is no place for an error about a
    feature nobody asked for by name.
    """
    if gateway_lookup is None:
        from ..probes.path import default_gateway as gateway_lookup
    try:
        gateway = gateway_lookup()
    except Exception:
        gateway = ""
    if not gateway:
        return False
    extras = list(config.watch_extras or [])
    if any(str(entry.get("ident", "")).lower() == gateway.lower() for entry in extras):
        return False
    extras.insert(0, {"kind": "target", "ident": gateway, "port": 80,
                      "label": tr("extras.router")})
    config.watch_extras = extras
    return True


class SetupWizard(QDialog):
    """Shown once, on a config that has never been through it."""

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(f"{APP_NAME} · {tr('wizard.title')}")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        heading = _wrapped(QLabel(f"<b>{tr('wizard.welcome', app=APP_NAME)}</b>", self))
        layout.addWidget(heading)
        blurb = _wrapped(QLabel(tr("wizard.blurb"), self), min_lines=2)
        blurb.setStyleSheet("color: palette(mid);")
        layout.addWidget(blurb)

        # ---------------------------------------------------------- language
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(tr("general.language"), self))
        self.language_combo = QComboBox(self)
        self.language_combo.addItem(tr("general.language_auto"), "auto")
        for code in LANGUAGES:
            self.language_combo.addItem(LANGUAGE_NAMES[code], code)
        self.language_combo.setCurrentIndex(
            max(0, self.language_combo.findData(config.language))
        )
        language_row.addWidget(self.language_combo, 1)
        layout.addLayout(language_row)

        # ------------------------------------------------------ what to watch
        watch_box = QGroupBox(tr("wizard.watch"), self)
        watch_layout = QVBoxLayout(watch_box)
        self._watch_group = QButtonGroup(self)
        self._watch_buttons = {}
        for value, key in CHOICES:
            button = QRadioButton(tr(key), watch_box)
            self._watch_group.addButton(button)
            self._watch_buttons[value] = button
            watch_layout.addWidget(button)
        self._watch_buttons["network"].setChecked(True)
        self._watch_group.buttonToggled.connect(lambda *_: self._sync())

        self.detail_edit = QLineEdit(watch_box)
        detail_form = QFormLayout()
        self.detail_label = QLabel(tr("wizard.detail.app"), watch_box)
        detail_form.addRow(self.detail_label, self.detail_edit)
        watch_layout.addLayout(detail_form)

        # Three lines: the longest of the four hints, in the wordiest language.
        self.detail_hint = _wrapped(QLabel("", watch_box), min_lines=3)
        self.detail_hint.setStyleSheet("color: palette(mid);")
        watch_layout.addWidget(self.detail_hint)
        layout.addWidget(watch_box)

        # ---------------------------------------------------------- placement
        place_box = QGroupBox(tr("wizard.place"), self)
        place_form = QFormLayout(place_box)
        self.corner_combo = QComboBox(place_box)
        self.corner_combo.addItem(tr("wizard.place.free"), "free")
        for corner in CORNERS:
            self.corner_combo.addItem(tr(f"overlay.corner.{corner}"), corner)
        place_form.addRow(tr("overlay.anchor"), self.corner_combo)

        self.autostart_check = QCheckBox(tr("general.autostart"), place_box)
        self.autostart_check.setEnabled(autostart_supported())
        if not autostart_supported():
            self.autostart_check.setToolTip(tr("general.autostart_unsupported"))
        place_form.addRow("", self.autostart_check)
        layout.addWidget(place_box)

        # ------------------------------------------------------------ updates
        update_box = QGroupBox(tr("wizard.updates"), self)
        update_layout = QVBoxLayout(update_box)
        self.update_check = QCheckBox(tr("update.enabled"), update_box)
        self.update_check.setChecked(config.updates.enabled)
        update_layout.addWidget(self.update_check)
        update_hint = _wrapped(QLabel(tr("update.hint"), update_box), min_lines=3)
        update_hint.setStyleSheet("color: palette(mid);")
        update_layout.addWidget(update_hint)
        layout.addWidget(update_box)

        footer = _wrapped(QLabel(tr("wizard.footer", version=__version__), self))
        footer.setStyleSheet("color: palette(mid);")
        layout.addWidget(footer)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, parent=self)
        buttons.button(QDialogButtonBox.Ok).setText(tr("wizard.start"))
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._sync()

    # ------------------------------------------------------------------ state
    def _selected(self) -> str:
        for value, button in self._watch_buttons.items():
            if button.isChecked():
                return value
        return "network"

    def _sync(self) -> None:
        """Only one of the four choices needs anything typed in."""
        choice = self._selected()
        needs_detail = choice in ("app", "target")
        self.detail_edit.setVisible(needs_detail)
        self.detail_label.setVisible(needs_detail)

        if choice == "app":
            self.detail_label.setText(tr("wizard.detail.app"))
            self.detail_edit.setPlaceholderText("RobloxPlayerBeta.exe")
            self.detail_hint.setText(tr("wizard.hint.app"))
        elif choice == "target":
            self.detail_label.setText(tr("wizard.detail.target"))
            self.detail_edit.setPlaceholderText("8.8.8.8")
            self.detail_hint.setText(tr("wizard.hint.target"))
        elif choice == "auto":
            self.detail_hint.setText(tr("wizard.hint.auto"))
        else:
            self.detail_hint.setText(tr("wizard.hint.network"))

    # ------------------------------------------------------------------- data
    def apply_to(self, config: Config) -> Config:
        """Fold the answers into a config; everything unasked keeps its default."""
        config.language = self.language_combo.currentData() or "auto"
        choice = self._selected()
        detail = self.detail_edit.text().strip()

        if choice == "network":
            config.detect.enabled = False
            config.manual_kind = "network"
            # "Is it my home network or the internet?" is the first question
            # anyone asks when the number goes red, and the router answers it.
            # Added once, here, where the user is choosing the general view.
            add_router(config)
        elif choice == "auto":
            config.detect.enabled = True
        elif choice == "app":
            config.detect.enabled = False
            config.manual_kind = "app"
            config.app_name = detail
            config.app_follow_foreground = not detail
        elif choice == "target":
            config.detect.enabled = False
            config.manual_kind = "target"
            config.target_host = detail

        corner = self.corner_combo.currentData()
        if corner == "free":
            config.overlay.anchor_mode = "free"
        else:
            config.overlay.anchor_mode = "screen"
            config.overlay.corner = corner

        config.autostart = self.autostart_check.isChecked()
        config.updates.enabled = self.update_check.isChecked()
        config.setup_done = True
        return config.sanitized()
