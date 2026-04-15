#!/usr/bin/env python3
"""
ATLAS mockups dev server — stdlib only, zero deps.
Serves frontend/mockups/ on :8765 with live reload.

Routes:
  GET /            → 302 to /styleguide.html
  GET /_reload     → max mtime across tracked files (plain text)
  GET /*.html      → file + injected reload poller before </body>
  GET /*           → normal static file

Client polls /_reload every 400ms; reload on change.
Run:  python3 frontend/mockups/_devserver.py
Stop: pkill -f _devserver.py
"""

import http.server
import os
import pathlib
import socketserver
import sys
from typing import Any

ROOT = pathlib.Path(__file__).parent.resolve()
PORT = int(os.environ.get("ATLAS_MOCKUP_PORT", "8765"))
TRACK_EXTS = {".html", ".css", ".js", ".json", ".svg"}

RELOAD_SCRIPT = (
    """
<script>
(function(){
  var last = null;
  async function tick() {
    try {
      var r = await fetch('/_reload', {cache:'no-store'});
      var t = (await r.text()).trim();
      if (last === null) { last = t; return; }
      if (t !== last) { last = t; location.reload(); }
    } catch (e) {}
  }
  setInterval(tick, 400);
  var pill = document.createElement('div');
  pill.textContent = '\u25cf live';
  pill.style.cssText = 'position:fixed;bottom:10px;right:10px;z-index:99999;'+
    'font:500 10px/1 Inter,system-ui,sans-serif;color:#0E5A43;background:#E6F2ED;'+
    'border:1px solid #9BD4BD;border-radius:999px;padding:5px 10px;'+
    'letter-spacing:0.04em;text-transform:uppercase;pointer-events:none;opacity:0.85;';
  document.addEventListener('DOMContentLoaded', function(){ document.body.appendChild(pill); });
})();
</script>
"""
).encode("utf-8")


def max_mtime() -> int:
    m = 0
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in TRACK_EXTS:
            try:
                m = max(m, p.stat().st_mtime_ns)
            except OSError:
                pass
    return m


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "":
            self.send_response(302)
            self.send_header("Location", "/styleguide.html")
            self.end_headers()
            return

        if self.path == "/_reload":
            self._send(200, str(max_mtime()).encode(), "text/plain; charset=utf-8")
            return

        # HTML: inject reload poller
        rel = self.path.split("?", 1)[0].lstrip("/")
        if rel.endswith(".html"):
            fp = ROOT / rel
            if fp.exists() and fp.is_file():
                page_bytes = fp.read_bytes()
                if b"</body>" in page_bytes:
                    page_bytes = page_bytes.replace(b"</body>", RELOAD_SCRIPT + b"</body>", 1)
                else:
                    page_bytes = page_bytes + RELOAD_SCRIPT
                self._send(200, page_bytes, "text/html; charset=utf-8")
                return

        # Fallback: normal static serving
        return super().do_GET()

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet, we don't need request logs
        pass


class ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    os.chdir(ROOT)
    with ReusableServer(("0.0.0.0", PORT), Handler) as srv:
        msg = f"atlas mockups dev server listening on http://0.0.0.0:{PORT}/ (root={ROOT})"
        print(msg, flush=True)  # noqa: T201 — CLI dev server, not production
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped", flush=True)  # noqa: T201 — CLI dev server
            sys.exit(0)


if __name__ == "__main__":
    main()
