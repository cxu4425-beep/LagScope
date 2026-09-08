"""Which radio carried it: the band, the access point, and what follows.

The Wi-Fi *reading* already existed and shipped - what is new is keeping it
per minute so the existing grouping can answer "you are slower on that
network". The parsing still cannot be exercised against a real adapter here,
so it is tested against captured tool output; the band arithmetic, which is
where a wrong answer would send someone to change a setting that was already
right, is a pure function and is tested exhaustively.
"""

import pytest

from lagscope.actions import ROAM_NOTICEABLE, suggest
from lagscope.history import Bucket, History
from lagscope.models import LatencySample
from lagscope.patterns import by_edge, by_link, edge_verdict
from lagscope.probes.path import (
    BAND_24, BAND_5, BAND_6, WifiInfo, band_from_channel, band_from_mhz,
    normalise_band, parse_wifi,
)


# ------------------------------------------------------------------- the band
@pytest.mark.parametrize("channel,expected", [
    ("1", BAND_24), ("6", BAND_24), ("11", BAND_24), ("14", BAND_24),
    ("36", BAND_5), ("48", BAND_5), ("149", BAND_5), ("165", BAND_5), ("177", BAND_5),
])
def test_band_from_channel(channel, expected):
    assert band_from_channel(channel) == expected


def test_channels_that_could_be_either_band_say_nothing():
    """Wi-Fi 6E restarts numbering at 1, so a high number is not automatically
    5 GHz. A wrong band would send someone to change a setting already right."""
    assert band_from_channel("200") == ""
    assert band_from_channel("233") == ""
    assert band_from_channel("") == ""
    assert band_from_channel("not a channel") == ""


@pytest.mark.parametrize("mhz,expected", [
    (2412, BAND_24), (2484, BAND_24),
    (5180, BAND_5), (5745, BAND_5),
    (5955, BAND_6), (6115, BAND_6),
    (None, ""), (0, ""), (900, ""),
])
def test_band_from_frequency_is_never_ambiguous(mhz, expected):
    assert band_from_mhz(mhz) == expected


def test_band_stated_by_the_adapter_is_read():
    assert normalise_band("5 GHz") == BAND_5
    assert normalise_band("2.4 GHz") == BAND_24
    assert normalise_band("6 GHz") == BAND_6
    assert normalise_band("") == ""


# --------------------------------------------------------- reading the adapter
WINDOWS_5G = """
    Name                   : Wi-Fi
    SSID                   : MyHomeNetwork
    BSSID                  : a4:2b:8c:11:22:33
    Radio type             : 802.11ac
    Band                   : 5 GHz
    Channel                : 36
    Receive rate (Mbps)    : 866.7
    Signal                 : 78%
"""

WINDOWS_24G_ZH = """
    名稱                   : WLAN
    SSID                   : 家裡的路由器
    BSSID                  : AA-BB-CC-DD-EE-FF
    無線電類型             : 802.11n
    頻道                   : 6
    接收速率(Mbps)         : 72
    訊號                   : 42%
"""

LINUX = """Connected to a4:2b:8c:11:22:33 (on wlan0)
        SSID: MyHomeNetwork
        freq: 5180
        signal: -62 dBm
        rx bitrate: 400.0 MBit/s
"""


def test_windows_band_field_wins():
    info = parse_wifi(WINDOWS_5G, "win32")
    assert info.band == BAND_5
    assert info.bssid == "a4:2b:8c:11:22:33"
    assert info.link_key == "MyHomeNetwork (5 GHz)"


def test_windows_chinese_labels_and_dashed_mac():
    info = parse_wifi(WINDOWS_24G_ZH, "win32")
    assert info.ssid == "家裡的路由器"
    # netsh prints a MAC with dashes on some systems and colons on others.
    assert info.bssid == "aa:bb:cc:dd:ee:ff"
    assert info.band == BAND_24 and info.crowded_band
    assert info.link_key == "家裡的路由器 (2.4 GHz)"


def test_linux_frequency_settles_the_band():
    info = parse_wifi(LINUX, "linux")
    assert info.freq_mhz == 5180
    assert info.band == BAND_5
    assert info.bssid == "a4:2b:8c:11:22:33"


