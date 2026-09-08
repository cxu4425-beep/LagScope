"""Splitting the path into segments, parsed from real OS tool output.

The samples below are the actual shapes these tools print on Windows (English
and Chinese), Linux and macOS. Parsing has to survive all of them, which is why
nothing here reads a translated summary line.
"""

import pytest

from lagscope.probes import path
from lagscope.probes.path import (
    PathReport, PingStats, WifiInfo, parse_gateway, parse_ping_times, parse_trace_hops,
    parse_wifi, ping_stats, verdict,
)

PING_WINDOWS_EN = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=13ms TTL=117
Reply from 8.8.8.8: bytes=32 time=12ms TTL=117
Request timed out.
Reply from 8.8.8.8: bytes=32 time=15ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),
Approximate round trip times in milli-seconds:
    Minimum = 12ms, Maximum = 15ms, Average = 13ms
"""

PING_WINDOWS_ZH = """
正在 Ping 8.8.8.8 具有 32 字节的数据:
来自 8.8.8.8 的回复: 字节=32 时间=23ms TTL=117
来自 8.8.8.8 的回复: 字节=32 时间=21ms TTL=117
请求超时。
来自 8.8.8.8 的回复: 字节=32 时间=25ms TTL=117

8.8.8.8 的 Ping 统计信息:
    数据包: 已发送 = 4，已接收 = 3，丢失 = 1 (25% 丢失)，
"""

PING_LINUX = """
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=11.4 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=117 time=12.8 ms
64 bytes from 8.8.8.8: icmp_seq=4 ttl=117 time=11.9 ms

--- 8.8.8.8 ping statistics ---
4 packets transmitted, 3 received, 25% packet loss, time 3005ms
rtt min/avg/max/mdev = 11.400/12.033/12.800/0.583 ms
"""


# --------------------------------------------------------------- ping timing
@pytest.mark.parametrize(
    "sample,expected",
    [
        (PING_WINDOWS_EN, [13.0, 12.0, 15.0]),
        (PING_WINDOWS_ZH, [23.0, 21.0, 25.0]),
        (PING_LINUX, [11.4, 12.8, 11.9]),
    ],
)
def test_reply_times_are_read_in_every_language(sample, expected):
    assert parse_ping_times(sample) == expected


def test_a_transcript_without_replies_yields_nothing():
    assert parse_ping_times("Request timed out.\nRequest timed out.") == []
    assert parse_ping_times("") == []


def test_statistics_come_from_the_replies_not_the_summary(monkeypatch):
    monkeypatch.setattr(path, "_run", lambda command, timeout: PING_WINDOWS_EN)

    stats = ping_stats("8.8.8.8", count=4)

    assert stats.received == 3 and stats.sent == 4
    assert stats.loss_pct == pytest.approx(25.0)
    assert stats.avg_ms == pytest.approx(13.33, abs=0.01)
    assert stats.min_ms == 12.0 and stats.max_ms == 15.0
    assert stats.jitter_ms == pytest.approx(2.0)          # |12-13| and |15-12|
    assert stats.ok


def test_a_host_that_never_answers(monkeypatch):
    monkeypatch.setattr(path, "_run", lambda command, timeout: "Request timed out.")
    stats = ping_stats("10.0.0.9", count=3)

    assert not stats.ok and stats.received == 0
    assert stats.loss_pct == 100.0 and stats.error == "no reply"


def test_ping_missing_from_the_system_is_reported(monkeypatch):
    monkeypatch.setattr(path, "_run", lambda command, timeout: None)
    assert ping_stats("8.8.8.8").error == "ping unavailable"


def test_no_host_is_not_an_error_worth_running():
    assert ping_stats("").error == "no-host"


# ------------------------------------------------------------------- gateway
def test_gateway_from_windows_route_table():
    output = """
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.1.1    192.168.1.20     25
===========================================================================
"""
    assert parse_gateway(output, "win32") == "192.168.1.1"


def test_gateway_from_linux_ip_route():
    output = "default via 10.0.0.1 dev wlan0 proto dhcp src 10.0.0.55 metric 600"
    assert parse_gateway(output, "linux") == "10.0.0.1"


def test_gateway_from_macos_route_get():
    output = """
   route to: default
destination: default
       mask: default
    gateway: 192.168.0.1
  interface: en0
"""
    assert parse_gateway(output, "darwin") == "192.168.0.1"


def test_no_default_route_is_not_a_crash():
    assert parse_gateway("", "linux") is None
    assert parse_gateway("nothing useful here", "win32") is None


# ---------------------------------------------------------------------- hops
def test_windows_tracert_hops():
    output = """
