"""Frame-capture sink for recording the 3D viewer,.

WHY THIS EXISTS. The viewer renders to a WebGL canvas at 2102 x 1484. The
browser-automation screenshot tool returns an image into the agent's context,
which is fine for one still and hopeless for a 200-frame animation. So instead
the PAGE captures itself and POSTs each frame here, and this process writes it
to disk. Frames never pass through the conversation.

The canvas IS readable - `deckgl-overlay.toDataURL` returns ~4 MB of real
pixels rather than a blank buffer, checked before any of this was written.

CORS: the viewer is served from :8731 and this listens on a different port, so
every response carries `Access-Control-Allow-Origin: *`. Nothing else is
permitted and nothing is served back.

    POST /frame?seq=0007&run=sunsweep   body = raw PNG or JPEG bytes
        -> writes <outdir>/<run>/<seq>.<ext>
    GET  /ping                          -> "ok", used by the page to confirm
    POST /done?run=sunsweep             -> prints the frame count

Run from district_v3:
    python -u scripts/frame_capture_server.py --port 8732 --out outputs/frames
"""
from __future__ import annotations

import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

OUT_ROOT = Path("outputs/frames")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self, code: int = 200, ctype: str = "text/plain", n: int = 0) -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(n))
        self.end_headers()

    def do_OPTIONS(self) -> None:          # preflight
        self._cors(204)

    def do_GET(self) -> None:
        body = b"ok"
        self._cors(200, "text/plain", len(body))
        self.wfile.write(body)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        run = (q.get("run", ["default"])[0] or "default")
        run = "".join(c for c in run if c.isalnum() or c in "-_")

        if u.path == "/done":
            d = OUT_ROOT / run
            n = len(list(d.glob("*"))) if d.exists() else 0
            print("[done] run=%s frames=%d -> %s" % (run, n, d), flush=True)
            body = str(n).encode()
            self._cors(200, "text/plain", len(body))
            self.wfile.write(body)
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length) if length else b""
        # Underscores and hyphens survive: the stills run posts real filenames
        # like `01_town_overview_day`, not a frame number, and stripping the
        # separators would collapse them into an unreadable blob.
        seq = (q.get("seq", ["0000"])[0] or "0000")
        seq = "".join(c for c in seq if c.isalnum() or c in "_-")
        ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"

        d = OUT_ROOT / run
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%s.%s" % (seq, ext))).write_bytes(data)
        if int(seq) % 20 == 0:
            print("  [%s] frame %s  %d KB" % (run, seq, len(data) // 1024), flush=True)

        body = b"ok"
        self._cors(200, "text/plain", len(body))
        self.wfile.write(body)

    def log_message(self, *a) -> None:     # keep the console readable
        return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8732)
    ap.add_argument("--out", default="outputs/frames")
    a = ap.parse_args()

    global OUT_ROOT
    OUT_ROOT = Path(a.out)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print("frame sink listening on http://127.0.0.1:%d  -> %s"
          % (a.port, OUT_ROOT.resolve()), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