def test_the_bssid_is_not_mistaken_for_the_network_name():
    """"BSSID" contains "ssid", and a MAC address is not a network name."""
    info = parse_wifi(WINDOWS_5G, "win32")
    assert info.ssid == "MyHomeNetwork"


def test_two_bands_sharing_one_name_are_still_two_links():
    """Plenty of routers name both bands the same. Grouping by SSID alone
    would average together the very two things worth telling apart."""
    a = WifiInfo(ssid="Home", channel="6").link_key
    b = WifiInfo(ssid="Home", channel="36").link_key
    assert a != b


def test_a_link_with_no_band_still_has_a_name():
    assert WifiInfo(ssid="Home").link_key == "Home"
    assert WifiInfo().link_key == ""


# ------------------------------------------------------------------- recording
def test_the_link_survives_a_round_trip_through_the_history_file():
    bucket = Bucket(start=1000.0, count=30, ok=29, avg_ms=1800.0,
                    link="Home (2.4 GHz)", signal_pct=42, roams=2)
    back = Bucket.from_row(bucket.as_row())
    assert back.link == "Home (2.4 GHz)"
    assert back.signal_pct == 42
    assert back.roams == 2


def test_history_written_before_this_existed_still_loads():
    """Rows are append-only for exactly this reason: an upgrade must not throw
    away the history that makes the comparison possible in the first place."""
    full = Bucket(start=1000.0, count=30, ok=29, avg_ms=1800.0, host="edge-1",
                  link="Home (5 GHz)", signal_pct=80, roams=1).as_row()
    old = Bucket.from_row(full[:15])
    assert old.host == "edge-1"
    assert old.link == "" and old.signal_pct is None and old.roams == 0


def _record(history, samples):
    for sample in samples:
        history.add(sample)


def test_a_roam_is_counted_but_arriving_is_not(tmp_path):
    history = History(path=tmp_path / "h.csv", bucket_s=60)
    base = dict(ok=True, total_ms=1000.0, link="Home (5 GHz)")
    _record(history, [
        LatencySample(bssid="", **base),            # radio said nothing yet
        LatencySample(bssid="aa:aa:aa:aa:aa:aa", **base),   # arriving: not a roam
        LatencySample(bssid="aa:aa:aa:aa:aa:aa", **base),
        LatencySample(bssid="bb:bb:bb:bb:bb:bb", **base),   # a roam
        LatencySample(bssid="aa:aa:aa:aa:aa:aa", **base),   # and back
    ])
    bucket = history._open.close()
    assert bucket.roams == 2
    assert bucket.link == "Home (5 GHz)"


def test_the_minute_takes_the_link_it_spent_most_of_itself_on(tmp_path):
    history = History(path=tmp_path / "h.csv", bucket_s=60)
    _record(history, [LatencySample(ok=True, total_ms=1.0, link="Home (5 GHz)")] * 4
                     + [LatencySample(ok=True, total_ms=1.0, link="Home (2.4 GHz)")])
    assert history._open.close().link == "Home (5 GHz)"


def test_signal_is_averaged_across_the_minute(tmp_path):
    history = History(path=tmp_path / "h.csv", bucket_s=60)
    _record(history, [LatencySample(ok=True, total_ms=1.0, link="Home", signal_pct=pct)
                      for pct in (40, 50, 60)])
    assert history._open.close().signal_pct == 50


# ------------------------------------------------------------------- comparing
def _minutes(link, count, avg, **extra):
    return [Bucket(start=1000.0 + i * 60, count=30, ok=30, avg_ms=avg,
                   link=link, **extra) for i in range(count)]


def test_a_slower_band_is_identified():
    buckets = _minutes("Home (2.4 GHz)", 20, 2600.0, signal_pct=38, stalls=2)
    buckets += _minutes("Home (5 GHz)", 20, 1850.0, signal_pct=82)
    verdict = edge_verdict(by_link(buckets), prefix="link")

    assert verdict.key == "link.differs" and verdict.matters
    assert verdict.best.host == "Home (5 GHz)"
    assert verdict.worst.host == "Home (2.4 GHz)"
    assert verdict.difference_ms == pytest.approx(750.0)


def test_the_wording_follows_the_prefix():
    """Same arithmetic, different conclusion: a CDN edge is handed to you and
    a wireless network is chosen, so they must not read the same."""
    buckets = _minutes("A", 20, 1000.0) + _minutes("B", 20, 2000.0)
    assert edge_verdict(by_link(buckets)).key.startswith("edge.")
    assert edge_verdict(by_link(buckets), prefix="link").key.startswith("link.")


