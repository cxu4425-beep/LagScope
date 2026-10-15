"""The screen-to-ears measurement: the click, the config, and the timing loop.

None of this can be checked by listening on the machine it was written on -
there is no audio device here - so what is testable is everything up to the
speaker: that the WAV is a real WAV, that the offset survives a round trip
through the config file, that it reaches the total exactly once, and that the
dialog's loop puts the flash where it promises to.
"""

import io
import os
import struct
import sys
import wave

import pytest

from lagscope import audio
from lagscope.config import Config
from lagscope.models import LatencySample


# ------------------------------------------------------------------ the click
def _samples(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as handle:
        frames = handle.readframes(handle.getnframes())
        return list(struct.unpack("<%dh" % (len(frames) // 2), frames))


def test_click_is_a_real_wav_file():
    data = audio.click_wav()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == audio.SAMPLE_RATE


def test_click_length_matches_the_duration_asked_for():
    with wave.open(io.BytesIO(audio.click_wav(duration_ms=20))) as handle:
        expected = audio.SAMPLE_RATE * 20 / 1000.0
        assert abs(handle.getnframes() - expected) <= 1


def test_click_fades_in_and_out_so_the_speaker_does_not_pop():
    """A rectangular window would add a click of its own at each edge - a
    second sound arriving at a different time from the one being measured."""
    values = _samples(audio.click_wav())
    peak = max(abs(v) for v in values)
    assert peak > 1000                      # there is actually a sound in there
    assert abs(values[0]) < peak * 0.05     # and it starts and ends quietly
    assert abs(values[-1]) < peak * 0.05


def test_click_amplitude_is_respected():
    loud = max(abs(v) for v in _samples(audio.click_wav(amplitude=0.8)))
    quiet = max(abs(v) for v in _samples(audio.click_wav(amplitude=0.2)))
    assert loud > quiet * 2


def test_click_survives_silly_arguments():
    assert len(_samples(audio.click_wav(duration_ms=0))) >= 1
    assert max(_samples(audio.click_wav(amplitude=5.0))) <= 32767
    assert set(_samples(audio.click_wav(amplitude=-1.0))) == {0}


# ----------------------------------------------------------------- playability
def test_posix_player_prefers_paplay(monkeypatch):
    monkeypatch.setattr(audio.shutil, "which",
                        lambda name: "/usr/bin/" + name if name in ("aplay", "paplay") else None)
    assert audio.posix_player()[0] == "/usr/bin/paplay"


def test_posix_player_falls_through_to_whatever_exists(monkeypatch):
    monkeypatch.setattr(audio.shutil, "which",
                        lambda name: "/usr/bin/ffplay" if name == "ffplay" else None)
    assert audio.posix_player()[0] == "/usr/bin/ffplay"


def test_no_player_means_not_available(monkeypatch):
    monkeypatch.setattr(audio.sys, "platform", "linux")
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    assert audio.posix_player() is None
    assert audio.available() is False


def test_only_windows_avoids_the_process_launch(monkeypatch):
    monkeypatch.setattr(audio.sys, "platform", "win32")
    assert audio.spawns_process() is False
    monkeypatch.setattr(audio.sys, "platform", "linux")
    assert audio.spawns_process() is True


@pytest.mark.skipif(sys.platform == "win32", reason="posix playback path")
def test_clicker_writes_one_file_and_reuses_it(monkeypatch, tmp_path):
    spawned = []

    class FakeProcess:
        def poll(self): return 0
        def terminate(self): pass

    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/paplay")
    monkeypatch.setattr(audio.subprocess, "Popen",
                        lambda cmd, **kw: spawned.append(cmd) or FakeProcess())
    clicker = audio.Clicker()
    assert clicker.play() and clicker.play()
    assert len(spawned) == 2
    # The same temporary file both times, not one per click.
    assert spawned[0] == spawned[1]
    path = spawned[0][-1]
    assert os.path.exists(path)
    clicker.close()
    assert not os.path.exists(path)


@pytest.mark.skipif(sys.platform == "win32", reason="posix playback path")
def test_clicker_reports_failure_rather_than_raising(monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    clicker = audio.Clicker()
    assert clicker.play() is False
    clicker.close()


# --------------------------------------------------------------------- config
def test_offset_survives_a_round_trip_through_the_config_file():
    config = Config()
    config.audio.offset_ms = 168.0
    config.audio.device_note = "WH-1000XM4"
    restored = Config.from_dict(config.to_dict())
    assert restored.audio.offset_ms == 168.0
    assert restored.audio.device_note == "WH-1000XM4"
    assert restored.audio.measured is True


def test_absurd_offsets_are_clamped_away():
    config = Config()
    config.audio.offset_ms = 99999.0
    config.audio.device_note = "x" * 500
    config = config.sanitized()
    assert config.audio.offset_ms == 500.0
    assert len(config.audio.device_note) == 80


def test_a_fresh_config_has_nothing_measured():
    assert Config().audio.measured is False


# ----------------------------------------------------- reaching the total once
class _FakeMonitor:
    """Just enough of MonitorWorker for the one method under test."""

    def __init__(self, config):
        import threading
        self._config = config
        self._lock = threading.Lock()


def _with_audio(config, sample):
    from lagscope.monitor import MonitorWorker

    return MonitorWorker._with_audio(_FakeMonitor(config), sample)


def test_measured_offset_is_added_to_the_total():
    config = Config()
    config.audio.offset_ms = 170.0
    out = _with_audio(config, LatencySample(total_ms=1000.0))
    assert out.total_ms == 1170.0
    assert out.audio_ms == 170.0


def test_offset_is_reported_but_not_added_when_switched_off():
    config = Config()
    config.audio.offset_ms = 170.0
    config.audio.include_in_total = False
    out = _with_audio(config, LatencySample(total_ms=1000.0))
    assert out.total_ms == 1000.0
    assert out.audio_ms == 170.0


def test_an_uncalibrated_machine_is_left_completely_alone():
    out = _with_audio(Config(), LatencySample(total_ms=1000.0))
    assert out.total_ms == 1000.0
    assert out.audio_ms is None


def test_a_failed_round_does_not_gain_a_total():
    """"About 170 ms" is not an answer to "is the stream up?"."""
    config = Config()
    config.audio.offset_ms = 170.0
    out = _with_audio(config, LatencySample(total_ms=None, ok=False))
    assert out.total_ms is None
    assert out.audio_ms == 170.0


# ------------------------------------------------------------ the timing loop
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _FakeClock:
    def __init__(self): self.t = 0
    def start(self): self.t = 0
    def restart(self): self.t = 0
    def elapsed(self): return self.t


class _FakeClicker:
    def __init__(self): self.plays = 0; self.last_error = ""
    def play(self): self.plays += 1; return True
    def stop(self): pass
    def close(self): pass


def _run_one_cycle(dialog, clock, upto):
    """Step the loop a millisecond at a time and record what happened when."""
    events = []
    lit = False
    for now in range(upto):
        clock.t = now
        before = dialog._clicker.plays
        dialog._tick()
        if dialog._clicker.plays > before:
            events.append(("click", now))
        if dialog.panel.lit != lit:
            lit = dialog.panel.lit
            events.append(("flash_on" if lit else "flash_off", now))
    return events


@pytest.mark.parametrize("offset", [0, 60, 150, 300])
def test_flash_lands_exactly_the_offset_after_the_click(qt_app, offset):
    from lagscope.ui.audiosync import AudioSyncDialog, FLASH_MS, PERIOD_MS

    dialog = AudioSyncDialog(Config())
    dialog._elapsed = clock = _FakeClock()
    dialog._clicker = _FakeClicker()
    dialog._available = True
    dialog.slider.setValue(offset)
    dialog._clicked = False
    dialog._flashed = False

    events = _run_one_cycle(dialog, clock, PERIOD_MS)
    kinds = [name for name, _ in events]
    times = dict(events)

    assert kinds == ["click", "flash_on", "flash_off"] if offset else kinds[0] == "click"
    assert times["click"] == 0
    # This is the whole measurement: the person reads the offset off the slider
    # believing the flash is that much later than the click.
    assert times["flash_on"] == offset
    assert times["flash_off"] == offset + FLASH_MS
    dialog.close()


def test_the_cycle_repeats(qt_app):
    from lagscope.ui.audiosync import AudioSyncDialog, PERIOD_MS

    dialog = AudioSyncDialog(Config())
    dialog._elapsed = clock = _FakeClock()
    dialog._clicker = _FakeClicker()
    dialog._available = True
    dialog.slider.setValue(100)
    dialog._clicked = False
    dialog._flashed = False

    for now in range(PERIOD_MS):
        clock.t = now
        dialog._tick()
    assert dialog._clicker.plays == 1
    clock.t = PERIOD_MS        # the wrap
    dialog._tick()
    assert dialog._clicker.plays == 2
    dialog.close()


def test_the_period_leaves_room_for_the_largest_offset():
    """A flash scheduled past the end of the cycle would never be shown."""
    from lagscope.ui import audiosync

    assert audiosync.MAX_OFFSET_MS + audiosync.FLASH_MS < audiosync.PERIOD_MS


def test_silence_stops_the_run_rather_than_calibrating_against_nothing(qt_app):
    from lagscope.ui.audiosync import AudioSyncDialog

    class _DeadClicker(_FakeClicker):
        def play(self):
            self.last_error = "the audio device is not available"
            return False

    dialog = AudioSyncDialog(Config())
    dialog._elapsed = _FakeClock()
    dialog._clicker = _DeadClicker()
    dialog._available = True
    dialog.start_button.setEnabled(True)
    dialog._clicked = False
    dialog._tick()
    assert dialog._available is False
    assert dialog.start_button.isEnabled() is False
    # and it says so, rather than leaving a dead button with no explanation.
    # isHidden(), not isVisible(): a child of a dialog that was never shown
    # reports invisible however its own flag is set.
    assert not dialog.failure_label.isHidden()
    assert "not available" in dialog.failure_label.text()
    dialog.close()


def test_saving_records_what_was_measured_and_when(qt_app):
    from lagscope.ui.audiosync import AudioSyncDialog

    config = Config()
    dialog = AudioSyncDialog(config)
    dialog.slider.setValue(175)
    dialog.note_field.setText("  Buds Pro  ")
    dialog._on_save()
    assert dialog.apply_to(config) is True
    assert config.audio.offset_ms == 175.0
    assert config.audio.device_note == "Buds Pro"
    assert config.audio.measured_at > 0
    dialog.close()


def test_clearing_wipes_the_date_too(qt_app):
    from lagscope.ui.audiosync import AudioSyncDialog

    config = Config()
    config.audio.offset_ms = 175.0
    config.audio.measured_at = 1_700_000_000.0
    config.audio.device_note = "old headphones"
    dialog = AudioSyncDialog(config)
    dialog._on_clear()
    assert dialog.apply_to(config) is True
    assert config.audio.offset_ms == 0.0
    assert config.audio.device_note == ""
    # A cleared calibration with a date on it would look like a real one.
    assert config.audio.measured_at == 0.0
    dialog.close()


def test_cancelling_changes_nothing(qt_app):
    from lagscope.ui.audiosync import AudioSyncDialog

    config = Config()
    config.audio.offset_ms = 120.0
    dialog = AudioSyncDialog(config)
    dialog.slider.setValue(300)
    assert dialog.apply_to(config) is False      # never saved
    assert config.audio.offset_ms == 120.0
    dialog.close()


# ------------------------------------------------------- the Windows path
class _FakeWinsound:
    """Windows' winsound, with the one rule that matters here.

    CPython's PC/winsound.c refuses SND_MEMORY together with SND_ASYNC
    outright - an async call would return while still holding a buffer it does
    not own - and raises RuntimeError. The real module was shipped for three
    releases doing exactly that, and the failure was invisible from any machine
    a test could run on. This stands in for it.
    """

    SND_ASYNC = 0x0001
    SND_NODEFAULT = 0x0002
    SND_MEMORY = 0x0004
    SND_PURGE = 0x0040
    SND_FILENAME = 0x00020000

    def __init__(self):
        self.calls = []

    def PlaySound(self, sound, flags):  # noqa: N802 - the real name
        if flags & self.SND_MEMORY and flags & self.SND_ASYNC:
            raise RuntimeError("Cannot play asynchronously from memory")
        self.calls.append((sound, flags))


@pytest.fixture
def windows(monkeypatch):
    fake = _FakeWinsound()
    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", fake)
    return fake


def test_the_click_plays_on_windows(windows):
    """The whole feature rested on this call, and it raised every time."""
    clicker = audio.Clicker()
    assert clicker.play() is True
    assert clicker.last_error == ""
    assert len(windows.calls) == 1
    clicker.close()


def test_windows_plays_from_a_file_not_from_memory(windows):
    clicker = audio.Clicker()
    clicker.play()
    sound, flags = windows.calls[0]

    assert isinstance(sound, str) and os.path.exists(sound)
    assert flags & _FakeWinsound.SND_FILENAME
    assert flags & _FakeWinsound.SND_ASYNC
    # The combination CPython rejects. Asserted directly, because the symptom
    # of getting it wrong is a greyed-out button on someone else's machine.
    assert not (flags & _FakeWinsound.SND_MEMORY)
    clicker.close()


def test_the_file_windows_plays_is_the_click(windows):
    clicker = audio.Clicker()
    clicker.play()
    sound, _flags = windows.calls[0]
    with open(sound, "rb") as handle:
        assert handle.read() == clicker.wav
    clicker.close()


def test_windows_reuses_one_file_across_clicks(windows):
    clicker = audio.Clicker()
    clicker.play()
    clicker.play()
    assert windows.calls[0][0] == windows.calls[1][0]
    clicker.close()


def test_the_temporary_file_is_cleaned_up(windows):
    clicker = audio.Clicker()
    clicker.play()
    path = windows.calls[0][0]
    clicker.close()
    assert not os.path.exists(path)


def test_a_failure_says_why(monkeypatch):
    """A silently greyed-out button leaves someone staring at a dialog that
    does nothing, with no way to find out what went wrong."""
    class _Broken(_FakeWinsound):
        def PlaySound(self, sound, flags):
            raise RuntimeError("the audio device is not available")

    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", _Broken())
    clicker = audio.Clicker()
    assert clicker.play() is False
    assert "not available" in clicker.last_error
    clicker.close()


def test_headphones_do_not_delay_a_round_trip():
    """The offset belongs in how late a stream reaches your ears. It has
    nothing to do with how long a packet takes to come back, and a ping with
    170 ms added would disagree with every other tool on the machine."""
    from lagscope.models import KIND_APP, KIND_NETWORK, KIND_TARGET

    config = Config()
    config.audio.offset_ms = 170.0
    for kind in (KIND_NETWORK, KIND_APP, KIND_TARGET):
        out = _with_audio(config, LatencySample(total_ms=20.0, kind=kind))
        assert out.total_ms == 20.0, kind
        assert out.audio_ms == 170.0          # still reported, just not added
