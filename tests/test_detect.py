"""Auto-detection: URLs, browser history, window titles, the bridge, and the
priority rules that combine them."""

import json
import sqlite3
import time
import urllib.error
import urllib.request

import pytest

from lagscope.config import DetectConfig
from lagscope.detect import client as client_source
from lagscope.detect import clipboard as clipboard_source
from lagscope.detect import history as history_source
from lagscope.detect import titles as title_source
from lagscope.detect.bridge import BridgeServer
from lagscope.detect.manager import AutoDetector
from lagscope.detect.urls import is_bilibili, target_from_url
from lagscope.models import KIND_LIVE, KIND_VIDEO


# ----------------------------------------------------------------------- URLs
@pytest.mark.parametrize(
    "url,kind,ident,page",
    [
        ("https://live.bilibili.com/21452505", KIND_LIVE, "21452505", 1),
        ("https://live.bilibili.com/21452505?spm_id_from=x", KIND_LIVE, "21452505", 1),
        ("https://live.bilibili.com/blanc/1234", KIND_LIVE, "1234", 1),
        ("https://live.bilibili.com/h5/9999", KIND_LIVE, "9999", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", KIND_VIDEO, "BV1GJ411x7h7", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=3", KIND_VIDEO, "BV1GJ411x7h7", 3),
        ("https://m.bilibili.com/video/av170001", KIND_VIDEO, "av170001", 1),
    ],
)
def test_watchable_urls(url, kind, ident, page):
    target = target_from_url(url, source="test")
    assert target is not None
    assert (target.kind, target.ident, target.page, target.source) == (kind, ident, page, "test")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/",
        "https://live.bilibili.com/",
        "https://space.bilibili.com/123",
        "https://www.bilibili.com/bangumi/play/ep123",   # not supported yet
        "https://evil.example.com/live.bilibili.com/1",
        "not a url",
        "",
    ],
)
def test_urls_that_are_not_watchable(url):
    assert target_from_url(url) is None


def test_is_bilibili_matches_only_real_subdomains():
    assert is_bilibili("https://live.bilibili.com/1")
    assert is_bilibili("https://bilibili.com/")
    assert not is_bilibili("https://bilibili.com.evil.net/")
    assert not is_bilibili("https://youtube.com/")


def test_a_page_number_is_carried_but_never_below_one():
    assert target_from_url("https://www.bilibili.com/video/BV1GJ411x7h7?p=0").page == 1
    assert target_from_url("https://www.bilibili.com/video/BV1GJ411x7h7?p=x").page == 1


# -------------------------------------------------------------------- history
def _chromium_db(path, rows):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE urls (id INTEGER, url TEXT, title TEXT, last_visit_time INTEGER)")
    for index, (url, title, ago_s) in enumerate(rows):
        stamp = int((time.time() - ago_s + 11_644_473_600) * 1_000_000)
        connection.execute("INSERT INTO urls VALUES (?,?,?,?)", (index, url, title, stamp))
    connection.commit()
    connection.close()
    return path


def _firefox_db(path, rows):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE moz_places (id INTEGER, url TEXT, title TEXT, last_visit_date INTEGER)")
    for index, (url, title, ago_s) in enumerate(rows):
        stamp = int((time.time() - ago_s) * 1_000_000)
        connection.execute("INSERT INTO moz_places VALUES (?,?,?,?)", (index, url, title, stamp))
    connection.commit()
    connection.close()
    return path


def test_timestamp_conversions():
    now = time.time()
    assert history_source.chromium_time_to_epoch(int((now + 11_644_473_600) * 1e6)) == pytest.approx(now, abs=1)
    assert history_source.firefox_time_to_epoch(int(now * 1e6)) == pytest.approx(now, abs=1)


def test_reads_only_bilibili_rows_newest_first(tmp_path):
    database = _chromium_db(tmp_path / "History", [
        ("https://example.com/other", "something else", 5),
        ("https://live.bilibili.com/21452505", "某某的直播间", 120),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", "某影片", 10),
    ])
    entries = history_source.read_history(database, "chrome")

    assert [entry.url for entry in entries] == [
        "https://www.bilibili.com/video/BV1GJ411x7h7",
        "https://live.bilibili.com/21452505",
    ]
    assert entries[0].browser == "chrome"


