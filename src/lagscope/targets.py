"""Deciding what to measure, in one place.

The GUI loop and the one-shot command line have to agree on this, and when the
rule lived in both of them they drifted apart. Everything Qt-free lives here so
the headless paths can use it too.
"""

from __future__ import annotations

from typing import Callable, Optional

from .models import (
    KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, WatchTarget,
)


def manual_target(config, foreground_app: Optional[Callable[[], str]] = None) -> WatchTarget:
    """What the user configured by hand, in priority order.

    ``foreground_app`` supplies the frontmost process name for "follow whichever
    app I am using"; it is injected because looking it up needs the window
    system.
    """
    kind = config.manual_kind

    # Chosen on purpose, so leftovers from another mode - a room number typed
    # once, an app picked last week - must not quietly take over.
    if kind == KIND_NETWORK:
        return WatchTarget(kind=KIND_NETWORK, source="manual")

    if kind == KIND_APP:
        name = config.app_name
        if config.app_follow_foreground and foreground_app is not None:
            name = foreground_app() or name
        if name:
            return WatchTarget(kind=KIND_APP, ident=name, source="manual")

    if kind == KIND_TARGET and config.target_host:
        return WatchTarget(kind=KIND_TARGET, ident=config.target_host,
                           page=config.target_port, source="manual")

    if kind == KIND_VIDEO and config.video_id:
        return WatchTarget(kind=KIND_VIDEO, ident=config.video_id,
                           page=config.video_page, source="manual")

    # Whatever is filled in wins when the preferred kind has nothing to measure.
    if config.room_id:
        return WatchTarget(kind=KIND_LIVE, ident=config.room_id, source="manual")
    if config.video_id:
        return WatchTarget(kind=KIND_VIDEO, ident=config.video_id,
                           page=config.video_page, source="manual")
    if config.app_name:
        return WatchTarget(kind=KIND_APP, ident=config.app_name, source="manual")
    if config.target_host:
        return WatchTarget(kind=KIND_TARGET, ident=config.target_host,
                           page=config.target_port, source="manual")
    return WatchTarget(kind=KIND_NETWORK, source="manual")


def resolve_target(config, detector=None,
                   foreground_app: Optional[Callable[[], str]] = None,
                   force_detect: bool = False) -> WatchTarget:
    """Auto-detection first (Bilibili only), then whatever was configured."""
    if config.detect.enabled and detector is not None:
        detected = detector.poll(force=force_detect)
        if detected is not None and not detected.is_empty:
            if detected.kind != KIND_VIDEO or config.detect.follow_videos:
                return detected
    return manual_target(config, foreground_app)
