"""Downloading and running an executable, which is the one feature here that
could do real harm if it were sloppy.

So most of these tests are about refusal: a download that does not match its
published hash, one offered over plain HTTP, one from a host that is not
GitHub, and one with no hash at all must every one of them end with nothing
executed. The happy path is a single test; the ways it must decline are many.
"""

import hashlib
import http.server
import os
import threading

import pytest

from lagscope import selfupdate
from lagscope.selfupdate import (
    Asset, INSTALLER_ASSET, can_self_update, download, host_allowed,
    installed_by_installer, parse_assets, pick_installer,
)

PAYLOAD = b"MZ" + b"pretend installer" * 500


@pytest.fixture
def server():
    """Serves PAYLOAD, so a download can be checked against a known hash."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):                          # noqa: N802 - http naming
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/{INSTALLER_ASSET}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def trusting(monkeypatch):
    """Treat the local test server as an allowed host, for the happy path."""
    monkeypatch.setattr(selfupdate, "host_allowed", lambda url: bool(url))


def _asset(url, payload=PAYLOAD, name=INSTALLER_ASSET):
    return Asset(name=name, url=url, size=len(payload),
                 sha256=hashlib.sha256(payload).hexdigest())


# ------------------------------------------------------------ reading a release
def test_the_installer_is_picked_out_of_the_asset_list():
    payload = {"assets": [
        {"name": "LagScope-linux-x64.tar.gz", "browser_download_url": "https://github.com/a",
         "size": 1, "digest": "sha256:" + "b" * 64},
        {"name": INSTALLER_ASSET, "browser_download_url": "https://github.com/b",
         "size": 2, "digest": "sha256:" + "a" * 64},
    ]}
    assets = parse_assets(payload)
    assert pick_installer(assets).name == INSTALLER_ASSET
    assert pick_installer(assets).sha256 == "a" * 64


def test_a_release_without_an_installer_offers_nothing():
    assert pick_installer(parse_assets({"assets": []})) is None
    assert pick_installer(parse_assets({})) is None


def test_an_asset_with_no_digest_is_not_verifiable():
    payload = {"assets": [{"name": INSTALLER_ASSET,
                           "browser_download_url": "https://github.com/b", "size": 2}]}
    assert pick_installer(parse_assets(payload)).verifiable is False


def test_a_digest_that_is_not_sha256_is_ignored_rather_than_trusted():
    payload = {"assets": [{"name": INSTALLER_ASSET, "browser_download_url": "https://github.com/b",
                           "size": 2, "digest": "md5:" + "a" * 32}]}
    assert pick_installer(parse_assets(payload)).sha256 == ""


def test_junk_in_the_asset_list_does_not_raise():
    assert parse_assets({"assets": ["nonsense", None, 42]}) == []


# ------------------------------------------------------------------ where from
@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://github.com/owner/repo/releases/download/v1/x.exe", True),
        ("https://objects.githubusercontent.com/x", True),
        ("http://github.com/owner/repo/x.exe", False),        # not over https
        ("https://github.com.evil.example/x.exe", False),      # lookalike host
        ("https://evil.example/x.exe", False),
        ("https://raw.githubusercontent.com/x", False),        # not a release host
        ("", False),
    ],
)
def test_only_github_release_hosts_over_https_are_accepted(url, allowed):
    assert host_allowed(url) is allowed


# ----------------------------------------------------------------- downloading
def test_a_matching_download_is_kept(tmp_path, server, trusting):
    result = download(_asset(server), directory=str(tmp_path))
    assert result.ok
    assert open(result.path, "rb").read() == PAYLOAD
    assert not os.path.exists(result.path + ".part")   # nothing half-written left


def test_a_download_whose_hash_differs_is_deleted_not_run(tmp_path, server, trusting):
    """The published hash is the only thing between a download and execution."""
    wrong = Asset(name=INSTALLER_ASSET, url=server, size=len(PAYLOAD),
                  sha256="0" * 64)
    result = download(wrong, directory=str(tmp_path))

    assert not result.ok
    assert result.error == "checksum-mismatch"
    assert list(tmp_path.iterdir()) == []           # the bytes are gone


def test_a_download_of_the_wrong_size_is_refused(tmp_path, server, trusting):
    wrong = Asset(name=INSTALLER_ASSET, url=server, size=len(PAYLOAD) + 99,
                  sha256=hashlib.sha256(PAYLOAD).hexdigest())
    result = download(wrong, directory=str(tmp_path))
    assert result.error == "wrong-size"
    assert list(tmp_path.iterdir()) == []


def test_an_asset_with_no_digest_is_never_downloaded(tmp_path, server, trusting):
    bare = Asset(name=INSTALLER_ASSET, url=server, size=len(PAYLOAD))
    assert download(bare, directory=str(tmp_path)).error == "no-digest"
    assert list(tmp_path.iterdir()) == []


def test_an_untrusted_host_is_refused_before_any_request(tmp_path):
    result = download(_asset("https://evil.example/x.exe"), directory=str(tmp_path))
    assert result.error == "untrusted-host"
    assert list(tmp_path.iterdir()) == []


def test_a_cancelled_download_leaves_nothing_to_run(tmp_path, server, trusting):
    result = download(_asset(server), directory=str(tmp_path),
                      cancelled=lambda: True)
    assert result.error == "cancelled"
    assert not os.path.exists(os.path.join(str(tmp_path), INSTALLER_ASSET))


def test_an_unreachable_server_is_reported_not_raised(tmp_path, trusting):
    result = download(_asset("http://127.0.0.1:1/x.exe"), directory=str(tmp_path))
    assert not result.ok and result.error


def test_progress_is_reported_while_downloading(tmp_path, server, trusting):
    seen = []
    download(_asset(server), directory=str(tmp_path),
             on_progress=lambda done, total: seen.append((done, total)))
    assert seen and seen[-1][0] == len(PAYLOAD)


# ------------------------------------------------------- who may update itself
def test_a_portable_copy_does_not_update_itself(tmp_path, monkeypatch):
    """No uninstaller beside it means it was unzipped, not installed."""
    monkeypatch.setattr("sys.platform", "win32")
    assert installed_by_installer(str(tmp_path)) is False


def test_an_installed_copy_is_recognised_by_its_uninstaller(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    (tmp_path / "unins000.exe").write_bytes(b"x")
    assert installed_by_installer(str(tmp_path)) is True


def test_nothing_updates_itself_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    (tmp_path / "unins000.exe").write_bytes(b"x")
    assert installed_by_installer(str(tmp_path)) is False


def test_a_missing_directory_is_not_an_error(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert installed_by_installer("/no/such/folder") is False


def test_every_condition_must_hold_before_an_executable_is_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    (tmp_path / "unins000.exe").write_bytes(b"x")
    good = _asset("https://github.com/o/r/releases/download/v1/" + INSTALLER_ASSET)

    assert can_self_update(good, str(tmp_path)) is True
    assert can_self_update(None, str(tmp_path)) is False
    assert can_self_update(Asset(name=INSTALLER_ASSET, url=good.url),
                           str(tmp_path)) is False        # no digest
    assert can_self_update(_asset("https://evil.example/x.exe"),
                           str(tmp_path)) is False        # wrong host


def test_a_portable_copy_declines_even_with_a_perfect_asset(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    good = _asset("https://github.com/o/r/releases/download/v1/" + INSTALLER_ASSET)
    assert can_self_update(good, str(tmp_path)) is False   # no uninstaller present


# ------------------------------------------------------------------ the handoff
def test_a_missing_installer_is_not_launched():
    assert selfupdate.launch_installer("/no/such/file.exe") is False
    assert selfupdate.launch_installer("") is False


def test_the_installer_is_never_asked_to_restart_through_restart_manager(tmp_path, monkeypatch):
    """Restart Manager relaunches the onefile *child* process, which then
    fails PyInstaller's parent-executable check and shows a security error
    instead of the app. The installer's own "run now" step is the way back.
    """
    path = tmp_path / INSTALLER_ASSET
    path.write_bytes(b"x")
    started = {}
    monkeypatch.setattr(selfupdate.subprocess, "Popen",
                        lambda args, **kw: started.setdefault("args", args))

    assert selfupdate.launch_installer(str(path)) is True
    assert "/NORESTARTAPPLICATIONS" in started["args"]
    assert "/RESTARTAPPLICATIONS" not in started["args"]
    assert started["args"][0] == str(path)


def test_the_installer_script_does_not_restart_applications_either():
    """The command-line flag and the script directive have to agree; either
    one alone would still let Restart Manager relaunch the child process."""
    import pathlib
    import re

    script = pathlib.Path("packaging/installer.iss").read_text(encoding="utf-8")
    directives = re.findall(r"^RestartApplications=(\w+)", script, re.MULTILINE)
    assert directives == ["no"], directives


# ------------------------------------ the environment handed to the installer
def test_pyinstaller_variables_never_reach_the_installer():
    """The installer passes its environment on to the copy of the app it
    launches from "run now". With _PYI_PARENT_PROCESS_LEVEL still set, that
    app decides it is a onefile child and checks that its parent runs the same
    executable - its parent is the installer, so it does not, and the app that
    just finished installing opens with a security error instead."""
    from lagscope.selfupdate import clean_environment

    source = {
        "PATH": "/usr/bin",
        "APPDATA": r"C:\Users\someone\AppData\Roaming",
        "_PYI_PARENT_PROCESS_LEVEL": "0",
        "_PYI_ARCHIVE_FILE": r"C:\Program Files\LagScope\LagScope.exe",
        "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI123",
        "_MEIPASS2": r"C:\Temp\_MEI123",
    }
    out = clean_environment(source)

    assert not [key for key in out if key.startswith("_PYI_")]
    assert "_MEIPASS2" not in out
    # everything the installer legitimately needs survives
    assert out["PATH"] == "/usr/bin"
    assert out["APPDATA"] == source["APPDATA"]


def test_a_variable_a_future_bootloader_adds_is_dropped_too():
    """The names are a moving target; the prefix is the contract."""
    from lagscope.selfupdate import clean_environment

    assert "_PYI_SOMETHING_NEW" not in clean_environment({"_PYI_SOMETHING_NEW": "1"})


def test_the_installer_is_started_with_the_scrubbed_environment(monkeypatch, tmp_path):
    """Not just that clean_environment is right, but that Popen is given it -
    the previous bug was a missing argument, not a wrong function."""
    import subprocess as sp

    from lagscope import selfupdate

    installer = tmp_path / "LagScope-setup.exe"
    installer.write_bytes(b"MZ")
    seen = {}

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen["env"] = kwargs.get("env")
        return object()

    monkeypatch.setattr(selfupdate.os, "environ",
                        {"PATH": "/usr/bin", "_PYI_PARENT_PROCESS_LEVEL": "0"})
    monkeypatch.setattr(sp, "Popen", fake_popen)

    assert selfupdate.launch_installer(str(installer)) is True

    assert seen["env"] is not None, "Popen was called without env="
    assert "_PYI_PARENT_PROCESS_LEVEL" not in seen["env"]
    assert seen["env"]["PATH"] == "/usr/bin"
    assert "/NORESTARTAPPLICATIONS" in seen["args"]