def test_reads_firefox_places(tmp_path):
    database = _firefox_db(tmp_path / "places.sqlite", [
        ("https://live.bilibili.com/777", "直播间", 30),
    ])
    entries = history_source.read_history(database, "firefox", firefox=True)
    assert entries[0].url.endswith("/777")


def test_the_original_file_is_never_opened_for_writing(tmp_path):
    database = _chromium_db(tmp_path / "History", [("https://live.bilibili.com/1", "t", 1)])
    before = database.stat().st_mtime_ns
    history_source.read_history(database, "chrome")
    assert database.stat().st_mtime_ns == before


def test_scan_drops_entries_outside_the_window(tmp_path):
    database = _chromium_db(tmp_path / "History", [
        ("https://live.bilibili.com/1", "recent", 30),
        ("https://live.bilibili.com/2", "old", 4000),
    ])
    databases = [("chrome", database, False)]

    fresh = history_source.scan(window_s=300, databases=databases)
    everything = history_source.scan(window_s=7200, databases=databases)

    assert [entry.title for entry in fresh] == ["recent"]
    assert len(everything) == 2


def test_a_broken_database_is_skipped(tmp_path):
    broken = tmp_path / "History"
    broken.write_bytes(b"this is not sqlite")
    assert history_source.scan(databases=[("chrome", broken, False)]) == []
    assert history_source.scan(databases=[("chrome", tmp_path / "missing", False)]) == []


# --------------------------------------------------------------------- titles
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("某某的直播间 - Google Chrome", "某某的直播间"),
        ("影片标题_哔哩哔哩 - Mozilla Firefox", "影片标题_哔哩哔哩"),
        ("页面 and 3 more pages - Brave", "页面"),
        ("plain title", "plain title"),
    ],
)
def test_normalize_title(raw, expected):
    assert title_source.normalize_title(raw) == expected


def test_title_matching_needs_a_real_overlap():
    windows = ["某某的直播间 - 哔哩哔哩直播 - Google Chrome", "Terminal"]
    assert title_source.title_matches("某某的直播间 - 哔哩哔哩直播", windows)
    assert not title_source.title_matches("完全不同的页面标题", windows)
    assert not title_source.title_matches("短", windows)      # too short to be evidence
    assert not title_source.title_matches("某某的直播间", [])


# --------------------------------------------------------------------- bridge
def _post(port, payload, origin="https://live.bilibili.com"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/report",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def bridge():
    server = BridgeServer(port=0)
    # Port 0 lets the OS choose a free one; read it back for the requests.
    assert server.start()
    server.port = server._server.server_address[1]
    yield server
    server.stop()


def test_bridge_accepts_a_report_from_bilibili(bridge):
    status, body = _post(bridge.port, {"url": "https://live.bilibili.com/21452505", "title": "直播间"})

    assert status == 200 and body["watched"] is True
    target = bridge.latest()
    assert target.kind == KIND_LIVE and target.ident == "21452505" and target.source == "bridge"


def test_bridge_clears_the_target_when_you_navigate_away(bridge):
    _post(bridge.port, {"url": "https://live.bilibili.com/1", "title": "t"})
    _post(bridge.port, {"url": "https://www.bilibili.com/", "title": "home"})
    assert bridge.latest() is None


def test_bridge_refuses_other_origins(bridge):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(bridge.port, {"url": "https://live.bilibili.com/1"}, origin="https://evil.example.com")
    assert excinfo.value.code == 403
    assert bridge.latest() is None


def test_bridge_reports_go_stale(bridge):
    _post(bridge.port, {"url": "https://live.bilibili.com/1", "title": "t"})
    assert bridge.latest() is not None          # fresh, with the real timeout

    # A timeout of zero trusts nothing, whatever the clock's resolution is -
    # on Windows an age of exactly 0.0 is a normal reading for a report that
    # arrived a moment ago.
    bridge.timeout_s = 0.0
    assert bridge.latest() is None


def test_bridge_rejects_junk(bridge):
    with pytest.raises(urllib.error.HTTPError):
        request = urllib.request.Request(
            f"http://127.0.0.1:{bridge.port}/report", data=b"not json",
            headers={"Content-Type": "application/json", "Origin": "https://live.bilibili.com"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=3)


# ------------------------------------------------------------------ clipboard
@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://live.bilibili.com/21452505", "https://live.bilibili.com/21452505"),
        # what the desktop client's share sheet actually puts on the clipboard
        ("【标题】 https://live.bilibili.com/21452505?share_source=copy_web",
         "https://live.bilibili.com/21452505?share_source=copy_web"),
        ("看看这个 https://www.bilibili.com/video/BV1GJ411x7h7?p=2 挺好的",
         "https://www.bilibili.com/video/BV1GJ411x7h7?p=2"),
        ("短链 https://b23.tv/AbCd123", "https://b23.tv/AbCd123"),
        ("（https://live.bilibili.com/1）", "https://live.bilibili.com/1"),
        ("no link here", None),
        ("https://youtube.com/watch?v=1", None),
        ("", None),
    ],
)
def test_extract_bilibili_url(text, expected):
    assert clipboard_source.extract_bilibili_url(text) == expected


