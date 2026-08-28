"""Prove the solar-thermal wiring is INVISIBLE when the flag is off.

. The project's standing requirement for any additive change is
that the production path stays byte-exact. For an LP the strongest available
statement is stronger than "the number matched": it is that the MODEL ITSELF
is structurally identical - same variables, same constraints, same counts -
so there is no path by which a number COULD move.

This builds the multi-period Pyomo model three ways and compares component
counts:

  1. flag off, flag off      <- production. The baseline.
  2. config on, scenario off <- one switch is not enough.
  3. config on, scenario on  <- the technology actually appears.

(1) and (2) must be IDENTICAL. (3) must differ by exactly the solar-thermal
components and nothing else.

Writes straight to a file with no pipe. CLAUDE.md records a suite whose
result was lost because it was piped through `tail`, which buffers - so
nothing was written until it exited and the session ended first.

    PYTHONPATH=. python -u scripts/solar_thermal_off_structural_proof.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pyomo.environ as pyo

from energy.costs import load_economics
from energy.network import load_optimised_network

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "verification" / "solar_thermal_off_proof_20260817.txt"


def component_counts(m) -> Counter:
    """Name -> number of index entries, for every active component."""
    c = Counter()
    for comp in m.component_objects(
            (pyo.Var, pyo.Constraint, pyo.Expression, pyo.Objective),
            active=True):
        try:
            c[comp.name] = len(comp)
        except TypeError:
            c[comp.name] = 1
    return c


def scenario_with(econ, name: str, **overrides):
    """A copy of scenario `name` with fields overridden.

    *** `Scenario` IS A FROZEN DATACLASS. *** A first version of this script
    wrote `sc.allow_solar_thermal = True` inside a `try/except Exception:
    pass`, which swallowed the resulting FrozenInstanceError. The flag was
    therefore never set, the "both flags on" case built an identical model,
    and the script reported PASS on a comparison that had tested nothing.
    That is the silent-failure class this project has been bitten by before,
    and the fix is to use `replace` and let a real error surface.
    """
    import dataclasses
    return dataclasses.replace(econ.scenario(name), **overrides)


def main() -> None:
    # ---- PROGRESS TRACKING, AND IT IS NOT OPTIONAL -----------------------
    # runs.. are you sure its running".
    # He was right, and the first version of this script had none: every line
    # went into a list and printed at the end, so it produced NOTHING for 45
    # minutes and there was no way to tell work from hang without attaching
    # py-spy. That is the same buffering failure CLAUDE.md already records
    # against a lost suite run ("piped through tail, which buffers - so
    # nothing was written until it exited"), rediscovered in a new form.
    # Every line now prints immediately, flushed, with elapsed time.
    import time
    _t0 = time.time()
    lines = []

    def w(msg: str = "") -> None:
        lines.append(msg)
        print(msg, flush=True)

    def step(msg: str) -> None:
        print(f"[{time.time()-_t0:7.1f}s] {msg}", flush=True)

    step("loading economics")
    econ = load_economics(force_reload=True)
    step("building network (geometric shading precompute, ~5 min)")
    net = load_optimised_network(econ=econ)
    step("network ready")
    w("Solar thermal OFF-path structural proof")
    w("=" * 70)

    from energy import dispatch as D
    # The PRODUCTION path is multi-period (`multi_period.enabled: true`), and
    # it has a standalone builder, so the model can be constructed and
    # inspected without paying for a solve.
    builder = getattr(D, "_build_pyomo_model_multi_period", None)
    if builder is None:
        sys.exit("no multi-period Pyomo builder found")

    def counts(cfg_on, scen_on):
        label = f"config={'ON ' if cfg_on else 'OFF'} scenario={'ON ' if scen_on else 'OFF'}"
        step(f"  building model: {label}")
        _b = time.time()
        econ.technologies["solar_thermal"] = {
            **econ.technologies["solar_thermal"], "enabled": bool(cfg_on)}
        sc = scenario_with(econ, "full_stack",
                           allow_solar_thermal=bool(scen_on))
        # assert the override actually took, rather than trusting it
        assert sc.allow_solar_thermal is bool(scen_on), "flag did not set"
        out = builder(net, econ, sc, alpha=0.0)
        # the multi-period builder returns
        # (model, period_years, slice_ids, hours_of, weights)
        m = out[0] if isinstance(out, tuple) else out
        c = component_counts(m)
        step(f"  built in {time.time()-_b:.1f}s: {len(c)} components, "
             f"{sum(c.values()):,} entries")
        return c

    # ---- expression-level check, cheaper and sharper than the counts ------
    # Counts alone would not catch a stray constant added to a pinned
    # expression. The balance constraint is the one every optional technology
    # writes into, so it is the one to look at. With the flag off it must not
    # mention solar thermal in any form.
    econ.technologies["solar_thermal"] = {
        **econ.technologies["solar_thermal"], "enabled": False}
    sc = scenario_with(econ, "full_stack", allow_solar_thermal=False)
    out = builder(net, econ, sc, alpha=0.0)
    m0 = out[0] if isinstance(out, tuple) else out
    bal = getattr(m0, "balance", None)
    sample = None
    if bal is not None:
        for idx in bal:
            sample = str(bal[idx].body)
            break
    w("BALANCE EXPRESSION WITH THE FLAG OFF")
    w("-" * 70)
    if sample is None:
        w("  could not read a balance constraint")
    else:
        w(f"  length {len(sample)} chars")
        bad = [t for t in ("st_serve", "st_collect", "st_new", "st_installed")
               if t in sample]
        if bad:
            ok_expr = False
            w(f"  FAIL  the off expression still mentions: {bad}")
        else:
            ok_expr = True
            w("  PASS  no solar-thermal term appears in the off expression")
        w(f"  first 220 chars: {sample[:220]}")
    w("")

    base = counts(False, False)
    half = counts(True, False)
    full = counts(True, True)

    w(f"builder: {builder.__name__}")
    w("")
    w(f"(1) config OFF, scenario OFF : {len(base)} components,"
      f" {sum(base.values()):,} index entries")
    w(f"(2) config ON,  scenario OFF : {len(half)} components,"
      f" {sum(half.values()):,} index entries")
    w(f"(3) config ON,  scenario ON  : {len(full)} components,"
      f" {sum(full.values()):,} index entries")
    w("")

    ok = True
    if base == half:
        w("PASS  (1) == (2) exactly. One switch is not enough to reach the")
        w("      LP, which is the intended two-key gate.")
    else:
        ok = False
        w("FAIL  (1) != (2). Turning the CONFIG flag on changed the model")
        w("      even with the scenario flag off. Differences:")
        for k in sorted(set(base) | set(half)):
            if base.get(k) != half.get(k):
                w(f"        {k}: {base.get(k)} -> {half.get(k)}")

    added = {k: v for k, v in full.items() if k not in base}
    changed = {k: (base[k], full[k]) for k in base
               if k in full and base[k] != full[k]}
    removed = [k for k in base if k not in full]

    w("")
    w("(3) vs (1) - what switching the technology on actually does:")
    for k, v in sorted(added.items()):
        w(f"  ADDED    {k:<28} {v:,} entries")
    for k, (a, b) in sorted(changed.items()):
        w(f"  CHANGED  {k:<28} {a:,} -> {b:,}")
    for k in removed:
        ok = False
        w(f"  REMOVED  {k}   <- UNEXPECTED")

    stray = [k for k in added if not k.startswith("st_")]
    if stray:
        ok = False
        w("")
        w("FAIL  components were added that are NOT solar thermal:")
        for k in stray:
            w(f"        {k}")
    if changed:
        ok = False
        w("")
        w("FAIL  existing components changed size. Switching a technology on")
        w("      must ADD constraints, never resize the ones already there.")

    ok = ok and bool(locals().get("ok_expr", False))
    w("")
    w("RESULT: " + ("PASS - the off path is structurally identical"
                    if ok else "FAIL - see above"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
