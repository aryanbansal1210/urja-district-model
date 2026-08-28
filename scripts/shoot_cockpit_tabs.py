"""One tall PNG per cockpit tab, with the whole panel expanded.

    python scripts/shoot_cockpit_tabs.py
    python scripts/shoot_cockpit_tabs.py live impact     # only these tabs

WHY THIS EXISTS
the author, "give me the pictures for all the tabs of cockpit one by one
separately, not screenshots but like the design pictures, like the extended one
with all the info in one pic for one tab, like it will be long."

A screenshot of the running viewer only ever catches the scrolled viewport, and
the cockpit is deliberately a short panel that scrolls internally. This drives
the viewer's OWN plate mode (`?cockpit_shot=<tab>`, see applyCockpitShotMode in
viewer3d/app.js) which expands the panel to its natural height, then rasterises
it. Reusing the app's rendering is the point: the plates cannot drift from what
the viewer actually draws.

TWO TRAPS INHERITED FROM WRITEUP/figures/make_png.py, both cost time before:
  1. `--screenshot` MUST be an absolute path. Edge resolves a relative one
     against its own working directory, fails, and still exits 0 - nothing is
     written and nothing complains.
  2. Do NOT pass `--user-data-dir`. With the user's own Edge running, the
     headless instance exits before writing anything.

The page reports the height it needs in `document.title` (`cockpit-<tab>-<px>`),
so this takes a first pass to measure and a second to shoot at the right size.
Without that the tall tabs come out cropped.
"""
from __future__ import annotations

import functools
import http.server
import pathlib
import re
import struct
import subprocess
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VIEWER = ROOT / "viewer3d"
OUT = ROOT / "outputs" / "cockpit_plates"
EDGE = pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

TABS = ["live", "trends", "trading", "impact", "cells", "settings"]
# The three pieces of chrome outside the cockpit. Each reports its OWN width as
# well as its height, because unlike the cockpit they are not all one width -
# the banner is wide and short, the two panels are narrow and tall.
PANELS = {
    "banner": 1560,        # measure-pass viewport: wide enough for one line
    "legend": 520,
    "keynumbers": 760,
}
WIDTH = 434          # panel is 390 wide + margin, matching the real cockpit
SCALE = 2            # retina, so the plates stand up in a printed appendix
PORT = 8629
FALLBACK_HEIGHT = 1400


def png_size(path: pathlib.Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a png")
    return struct.unpack(">II", head[16:24])


def serve() -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def run_edge(url: str, dst: pathlib.Path, width: int, height: int) -> None:
    """Shoot at `width` x `height` CSS pixels, rasterised at SCALE.

    THE TRAP: `--window-size` is CSS pixels. Passing width*SCALE does NOT give
    a 2x image - it gives a genuinely WIDER PAGE, which fires different media
    queries and lays the panel out at a different height. Measuring at 660 and
    shooting at 1320 is why the first plates carried a long empty tail: the
    measured layout was not the layout being shot. `--force-device-scale-factor`
    is the flag that actually scales pixels while leaving the CSS layout alone.
    """
    dst.unlink(missing_ok=True)
    subprocess.run(
        [str(EDGE), "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--force-device-scale-factor={SCALE}",
         f"--screenshot={dst}", f"--window-size={width},{height}",
         "--virtual-time-budget=7000", url],
        capture_output=True, timeout=60,
    )


def measure_panel(url: str, probe_width: int) -> tuple[int, int]:
    """Read `panel-<name>-<w>-<h>` out of <title> via --dump-dom."""
    proc = subprocess.run(
        [str(EDGE), "--headless", "--disable-gpu", "--dump-dom",
         f"--force-device-scale-factor={SCALE}",
         f"--window-size={probe_width},{FALLBACK_HEIGHT}",
         "--virtual-time-budget=7000", url],
        capture_output=True, timeout=60, text=True, errors="replace",
    )
    m = re.search(r"panel-[a-z]+-(\d+)-(\d+)", proc.stdout or "")
    if not m:
        return probe_width, FALLBACK_HEIGHT
    return int(m.group(1)), int(m.group(2))


def shoot_panel(name: str) -> bool:
    probe = PANELS[name]
    url = f"http://127.0.0.1:{PORT}/viewer3d/index.html?panel_shot={name}"
    dst = (OUT / f"panel_{name}.png").resolve()
    width, height = measure_panel(url, probe)
    run_edge(url, dst, width, height)
    if not dst.exists():
        print(f"  {name:<12} NOT WRITTEN")
        return False
    w, h = png_size(dst)
    print(f"  {name:<12} {w}x{h}  {dst.stat().st_size/1024:.0f} KB")
    return True


def measure(url: str) -> int:
    """First pass: read the height the page says it needs.

    `--dump-dom` prints the serialised DOM to stdout, and plate mode writes
    `cockpit-<tab>-<px>` into <title>, so one cheap pass gives the exact height.
    Without it every plate is shot at a fixed size and carries a long empty
    tail (or, worse, gets cropped).
    """
    proc = subprocess.run(
        [str(EDGE), "--headless", "--disable-gpu", "--dump-dom",
         f"--force-device-scale-factor={SCALE}",
         f"--window-size={WIDTH},{FALLBACK_HEIGHT}",
         "--virtual-time-budget=7000", url],
        capture_output=True, timeout=60, text=True, errors="replace",
    )
    m = re.search(r"cockpit-[a-z]+-(\d+)", proc.stdout or "")
    return int(m.group(1)) if m else FALLBACK_HEIGHT


def shoot(tab: str) -> bool:
    url = f"http://127.0.0.1:{PORT}/viewer3d/index.html?cockpit_shot={tab}"
    dst = (OUT / f"cockpit_{tab}.png").resolve()      # ABSOLUTE, see docstring
    height = measure(url)
    run_edge(url, dst, WIDTH, height)          # CSS px; SCALE handles the rest
    if not dst.exists():
        print(f"  {tab:<10} NOT WRITTEN")
        return False
    w, h = png_size(dst)
    print(f"  {tab:<10} {w}x{h}  {dst.stat().st_size/1024:.0f} KB")
    return True


def main() -> None:
    if not EDGE.exists():
        sys.exit(f"Edge not found at {EDGE}")
    want = [a.lower() for a in sys.argv[1:]]
    tabs = [t for t in TABS if not want or t in want]
    panels = [p for p in PANELS if not want or p in want]
    if not tabs and not panels:
        sys.exit("no match; choose from "
                 f"{', '.join(TABS)}, {', '.join(PANELS)}")

    OUT.mkdir(parents=True, exist_ok=True)
    srv = serve()
    try:
        total = len(tabs) + len(panels)
        print(f"shooting {total} plates into {OUT}")
        good = sum(shoot(t) for t in tabs) + sum(shoot_panel(p) for p in panels)
    finally:
        srv.shutdown()
    print(f"\n{good}/{total} written")


if __name__ == "__main__":
    main()