def test_short_links_are_recognised_and_expanded():
    assert clipboard_source.is_short_link("https://b23.tv/AbCd123")
    assert not clipboard_source.is_short_link("https://live.bilibili.com/1")

    expanded = clipboard_source.expand_short_link(
        lambda url: "https://live.bilibili.com/21452505?from=b23", "https://b23.tv/AbCd123"
    )
    assert expanded.startswith("https://live.bilibili.com/21452505")


def test_a_short_link_that_cannot_be_resolved_is_dropped():
    def failing(url):
        raise OSError("no network")

    assert clipboard_source.expand_short_link(failing, "https://b23.tv/x") is None
    assert clipboard_source.expand_short_link(lambda url: None, "https://b23.tv/x") is None


def test_clipboard_text_is_capped(monkeypatch):
    padding = "x" * (clipboard_source.MAX_CLIPBOARD_CHARS + 100)
    assert clipboard_source.extract_bilibili_url(padding + "https://live.bilibili.com/1") is None


# --------------------------------------------------------------- title memory
def test_title_memory_learns_and_recalls(tmp_path):
    memory = title_source.TitleMemory(tmp_path / "titles.json")

    assert memory.remember("某某的直播间 - 哔哩哔哩", KIND_LIVE, "21452505")
    entry = memory.lookup(["某某的直播间 - 哔哩哔哩", "Explorer"])

    assert entry["kind"] == KIND_LIVE and entry["ident"] == "21452505"
    # and it survives a restart
    assert title_source.TitleMemory(tmp_path / "titles.json").lookup(["某某的直播间 - 哔哩哔哩"])


def test_title_memory_refuses_useless_titles(tmp_path):
    memory = title_source.TitleMemory(tmp_path / "titles.json")

    assert not memory.remember("哔哩哔哩", KIND_LIVE, "1")          # says nothing about the room
    assert not memory.remember("某某的直播间", KIND_LIVE, "")        # no target
    assert not memory.remember("記事本 - Notepad", KIND_LIVE, "1")   # not a Bilibili window
    assert len(memory) == 0


def test_title_memory_is_bounded(tmp_path):
    memory = title_source.TitleMemory(tmp_path / "titles.json", limit=10)
    for index in range(30):
        memory.remember(f"直播间编号 {index} - 哔哩哔哩", KIND_LIVE, str(index))
    assert len(memory) == 10
    # the newest pairs are the ones kept
    assert memory.lookup(["直播间编号 29 - 哔哩哔哩"])["ident"] == "29"
    assert memory.lookup(["直播间编号 0 - 哔哩哔哩"]) is None


def test_a_corrupt_memory_file_is_ignored(tmp_path):
    path = tmp_path / "titles.json"
    path.write_text("{not json", encoding="utf-8")
    assert len(title_source.TitleMemory(path)) == 0


