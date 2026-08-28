"""Render the Urja app icons from one SVG, in the app's own palette.

WHY THIS EXISTS. The shipped icons were a black tile with a green lightning
bolt, drawn for the pre- dark theme. The redesigned app is warm
paper and amber, so on a home screen the icon looked like a different product.

NO IMAGING LIBRARY IS AVAILABLE in this environment - PIL, cairosvg and
reportlab are all absent - so rendering goes through headless Edge, the same
route WRITEUP/figures/make_png.py uses, and the same two traps apply:

  1. `--screenshot` MUST BE AN ABSOLUTE PATH. Edge silently writes nothing on
     a relative one and still exits 0.
  2. NEVER pass `--user-data-dir`. It makes headless Edge exit before it
     writes.

DESIGN. Warm paper ground (#EFEDE7, the app's --canvas) with an amber sun
(#E8B54E, --solar) over an ink roofline (#1B1B1B, --ink): rooftop solar, said
in three shapes. Everything sits inside the central 66% so the 512 icon
survives being cropped to a circle as a MASKABLE icon, which the manifest
declares it to be.

    python scripts/build_app_icons.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ICONS = HERE.parent / "app" / "icons"
EDGE = pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application"
                    r"\msedge.exe")

CANVAS, SOLAR, INK, LINE = "#EFEDE7", "#E8B54E", "#1B1B1B", "#E4E2DC"

# THE MARK IS LIFTED VERBATIM FROM THE APP'S OWN INTRO SCREEN (app.js,
# firstRun),, because
# approximation of it was visibly not the same drawing. Every number below -
# r=52, stroke 8, the house path, the 3.4 door stroke - is copied from there,
# so the icon and the splash are provably one mark rather than two that
# resemble each other. If firstRun's svg is ever restyled, re-run this.
# The arc length is READ FROM data.js, the same `renewable_share` the intro
# screen uses, so the ring shows the town's real figure rather than a decorative
# re-running this script if you want them to keep matching.
def _renewable_share() -> float:
    import json
    import re
    try:
        t = (HERE.parent / "app" / "data.js").read_text(encoding="utf-8")
        d = json.loads(t[re.search(r"window\.APP_DATA\s*=\s*", t).end():]
                       .rstrip().rstrip(";"))
        return float(d["town"]["renewable_share"])
    except Exception:
        return 0.78                      # last known, if data.js is unreadable

_CIRC = 2 * 3.14159265 * 52           # 326.7, the intro screen's own circle

# 0.86 shrinks the mark so its outer edge lands inside the MASKABLE safe zone.
# Untouched, the stroke reaches r=56 of a 60 half-box - 93% of the radius -
# and a launcher cropping the tile to a circle would clip the ring. At 0.86 the
# edge sits at 48/60 = 80%, which is the documented safe fraction.
_FIT = 0.86


def _svg(size: int) -> str:
    """The intro-screen mark, at an EXPLICIT pixel size.

    TRAP 3, and two attempts fell into it before this one. Sizing the SVG in
    viewport units (width:100vw) inside an HTML wrapper does NOT work here:
    headless Edge does not give a 180 px window a 180 px viewport, so 100vw
    resolved larger than the screenshot and the capture returned the top-left
    corner - plain background. icon-192 and apple-touch-icon shipped BLANK and
    reached a home screen as an empty tile. Setting width/height on the SVG
    itself makes the intrinsic size the target, independent of viewport.
    """
    on = _CIRC * _renewable_share()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}"
     height="{size}" viewBox="0 0 120 120">
  <rect width="120" height="120" fill="{CANVAS}"/>
  <g transform="translate(60 60) scale({_FIT}) translate(-60 -60)">
    <circle cx="60" cy="60" r="52" fill="none" stroke="{LINE}" stroke-width="8"/>
    <circle cx="60" cy="60" r="52" fill="none" stroke="{SOLAR}" stroke-width="8"
            stroke-linecap="round"
            stroke-dasharray="{on:.0f} {_CIRC:.0f}"
            transform="rotate(-90 60 60)"/>
    <path d="M60 38 40 56v22h40V56z" fill="none" stroke="{INK}"
          stroke-width="4" stroke-linejoin="round"/>
    <path d="M55 78V66h10v12" fill="none" stroke="{INK}"
          stroke-width="3.4" stroke-linejoin="round"/>
  </g>
</svg>
"""


WRAP = """<!doctype html><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;overflow:hidden;background:{bg}}}
svg{{display:block}}</style>
{svg}"""


def render(out: pathlib.Path, size: int, tmp_dir: pathlib.Path) -> bool:
    out = out.resolve()                      # trap 1: absolute, always
    if out.exists():
        out.unlink()
    page = (tmp_dir / f"_icon_{size}.html").resolve()
    page.write_text(WRAP.format(bg=CANVAS, svg=_svg(size)), encoding="utf-8")
    subprocess.run([str(EDGE), "--headless", "--disable-gpu",
                    "--hide-scrollbars", f"--screenshot={out}",
                    f"--window-size={size},{size}",
                    "--virtual-time-budget=4000",
                    page.as_uri()],
                   capture_output=True, text=True, timeout=120)
    page.unlink(missing_ok=True)
    return out.exists()


def looks_blank(p: pathlib.Path) -> bool:
    """Cheap guard against shipping an empty tile again.

    A flat single-colour PNG of this size compresses to a few hundred bytes;
    the real mark lands well above that. Not a pixel check - just enough to
    make the failure that reached the author's home screen impossible to repeat
    silently.
    """
    return p.stat().st_size < 1200


def main() -> int:
    if not EDGE.exists():
        sys.exit(f"Edge not found at {EDGE}")
    ICONS.mkdir(parents=True, exist_ok=True)
    (ICONS / "_icon.svg").write_text(_svg(512), encoding="utf-8")  # for editing
    targets = [("icon-512.png", 512), ("icon-192.png", 192),
               ("apple-touch-icon.png", 180)]
    ok = True
    for name, size in targets:
        dst = ICONS / name
        if not render(dst, size, ICONS):
            print(f"  FAILED {name} - nothing written")
            ok = False
        elif looks_blank(dst):
            print(f"  FAILED {name} - {dst.stat().st_size:,} B, that is BLANK")
            ok = False
        else:
            print(f"  wrote {name:<22} {size}x{size}  {dst.stat().st_size:,} B")
    if not ok:
        print("\n  Icons NOT updated. Do not deploy - the phone would show an "
              "empty tile.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
