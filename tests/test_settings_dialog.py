"""The settings dialog must give back exactly what it was given.

A mode the dialog cannot show is a mode it replaces with whatever its first
entry is the moment someone presses OK - for an unrelated reason, like
changing the theme. Internet mode was added without a dropdown entry, and
that is what would have happened to everyone using it.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from lagscope.config import Config  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(config, monkeypatch):
    from lagscope.ui import settings as settings_module

    # The app list reads the live connection table; not this test's business.
    monkeypatch.setattr("lagscope.probes.appnet.list_apps", lambda: [])
    dialog = settings_module.SettingsDialog(config)
    dialog.load_from(config)
    return dialog


@pytest.mark.parametrize("kind, detect", [
    ("network", False), ("app", False), ("target", False),
    ("live", False), ("video", False), ("live", True),
])
def test_every_mode_survives_opening_settings_and_pressing_ok(qapp, monkeypatch, kind, detect):
    config = Config()
    config.manual_kind = kind
    config.detect.enabled = detect
    config.app_name = "game.exe"
    config.target_host = "203.0.113.5"
    config.room_id = "21452505"
    config.video_id = "BV1GJ411x7h7"

    out = _dialog(config, monkeypatch).to_config()

    assert out.manual_kind == kind
    assert out.detect.enabled == detect


def test_a_fresh_config_opens_on_internet_mode(qapp, monkeypatch):
    dialog = _dialog(Config(), monkeypatch)
    assert dialog.target_combo.currentData() == "network"


def test_only_the_chosen_modes_fields_are_shown(qapp, monkeypatch):
    dialog = _dialog(Config(), monkeypatch)
    form = dialog._target_form

    def shown(widget):
        return form.isRowVisible(widget)

    assert shown(dialog.network_hint)
    assert not shown(dialog.room_edit) and not shown(dialog.target_host_edit)
    assert dialog._detect_box.isHidden()          # the Bilibili-only group

    dialog.target_combo.setCurrentIndex(dialog.target_combo.findData("target"))
    assert shown(dialog.target_host_edit) and not shown(dialog.network_hint)

    dialog.target_combo.setCurrentIndex(dialog.target_combo.findData("auto"))
    assert shown(dialog.room_edit) and not dialog._detect_box.isHidden()


def test_network_thresholds_round_trip(qapp, monkeypatch):
    config = Config()
    config.thresholds.net_good_ms = 40.0
    config.thresholds.net_warn_ms = 90.0
    out = _dialog(config, monkeypatch).to_config()
    assert (out.thresholds.net_good_ms, out.thresholds.net_warn_ms) == (40.0, 90.0)