# -------------------------------------------------------------------- manager
class FakeBridge:
    def __init__(self, target=None):
        self.target = target
        self.running = True
        self.port = 1
        self.timeout_s = 120.0

    def latest(self):
        return self.target

    def start(self):
        return True

    def stop(self):
        self.running = False


def _detector(monkeypatch, entries=(), titles=(), client_entries=(), **config_kwargs):
    # Detection is opt-in for a fresh install; these tests are about what it
    # does once someone has turned it on.
    config_kwargs.setdefault("enabled", True)
    config = DetectConfig(**config_kwargs)
    monkeypatch.setattr(history_source, "scan", lambda **kwargs: list(entries))
    monkeypatch.setattr(title_source, "window_titles", lambda: list(titles))
    monkeypatch.setattr(client_source.ClientScanner, "scan",
                        lambda self, **kwargs: list(client_entries))
    monkeypatch.setattr(client_source.ClientScanner, "discover", lambda self, force=False: [])
    return AutoDetector(config)


def _entry(url, title, ago_s=10):
    return history_source.HistoryEntry(url=url, title=title, visited_at=time.time() - ago_s)


def test_detector_returns_nothing_when_disabled(monkeypatch):
    detector = _detector(monkeypatch, entries=[_entry("https://live.bilibili.com/1", "t")],
                         enabled=False)
    assert detector.poll() is None


def test_detector_picks_the_newest_history_entry(monkeypatch):
    entries = [
        _entry("https://www.bilibili.com/video/BV1GJ411x7h7?p=2", "影片", ago_s=5),
        _entry("https://live.bilibili.com/21452505", "直播间", ago_s=60),
    ]
    detector = _detector(monkeypatch, entries=entries, use_titles=False)

    target = detector.poll()

    assert target.kind == KIND_VIDEO and target.ident == "BV1GJ411x7h7" and target.page == 2
    assert target.source == "history"


def test_the_window_title_wins_over_recency(monkeypatch):
    entries = [
        _entry("https://www.bilibili.com/video/BV1GJ411x7h7", "刚打开的影片", ago_s=5),
        _entry("https://live.bilibili.com/21452505", "我正在看的直播间", ago_s=600),
    ]
    detector = _detector(monkeypatch, entries=entries,
                         titles=["我正在看的直播间 - 哔哩哔哩直播 - Google Chrome"])

    target = detector.poll()

    assert target.ident == "21452505" and target.source == "history+title"


def test_the_bridge_outranks_the_history(monkeypatch):
    entries = [_entry("https://live.bilibili.com/1", "直播间")]
    detector = _detector(monkeypatch, entries=entries)
    detector._bridge = FakeBridge(target_from_url("https://live.bilibili.com/999", source="bridge"))

    target = detector.poll()

    assert target.ident == "999" and target.source == "bridge"


def test_history_scans_are_rate_limited(monkeypatch):
    calls = []

    def counting_scan(**kwargs):
        calls.append(1)
        return [_entry("https://live.bilibili.com/1", "直播间")]

    detector = _detector(monkeypatch, poll_interval_s=300)
    monkeypatch.setattr(history_source, "scan", counting_scan)

    first = detector.poll()
    second = detector.poll()

    assert len(calls) == 1                    # the second poll reused the answer
    assert second is first
    detector.poll(force=True)
    assert len(calls) == 2


def test_a_failing_history_scan_does_not_raise(monkeypatch):
    detector = _detector(monkeypatch)

    def boom(**kwargs):
        raise sqlite3.DatabaseError("locked")

    monkeypatch.setattr(history_source, "scan", boom)
    assert detector.poll(force=True) is None


def test_history_entries_that_are_not_watchable_are_ignored(monkeypatch):
    detector = _detector(monkeypatch, entries=[_entry("https://www.bilibili.com/", "首页")])
    assert detector.poll() is None


# ------------------------------------ the official desktop client, hands-free
def test_the_desktop_client_is_detected_without_any_user_action(monkeypatch):
    detector = _detector(
        monkeypatch,
        client_entries=[_entry("https://live.bilibili.com/31415926", "某某的直播间", ago_s=5)],
    )

    target = detector.poll(force=True)

    assert target.kind == KIND_LIVE and target.ident == "31415926"
    assert target.source == "client"