def test_wireless_grouping_does_not_disturb_the_edge_grouping():
    buckets = _minutes("Home (2.4 GHz)", 20, 2600.0)
    assert by_edge(buckets) == []          # no edge was recorded on these
    assert edge_verdict(by_edge(buckets)).key == "edge.not_enough"


def test_a_wired_machine_produces_no_link_comparison():
    buckets = [Bucket(start=1000.0 + i * 60, count=30, ok=30, avg_ms=1800.0)
               for i in range(30)]
    assert by_link(buckets) == []


def test_signal_and_roams_reach_the_comparison():
    buckets = _minutes("Home (2.4 GHz)", 12, 2000.0, signal_pct=40, roams=1)
    stats = by_link(buckets)[0]
    assert stats.signal_pct == pytest.approx(40.0)
    assert stats.roams == 12
    assert stats.as_dict()["signal_pct"] == 40


# -------------------------------------------------------------- what to do now
class _Verdict:
    def __init__(self, matters=True):
        self.matters = matters
        self.difference_ms = 750.0
        self.best = type("S", (), {"host": "Home (5 GHz)", "share_pct": 50.0})()
        self.worst = type("S", (), {"host": "Home (2.4 GHz)", "share_pct": 50.0})()


def _keys(actions):
    return [action.key for action in actions]


def test_a_measurably_worse_network_becomes_a_suggestion():
    actions = suggest(link_verdict=_Verdict())
    assert "action.switch_band" in _keys(actions)
    detail = [a.detail for a in actions if a.key == "action.switch_band"][0]
    assert "Home (2.4 GHz)" in detail and "Home (5 GHz)" in detail


def test_networks_that_perform_alike_suggest_nothing():
    assert _keys(suggest(link_verdict=_Verdict(matters=False))) == []


def test_repeated_handovers_are_worth_reporting():
    assert "action.roaming" in _keys(suggest(roams=ROAM_NOTICEABLE))
    # A laptop carried across the house once or twice is not a fault.
    assert "action.roaming" not in _keys(suggest(roams=ROAM_NOTICEABLE - 1))


def test_bluetooth_and_24ghz_are_flagged_together():
    assert "action.bt_interference" in _keys(suggest(band="2.4", bluetooth_ms=170.0))


def test_the_bluetooth_warning_needs_both_halves():
    """It is a fact about a band plus a fact about what is plugged in. Either
    on its own says nothing."""
    assert "action.bt_interference" not in _keys(suggest(band="5", bluetooth_ms=170.0))
    assert "action.bt_interference" not in _keys(suggest(band="2.4", bluetooth_ms=0.0))


def test_the_wireless_suggestions_count_as_something_you_can_fix():
    from lagscope.actions import has_local_cause

    assert has_local_cause(suggest(link_verdict=_Verdict())) is True
    assert has_local_cause(suggest(roams=5)) is True


# --------------------------------------------- strong signal versus weak
def _signal_minutes(count, avg, pct, **extra):
    return [Bucket(start=1000.0 + i * 60, count=30, ok=30, avg_ms=avg,
                   signal_pct=pct, link="Home (5 GHz)", **extra)
            for i in range(count)]


def test_the_weak_minutes_are_compared_against_the_strong_ones():
    """Most homes have exactly one network, so by_link has nothing to compare -
    while the answer sits in the same rows it just averaged away."""
    from lagscope.patterns import SIGNAL_STRONG, SIGNAL_WEAK, by_signal

    buckets = _signal_minutes(45, 1800.0, 85) + _signal_minutes(15, 2900.0, 38, stalls=3)
    stats = {item.host: item for item in by_signal(buckets)}

    assert set(stats) == {SIGNAL_STRONG, SIGNAL_WEAK}
    assert stats[SIGNAL_STRONG].avg_ms == pytest.approx(1800.0)
    assert stats[SIGNAL_WEAK].avg_ms == pytest.approx(2900.0)
    assert stats[SIGNAL_WEAK].stalls == 45

    verdict = edge_verdict(by_signal(buckets), prefix="signal")
    assert verdict.key == "signal.differs" and verdict.matters
    assert verdict.difference_ms == pytest.approx(1100.0)
    assert verdict.worst.host == SIGNAL_WEAK


