"""D7 - annealing progression figure: REAL intermediate layouts.

the author: "have a diagram showing 4-5 different annealing outcomes, from start
to finish, showing how they got more annealed over iterations".

This runs a SEPARATE, SHORTER anneal purely to capture snapshots, replicating
the production loop (same _make_move, same total_cost, same seed 42, same
config weights and temperature schedule) but pausing at intervals to copy the
grid. It NEVER writes to outputs/geojson3d/ - the frozen seed-42 production
layout is untouched. The figure is therefore an honest illustration of the
MECHANISM at a shorter budget, not a re-derivation of the thesis layout, and
the caption says so.

Run:   python scripts/d7_anneal_progression.py [--iters 1200] [--shots 5]
Out:   outputs/figures/D7_anneal_progression.svg
       outputs/figures/_d7_snapshots.json   (cached; re-run with --force)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_config                      # noqa: E402
from core.demographics import load_demand_norms, load_demographics  # noqa: E402
from core.land_use import LandUse                        # noqa: E402
from core.requirements import derive_requirements        # noqa: E402
from layout.generator import generate                    # noqa: E402
from layout.locked_zones import apply_locked_zones       # noqa: E402
from layout.optimiser import _make_move, total_cost, DEFAULT_WEIGHTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "figures"
CACHE = OUT / "_d7_snapshots.json"

# land use -> figure colour (matches the palette used across D1-D6)
COLOURS = {
    "RESIDENTIAL_LOW": "#E8CCA3", "RESIDENTIAL_MID": "#D6B88D",
    "RESIDENTIAL_HIGH": "#C2A47A", "ROAD": "#B9C0CC",
    "SOLAR_FARM": "#2F6F9F", "OPEN_SPACE": "#6E9E5E",
    "BLUE_SPACE": "#4088C8", "PARKING_LOT": "#8E96A4",
    "SCHOOL": "#8FA8C4", "HEALTHCARE": "#7EC0AE", "OFFICE": "#9FB6CC",
    "PUBLIC_SERVICES": "#9AA6C0", "SHOPPING_CENTRE": "#D9A96C",
    "RETAIL_HIGHSTREET": "#E0B071", "RESTAURANT_FOOD_SERVICE": "#D6A184",
    "HOTEL_GUESTHOUSE": "#C2A6AE", "RELIGIOUS": "#E0CDA0",
    "LIGHT_INDUSTRY": "#A6AAB6", "WAREHOUSE_COLD_STORAGE": "#96A0B4",
}
DEFAULT_COLOUR = "#C9CFD9"


def snapshot(grid) -> list:
    """Compact [[landuse_name,...],...] by row."""
    rows = []
    for r in range(grid.n_rows):
        rows.append([grid.at(r, c).land_use.name for c in range(grid.n_cols)])
    return rows


def run_capture(iters: int, shots: int, marks_arg: str = "") -> dict:
    cfg = load_config()
    demo = load_demographics()
    norms = load_demand_norms()
    req = derive_requirements(demo, norms, cfg)
    seed_name = cfg.optimisation.get("initial_seed_archetype",
                                     "chandigarh_sector")
    grid = generate(seed_name)
    solar_req = int(req.required_cells_by_landuse.get(LandUse.SOLAR_FARM, 225))
    apply_locked_zones(grid, solar_cells=solar_req)

    opt = cfg.optimisation or {}
    T0 = float(opt.get("initial_temperature", 0.10))
    Tf = float(opt.get("final_temperature", 0.001))
    hard_p = float(opt.get("hard_penalty", 25.0))
    soft_p = float(opt.get("soft_penalty", 2.0))
    seed = int(opt.get("rng_seed", 42))
    weights = DEFAULT_WEIGHTS

    rng = random.Random(seed)
    cur = total_cost(grid, req, cfg, weights, hard_p, soft_p)
    best, best_grid = cur, grid.copy()
    decay = (Tf / T0) ** (1.0 / max(1, iters - 1))
    T = T0

    if marks_arg:
        marks = sorted({int(m) for m in marks_arg.split(",") if m.strip()})
        iters = max(iters, max(marks))
    else:
        marks = [0] + [int(round(iters * (i + 1) / (shots - 1)))
                       for i in range(shots - 1)]
    frames, trace = [], []
    frames.append({"iter": 0, "cost": cur, "grid": snapshot(grid)})
    print(f"  captured iter 0 (cost {cur:+.2f})", flush=True)

    t0 = time.time()
    for i in range(iters):
        _mt, undo = _make_move(grid, rng, req, cfg)
        new = total_cost(grid, req, cfg, weights, hard_p, soft_p)
        if (new - cur) < 0 or rng.random() < math.exp(
                -(new - cur) / max(T, 1e-12)):
            cur = new
            if cur < best:
                best, best_grid = cur, grid.copy()
        else:
            undo()
        trace.append(round(cur, 4))
        T *= decay
        if (i + 1) in marks:
            frames.append({"iter": i + 1, "cost": cur, "grid": snapshot(grid)})
            print(f"  captured iter {i + 1} (cost {cur:+.2f}, "
                  f"{time.time() - t0:.0f}s)", flush=True)
    return {"frames": frames, "trace": trace, "iters": iters,
            "seed": seed, "T0": T0, "Tf": Tf}


def production_frame() -> dict | None:
    """The REAL frozen production layout (seed 42, 15,000 iterations) read
    from the exported GeoJSON, so the strip ends on the actual deliverable
    rather than on a short run's stopping point."""
    import json
    p = ROOT / "outputs" / "geojson3d" / "optimised_sa.geojson"
    if not p.exists():
        print("  (production geojson not found - final panel skipped)")
        return None
    gj = json.loads(p.read_text(encoding="utf-8"))
    cells = {}
    nr = nc = 0
    for f in gj.get("features", []):
        pr = f.get("properties") or {}
        if pr.get("role") != "parcel":
            continue
        r, c = pr.get("row"), pr.get("col")
        if r is None or c is None:
            continue
        lu = str(pr.get("land_use", "")).upper()
        cells[(int(r), int(c))] = lu
        nr, nc = max(nr, int(r) + 1), max(nc, int(c) + 1)
    if not cells:
        print("  (no parcel features - final panel skipped)")
        return None
    grid = [[cells.get((r, c), "OPEN_SPACE") for c in range(nc)]
            for r in range(nr)]
    print(f"  production layout loaded: {nr}x{nc}, {len(cells)} parcels")
    return {"iter": None, "cost": 20.56, "grid": grid, "production": True}