def test_the_client_beats_an_older_browser_page(monkeypatch):
    detector = _detector(
        monkeypatch,
        entries=[_entry("https://live.bilibili.com/111", "浏览器里的旧页面", ago_s=400)],
        client_entries=[_entry("https://live.bilibili.com/222", "客户端正在放的", ago_s=5)],
        use_titles=False,
    )

    assert detector.poll(force=True).ident == "222"


def test_a_newer_browser_page_still_wins_over_an_old_client_entry(monkeypatch):
    detector = _detector(
        monkeypatch,
        entries=[_entry("https://live.bilibili.com/111", "刚打开的网页", ago_s=5)],
        client_entries=[_entry("https://live.bilibili.com/222", "客户端很久以前", ago_s=900)],
        use_titles=False,
    )

    assert detector.poll(force=True).ident == "111"


def test_the_client_source_can_be_turned_off(monkeypatch):
    detector = _detector(
        monkeypatch,
        client_entries=[_entry("https://live.bilibili.com/222", "客户端", ago_s=5)],
        use_client=False,
    )

    assert detector.poll(force=True) is None


def test_the_client_teaches_its_window_title(monkeypatch, tmp_path):
    monkeypatch.setattr(title_source, "foreground_title", lambda: "某某的直播间 - 哔哩哔哩")
    monkeypatch.setattr(history_source, "scan", lambda **kwargs: [])
    monkeypatch.setattr(title_source, "window_titles", lambda: ["某某的直播间 - 哔哩哔哩"])
    monkeypatch.setattr(
        client_source.ClientScanner, "scan",
        lambda self, **kwargs: [_entry("https://live.bilibili.com/31415926", "", ago_s=5)],
    )
    monkeypatch.setattr(client_source.ClientScanner, "discover", lambda self, force=False: [])
    detector = AutoDetector(DetectConfig(enabled=True), memory_path=tmp_path / "titles.json")

    detector.poll(force=True)

    assert detector.remembered_titles == 1


