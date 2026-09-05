"""A read-only dashboard your phone can open.

The overlay lives on the machine being measured, which is no help when the PC
is across the room or you are holding the phone while the game runs. This
serves the same numbers as a small web page on the local network: no app to
install, and it works the same on Android and iOS.

Deliberately narrow: it only ever *reads*. There is no endpoint that changes a
setting or controls the monitor, so the worst a stranger on your network can do
is look at latency figures - and even that needs the access code.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dependency
    psutil = None  # type: ignore

LOG = logging.getLogger(__name__)

DEFAULT_PORT = 23125


class _Snapshot:
    """Latest state, written by the GUI thread and read by request threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {"ok": False}

    def set(self, data: dict) -> None:
        with self._lock:
            self._data = data

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)


def local_addresses() -> list:
    """This machine's LAN addresses, best guess first.

    The address a phone should type is the one on the same subnet as the phone,
    so the route-based guess (which interface reaches the internet) comes first.
    """
    found: list = []

    # The interface that would carry outbound traffic is almost always the one
    # the phone is also on; no packet is actually sent.
    probe = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.2)
        probe.connect(("8.8.8.8", 53))
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        if probe is not None:
            probe.close()

    if psutil is not None:
        try:
            for name, addresses in psutil.net_if_addrs().items():
                if name.lower().startswith(("lo", "docker", "veth", "vmnet", "vbox")):
                    continue
                for entry in addresses:
                    if entry.family != socket.AF_INET:
                        continue
                    try:
                        address = ipaddress.ip_address(entry.address)
                    except ValueError:
                        continue
                    if address.is_loopback or address.is_link_local:
                        continue
                    if entry.address not in found:
                        found.append(entry.address)
        except Exception as exc:  # pragma: no cover - platform dependent
            LOG.debug("interface list unavailable: %s", exc)
    return found


# The query parameter the access code arrives in. The Android viewer builds
# its URL with the same name (Pairing.QUERY_KEY) and a test asserts the two
# agree - they disagreed once, and neither side's own tests could tell,
# because each was perfectly consistent with itself.
ACCESS_QUERY = "key"


def dashboard_urls(port: int, code: str = "") -> list:
    """The addresses to type into a phone browser."""
    suffix = f"/?{ACCESS_QUERY}={code}" if code else "/"
    return [f"http://{address}:{port}{suffix}" for address in local_addresses()]


PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#12141a">
<title>LagScope</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0; padding: env(safe-area-inset-top) 16px 24px;
    background: #12141a; color: #f4f6fb;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", system-ui, sans-serif;
  }
  header { display: flex; align-items: baseline; gap: 8px; padding: 18px 2px 6px; }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; letter-spacing: .04em; }
  header span { font-size: 13px; color: #9aa3b5; margin-left: auto;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
  .total { font-size: 64px; font-weight: 700; line-height: 1.05; margin: 4px 0 2px;
           font-variant-numeric: tabular-nums; }
  .sub { color: #9aa3b5; font-size: 13px; margin-bottom: 18px; }
  .card { background: #171a22; border: 1px solid #2b303c; border-radius: 14px;
          padding: 14px 16px; margin-bottom: 12px; }
  .row { display: flex; justify-content: space-between; align-items: baseline;
         padding: 7px 0; font-size: 15px; }
  .row + .row { border-top: 1px solid #23283300; }
  .row .k { color: #9aa3b5; }
  .row .v { font-variant-numeric: tabular-nums; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .extras { margin-bottom: 12px; }
  .extras .row .v { font-weight: 600; }
  .stat { background: #171a22; border: 1px solid #2b303c; border-radius: 14px; padding: 12px 14px; }
  .stat .k { color: #9aa3b5; font-size: 12px; }
  .stat .v { font-size: 20px; font-weight: 600; margin-top: 2px; font-variant-numeric: tabular-nums; }
  svg { display: block; width: 100%; height: 72px; }
  .good { color: #3fd07f; } .warn { color: #f6c445; } .bad { color: #ff5d5d; }
  .unknown { color: #9aa3b5; }
  .offline { text-align: center; padding: 28px 12px; color: #ff5d5d; font-size: 15px; }
  footer { color: #5b6376; font-size: 12px; text-align: center; margin-top: 18px; }
</style>
</head>
<body>
<header><h1>LagScope</h1><span id="target">—</span></header>
<div class="total unknown" id="total">--</div>
<div class="sub" id="status">连接中…</div>
<div id="body" hidden>
  <div class="card" id="breakdown"></div>
  <div class="card extras" id="extras" hidden></div>
  <div class="card"><svg id="spark" viewBox="0 0 300 72" preserveAspectRatio="none"></svg></div>
  <div class="grid" id="stats"></div>
</div>
<div class="offline" id="offline" hidden>连不上监视器<br><small id="offlineHint"></small></div>
<footer id="foot"></footer>
<script>
const KEY = new URLSearchParams(location.search).get("key") || "";
const $ = (id) => document.getElementById(id);
let misses = 0;

function fmtMs(v) {
  if (v === null || v === undefined) return "--";
  if (v < 1000) return Math.round(v) + " ms";
  if (v < 60000) return (v / 1000).toFixed(2) + " s";
  return Math.floor(v / 60000) + " m " + ((v % 60000) / 1000).toFixed(0) + " s";
}
function fmtMbps(v) {
  if (v === null || v === undefined) return "--";
  if (v < 1) return Math.round(v * 1000) + " kbps";
  if (v < 1000) return v.toFixed(1) + " Mbps";
  return (v / 1000).toFixed(2) + " Gbps";
}
function spark(values) {
  const el = $("spark");
  const pts = values.filter((v) => v !== null);
  if (pts.length < 2) { el.innerHTML = ""; return; }
  const lo = Math.min(...pts), hi = Math.max(...pts), span = Math.max(1, hi - lo);
  const step = 300 / Math.max(1, values.length - 1);
  let d = "", pen = false;
  values.forEach((v, i) => {
    if (v === null) { pen = false; return; }
    const x = (i * step).toFixed(1);
    const y = (68 - ((v - lo) / span) * 62).toFixed(1);
    d += (pen ? "L" : "M") + x + " " + y + " ";
    pen = true;
  });
  el.innerHTML = '<path d="' + d + '" fill="none" stroke="#00a1d6" stroke-width="2" ' +
                 'stroke-linejoin="round" stroke-linecap="round"/>';
}
function render(s) {
  $("offline").hidden = true;
  $("body").hidden = false;
  $("target").textContent = s.target || "";
  const total = $("total");
  total.textContent = fmtMs(s.total_ms);
  total.className = "total " + (s.level || "unknown");
  $("status").textContent = s.status || (s.measured ? "实测" : "估算");

  $("breakdown").innerHTML = s.rows
    .map((r) => '<div class="row"><span class="k">' + r[0] + '</span><span class="v">' +
                r[1] + "</span></div>")
    .join("");
  const extras = s.extras || [];
  const extrasEl = $("extras");
  extrasEl.hidden = extras.length === 0;
  extrasEl.innerHTML = extras
    .map((e) => '<div class="row"><span class="k">' + e.label +
                '</span><span class="v ' + (e.level || "unknown") + '">' + e.value +
                "</span></div>")
    .join("");
  spark(s.spark || []);
  $("stats").innerHTML = s.stats
    .map((r) => '<div class="stat"><div class="k">' + r[0] + '</div><div class="v">' +
                r[1] + "</div></div>")
    .join("");
  $("foot").textContent = s.foot || "";
}
async function tick() {
  try {
    const res = await fetch("api/state" + (KEY ? "?key=" + encodeURIComponent(KEY) : ""),
                            { cache: "no-store" });
    if (res.status === 403) {
      $("body").hidden = true; $("offline").hidden = false;
      $("offlineHint").textContent = "访问码不对";
      return;
    }
    render(await res.json());
    misses = 0;
  } catch (e) {
    if (++misses >= 3) {
      $("body").hidden = true;
      $("offline").hidden = false;
      $("offlineHint").textContent = "电脑上的 LagScope 可能已关闭，或手机不在同一个网络";
    }
  }
}
tick();
setInterval(tick, 2000);
</script>
</body>
</html>
"""


def _make_handler(snapshot: _Snapshot, access_code: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "LagScopeDashboard"

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            LOG.debug("dashboard %s", fmt % args)

        def _authorised(self, query: dict) -> bool:
            if not access_code:
                return True
            return (query.get(ACCESS_QUERY) or [""])[0] == access_code

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # The page is self-contained; forbid anything external outright.
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"

            if path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/state":
                if not self._authorised(query):
                    self._send(403, b'{"error":"bad key"}', "application/json")
                    return
                payload = json.dumps(snapshot.get(), ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            self._send(404, b'{"error":"not found"}', "application/json")

    return Handler


def reuse_address_ok(platform: str = "") -> bool:
    """Whether SO_REUSEADDR is safe to set on this platform.

    The two families disagree about what the option means. On Unix it only
    allows rebinding a port stuck in TIME_WAIT, which is exactly what anyone
    restarting a server wants. On Windows it means "take this port even if
    another socket is bound to it right now" - so two copies of LagScope, or
    LagScope and anything else already on 23125, would both bind happily and
    requests would land on whichever socket the kernel felt like.

    Taking the platform as an argument is what makes the decision checkable
    from any machine rather than only from a Windows one.
    """
    return not (platform or sys.platform).startswith(("win", "cygwin"))


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """An HTTP server that refuses a port somebody else already holds."""

    allow_reuse_address = reuse_address_ok()


class DashboardServer:
    """Serves the phone dashboard; safe to start and stop repeatedly."""

    def __init__(self, port: int = DEFAULT_PORT, access_code: str = "",
                 bind_host: str = "0.0.0.0") -> None:
        self.port = int(port)
        self.access_code = access_code
        self.bind_host = bind_host
        self._snapshot = _Snapshot()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> bool:
        if self._server is not None:
            return True
        try:
            server = _ExclusiveHTTPServer(
                (self.bind_host, self.port), _make_handler(self._snapshot, self.access_code)
            )
        except OSError as exc:
            LOG.warning("dashboard could not listen on %s:%s: %s", self.bind_host, self.port, exc)
            return False
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="lagscope-web",
                                        kwargs={"poll_interval": 0.5}, daemon=True)
        self._thread.start()
        LOG.info("phone dashboard on %s", ", ".join(dashboard_urls(self.port, self.access_code)))
        return True

    def stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def publish(self, data: dict) -> None:
        self._snapshot.set(data)

    def urls(self) -> list:
        return dashboard_urls(self.port, self.access_code)
