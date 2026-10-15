#!/usr/bin/env python3
"""Regenerate the animated overlay demo used by README.md.

    python docs/make_demo_gif.py

Frames come from the real OverlayWindow rendering real LatencySample objects -
the same paint code that runs on a desktop - driven by a scripted sequence
instead of a live connection, so the picture is honest about what the widget
looks like without claiming to be a recording of a particular session.

Runs headless (offscreen Qt), so it works over SSH and in CI. Needs Pillow.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LAGSCOPE_CONFIG_DIR", tempfile.mkdtemp(prefix="lagscope-gif-"))

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lagscope.config import Config  # noqa: E402
from lagscope.i18n import set_language  # noqa: E402
from lagscope.models import (  # noqa: E402
    KIND_NETWORK, KIND_TARGET, ExtraResult, LatencySample, RollingStats,
)
from lagscope.probes.display import DisplayProbe  # noqa: E402
from lagscope.ui.overlay import OverlayWindow  # noqa: E402

OUT = ROOT / "docs" / "images" / "overlay-demo.gif"
FRAMES = 64
FRAME_MS = 110

EXTRAS = [
    ExtraResult(key="a", label="路由器", kind=KIND_TARGET, ident="192.168.1.1",
                rtt_ms=2.1, ok=True),
    ExtraResult(key="b", label="DNS 8.8.8.8", kind=KIND_TARGET, ident="8.8.8.8",
                rtt_ms=28.0, ok=True),
]


def load(index: int) -> float:
    """0 when the line is quiet, up to 1 while someone in the house downloads."""
    if 26 <= index < 42:
        return math.sin((index - 26) / 16.0 * math.pi)
    return 0.0


def story(index: int) -> float:
    """A calm stretch, a spike that pushes it into the red, then recovery.

    The spike comes with the download speed shooting up - someone started a
    download - while the router beside it stays green: the whole point of
    the app on one card. Showing only the calm part would be a worse
    advertisement than showing what the thing is actually for.
    """
    calm = 14 + math.sin(index / 5.0) * 3
    return calm + load(index) * 210


def frame_image(window: OverlayWindow, scratch: Path, index: int) -> Image.Image:
    """Grab the widget as a PIL image, via a scratch PNG Qt is happy to write."""
    target = scratch / f"frame-{index:03d}.png"
    window.grab().save(str(target), "PNG")
    with Image.open(target) as opened:
        return opened.convert("RGB")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    set_language("zh_TW")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    config = Config()
    config.overlay.scale = 1.15
    window = OverlayWindow(config, DisplayProbe())
    window.show()
    window.set_extras(EXTRAS)
    window.set_room_label("網路連線")

    stats = RollingStats(120)
    random.seed(11)
    scratch = Path(tempfile.mkdtemp(prefix="lagscope-frames-"))
    images = []
    for index in range(FRAMES):
        total = story(index) + random.random() * 4
        sample = LatencySample(
            network_ms=total,
            total_ms=total,
            ok=True,
            estimated=False,
            kind=KIND_NETWORK,
            method="tcp",
            host="1.1.1.1:443",
            title="Cloudflare 1.1.1.1",
            rtt_to_edge=True,
            down_mbps=2.5 + random.random() * 1.5 + load(index) * 88.0,
            up_mbps=0.4 + random.random() * 0.3,
        )
        stats.append(sample)
        window.update_sample(sample, stats)
        QApplication.processEvents()
        images.append(frame_image(window, scratch, index))

    # The first frames only have a couple of samples in the sparkline, which
    # looks broken rather than empty; start once the window has filled in.
    images = images[8:]

    # The overlay is flat colour and text, so one shared palette keeps the
    # file small. It has to be built from the whole story rather than the first
    # frame: a palette taken from a calm green frame has no red in it, and the
    # spike - the entire point of the demo - would come out amber.
    montage = Image.new("RGB", (images[0].width, images[0].height * len(images)))
    for row, image in enumerate(images):
        montage.paste(image, (0, row * images[0].height))
    palette = montage.quantize(colors=64, method=Image.MEDIANCUT)
    frames = [image.quantize(palette=palette, dither=Image.Dither.NONE)
              for image in images]
    frames[0].save(
        OUT, save_all=True, append_images=frames[1:], duration=FRAME_MS, loop=0,
        optimize=True,
    )
    print(f"{OUT}  ({OUT.stat().st_size // 1024} KB, {len(images)} frames)")
    for leftover in scratch.glob("*.png"):
        leftover.unlink()
    scratch.rmdir()
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
