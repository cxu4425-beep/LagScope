"""Fetch and install the new version, instead of pointing at a web page.

Telling someone a new version exists and then making them find a browser, a
releases page, the right file among four, and a download folder is most of the
work left undone. This does that part.

It is also the one feature here that downloads something and then *runs* it,
so the rules are deliberately strict and the failure mode is deliberately dull:

* **The download must come from GitHub.** The URL is taken from the releases
  API, not from anything a user typed, and its host is checked against a fixed
  list anyway. An unexpected answer from the API cannot redirect this to
  somewhere else.
* **The bytes must match the digest the API published.** The hash is computed
  while writing and compared before anything is run. No digest published means
  no automatic install - the update is offered as a link instead. Running an
  unverified executable to save someone a click is not a trade worth making.
* **Only the installed build updates itself.** A portable copy is left alone:
  replacing a running executable in place is a rewrite of the file someone is
  executing, and getting it wrong leaves them with no working app at all. They
  get the download page, which is what they had before.

The handoff matters as much as the download. Windows will not replace a
running executable, so the app starts the installer and then quits at once,
leaving nothing locked. That is also why the installer carries ``AppMutex``:
when the update is *not* driven from in here, it needs to notice by itself.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from . import APP_NAME, __version__

LOG = logging.getLogger(__name__)

# Where release assets may be served from. Anything else is refused outright.
ALLOWED_HOSTS = (
    "github.com",
    "www.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "api.github.com",
)
# The Windows installer is the only asset this can hand over to.
INSTALLER_ASSET = "LagScope-setup.exe"
MAX_BYTES = 250 * 1024 * 1024
CHUNK = 128 * 1024


@dataclass(frozen=True)
class Asset:
    """One downloadable file from a release, and how to know it is intact."""

    name: str = ""
    url: str = ""
    size: int = 0
    sha256: str = ""            # lowercase hex, "" when the API published none

    @property
    def verifiable(self) -> bool:
        return len(self.sha256) == 64


def parse_assets(payload: dict) -> list:
    """Read the asset list out of a releases API response."""
    out = []
    for item in (payload or {}).get("assets") or ():
        if not isinstance(item, dict):
            continue
        digest = str(item.get("digest") or "")
        if digest.startswith("sha256:"):
            digest = digest[len("sha256:"):].strip().lower()
        else:
            digest = ""
        out.append(Asset(
            name=str(item.get("name") or ""),
            url=str(item.get("browser_download_url") or ""),
            size=int(item.get("size") or 0),
            sha256=digest,
        ))
    return out


def pick_installer(assets) -> Optional[Asset]:
    """The Windows installer, if this release published one."""
    for asset in assets or ():
        if asset.name == INSTALLER_ASSET and asset.url:
            return asset
    return None


def host_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme != "https":
        return False
    return (parsed.hostname or "").lower() in ALLOWED_HOSTS


def app_directory() -> str:
    """The folder the running program lives in (the exe's, when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def installed_by_installer(directory: Optional[str] = None) -> bool:
    """True when this copy was put here by the Inno Setup installer.

    Inno always leaves its uninstaller beside the program, so its presence is
    the marker - no registry key to go stale and no flag to write.
    """
    if not sys.platform.startswith("win"):
        return False
    folder = directory if directory is not None else app_directory()
    try:
        return any(name.lower().startswith("unins") and name.lower().endswith(".exe")
                   for name in os.listdir(folder))
    except OSError:
        return False


def can_self_update(asset: Optional[Asset], directory: Optional[str] = None) -> bool:
    """Every condition that must hold before an executable is downloaded."""
    return bool(
        asset is not None
        and asset.verifiable                 # nothing unverified is ever run
        and host_allowed(asset.url)
        and installed_by_installer(directory)
    )


@dataclass(frozen=True)
class DownloadResult:
    path: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.path) and not self.error