Tracing route to 8.8.8.8 over a maximum of 3 hops

  1     1 ms     1 ms     1 ms  192.168.1.1
  2    12 ms    11 ms    13 ms  100.64.0.1
  3     *        *        *     Request timed out.

Trace complete.
"""
    hops = parse_trace_hops(output)

    assert hops[0] == (1, "192.168.1.1", 1.0)
    assert hops[1] == (2, "100.64.0.1", 11.0)
    assert len(hops) == 2            # the timed-out hop has no address


def test_linux_traceroute_hops():
    output = """
traceroute to 8.8.8.8 (8.8.8.8), 3 hops max, 60 byte packets
 1  10.0.0.1  0.512 ms  0.480 ms  0.470 ms
 2  100.64.0.1  9.8 ms  9.7 ms  10.1 ms
 3  * * *
"""
    hops = parse_trace_hops(output)

    assert [hop[1] for hop in hops] == ["10.0.0.1", "100.64.0.1"]
    assert hops[1][2] == pytest.approx(9.7)


def test_the_first_external_hop_skips_the_router(monkeypatch):
    output = " 1  10.0.0.1  0.5 ms\n 2  100.64.0.1  9.8 ms\n"
    monkeypatch.setattr(path, "_run", lambda command, timeout: output)
    assert path.first_external_hop("8.8.8.8") == ("100.64.0.1", 9.8)


def test_no_trace_tool_is_not_fatal(monkeypatch):
    monkeypatch.setattr(path, "_run", lambda command, timeout: None)
    assert path.first_external_hop("8.8.8.8") is None


# --------------------------------------------------------------------- Wi-Fi
def test_wifi_from_windows_netsh_english():
    output = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    SSID                   : MyHomeNetwork
    BSSID                  : a4:2b:8c:11:22:33
    Radio type             : 802.11ac
    Channel                : 36
    Receive rate (Mbps)    : 866.7
    Signal                 : 78%
"""
    info = parse_wifi(output, "win32")

    assert info.ssid == "MyHomeNetwork" and info.signal_pct == 78
    assert info.radio == "802.11ac" and info.channel == "36"
    assert info.rx_mbps == pytest.approx(866.7)
    assert not info.weak


def test_wifi_from_windows_netsh_chinese():
    output = """
    名称                   : WLAN
    SSID                   : 家里的路由器
    无线电类型             : 802.11n
    信道                   : 6
    接收速率(Mbps)         : 72
    信号                   : 42%
"""
    info = parse_wifi(output, "win32")

    assert info.ssid == "家里的路由器" and info.signal_pct == 42
    assert info.weak                       # this is worth telling the user about


def test_wifi_from_linux_iw():
    output = """
Connected to a4:2b:8c:11:22:33 (on wlan0)
        SSID: MyHomeNetwork
        freq: 5180
        signal: -62 dBm
        rx bitrate: 780.0 MBit/s
"""
    info = parse_wifi(output, "linux")

    assert info.ssid == "MyHomeNetwork"
    assert info.signal_pct == 76           # -62 dBm mapped onto 0-100
    assert info.rx_mbps == pytest.approx(780.0)


def test_a_machine_on_ethernet_reports_no_wifi():
    assert parse_wifi("", "win32") is None


# ------------------------------------------------------------------ verdict
def _stats(host, avg, loss_pct=0.0, sent=5):
    received = int(round(sent * (1 - loss_pct / 100.0)))
    return PingStats(host=host, sent=sent, received=received, avg_ms=avg,
                     min_ms=avg, max_ms=avg, jitter_ms=1.0)


def test_a_healthy_path_says_so():
    report = PathReport(target="8.8.8.8",
                        gateway_stats=_stats("192.168.1.1", 2.0),
                        hop_stats=_stats("100.64.0.1", 9.0),
                        target_stats=_stats("8.8.8.8", 24.0))
    assert verdict(report)[0] == "verdict.ok"


def test_a_slow_router_hop_blames_the_home_network():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 45.0),
                        target_stats=_stats("8.8.8.8", 90.0))
    assert verdict(report)[0] == "verdict.home"


def test_a_slow_router_hop_on_weak_wifi_blames_the_wifi():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 45.0),
                        target_stats=_stats("8.8.8.8", 90.0),
                        wifi=WifiInfo(ssid="Home", signal_pct=35))
    assert verdict(report)[0] == "verdict.wifi"