def build_figure(data: dict) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from thesis_diagrams import (Svg, INK, MUTED, FAINT, LINE, C_OPT,
                                 C_RESULT, C_WARN, BAND)
    frames = list(data["frames"])
    # the production panel is NOT appended once the snapshot run
    # itself reaches the full 15,000 iterations. That run starts from a
    # different state (only the solar lock, not the full pre-anneal lock
    # set), so it converges to ~+49 while production sits at +20.6; showing
    # them side by side implied a continuity that does not exist. The strip is
    # now ONE coherent run and the caption states the comparison.
    if data.get("iters", 0) < 15000:
        prod = production_frame()
        if prod:
            frames.append(prod)
    n = len(frames)
    W = 1100
    gap, gy = 20, 132
    per_row = n if n <= 5 else (n + 1) // 2
    rows_n = 1 if n <= 5 else 2
    gs = int((W - 120 - (per_row - 1) * gap) / per_row)
    row_h = gs + 58
    total_w = per_row * gs + (per_row - 1) * gap
    x0 = max(60, (W - total_w) // 2)
    H = gy + rows_n * row_h + 24 + 76 + 26   # rows + trace, no legend
    s = Svg(W, H, "D7   The plan emerging: annealing from start to finish")

    # Open space dominates (~55% of cells); paint it once as a background and
    # draw only the built fabric. Halves the file and sharpens the read.
    BG = COLOURS["OPEN_SPACE"]
    changed_total = 0
    for k, f in enumerate(frames):
        gx = x0 + (k % per_row) * (gs + gap)
        gy_k = gy + (k // per_row) * row_h
        rows = f["grid"]
        nr, nc = len(rows), len(rows[0])
        c = gs / max(nr, nc)
        s.rect(gx, gy_k, gs, gs, fill=BG, stroke="none", rx=1, opacity=0.85)
        prev = (frames[k - 1]["grid"]
                if k and not f.get("production") else None)
        for r in range(nr):
            for col in range(nc):
                lu = rows[r][col]
                if lu != "OPEN_SPACE":
                    s.rect(gx + col * c, gy_k + r * c, c - 0.3, c - 0.3,
                           fill=COLOURS.get(lu, DEFAULT_COLOUR),
                           stroke="none", rx=0.3, opacity=0.96)
        # mark what MOVED since the previous frame - makes a 3-4% delta legible
        if prev is not None:
            for r in range(nr):
                for col in range(nc):
                    if prev[r][col] != rows[r][col]:
                        changed_total += 1
                        s.rect(gx + col * c - 0.5, gy_k + r * c - 0.5, c + 0.4,
                               c + 0.4, fill="none", stroke=C_WARN, sw=0.9)
        is_prod = f.get("production")
        s.rect(gx - 2, gy_k - 2, gs + 4, gs + 4, fill="none",
               stroke=C_RESULT if is_prod else LINE,
               sw=2.0 if is_prod else 1.0)
        if is_prod:
            lab = "FINAL PLAN"
        elif k == 0:
            lab = "start"
        else:
            lab = f"{f['iter']:,} iters"
        s.text(gx + gs / 2, gy_k + gs + 20, lab, 10.2, INK, bold=True,
               anchor="middle")
        sub = ("15,000 iters" if is_prod
               else f"cost {f['cost']:+.1f}")
        s.text(gx + gs / 2, gy_k + gs + 34, sub, 9.2,
               C_WARN if k == 0 else (C_RESULT if is_prod else MUTED),
               anchor="middle")
        if is_prod:
            s.text(gx + gs / 2, gy_k + gs + 47, "cost +20.6", 9.2, C_RESULT,
                   anchor="middle")
        if k < n - 1:
            s.arrow(gx + gs + 4, gy_k + gs / 2, gx + gs + gap - 4, gy_k + gs / 2,
                    FAINT, 1.3, head=4.0)
    s.text(x0, 96, "ITERATIONS", 9.2, FAINT, bold=True, spacing=1.6)

    # cost trace underneath, aligned to the frames
    tr = data["trace"]
    # below ALL rows (was gy + gs + 66, which assumed a single row and
    # drew the trace straight over the second row of grids)
    ty, th = gy + rows_n * row_h + 24, 76
    tx0, tw_ = x0, total_w
    lo, hi = min(tr) - 4, max(tr[:40] + [max(tr)]) + 4
    s.rect(tx0, ty, tw_, th, fill="#FFFFFF", stroke=LINE)
    d = ""
    for i, v in enumerate(tr):
        px = tx0 + tw_ * i / max(1, len(tr) - 1)
        py = ty + th - (v - lo) / max(1e-9, hi - lo) * th
        d += ("M " if i == 0 else " L ") + f"{px:.1f} {py:.1f}"
    s.path(d, C_OPT, sw=1.6)
    for f in frames:
        if f.get("production") or f.get("iter") is None:
            continue
        px = tx0 + tw_ * f["iter"] / max(1, data["iters"])
        py = ty + th - (f["cost"] - lo) / max(1e-9, hi - lo) * th
        s.circle(min(px, tx0 + tw_), max(ty, min(py, ty + th)), 3.6, C_OPT)
    s.text(tx0, ty - 8, "OBJECTIVE COST", 9.2, FAINT, bold=True, spacing=1.6)

    # legend removed: the colours are explained in D2/D3
    s.save("D7_anneal_progression.svg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=1200)
    ap.add_argument("--shots", type=int, default=5)
    ap.add_argument("--marks", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and not a.force:
        print(f"using cached snapshots ({CACHE.name}); --force to re-run")
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        print(f"capturing {a.shots} snapshots over {a.iters} iterations "
              f"(separate run; the frozen layout is NOT touched)")
        data = run_capture(a.iters, a.shots, a.marks)
        CACHE.write_text(json.dumps(data), encoding="utf-8")
    build_figure(data)
    write_caption()


D7_CAPTION = (
    "Eight real intermediate layouts from a single 15,000-iteration annealing "
    "run at seed 42, captured at 0, 1,000, 2,500, 5,000, 7,500, 10,000, "
    "12,500 and 15,000 iterations, with the objective cost falling from "
    "+190.7 to +49.2. Rust outlines mark every cell that changed since the "
    "previous frame, which shows the optimiser performing targeted local "
    "surgery rather than wholesale reshuffling, and shows the early iterations "
    "doing almost all of the structural work. This run applies only the solar "
    "land lock, whereas the production layout additionally fixes the hospital "
    "campus, high-street chain, solar ring and agricultural band before "
    "annealing begins; that is why it starts and finishes higher than the "
    "frozen plan, which reaches +20.6.")


def write_caption() -> None:
    """Append D7's caption to the shared captions file. thesis_diagrams.py
    rewrites that file from scratch for D1-D6, so this must run after it."""
    p = OUT / "_captions.md"
    txt = p.read_text(encoding="utf-8") if p.exists() else ""
    if "Figure 7" in txt:
        return
    with p.open("a", encoding="utf-8") as f:
        f.write("\n**Figure 7 - The plan emerging.** " + D7_CAPTION + "\n")


if __name__ == "__main__":
    main()
