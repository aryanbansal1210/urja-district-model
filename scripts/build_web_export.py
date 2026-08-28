"""Build a self-contained, hostable copy of the 3D viewer.

WHY THIS EXISTS
    The viewer runs from the repo, where it reads its layouts from
    `../outputs/geojson3d` and pulls deck.gl off unpkg. Neither works for a
    link someone can open: the data sits outside the served folder, and the
    CDN is a third-party dependency that can disappear or be blocked.

WHAT IT PRODUCES
    A directory that can be dropped on any static host as-is. Nothing in it
    points outside itself.

WHAT IT DELIBERATELY LEAVES OUT
    videos/        38.61 MB   demo captures, not part of the app
    screenshots/   17.16 MB   ditto
    _design/        4.80 MB   design reference plates
    *.bak, *.py     3.65 MB   nine app.js backups and the build scripts
    CANDIDATE*     13.67 MB   scratch layouts the viewer never offers
    Shipping the folder as-is would be ~80 MB of which the app uses under 3.

THE SOURCE TREE IS NEVER MODIFIED. DATA_ROOT is rewritten in the COPY only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VIEWER = ROOT / "viewer3d"
GEOJSON = ROOT / "outputs" / "geojson3d"

# The six layouts the viewer actually offers in its picker. Anything else in
# outputs/geojson3d is scratch (the CANDIDATE series) and must not ship.
LAYOUTS = [
    "optimised_sa",
    "chandigarh_sector",
    "dispersed_low",
    "compact_centre",
    "radial",
    "zirakpur_ribbon",
]

# deck.gl, pinned. The source reads `@^9.0.0`, a RANGE, which means the page
# can silently change behaviour when unpkg resolves it to a new minor. An
# export that is meant to be citable in a thesis pins the exact build.
DECKGL_VERSION = "9.0.38"
DECKGL_URL = f"https://unpkg.com/deck.gl@{DECKGL_VERSION}/dist.min.js"

SKIP_SUFFIX = (".py", ".md")
SKIP_DIRS = {"videos", "screenshots", "_design", "__pycache__"}
TEXT_SUFFIX = (".js", ".css", ".html", ".json", ".geojson", ".svg")


def _keep(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if ".bak" in path.name:
        return False
    # Leading underscore marks scratch harnesses that live beside the app:
    # _capture.html, _shot_viewer.html, _shot_app.html are screenshot rigs and
    # have no business on a public host.
    if path.name.startswith("_"):
        return False
    return path.suffix.lower() not in SKIP_SUFFIX


def copy_viewer(dst: Path) -> int:
    n = 0
    for src in VIEWER.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(VIEWER)
        if not _keep(rel):
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        n += 1
    return n


def copy_layouts(dst: Path) -> tuple[int, int]:
    data = dst / "data"
    data.mkdir(parents=True, exist_ok=True)
    total = 0
    for stem in LAYOUTS:
        src = GEOJSON / f"{stem}.geojson"
        if not src.exists():
            sys.exit(f"missing layout: {src}")
        shutil.copy2(src, data / src.name)
        total += src.stat().st_size

    # THE MANIFEST HAS TO SHIP TOO, and it was being left behind (found
    # by opening the export: it came up on Chandigarh Sector).
    # `loadManifest` fetches `${DATA_ROOT}/manifest.json`; with no file it
    # 404s, throws, and the catch falls back to FALLBACK_LAYOUTS - whose FIRST
    # entry is chandigarh_sector, so a link meant to show the thesis design
    # opened on a baseline archetype. The manifest also carries `center`, so
    # the camera and sun position were falling back as well.
    # Filtered to LAYOUTS so the CANDIDATE scratch entries cannot leak in.
    src_manifest = GEOJSON / "manifest.json"
    if not src_manifest.exists():
        sys.exit(f"missing manifest: {src_manifest}")
    manifest = json.loads(src_manifest.read_text(encoding="utf-8"))
    kept = [row for row in manifest.get("layouts", []) if row.get("name") in LAYOUTS]
    if len(kept) != len(LAYOUTS):
        missing = sorted(set(LAYOUTS) - {row.get("name") for row in kept})
        sys.exit(f"manifest is missing shipped layouts: {missing}")
    # optimised_sa first, so the fallback path lands on the town too.
    kept.sort(key=lambda row: LAYOUTS.index(row["name"]))
    manifest["layouts"] = kept
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    return len(LAYOUTS), total


# The viewer reads SIX things, not one. Only DATA_ROOT was ever repointed, so
# every export shipped without the other five and came up with "Dispatch
# results unavailable; 3D scene loaded without the energy cockpit" - the whole
# cockpit dead, which is precisely the part
#. Each entry: the constant, the source file, and where it lands.
SUPPORT_FILES = [
    ("DISPATCH_RESULTS_URL", "outputs/data/energy/dispatch_results.json", "data/dispatch_results.json"),
    ("BASELINE_AUDIT_URL", "outputs/data/baseline_audit.md", "data/baseline_audit.md"),
    ("PRICE_SCENARIO_SWEEP_URL", "outputs/data/energy/price_scenario_sweep.csv", "data/price_scenario_sweep.csv"),
    ("PLACEMENT_AUDIT_URL", "outputs/data/placement_audit.md", "data/placement_audit.md"),
    ("ECONOMICS_URL", "config/economics.yaml", "data/economics.yaml"),
]


def copy_support_files(dst: Path) -> int:
    """Ship everything the viewer fetches, not just the layouts."""
    total = 0
    for _const, rel, target in SUPPORT_FILES:
        src = ROOT / rel
        if not src.exists():
            sys.exit(f"missing support file: {src}")
        out = dst / target
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        total += src.stat().st_size
    return total


def repoint_data_root(dst: Path) -> None:
    """Rewrite every source path in the COPY so it reads from./data."""
    app = dst / "app.js"
    text = app.read_text(encoding="utf-8")
    new, count = re.subn(
        r'const DATA_ROOT = "\.\./outputs/geojson3d";',
        'const DATA_ROOT = "./data";',
        text,
        count=1,
    )
    if count != 1:
        sys.exit("DATA_ROOT rewrite failed - the declaration changed shape")

    # ENERGY_SUMMARY_URL is an alias of DISPATCH_RESULTS_URL, so it follows for
    # free and must NOT be rewritten separately.
    for const, _rel, target in SUPPORT_FILES:
        pattern = rf'const {const} = "[^"]+";'
        new, n = re.subn(pattern, f'const {const} = "./{target}";', new, count=1)
        if n != 1:
            sys.exit(f"{const} rewrite failed - the declaration changed shape")
    app.write_text(new, encoding="utf-8")


def vendor_deckgl(dst: Path) -> None:
    """Download deck.gl once and point index.html at the local copy.

    Kept behind a flag because it is the only step that touches the network.
    """
    import urllib.request

    out = dst / "vendor"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "deck.gl.min.js"
    print(f"  fetching {DECKGL_URL}")
    with urllib.request.urlopen(DECKGL_URL, timeout=120) as r:
        target.write_bytes(r.read())
    print(f"  vendored {target.stat().st_size / 1048576:.2f} MB")

    idx = dst / "index.html"
    html = idx.read_text(encoding="utf-8")
    new, count = re.subn(
        r'https://unpkg\.com/deck\.gl@[^"\']*',
        "./vendor/deck.gl.min.js",
        html,
    )
    if count != 1:
        sys.exit(f"expected one deck.gl script tag, rewrote {count}")
    idx.write_text(new, encoding="utf-8")


def precompress(dst: Path) -> tuple[int, int]:
    """Write a.gz beside every text asset.

    Static hosts that honour precompressed files (Netlify, nginx with
    gzip_static, Cloudflare Pages) serve these directly. Hosts that compress
    on the fly ignore them and cost only disk. The geojson is where this
    matters: 66.59 MB of layouts becomes about 2.16 MB on the wire.
    """
    raw = comp = 0
    for p in dst.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIX:
            continue
        data = p.read_bytes()
        blob = gzip.compress(data, 9)
        p.with_suffix(p.suffix + ".gz").write_bytes(blob)
        raw += len(data)
        comp += len(blob)
    return raw, comp


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "web_export"))
    ap.add_argument("--vendor-deckgl", action="store_true",
                    help="download deck.gl and self-host it (network access)")
    args = ap.parse_args()

    dst = Path(args.out)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    print(f"building into {dst}")
    n = copy_viewer(dst)
    print(f"  {n} viewer files")
    count, total = copy_layouts(dst)
    total += copy_support_files(dst)
    print(f"  {len(SUPPORT_FILES)} support files (dispatch results, audits, economics)")
    print(f"  {count} layouts, {total / 1048576:.2f} MB raw")
    repoint_data_root(dst)
    print("  DATA_ROOT -> ./data")

    if args.vendor_deckgl:
        vendor_deckgl(dst)
    else:
        print("  deck.gl NOT vendored (rerun with --vendor-deckgl); the export "
              "still points at unpkg and is not self-contained")

    raw, comp = precompress(dst)
    on_disk = sum(p.stat().st_size for p in dst.rglob("*") if p.is_file())
    print(f"\n  text assets {raw / 1048576:.2f} MB -> gzip "
          f"{comp / 1048576:.2f} MB ({100 * (1 - comp / raw):.1f}% smaller)")
    print(f"  export on disk {on_disk / 1048576:.2f} MB "
          f"(includes the .gz copies)")
    print(f"\ndone: {dst}")


if __name__ == "__main__":
    main()
