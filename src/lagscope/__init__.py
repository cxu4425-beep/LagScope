"""LagScope - a latency monitor for any application, with deep Bilibili support.

A cross-platform desktop overlay that answers "how laggy is this right now?":
the round trip to whatever servers an application is talking to, and - for
Bilibili - the delay from the live edge (server) through your machine (client)
to your screen (display).
"""

__all__ = ["__version__", "APP_NAME", "APP_ID", "REPO_URL", "LEGACY_APP_NAME", "LEGACY_APP_ID"]

__version__ = "4.11.5"

APP_NAME = "LagScope"
APP_ID = "lagscope"
REPO_URL = "https://github.com/cxu4425-beep/LagScope"

# Named "Bilibili Latency Monitor" up to 1.1.1; settings are migrated from the
# old per-user folders on first run so an upgrade keeps them.
LEGACY_APP_NAME = "Bilibili Latency Monitor"
LEGACY_APP_ID = "bili-latency-monitor"