def test_a_broken_client_folder_does_not_break_detection(monkeypatch):
    detector = _detector(monkeypatch,
                         entries=[_entry("https://live.bilibili.com/111", "网页", ago_s=5)],
                         use_titles=False)

    def boom(self, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(client_source.ClientScanner, "scan", boom)

    assert detector.poll(force=True).ident == "111"


def test_the_report_lists_every_source(monkeypatch):
    detector = _detector(
        monkeypatch,
        client_entries=[_entry("https://live.bilibili.com/31415926", "直播间", ago_s=5)],
    )

    report = detector.report()

    assert report["client"]["used"] is True
    assert report["client"]["found"][0]["id"] == "31415926"
    assert report["result"]["id"] == "31415926"
    assert set(report) >= {"client", "browser_history", "window_titles", "clipboard", "bridge"}


# ---------------------------------- the desktop client, copy-link fallback
def test_a_copied_link_switches_the_target_immediately(monkeypatch):
    detector = _detector(monkeypatch, poll_interval_s=300)   # scans are far apart

    submitted = detector.submit_clipboard("【某某直播间】 https://live.bilibili.com/7777?share_source=copy_web")

    assert submitted.kind == KIND_LIVE and submitted.ident == "7777"
    # no waiting for the next scheduled scan
    assert detector.poll().ident == "7777"
    assert detector.poll().source == "clipboard"


def test_a_copied_video_link_keeps_the_part_number(monkeypatch):
    detector = _detector(monkeypatch)
    target = detector.submit_clipboard("https://www.bilibili.com/video/BV1GJ411x7h7?p=3")
    assert target.kind == KIND_VIDEO and target.page == 3


def test_the_same_clipboard_text_is_only_acted_on_once(monkeypatch):
    detector = _detector(monkeypatch)
    text = "https://live.bilibili.com/7777"
    assert detector.submit_clipboard(text) is not None
    assert detector.submit_clipboard(text) is None


def test_clipboard_without_a_link_changes_nothing(monkeypatch):
    detector = _detector(monkeypatch)
    detector.submit_clipboard("https://live.bilibili.com/7777")
    assert detector.submit_clipboard("买菜清单：西红柿、鸡蛋") is None
    assert detector.poll().ident == "7777"


def test_clipboard_can_be_turned_off(monkeypatch):
    detector = _detector(monkeypatch, use_clipboard=False)
    assert detector.submit_clipboard("https://live.bilibili.com/7777") is None


def test_a_copied_short_link_is_resolved(monkeypatch):
    detector = _detector(monkeypatch)
    detector.set_url_resolver(lambda url: "https://live.bilibili.com/21452505?from=b23")

    target = detector.submit_clipboard("分享 https://b23.tv/AbCd123")

    assert target.kind == KIND_LIVE and target.ident == "21452505"


def test_a_short_link_without_a_resolver_is_ignored(monkeypatch):
    detector = _detector(monkeypatch)
    assert detector.submit_clipboard("https://b23.tv/AbCd123") is None


def test_copying_a_link_teaches_the_client_window_title(monkeypatch, tmp_path):
    config = DetectConfig(enabled=True)
    monkeypatch.setattr(history_source, "scan", lambda **kwargs: [])
    monkeypatch.setattr(title_source, "window_titles", lambda: ["某某的直播间 - 哔哩哔哩"])
    monkeypatch.setattr(title_source, "foreground_title", lambda: "某某的直播间 - 哔哩哔哩")
    detector = AutoDetector(config, memory_path=tmp_path / "titles.json")

    detector.submit_clipboard("https://live.bilibili.com/7777")

    # Later on, with nothing in the clipboard any more, the open client window
    # is recognised from its title alone.
    fresh = AutoDetector(config, memory_path=tmp_path / "titles.json")
    target = fresh.poll(force=True)
    assert target.ident == "7777" and target.source == "title"


def test_a_generic_client_title_teaches_nothing(monkeypatch, tmp_path):
    config = DetectConfig(enabled=True)
    monkeypatch.setattr(history_source, "scan", lambda **kwargs: [])
    monkeypatch.setattr(title_source, "window_titles", lambda: ["哔哩哔哩"])
    monkeypatch.setattr(title_source, "foreground_title", lambda: "哔哩哔哩")
    detector = AutoDetector(config, memory_path=tmp_path / "titles.json")

    detector.submit_clipboard("https://live.bilibili.com/7777")

    assert detector.remembered_titles == 0
    # the copied link still sticks, which is what keeps the client usable
    assert detector.poll(force=True).ident == "7777"


def test_an_open_window_beats_an_older_copied_link(monkeypatch):
    entries = [_entry("https://live.bilibili.com/21452505", "我正在看的直播间", ago_s=300)]
    detector = _detector(monkeypatch, entries=entries,
                         titles=["我正在看的直播间 - 哔哩哔哩直播 - Google Chrome"])
    detector.submit_clipboard("https://live.bilibili.com/7777")

    target = detector.poll(force=True)

    assert target.ident == "21452505" and target.source == "history+title"


def test_a_copied_link_beats_older_history(monkeypatch):
    entries = [_entry("https://live.bilibili.com/111", "旧的直播间", ago_s=900)]
    detector = _detector(monkeypatch, entries=entries, use_titles=False)

    detector.submit_clipboard("https://live.bilibili.com/7777")

    assert detector.poll(force=True).ident == "7777"


def test_newer_history_beats_an_older_copied_link(monkeypatch):
    detector = _detector(monkeypatch, use_titles=False)
    detector.submit_clipboard("https://live.bilibili.com/7777")
    # a browser page opened after the copy
    detector._clipboard_target = detector._clipboard_target.__class__(
        kind=KIND_LIVE, ident="7777", source="clipboard", detected_at=time.time() - 600
    )
    monkeypatch.setattr(history_source, "scan",
                        lambda **kwargs: [_entry("https://live.bilibili.com/222", "新的", ago_s=5)])

    assert detector.poll(force=True).ident == "222"