def download(asset: Asset, directory: Optional[str] = None,
             on_progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None,
             timeout_s: float = 30.0) -> DownloadResult:
    """Fetch the asset, hashing as it goes, and refuse anything that differs."""
    if not asset or not asset.url:
        return DownloadResult(error="no-asset")
    if not host_allowed(asset.url):
        return DownloadResult(error="untrusted-host")
    if not asset.verifiable:
        return DownloadResult(error="no-digest")

    folder = directory or tempfile.mkdtemp(prefix="lagscope-update-")
    os.makedirs(folder, exist_ok=True)
    # ".part" until it has been verified, so a half download can never be run.
    partial = os.path.join(folder, asset.name + ".part")
    final = os.path.join(folder, asset.name)

    request = urllib.request.Request(
        asset.url,
        headers={"Accept": "application/octet-stream",
                 "User-Agent": f"{APP_NAME}/{__version__}"},
    )
    digest = hashlib.sha256()
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            # A redirect off GitHub would be a redirect away from the checks.
            if not host_allowed(response.geturl()):
                return DownloadResult(error="untrusted-redirect")
            total = asset.size or int(response.headers.get("Content-Length") or 0)
            with open(partial, "wb") as handle:
                while True:
                    if cancelled is not None and cancelled():
                        return DownloadResult(error="cancelled")
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_BYTES:
                        return DownloadResult(error="too-large")
                    digest.update(chunk)
                    handle.write(chunk)
                    if on_progress is not None:
                        on_progress(written, total)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return DownloadResult(error=str(exc)[:160])
    finally:
        if not os.path.exists(partial):
            pass
        elif written <= 0:
            _quietly_remove(partial)

    if asset.size and written != asset.size:
        _quietly_remove(partial)
        return DownloadResult(error="wrong-size")
    if digest.hexdigest() != asset.sha256:
        # The published hash is the only thing standing between a download and
        # an execution, so a mismatch discards the file rather than warning.
        _quietly_remove(partial)
        return DownloadResult(error="checksum-mismatch")

    try:
        os.replace(partial, final)
    except OSError as exc:
        return DownloadResult(error=str(exc)[:160])
    return DownloadResult(path=final)


def _quietly_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# PyInstaller's onefile bootloader passes state to its own child through the
# environment, and children inherit it. Anything we launch that is *itself* a
# onefile build would read these and conclude it is such a child.
PYI_ENVIRONMENT = ("_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE",
                   "_PYI_PARENT_PROCESS_LEVEL", "_PYI_SPLASH_IPC",
                   "_PYI_LINUX_PROCESS_NAME", "_MEIPASS2")


def clean_environment(source=None) -> dict:
    """The environment minus PyInstaller's private variables.

    The installer inherits whatever we hand it, and then hands that on to the
    copy of the app it launches from its "run now" checkbox. With
    _PYI_PARENT_PROCESS_LEVEL still set, that fresh app decides it must be a
    onefile child process and checks that its parent runs the same executable.
    Its parent is the installer, so it does not - and the app that has just
    finished installing opens with "Security validation failure: parent
    process has different executable!" instead.

    Starting it from the Start menu works, because Explorer's environment
    never had these in it. This makes the installer's environment look the
    same way.
    """
    environment = dict(os.environ if source is None else source)
    for name in PYI_ENVIRONMENT:
        environment.pop(name, None)
    # A future bootloader may add more; the prefix is the contract.
    for name in [key for key in environment if key.startswith("_PYI_")]:
        environment.pop(name, None)
    return environment


def launch_installer(path: str, silent: bool = False) -> bool:
    """Start the downloaded installer and return, so the caller can quit.

    The caller *must* quit straight after: Windows will not let the installer
    replace an executable that is still running, which is the whole reason this
    does not wait for it.
    """
    if not path or not os.path.exists(path):
        return False
    arguments = [path]
    if silent:
        arguments += ["/SILENT", "/NOCANCEL"]
    # /NORESTARTAPPLICATIONS, not /RESTARTAPPLICATIONS: Restart Manager would
    # relaunch the onefile *child* process, which then fails PyInstaller's
    # parent-executable check and shows a security error instead of the app.
    # The installer's own "run now" step brings it back - and only does so
    # correctly because of the scrubbed environment below, which the same
    # check would otherwise trip over for a different reason.
    arguments += ["/NORESTART", "/NORESTARTAPPLICATIONS"]
    try:
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(arguments, close_fds=True, creationflags=creationflags,
                         env=clean_environment())
        return True
    except (OSError, ValueError) as exc:
        LOG.warning("could not start the installer: %s", exc)
        return False
