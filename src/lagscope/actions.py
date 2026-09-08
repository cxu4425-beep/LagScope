"""The last mile: what to actually do about it.

Every other part of this app stops at the diagnosis. "Your Wi-Fi signal is
weak" and "you were assigned a peer-assisted node" are true and useless on
their own - the person reading them still has to know what a peer-assisted
node *is* before they can do anything, and most people reasonably do not.

So this turns what was observed into a short ordered list of things to try.
Two rules shape it:

* **Only from evidence.** Each suggestion names the finding that produced it.
  Nothing is offered because it is generally good advice; a list that always
  says "restart your router" teaches people to ignore the list.
* **Ordered by what the evidence supports**, not by how easy it is. Telling
  someone to move to 5GHz when the measurement says the congestion is two
  hops beyond their house wastes their afternoon.

Where the honest answer is "this is not yours to fix" - a congested
cross-border link at nine in the evening - it says that, and says what can be
done anyway. That is more useful than an action list that pretends every
problem has a local fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

# Bigger number = offered first. Grouped so related causes stay together.
PRIORITY_BLOCKING = 100         # nothing works until this is dealt with
PRIORITY_STRONG = 80            # the evidence points here specifically
PRIORITY_LIKELY = 60
PRIORITY_CONTEXT = 40           # worth knowing, not necessarily worth doing
PRIORITY_WEAK = 20

# Below this, an access-point change or two over a whole session is a laptop
# being carried around, not a problem to report.
ROAM_NOTICEABLE = 3


@dataclass(frozen=True)
class Action:
    """One thing to try, and the observation that earned it a place."""

    key: str                    # i18n key for the suggestion
    because_key: str = ""       # i18n key for the evidence behind it
    priority: int = PRIORITY_LIKELY
    detail: str = ""            # a measured value, already formatted

    def as_dict(self) -> dict:
        return {"key": self.key, "because": self.because_key,
                "priority": self.priority, "detail": self.detail}


def suggest(*, edge_verdict=None, pattern=None, verdict_key: str = "",
            peer_hosts: Sequence = (), loss_pct: Optional[float] = None,
            speed_mbps: Optional[float] = None,
            switches: int = 0, link_verdict=None, roams: int = 0,
            band: str = "", bluetooth_ms: float = 0.0,
            signal_verdict=None) -> List[Action]:
    """Build the ordered list from what was actually measured.

    Everything is optional: the caller passes what it has, and an absent
    observation simply produces no suggestion rather than a hedged one.
    """
    out: List[Action] = []

    # --- being handed a consumer node is specific, common, and fixable
    if peer_hosts:
        out.append(Action(
            key="action.peer_node", because_key="action.because.peer",
            priority=PRIORITY_STRONG, detail=", ".join(list(peer_hosts)[:2]),
        ))

    # --- one edge measurably worse than another you also had
    if edge_verdict is not None and getattr(edge_verdict, "matters", False):
        worst = edge_verdict.worst
        out.append(Action(
            key="action.edge_reassign", because_key="action.because.edge",
            priority=PRIORITY_STRONG,
            detail=f"{worst.host} (+{edge_verdict.difference_ms:.0f} ms, "
                   f"{worst.share_pct:.0f}%)" if worst else "",
        ))

    # --- one wireless network measurably worse than another you also used
    if link_verdict is not None and getattr(link_verdict, "matters", False):
        worst = getattr(link_verdict, "worst", None)
        best = getattr(link_verdict, "best", None)
        out.append(Action(
            key="action.switch_band", because_key="action.because.link",
            priority=PRIORITY_STRONG,
            detail=(f"{worst.host} \u2192 {best.host} "
                    f"(+{link_verdict.difference_ms:.0f} ms)") if worst and best else "",
        ))

    # --- a weak signal is the commonest wireless fault and the only one most
    # --- people can compare, because most homes have exactly one network
    if signal_verdict is not None and getattr(signal_verdict, "matters", False):
        worst = getattr(signal_verdict, "worst", None)
        out.append(Action(
            key="action.signal", because_key="action.because.signal",
            priority=PRIORITY_STRONG,
            detail=(f"+{signal_verdict.difference_ms:.0f} ms, "
                    f"{worst.share_pct:.0f}%") if worst else "",
        ))

    # --- the access point changing under you is a stall with no other cause
    if roams >= ROAM_NOTICEABLE:
        out.append(Action(key="action.roaming", because_key="action.because.roams",
                          priority=PRIORITY_LIKELY, detail=str(roams)))

    # --- 2.4 GHz Wi-Fi and Bluetooth are the same radio band
    if band == "2.4" and bluetooth_ms > 0:
        # Not a measurement: nothing here observed the two interfering. It is a
        # fact about the band plus a fact about what is plugged in, and it is
        # worth saying because the fix - move to 5 GHz - is one click and
        # people never connect the two things themselves.
        out.append(Action(key="action.bt_interference",
                          because_key="action.because.bt_band",
                          priority=PRIORITY_CONTEXT))

    # --- a clock-shaped problem is congestion, and congestion is not local
    if pattern is not None and getattr(pattern, "has_pattern", False):
        out.append(Action(
            key="action.peak_hours", because_key="action.because.pattern",
            priority=PRIORITY_CONTEXT,
        ))

    # --- what the path check blamed, when it blamed something
    blame = {
        "verdict.wifi": ("action.wifi", PRIORITY_STRONG),
        "verdict.home": ("action.home", PRIORITY_STRONG),
        "verdict.dns": ("action.dns", PRIORITY_LIKELY),
        "verdict.isp": ("action.isp", PRIORITY_CONTEXT),
        "verdict.server": ("action.server", PRIORITY_CONTEXT),
        "verdict.loss": ("action.loss", PRIORITY_BLOCKING),
        "verdict.target_down": ("action.target_down", PRIORITY_BLOCKING),
    }
    if verdict_key in blame:
        key, priority = blame[verdict_key]
        out.append(Action(key=key, because_key="action.because.verdict",
                          priority=priority))

    # --- loss ruins a stream at levels that barely dent a download
    if loss_pct is not None and loss_pct >= 2.0 and verdict_key != "verdict.loss":
        out.append(Action(key="action.loss", because_key="action.because.loss",
                          priority=PRIORITY_BLOCKING, detail=f"{loss_pct:.1f}%"))

    # --- a line that genuinely cannot carry the quality being asked for
    if speed_mbps is not None and speed_mbps < 5.0:
        out.append(Action(key="action.lower_quality", because_key="action.because.speed",
                          priority=PRIORITY_STRONG, detail=f"{speed_mbps:.1f} Mbps"))

    # --- flapping between edges is its own problem
    if switches >= 5:
        out.append(Action(key="action.flapping", because_key="action.because.switches",
                          priority=PRIORITY_WEAK, detail=str(switches)))

    out.sort(key=lambda action: -action.priority)
    return out


def has_local_cause(actions: Sequence) -> bool:
    """True when at least one suggestion is something the viewer can do at home.

    Used to decide whether to add the "this one is not yours to fix" note: it
    belongs on a list that is otherwise all congestion, and would be noise on a
    list that already tells someone to move their router.
    """
    local = {"action.wifi", "action.home", "action.dns", "action.lower_quality",
             "action.peer_node", "action.edge_reassign", "action.switch_band",
             "action.roaming", "action.bt_interference", "action.signal"}
    return any(getattr(action, "key", "") in local for action in actions or ())
