"""The self-test: it has to report a broken machine, not fall over on one."""

from pathlib import Path

from lagscope import selftest
from lagscope.selftest import (
    FAIL, OK, SKIP, WARN, CheckResult, _check, check_dns, check_environment,
    format_report, worst_status,
)


def test_a_check_that_raises_becomes_a_failure_not_a_crash():
    def explode(result):
        raise RuntimeError("the probe blew up")

    result = _check("boom", explode)

    assert result.status == FAIL
    assert any("the probe blew up" in line for line in result.lines)


def test_every_check_is_timed():
    result = _check("quiet", lambda r: None)
    assert result.status == OK
    assert result.lines[-1].endswith("ms)")


def test_the_environment_check_says_what_it_is_running_on():
    result = _check("environment", check_environment)
    body = " ".join(result.lines)
    assert "LagScope" in body and "python" in body


def test_a_resolver_that_answers_nothing_is_a_failure(monkeypatch):
    from lagscope.probes import path as path_module

    monkeypatch.setattr(path_module, "dns_ms", lambda host, **kwargs: None)
    result = _check("dns", check_dns)

    assert result.status == FAIL


def test_the_report_is_readable_and_counts_every_outcome():
    results = [
        CheckResult("fine", OK, ["all good"]),
        CheckResult("iffy", WARN, ["not sure"]),
        CheckResult("broken", FAIL, ["it did not work"]),
        CheckResult("later", SKIP, ["needs a room id"]),
    ]

    report = format_report(results)

    for name in ("fine", "iffy", "broken", "later"):
        assert name in report
    assert "1 ok, 1 warning(s), 1 failure(s), 1 skipped" in report
    assert "[FAIL] broken" in report
    # The privacy note is the promise the output has to keep.
    assert "no public IP" in report


def test_the_worst_outcome_decides_the_exit_code():
    assert worst_status([CheckResult("a", OK)]) == OK
    assert worst_status([CheckResult("a", OK), CheckResult("b", SKIP)]) == SKIP
    assert worst_status([CheckResult("a", SKIP), CheckResult("b", WARN)]) == WARN
    assert worst_status([CheckResult("a", WARN), CheckResult("b", FAIL)]) == FAIL


def test_the_output_never_carries_the_wifi_name():
    """The report is meant to be pasted in public; the SSID is not."""
    report = format_report([CheckResult("path tools", OK, ["default gateway: 192.168.1.1"])])
    assert "ssid" not in report.lower()


def test_a_room_check_without_a_room_is_skipped_not_failed():
    result = _check("room", lambda r: selftest.check_room(r, None, ""))
    assert result.status == SKIP


def test_the_bilibili_checks_report_the_reason_they_could_not_run():
    class Dead:
        def fetch_room_info(self, room):
            raise ConnectionError("Tunnel connection failed: 403 Forbidden")

    result = _check("room", lambda r: selftest.check_room(r, Dead(), "21452505"))

    assert result.status == FAIL
    assert any("403" in line for line in result.lines)


class _Endpoint:
    def __init__(self, host, fmt="fmp4", protocol="http_hls", qn=10000):
        self.host, self.fmt, self.protocol, self.qn = host, fmt, protocol, qn


class _StreamWithEmptyCache:
    """A probe as the self-test actually finds it.

    fetch_endpoints() returns a list without storing it; only the monitoring
    path fills the cache that hosts_available() reads. The self-test calls the
    former, so the latter is empty - which is exactly the state that produced
    "0 distinct edge(s)" against six real hostnames on a live room.
    """

    def __init__(self, endpoints):
        self._endpoints = endpoints

    def fetch_endpoints(self, room):
        return self._endpoints

    def hosts_available(self):
        return []                     # the cache the monitor would have filled

    def choose_endpoint(self, endpoints):
        return endpoints[0] if endpoints else None


def test_distinct_hosts_counts_what_is_in_front_of_it():
    endpoints = [_Endpoint("a.example"), _Endpoint("b.example"), _Endpoint("a.example"),
                 _Endpoint("")]
    assert selftest.distinct_hosts(endpoints) == ["a.example", "b.example"]
    assert selftest.distinct_hosts([]) == []
    assert selftest.distinct_hosts(None) == []


def test_the_edge_count_does_not_depend_on_a_cache_this_check_never_filled():
    stream = _StreamWithEmptyCache([
        _Endpoint("d1--ov-gotcha207.bilivideo.com"),
        _Endpoint("d1--ov-gotcha207b.bilivideo.com"),
        _Endpoint("d1--ov-gotcha07.bilivideo.com", fmt="flv"),
    ])
    result = _check("play URLs", lambda r: selftest.check_endpoints(r, stream, "32101172"))
    assert any("3 endpoint(s), 3 distinct edge(s)" in line for line in result.lines)


def test_a_pcdn_node_is_reported_even_though_the_cache_is_empty():
    """The real cost of the bug: peers[] was built from the empty cache, so
    this warning could never fire however many PCDN nodes were offered."""
    stream = _StreamWithEmptyCache([
        _Endpoint("d1--ov-gotcha207.bilivideo.com"),
        _Endpoint("xy123x45x67x89xy.mcdn.bilivideo.cn"),
    ])
    result = _check("play URLs", lambda r: selftest.check_endpoints(r, stream, "32101172"))
    assert result.status == WARN
    assert any("PCDN" in line or "peer-assisted" in line for line in result.lines)