def test_losing_packets_to_the_router_is_a_home_problem():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 3.0, loss_pct=20.0),
                        target_stats=_stats("8.8.8.8", 30.0))
    assert verdict(report)[0] == "verdict.home"


def test_a_jump_at_the_first_external_hop_blames_the_isp():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 2.0),
                        hop_stats=_stats("100.64.0.1", 95.0),
                        target_stats=_stats("8.8.8.8", 110.0))
    assert verdict(report)[0] == "verdict.isp"


def test_a_distant_server_is_named_as_such():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 2.0),
                        hop_stats=_stats("100.64.0.1", 8.0),
                        target_stats=_stats("far.example.com", 220.0))
    assert verdict(report)[0] == "verdict.server"


def test_loss_to_the_target_is_called_out_before_speed():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 2.0),
                        target_stats=_stats("8.8.8.8", 30.0, loss_pct=10.0))
    assert verdict(report)[0] == "verdict.loss"


def test_an_unreachable_target_on_a_healthy_lan():
    report = PathReport(gateway_stats=_stats("192.168.1.1", 2.0),
                        target_stats=PingStats(host="down.example.com", sent=5, received=0))
    assert verdict(report)[0] == "verdict.target_down"


def test_a_router_that_ignores_pings_is_noted_not_blamed():
    report = PathReport(
        gateway_stats=PingStats(host="192.168.1.1", sent=5, received=0, error="no reply"),
        target_stats=_stats("8.8.8.8", 25.0),
    )
    assert verdict(report)[0] == "verdict.ok"
    assert "gateway-silent" in report.notes


def test_nothing_measured_at_all():
    assert verdict(PathReport())[0] == "verdict.unknown"


def test_the_report_serialises_for_the_cli_and_the_phone():
    report = PathReport(target="8.8.8.8", gateway="192.168.1.1",
                        gateway_stats=_stats("192.168.1.1", 2.0),
                        target_stats=_stats("8.8.8.8", 25.0),
                        wifi=WifiInfo(ssid="Home", signal_pct=80))
    data = report.as_dict()

    assert data["segments"]["you_to_router"]["avg_ms"] == 2.0
    assert data["segments"]["router_to_isp"] is None
    assert data["wifi"]["ssid"] == "Home"
    assert data["verdict"] == "verdict.ok"


def test_a_machine_without_ping_says_so_instead_of_blaming_the_target():
    """Reporting "the server is down" when it is our own toolbox that is empty
    would send the user chasing the wrong problem."""
    missing = PingStats(host="8.8.8.8", sent=5, received=0, error="ping unavailable")
    report = PathReport(target="8.8.8.8", target_stats=missing)

    assert verdict(report)[0] == "verdict.no_ping"


def test_a_real_unreachable_target_is_still_distinguished():
    report = PathReport(
        target="8.8.8.8",
        gateway_stats=_stats("192.168.1.1", 2.0),
        target_stats=PingStats(host="8.8.8.8", sent=5, received=0, error="no reply"),
    )
    assert verdict(report)[0] == "verdict.target_down"


def test_console_output_is_decoded_without_ever_raising():
    """subprocess text=True raised UnicodeDecodeError on output it could not
    decode - and that is neither an OSError nor a SubprocessError, so it went
    straight past the handler and was swallowed several frames up as "wifi
    state unavailable". The reading vanished with no error anywhere."""
    from lagscope.probes.path import _decode

    assert _decode("SSID : Home\n".encode("utf-8")).startswith("SSID")
    # Bytes that are not valid UTF-8 must still come back as something.
    assert _decode("訊號 : 99%".encode("cp950"))
    assert _decode(b"\xff\xfe\x00\x01") is not None


def test_ascii_survives_even_when_the_labels_do_not():
    """A network name, an address or a percentage is ASCII, so it stays
    readable however badly the surrounding words decode."""
    from lagscope.probes.path import _decode, parse_wifi

    raw = ("    SSID                   : MyNetwork\n"
           "    訊號                   : 99%\n").encode("cp950")
    info = parse_wifi(_decode(raw), "win32")
    assert info.ssid == "MyNetwork"


def test_the_channel_label_covers_both_chinese_windows():
    """Windows says 通道 in Traditional Chinese and 信道 in Simplified. 頻道 is
    the word for a television channel and was never one of them."""
    from lagscope.probes.path import parse_wifi

    for label in ("Channel", "通道", "信道"):
        info = parse_wifi(f"    SSID : Net\n    {label} : 36\n", "win32")
        assert info.channel == "36", label
        assert info.band == "5", label
