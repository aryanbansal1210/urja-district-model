"""Straight-down plan views of the town, day and night.

    python scripts/shoot_map_plates.py                 # all 8
    python scripts/shoot_map_plates.py optimised_2055  # one

WHY THIS EXISTS
the author, "take a top down view of the model... one for the optimised
2030, 2042, 2055 and zirakpur too. take one at 12 pm and one at 10 pm."

Four subjects x two hours = eight plates. It drives the viewer's own map plate
mode (`?map_shot=<layout>&year=<yyyy>&hour=<h>`, see applyMapShotMode in
viewer3d/app.js), so the plates show exactly what the viewer draws.

THE TRAP THAT COSTS THE MOST TIME HERE: deck.gl runs a requestAnimationFrame
loop, and under headless Edge's virtual clock a live rAF loop advances virtual
time forever - `--virtual-time-budget` never expires and NO FILE IS EVER
WRITTEN. Plate mode copies the settled canvas into an <img> and only then
finalises deck, so the loop stops while the picture survives. Do not "simplify"
that away.

Software WebGL: --disable-gpu falls back to SwiftShader, which renders this
scene fine but slowly, hence the generous virtual-time budget.
"""
from __future__ import annotations

import functools
import http.server
import pathlib
import struct
import subprocess
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "outputs" / "map_plates"
EDGE = pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

WIDTH, HEIGHT = 1600, 1600      # square, because a plan view of a square town is
SCALE = 1        # 1600x1600 native. SwiftShader (software WebGL) cannot
                 # rasterise 2400x2400 of this scene inside any sane timeout.
PORT = 8633

# (name, layout, year) - the year only moves the build, not the layout.
SUBJECTS = [
    ("optimised_2030", "optimised_sa", "2030"),
    ("optimised_2042", "optimised_sa", "2042"),
    ("optimised_2055", "optimised_sa", "2055"),
    ("zirakpur", "zirakpur_ribbon", "2030"),
]
HOURS = [("noon", 12), ("night", 22)]


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


def shoot(name: str, layout: str, year: str, label: str, hour: int) -> bool:
    url = (f"http://127.0.0.1:{PORT}/viewer3d/index.html"
           f"?map_shot={layout}&year={year}&hour={hour}")
    dst = (OUT / f"plan_{name}_{label}.png").resolve()   # ABSOLUTE, always
    dst.unlink(missing_ok=True)
    subprocess.run(
        [str(EDGE), "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--force-device-scale-factor={SCALE}",
         f"--screenshot={dst}", f"--window-size={WIDTH},{HEIGHT}",
         "--virtual-time-budget=20000", url],
        capture_output=True, timeout=300,
    )
    if not dst.exists():
        print(f"  {name}_{label:<6} NOT WRITTEN")
        return False
    w, h = png_size(dst)
    print(f"  plan_{name}_{label:<6} {w}x{h}  {dst.stat().st_size/1024:.0f} KB")
    return True


def main() -> None:
    if not EDGE.exists():
        sys.exit(f"Edge not found at {EDGE}")
    want = [a.lower() for a in sys.argv[1:]]
    subjects = [s for s in SUBJECTS if not want or s[0] in want]
    if not subjects:
        sys.exit("no match; choose from "
                 f"{', '.join(s[0] for s in SUBJECTS)}")

    OUT.mkdir(parents=True, exist_ok=True)
    srv = serve()
    try:
        total = len(subjects) * len(HOURS)
        print(f"shooting {total} plan views into {OUT}")
        good = 0
        for name, layout, year in subjects:
            for label, hour in HOURS:
                good += shoot(name, layout, year, label, hour)
    finally:
        srv.shutdown()
    print(f"\n{good}/{total} written")


if __name__ == "__main__":
    main()
