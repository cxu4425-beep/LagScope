"""Status bar / system tray icon.

The icon itself is redrawn with the current latency, so the number is readable
without opening anything - that is the "keep it in the status bar" mode. The
overlay is the "keep it on the Bilibili window" mode; both can run at once.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from .. import APP_NAME
from ..config import Config
from ..i18n import tr
from .. import presentation
from ..models import LatencySample
from .icons import app_icon, value_icon
from .theme import color_for_level, format_ms_short, palette_for


class TrayIcon(QSystemTrayIcon):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_icon(), parent)
        self._config = config
        self._last_key: tuple = ()
        self.setToolTip(APP_NAME)

    def apply_config(self, config: Config) -> None:
        self._config = config
        self._last_key = ()
        if not config.tray.show_value_in_icon:
            self.setIcon(app_icon())

    def set_menu(self, menu: QMenu) -> None:
        self.setContextMenu(menu)

    def update_sample(self, sample: Optional[LatencySample], status_text: str,
                      stats=None, usage_line: str = "") -> None:
        palette = palette_for(self._config.overlay.theme)
        value = sample.total_ms if (sample and sample.ok) else None
        level = presentation.level(value, self._config.thresholds,
                                   sample.kind if sample else None)
        color = color_for_level(palette, level)

        if self._config.tray.show_value_in_icon:
            text = format_ms_short(value)
            key = (text, color)
            if key != self._last_key:
                self._last_key = key
                self.setIcon(value_icon(text, color))

        self.setToolTip(presentation.tooltip(sample, status_text, stats, APP_NAME,
                                             usage_line))