def test_the_split_is_the_threshold_the_rest_of_the_app_uses():
    """Two parts of the app disagreeing about what "weak" means would be worse
    than either of them being slightly off."""
    from lagscope.patterns import SIGNAL_STRONG, SIGNAL_WEAK, by_signal
    from lagscope.probes.path import WIFI_WEAK_PCT

    below = by_signal(_signal_minutes(12, 2000.0, WIFI_WEAK_PCT - 1))
    at = by_signal(_signal_minutes(12, 2000.0, WIFI_WEAK_PCT))
    assert below[0].host == SIGNAL_WEAK
    assert at[0].host == SIGNAL_STRONG


def test_a_wired_machine_has_nothing_to_split():
    from lagscope.patterns import by_signal

    assert by_signal([Bucket(start=1000.0 + i * 60, count=30, ok=30, avg_ms=1800.0)
                      for i in range(30)]) == []
    assert by_signal([]) == []


def test_one_side_only_is_still_reported_as_one_side():
    """Always strong is good news; always weak is the answer by itself. Both
    have to be distinguishable from "nothing to compare"."""
    from lagscope.patterns import SIGNAL_STRONG, SIGNAL_WEAK, by_signal

    strong = edge_verdict(by_signal(_signal_minutes(30, 1800.0, 90)), prefix="signal")
    assert strong.key == "signal.only_one" and strong.best.host == SIGNAL_STRONG

    weak = edge_verdict(by_signal(_signal_minutes(30, 2600.0, 30)), prefix="signal")
    assert weak.key == "signal.only_one" and weak.best.host == SIGNAL_WEAK
    assert weak.best.signal_pct == pytest.approx(30.0)


def test_a_short_weak_stretch_is_not_enough_to_conclude_from():
    from lagscope.patterns import MIN_BUCKETS_PER_EDGE, by_signal

    buckets = (_signal_minutes(30, 1800.0, 85)
               + _signal_minutes(MIN_BUCKETS_PER_EDGE - 1, 3000.0, 30))
    assert edge_verdict(by_signal(buckets), prefix="signal").key == "signal.only_one"


def test_the_original_buckets_are_not_disturbed():
    """The grouping wraps them to add a label; the history rows themselves are
    not something to be editing."""
    from lagscope.patterns import by_signal

    buckets = _signal_minutes(12, 1800.0, 85)
    by_signal(buckets)
    assert not any(hasattr(bucket, "signal_band") for bucket in buckets)


def test_a_weak_signal_becomes_a_suggestion():
    actions = suggest(signal_verdict=_Verdict())
    assert "action.signal" in _keys(actions)


def test_the_labels_are_real_translation_keys():
    """They are stored, not translated, so they have to exist to be shown."""
    from lagscope.i18n import STRINGS
    from lagscope.patterns import SIGNAL_STRONG, SIGNAL_WEAK

    assert SIGNAL_STRONG in STRINGS and SIGNAL_WEAK in STRINGS


@pytest.mark.parametrize("pct,expected", [
    (90, "signal.always_strong"),        # good news, and worth saying so
    (30, "signal.always_weak"),          # the answer by itself
])
def test_one_band_only_means_two_opposite_things(pct, expected):
    from lagscope.patterns import by_signal, signal_note_key

    verdict = edge_verdict(by_signal(_signal_minutes(30, 2000.0, pct)), prefix="signal")
    assert verdict.key == "signal.only_one"
    assert signal_note_key(verdict) == expected


def test_every_other_verdict_keeps_its_own_key():
    from lagscope.patterns import by_signal, signal_note_key

    buckets = _signal_minutes(45, 1800.0, 85) + _signal_minutes(15, 2900.0, 38)
    assert signal_note_key(edge_verdict(by_signal(buckets), prefix="signal")) \
        == "signal.differs"
    assert signal_note_key(edge_verdict([], prefix="signal")) == "signal.not_enough"


def test_the_sentences_it_can_choose_all_exist():
    from lagscope.i18n import STRINGS

    for key in ("signal.always_strong", "signal.always_weak", "signal.differs",
                "signal.same", "signal.not_enough"):
        assert key in STRINGS, key
