"""Measuring "the internet" with nothing configured.

The first thing a new user sees, so the cases that matter are the ordinary
ones done right - the nearest anchor is chosen and kept - and the unhappy ones
done cheaply: no network at all must not turn every round into four timeouts.
"""

from __future__ import annotations

import pytest

from lagscope.probes.internet import (
    FAILURES_BEFORE_RECHOOSE, RECHOOSE_S, RETRY_S, Anchor, InternetProbe,
)

A = Anchor("10.0.0.1", 443, "Near")
B = Anchor("10.0.0.2", 443, "Far")
C = Anchor("10.0.0.3", 443, "Filtered")


class Net:
    """A scripted network: per-host TCP and ICMP answers, every call logged."""

    def __init__(self, tcp=None, icmp=None):
        self.tcp = dict(tcp or {})
        self.icmp = dict(icmp or {})
        self.calls = []
        self.now = 1000.0

    def connect(self, host, port, timeout_s):
        self.calls.append(("tcp", host))
        return self.tcp.get(host)

    def ping(self, host, timeout_s):
        self.calls.append(("icmp", host))
        return self.icmp.get(host)

    def clock(self):
        return self.now

    def probe(self, anchors=(A, B, C)):
        return InternetProbe(anchors, connect=self.connect, ping=self.ping, clock=self.clock)


def test_the_nearest_anchor_that_answers_is_chosen_and_measured():
    net = Net(tcp={A.host: 12.0, B.host: 80.0})
    probe = net.probe()

    result = probe.measure()

    assert result.ok and result.anchor == A and result.rtt_ms == 12.0
    assert result.method == "tcp"


def test_after_choosing_only_the_chosen_anchor_is_measured():
    net = Net(tcp={A.host: 12.0, B.host: 80.0})
    probe = net.probe()
    probe.measure()
    net.calls.clear()

    for _ in range(5):
        probe.measure()

    assert net.calls == [("tcp", A.host)] * 5


def test_ping_is_used_when_every_handshake_is_filtered():
    net = Net(icmp={B.host: 30.0})
    probe = net.probe()

    result = probe.measure()

    assert result.ok and result.anchor == B and result.method == "icmp"


def test_a_filtered_anchor_is_abandoned_after_a_few_failures_not_one():
    net = Net(tcp={A.host: 12.0, B.host: 80.0})
    probe = net.probe()
    probe.measure()                       # chooses A
    net.tcp.pop(A.host)                   # A starts being filtered
    net.now += RETRY_S + 1                # long enough since the last survey

    for _ in range(FAILURES_BEFORE_RECHOOSE):
        result = probe.measure()
        assert not result.ok and result.anchor == A   # loss is reported as loss

    result = probe.measure()              # now it looks elsewhere
    assert result.ok and result.anchor == B


def test_the_choice_is_reconsidered_after_half_an_hour():
    net = Net(tcp={A.host: 12.0, B.host: 80.0})
    probe = net.probe()
    probe.measure()
    net.tcp[B.host] = 5.0                 # moved house; B is nearer now
    net.now += RECHOOSE_S + 1

    assert probe.measure().anchor == B


def test_with_no_network_a_round_costs_one_timeout_not_a_survey():
    net = Net()
    probe = net.probe()

    first = probe.measure()               # one survey, found nothing
    assert not first.ok
    net.calls.clear()

    for _ in range(10):
        net.now += 2.0
        assert not probe.measure().ok

    # One address, TCP then ping, per round - never the whole list again
    # until RETRY_S has passed.
    assert len(net.calls) == 10 * 2
    assert {host for _kind, host in net.calls} == {A.host}


def test_the_survey_is_retried_once_the_network_comes_back():
    net = Net()
    probe = net.probe()
    probe.measure()
    net.tcp[B.host] = 9.0
    net.now += RETRY_S + 1

    result = probe.measure()
    assert result.ok and result.anchor == B


def test_a_lost_handshake_is_ordinary_loss_not_a_reason_to_switch():
    net = Net(tcp={A.host: 12.0, B.host: 80.0})
    probe = net.probe()
    probe.measure()
    flaky = iter([None, 12.0, None, 12.0])
    net.connect = lambda host, port, timeout: next(flaky) if host == A.host else 80.0
    probe._connect = net.connect

    anchors = {probe.measure().anchor for _ in range(4)}
    assert anchors == {A}


def test_an_empty_anchor_list_is_a_programming_error():
    with pytest.raises(ValueError):
        InternetProbe(())


def test_the_default_anchors_are_public_anycast_on_443():
    from lagscope.probes.internet import ANCHORS

    assert len(ANCHORS) >= 3
    assert all(anchor.port == 443 for anchor in ANCHORS)
    # No single country's blocking can take all of them out.
    assert {"1.1.1.1", "223.5.5.5"} <= {anchor.host for anchor in ANCHORS}