def test_the_account_name_is_taken_out_of_paths(monkeypatch):
    """The output ends by promising it carries no account details, and is
    meant to be pasted into a forum thread. C:\\Users\\<name> is an account
    name, so the promise was not true until this."""
    monkeypatch.setattr(selftest.sys, "platform", "win32")
    monkeypatch.setattr(selftest.Path, "home",
                        classmethod(lambda cls: Path(r"C:\Users\cxu44")))
    out = selftest.redact_home(r"C:\Users\cxu44\AppData\Roaming\LagScope")
    assert "cxu44" not in out
    assert out == r"%USERPROFILE%\AppData\Roaming\LagScope"


def test_a_redirected_profile_is_redacted_too(monkeypatch):
    """A roaming or redirected profile does not match Path.home(), but the
    shape of the path still gives the name away."""
    monkeypatch.setattr(selftest.sys, "platform", "win32")
    monkeypatch.setattr(selftest.Path, "home",
                        classmethod(lambda cls: Path(r"D:\Profiles\someone")))
    assert "cxu44" not in selftest.redact_home(r"C:\Users\cxu44\AppData\Roaming")


def test_posix_homes_are_redacted(monkeypatch):
    monkeypatch.setattr(selftest.sys, "platform", "linux")
    monkeypatch.setattr(selftest.Path, "home", classmethod(lambda cls: Path("/home/ann")))
    assert selftest.redact_home("/home/ann/.config/lagscope") == "~/.config/lagscope"
    monkeypatch.setattr(selftest.Path, "home", classmethod(lambda cls: Path("/root")))
    assert selftest.redact_home("/Users/bob/Library") == "~/Library"


def test_a_path_with_no_account_name_in_it_is_left_alone(monkeypatch):
    monkeypatch.setattr(selftest.Path, "home", classmethod(lambda cls: Path("/home/ann")))
    assert selftest.redact_home("/opt/lagscope") == "/opt/lagscope"


def test_the_config_folder_line_itself_is_redacted(monkeypatch, tmp_path):
    """The end-to-end version, and the one that would have caught the slip.

    redact_home() being correct is not enough - the bug was that the line
    printed the folder without calling it. This drives the real check and
    reads what it emitted.
    """
    import lagscope.config as config_module

    home = tmp_path / "Users" / "cxu44"
    folder = home / "AppData" / "Roaming" / "LagScope"
    folder.mkdir(parents=True)
    monkeypatch.setattr(config_module, "app_config_dir", lambda: folder)
    monkeypatch.setattr(selftest.Path, "home", classmethod(lambda cls: home))

    result = _check("config folder and report", selftest.check_writable)

    assert result.status == OK
    assert any("config folder:" in line for line in result.lines)
    assert not any("cxu44" in line for line in result.lines), result.lines


def test_a_missing_wireless_reading_is_reported_not_swallowed(monkeypatch):
    """It failed silently on a real machine for two days: the history recorded
    no wireless, the report said the connection was probably wired, and the
    laptop had never been plugged in. Nothing said so anywhere."""
    from lagscope.probes import path as path_module

    monkeypatch.setattr(path_module, "wifi_info", lambda: None)
    monkeypatch.setattr(path_module, "_run", lambda cmd, t: "")

    result = _check("wireless", selftest.check_wireless)

    assert result.status == WARN
    assert any("no wireless reading" in line for line in result.lines)


def test_the_labels_are_shown_so_a_parsing_failure_is_diagnosable(monkeypatch):
    from lagscope.probes import path as path_module

    monkeypatch.setattr(path_module, "wifi_info", lambda: None)
    monkeypatch.setattr(path_module, "_run", lambda cmd, t: (
        "    Name                   : Wi-Fi\n"
        "    SSID                   : PrivateNetworkName\n"
        "    Signal                 : 99%\n"))

    result = _check("wireless", selftest.check_wireless)
    body = " ".join(result.lines)

    assert "SSID" in body and "Signal" in body      # the labels are useful
    assert "PrivateNetworkName" not in body         # the values are not shown


def test_a_working_reading_never_prints_the_network_name(monkeypatch):
    """The report ends by promising it carries no Wi-Fi name."""
    from lagscope.probes import path as path_module
    from lagscope.probes.path import WifiInfo

    monkeypatch.setattr(path_module, "wifi_info",
                        lambda: WifiInfo(ssid="PrivateNetworkName", signal_pct=88,
                                         radio="802.11ax", channel="36", band="5"))

    result = _check("wireless", selftest.check_wireless)
    body = " ".join(result.lines)

    assert result.status == OK
    assert "88" in body and "802.11ax" in body
    assert "PrivateNetworkName" not in body


def test_a_band_that_could_not_be_established_is_flagged(monkeypatch):
    from lagscope.probes import path as path_module
    from lagscope.probes.path import WifiInfo

    monkeypatch.setattr(path_module, "wifi_info",
                        lambda: WifiInfo(ssid="Net", signal_pct=88, channel="200"))

    result = _check("wireless", selftest.check_wireless)
    assert result.status == WARN
    assert any("band" in line for line in result.lines)
