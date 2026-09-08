"""What a CDN hostname says about the machine serving you.

Bilibili's edge hostnames are not opaque - they encode who runs the node, and
often where it is and which carrier it sits behind::

    cn-hbyc-ct-01.bilivideo.com
    │  │    │  └── node number
    │  │    └───── ct: China Telecom
    │  └────────── hbyc: Hubei / Yichang
    └───────────── cn: mainland China

That matters because "why does it stutter" is usually a question about *which
machine you were assigned*, not about how much bandwidth you have. A viewer
who cannot see the answer cannot act on it.

Three things are decoded, and they are deliberately not equally trusted:

* **Who runs it** - self-built, a public cloud, or a peer-assisted node. Read
  straight off the name, and the part that actually drives a decision.
* **Which carrier** - the ``ct`` / ``cu`` / ``cm`` marker, equally direct.
* **Where it is** - a province and city code. This is the *guessable* part, so
  it is looked up in a table of codes we are confident about and otherwise
  reported as the raw code. Inventing a plausible city would be worse than
  admitting the code is unrecognised: someone would act on it.

Peer-assisted (PCDN / mCDN) nodes get a warning of their own. Those are not
datacentre machines - they are consumer connections reselling spare upstream,
and being handed one is a common and entirely invisible reason for a stream
that keeps stalling on a connection that tests fine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------- who runs it
SELF_BUILT = "selfbuilt"        # Bilibili's own edges
CLOUD = "cloud"                 # rented from a public cloud
PEER = "peer"                   # PCDN / mCDN: someone's home connection
UNKNOWN = "unknown"

# Substring -> (operator key, kind). Checked longest-first so that a more
# specific marker wins over a prefix of it.
OPERATORS = {
    "mirrorali": ("cdn.op.aliyun", CLOUD),
    "mirroraliov": ("cdn.op.aliyun", CLOUD),
    "mirrorcos": ("cdn.op.tencent", CLOUD),
    "mirrorcoso1": ("cdn.op.tencent", CLOUD),
    "mirrorhw": ("cdn.op.huawei", CLOUD),
    "mirrorhwo1": ("cdn.op.huawei", CLOUD),
    "mirrorbos": ("cdn.op.baidu", CLOUD),
    "mirrorks3": ("cdn.op.kingsoft", CLOUD),
    "mirrorks3ovs": ("cdn.op.kingsoft", CLOUD),
    "mirrorwcs": ("cdn.op.wangsu", CLOUD),
    "mirrorup": ("cdn.op.bilibili", SELF_BUILT),
    "gotcha": ("cdn.op.bilibili", SELF_BUILT),
    "bcache": ("cdn.op.bilibili", SELF_BUILT),
    "akamai": ("cdn.op.akamai", CLOUD),
    "akamaized": ("cdn.op.akamai", CLOUD),
}

# Carrier markers, as they appear between dashes in an edge name.
CARRIERS = {
    "ct": "cdn.isp.telecom",
    "cu": "cdn.isp.unicom",
    "cm": "cdn.isp.mobile",
    "ctcc": "cdn.isp.telecom",
    "cucc": "cdn.isp.unicom",
    "cmcc": "cdn.isp.mobile",
    "bgp": "cdn.isp.bgp",
    "js": "cdn.isp.edu",          # CERNET
}

# Province and city codes we are confident about. Everything else is reported
# as its raw code rather than guessed at - see the module docstring.
PROVINCES = {
    "bj": "cdn.pr.beijing", "sh": "cdn.pr.shanghai", "tj": "cdn.pr.tianjin",
    "cq": "cdn.pr.chongqing", "gd": "cdn.pr.guangdong", "js": "cdn.pr.jiangsu",
    "zj": "cdn.pr.zhejiang", "sd": "cdn.pr.shandong", "hb": "cdn.pr.hubei",
    "hn": "cdn.pr.hunan", "ha": "cdn.pr.henan", "he": "cdn.pr.hebei",
    "sc": "cdn.pr.sichuan", "fj": "cdn.pr.fujian", "ah": "cdn.pr.anhui",
    "jx": "cdn.pr.jiangxi", "ln": "cdn.pr.liaoning", "jl": "cdn.pr.jilin",
    "hl": "cdn.pr.heilongjiang", "sn": "cdn.pr.shaanxi", "sx": "cdn.pr.shanxi",
    "gx": "cdn.pr.guangxi", "gz": "cdn.pr.guizhou", "yn": "cdn.pr.yunnan",
    "gs": "cdn.pr.gansu", "nx": "cdn.pr.ningxia", "qh": "cdn.pr.qinghai",
    "xj": "cdn.pr.xinjiang", "xz": "cdn.pr.xizang", "nm": "cdn.pr.neimenggu",
    "hi": "cdn.pr.hainan",
}

# Only cities seen often enough to be sure of. A short honest table beats a
# long invented one.
CITIES = {
    "hbyc": "cdn.city.yichang", "hbwh": "cdn.city.wuhan",
    "jsnj": "cdn.city.nanjing", "jssz": "cdn.city.suzhou",
    "zjhz": "cdn.city.hangzhou", "zjnb": "cdn.city.ningbo",
    "gdgz": "cdn.city.guangzhou", "gdsz": "cdn.city.shenzhen",
    "gddg": "cdn.city.dongguan", "sccd": "cdn.city.chengdu",
    "sdqd": "cdn.city.qingdao", "sdjn": "cdn.city.jinan",
    "fjfz": "cdn.city.fuzhou", "fjxm": "cdn.city.xiamen",
    "hnzz": "cdn.city.zhengzhou", "hncs": "cdn.city.changsha",
    "ahhf": "cdn.city.hefei", "lnsy": "cdn.city.shenyang",
    "sxxa": "cdn.city.xian", "snxa": "cdn.city.xian",
    "cqcq": "cdn.pr.chongqing", "jxnc": "cdn.city.nanchang",
}

# A region prefix, where the name carries one.
REGIONS = {
    "cn": "cdn.region.mainland",
    "hk": "cdn.region.hongkong",
    "tw": "cdn.region.taiwan",
    "sg": "cdn.region.singapore",
    "jp": "cdn.region.japan",
    "us": "cdn.region.us",
    "ov": "cdn.region.overseas",
    "oversea": "cdn.region.overseas",
}

# Peer-assisted nodes: the mcdn domain, and the pattern that spells an IPv4
# address out inside the hostname (``xy118x123x45x67xy``).
_PEER_DOMAIN = re.compile(r"\bmcdn\.bilivideo\.c[no]m?\b|\bmcdn\.bilivideo\.cn\b")
_PEER_IP = re.compile(r"\bxy(\d{1,3})x(\d{1,3})x(\d{1,3})x(\d{1,3})xy\b")
# ``cn-hbyc-ct-01`` and friends: region, then a geo code, then a carrier.
_EDGE = re.compile(
    r"^(?P<region>[a-z]{2})-(?P<geo>[a-z]{2,8})-(?P<carrier>ct|cu|cm|ctcc|cucc|cmcc|bgp|js)(?:-|$)"
)


@dataclass(frozen=True)
class CdnInfo:
    """What could be read off a hostname, and nothing that could not."""

    host: str = ""
    operator_key: str = ""      # i18n key for who runs the node
    kind: str = UNKNOWN         # SELF_BUILT / CLOUD / PEER / UNKNOWN
    region_key: str = ""
    province_key: str = ""
    city_key: str = ""
    carrier_key: str = ""
    geo_code: str = ""          # the raw code, kept when it is not recognised
    peer_ip: str = ""           # the address a peer node spells out, if any

    @property
    def is_peer(self) -> bool:
        """A consumer connection reselling upstream, not a datacentre."""
        return self.kind == PEER

    @property
    def located(self) -> bool:
        return bool(self.region_key or self.province_key or self.city_key)

    def as_dict(self) -> dict:
        return {"host": self.host, "kind": self.kind,
                "operator": self.operator_key, "carrier": self.carrier_key,
                "region": self.region_key, "province": self.province_key,
                "city": self.city_key, "geo_code": self.geo_code,
                "peer_ip": self.peer_ip}


def _operator(host: str):
    """Longest marker wins, so ``mirrorhwo1`` is not read as ``mirrorhw``."""
    best = None
    for marker, value in OPERATORS.items():
        if marker in host and (best is None or len(marker) > len(best[0])):
            best = (marker, value)
    return best[1] if best else ("", UNKNOWN)


def _geo(code: str):
    """Split a geo code into province and city, admitting when it cannot."""
    if not code:
        return "", "", ""
    if code in CITIES:
        city = CITIES[code]
        return PROVINCES.get(code[:2], ""), city, ""
    if code in PROVINCES:
        return PROVINCES[code], "", ""
    if len(code) > 2 and code[:2] in PROVINCES:
        # The province is readable; the city half is not in our table, so the
        # raw code travels with it instead of a guess.
        return PROVINCES[code[:2]], "", code
    return "", "", code


def describe(host: str) -> CdnInfo:
    """Read what the hostname states. Never infers beyond it."""
    if not host:
        return CdnInfo()
    lowered = host.lower().strip()

    peer_match = _PEER_IP.search(lowered)
    if peer_match or _PEER_DOMAIN.search(lowered):
        address = ""
        if peer_match:
            parts = [int(part) for part in peer_match.groups()]
            if all(part <= 255 for part in parts):
                address = ".".join(str(part) for part in parts)
        return CdnInfo(host=host, operator_key="cdn.op.peer", kind=PEER,
                       peer_ip=address)

    operator_key, kind = _operator(lowered)
    name = lowered.split(".")[0]

    region_key = province_key = city_key = carrier_key = geo_code = ""
    match = _EDGE.match(name)
    if match:
        region_key = REGIONS.get(match.group("region"), "")
        carrier_key = CARRIERS.get(match.group("carrier"), "")
        province_key, city_key, geo_code = _geo(match.group("geo"))
    else:
        for token in name.split("-"):
            if not region_key and token in REGIONS:
                region_key = REGIONS[token]
            elif not carrier_key and token in CARRIERS:
                carrier_key = CARRIERS[token]

    return CdnInfo(host=host, operator_key=operator_key, kind=kind,
                   region_key=region_key, province_key=province_key,
                   city_key=city_key, carrier_key=carrier_key,
                   geo_code=geo_code)


def summary(host: str) -> str:
    """One human line, translated - or the bare hostname when nothing is read."""
    from ..i18n import tr

    info = describe(host)
    parts = []
    if info.operator_key:
        parts.append(tr(info.operator_key))
    where = [tr(key) for key in (info.city_key, info.province_key, info.region_key) if key]
    if where:
        place = where[0]
        if info.geo_code and not info.city_key:
            # The name carries a code we do not recognise. Showing it raw beats
            # dropping it: someone who knows the convention can still read it,
            # and nobody is told a city that may be wrong.
            place = f"{place} ({info.geo_code})"
        parts.append(place)
    elif info.geo_code:
        parts.append(info.geo_code)
    if info.carrier_key:
        parts.append(tr(info.carrier_key))
    return " · ".join(parts) if parts else host


def locate_line(host: str, rtt_ms=None, rtt_to_edge: bool = False) -> str:
    """Where the server is, as far as anything here can honestly say.

    Two independent sources, and they cover for each other. The hostname is
    exact when it says anything at all, and says nothing for a cloud-rented
    node or a PCDN peer. The round trip works for every server without
    exception, but only sets a ceiling.

    The ceiling is only offered when it was measured against the serving edge
    itself - the monitor falls back to timing the API host when the edge will
    not answer, and that is a different machine somewhere else - and only when
    it is narrow enough to mean anything. "Within 20 000 km" is not a location.
    """
    from ..i18n import tr
    from .distance import informative, max_distance_km

    where = summary(host)
    if not rtt_to_edge:
        return where
    km = max_distance_km(rtt_ms)
    if not informative(km):
        return where
    ceiling = tr("server.at_most_km", km=f"{km:,.0f}")
    # Keep whatever the first source produced, even when that is just the
    # address. Watching an application, the address *is* the answer to "which
    # server" - dropping it to show a distance alone would remove the only
    # part the reader can look up.
    return f"{where} \u00b7 {ceiling}" if where else ceiling


def detail(host: str) -> str:
    """What can be said about a host beyond its own name - or nothing.

    ``summary`` falls back to the bare hostname so a caller always has
    something to print. A table that already shows the host in one column and
    calls this for the next then prints it twice, which is what a real report
    did for every raw IP address it had measured.
    """
    described = summary(host)
    return "" if described == host else described
