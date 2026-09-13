"""Measuring the last hop the app could not see: screen to ears.

Everything else here ends at the picture. Someone listening on Bluetooth has
one more delay after that - usually larger than the display adds - and there is
no API to ask for it. Windows does not expose the A2DP codec in use, and
Android's BluetoothCodecConfig needs a permission reserved for system apps. A
lookup table of codecs would give a confident number for the wrong headset,
which is worse than none.

So this asks the only instrument that is definitely present and definitely
calibrated for the job: the person's own ear. A click plays and the panel
flashes; the flash is delayed by an adjustable amount; the person moves it
until the two coincide. At that point the delay they dialled in equals how much
later the sound arrived than the picture, which is exactly the quantity that
was missing.

Two honest limits, both shown in the dialog rather than buried here:

  - Precision is human. People notice audio/video mismatch somewhere around
    20-40 ms, so that is the resolution - fine against a 150 ms delay, useless
    for anything small.
  - This is a *difference*, not the headset's absolute latency. It is the
    number that belongs in a total that already ends at the photons, which is
    what it gets used for, but it should not be quoted as "my headphones add
    X ms" in isolation.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from ..audio import Clicker, available as audio_available, spawns_process
from ..config import Config
from ..health import AUDIO, HEALTH
from ..i18n import tr
from .icons import app_icon
from .theme import palette_for

# One cycle: click, then flash after the offset, then quiet until the next.
# Long enough that the previous click has finished ringing in the ear before
# the next begins, short enough to keep a rhythm the person can lock onto.
PERIOD_MS = 1200
FLASH_MS = 60
# The loop runs far faster than the events it schedules, so the flash lands
# within a few ms of where it was asked for. Qt's default coarse timers drift
# by up to 5%, which at this period would be 60 ms of error - the whole
# quantity being measured - hence PreciseTimer everywhere below.
TICK_MS = 4
MAX_OFFSET_MS = 400


class FlashPanel(QWidget):
    """A large block that lights up. Nothing else, on purpose.

    Anything with detail in it invites the eye to look *at* something, and a
    person hunting for detail reacts later than one watching a whole field
    change brightness. The flash is big and plain so it is seen, not read.
    """

    def __init__(self, accent: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent)
        self._lit = False
        # Big enough to be seen without looking straight at it - peripheral
        # vision reacts faster than a gaze hunting for a small indicator - but
        # capped so the slider and the readout stay on screen together.
        self.setMinimumHeight(130)
        self.setMaximumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    @property
    def lit(self) -> bool:
        return self._lit

    def set_lit(self, lit: bool) -> None:
        if lit != self._lit:
            self._lit = lit
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._accent if self._lit else QColor("#1b1e26"))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setPen(QColor("#0d0f14") if self._lit else QColor("#6d7688"))
        font = QFont(self.font())
        font.setPointSizeF(max(11.0, font.pointSizeF() + 2))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, tr("audio.watch_here"))
        painter.end()


class AudioSyncDialog(QDialog):
    """Dial the flash until it lands on the click, and keep the number."""

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(tr("audio.title"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(460)

        self._clicker: Optional[Clicker] = None
        self._available = audio_available()
        self._elapsed = QElapsedTimer()
        self._clicked = False
        self._flashed = False

        # What the dialog hands back; only written on Save.
        self.result_offset_ms: Optional[float] = None
        self.result_note: str = ""

        accent = palette_for(config.overlay.theme).accent
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(self._wrapped(tr("audio.intro")))
        layout.addWidget(self._wrapped(tr("audio.steps"), muted=True))

        self.panel = FlashPanel(accent, self)
        layout.addWidget(self.panel, 1)

        readout = QHBoxLayout()
        readout.addWidget(QLabel(tr("audio.offset_label"), self))
        self.value_label = QLabel(self)
        value_font = QFont(self.font())
        value_font.setPointSizeF(value_font.pointSizeF() + 6)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        readout.addWidget(self.value_label)
        readout.addStretch(1)
        self.start_button = QPushButton(tr("audio.start"), self)
        self.start_button.setCheckable(True)
        self.start_button.toggled.connect(self._on_toggle_run)
        readout.addWidget(self.start_button)
        layout.addLayout(readout)

        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, MAX_OFFSET_MS)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.setTickInterval(50)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.valueChanged.connect(self._on_offset_changed)
        layout.addWidget(self.slider)

        fine = QHBoxLayout()
        for delta in (-10, -1, 1, 10):
            button = QPushButton(f"{delta:+d}", self)
            button.setFixedWidth(52)
            button.clicked.connect(lambda _checked=False, d=delta: self._nudge(d))
            fine.addWidget(button)
        fine.addStretch(1)
        layout.addLayout(fine)

        self.hint_label = self._wrapped("", muted=True)
        layout.addWidget(self.hint_label)

        note_row = QHBoxLayout()
        note_row.addWidget(QLabel(tr("audio.device_note"), self))
        self.note_field = QLineEdit(config.audio.device_note, self)
        self.note_field.setPlaceholderText(tr("audio.device_hint"))
        self.note_field.setMaxLength(80)
        note_row.addWidget(self.note_field, 1)
        layout.addLayout(note_row)

        self.include_check = QCheckBox(tr("advanced.include_audio"), self)
        self.include_check.setChecked(config.audio.include_in_total)
        layout.addWidget(self.include_check)

        layout.addWidget(self._wrapped(tr("audio.accuracy"), muted=True))
        if spawns_process() and self._available:
            layout.addWidget(self._wrapped(tr("audio.spawn_caveat"), muted=True))
        # Always built, hidden until there is something to say: a failure that
        # only happens once playback is attempted has nowhere else to appear.
        self.failure_label = self._wrapped("")
        self.failure_label.setStyleSheet("color: palette(highlight);")
        self.failure_label.setVisible(False)
        layout.addWidget(self.failure_label)
        if not self._available:
            self._show_failure("", key="audio.unavailable")
            self.start_button.setEnabled(False)

        buttons = QHBoxLayout()
        self.clear_button = QPushButton(tr("audio.clear"), self)
        self.clear_button.clicked.connect(self._on_clear)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        cancel = QPushButton(tr("audio.close"), self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton(tr("audio.save"), self)
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

        self.slider.setValue(int(round(config.audio.offset_ms)))
        self._on_offset_changed(self.slider.value())

    # ------------------------------------------------------------- helpers
    def _wrapped(self, text: str, muted: bool = False) -> QLabel:
        label = QLabel(text, self)
        label.setWordWrap(True)
        if muted:
            label.setStyleSheet("color: palette(mid);")
        return label

    @property
    def offset_ms(self) -> int:
        return int(self.slider.value())

    def _nudge(self, delta: int) -> None:
        self.slider.setValue(self.slider.value() + delta)

    def _on_offset_changed(self, value: int) -> None:
        self.value_label.setText(tr("audio.readout", ms=value))
        self.hint_label.setText(
            tr("audio.hint_zero") if value == 0 else tr("audio.hint_adjusting"))

    # -------------------------------------------------------------- running
    def _show_failure(self, detail: str, key: str = "audio.failed") -> None:
        """Say that no sound came out, and what the system said about it.

        Two different failures, so two different sentences: no player found
        before anything started is not the same as playback refusing once it
        did, and telling a Windows user their machine has no audio program
        would send them looking for the wrong thing.
        """
        text = tr(key)
        if detail:
            text = f"{text}\n{detail}"
        self.failure_label.setText(text)
        self.failure_label.setVisible(True)
        # Also on the report, so "I could not calibrate Bluetooth" is visible
        # later, from the history window, without reopening this dialog.
        HEALTH.degraded(AUDIO, detail)

    def _on_toggle_run(self, running: bool) -> None:
        if running and not self._available:
            self.start_button.setChecked(False)
            return
        self.start_button.setText(tr("audio.stop") if running else tr("audio.start"))
        if running:
            if self._clicker is None:
                self._clicker = Clicker()
            self._clicked = False
            self._flashed = False
            self._elapsed.start()
            self._timer.start()
        else:
            self._timer.stop()
            self.panel.set_lit(False)
            if self._clicker is not None:
                self._clicker.stop()

    def _tick(self) -> None:
        elapsed = self._elapsed.elapsed()
        if elapsed >= PERIOD_MS:
            # Restart rather than subtract: a cycle that ran long because the
            # machine was busy should not push every later cycle out with it.
            self._elapsed.restart()
            elapsed = 0
            self._clicked = False
            self._flashed = False
            self.panel.set_lit(False)

        if not self._clicked:
            self._clicked = True
            if self._clicker is not None and self._clicker.play():
                HEALTH.working(AUDIO)     # a click came out; stop reporting it
            elif self._clicker is not None:
                # Playback died after the dialog opened - stop rather than let
                # someone calibrate against a silence, and say why. Greying the
                # button out on its own leaves a dialog that does nothing and
                # no way to find out what went wrong.
                self._available = False
                self.start_button.setChecked(False)
                self.start_button.setEnabled(False)
                self._show_failure(self._clicker.last_error)
                return

        offset = self.offset_ms
        if not self._flashed and elapsed >= offset:
            self._flashed = True
            self.panel.set_lit(True)
        elif self._flashed and self.panel.lit and elapsed >= offset + FLASH_MS:
            self.panel.set_lit(False)

    # -------------------------------------------------------------- results
    def _on_clear(self) -> None:
        self.slider.setValue(0)
        self.note_field.clear()
        self.result_offset_ms = 0.0
        self.result_note = ""
        self.accept()

    def _on_save(self) -> None:
        self.result_offset_ms = float(self.offset_ms)
        self.result_note = self.note_field.text().strip()
        self.accept()

    def apply_to(self, config: Config) -> bool:
        """Write what was measured into the config. False if nothing was."""
        if self.result_offset_ms is None:
            return False
        config.audio.offset_ms = self.result_offset_ms
        config.audio.device_note = self.result_note
        config.audio.include_in_total = self.include_check.isChecked()
        # Zero means "cleared", and a cleared calibration has no date.
        config.audio.measured_at = time.time() if self.result_offset_ms > 0 else 0.0
        return True

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._timer.stop()
        if self._clicker is not None:
            self._clicker.close()
            self._clicker = None
        super().closeEvent(event)

    def done(self, code: int) -> None:  # noqa: N802 - Qt naming
        self._timer.stop()
        if self._clicker is not None:
            self._clicker.close()
            self._clicker = None
        super().done(code)
