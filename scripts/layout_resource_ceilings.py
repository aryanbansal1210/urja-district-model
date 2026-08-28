"""The resource endowment the frozen layout hands the energy layer.

Section 5.1.2 of the thesis states what the plan makes available BEFORE any
optimisation chooses what to build. Those ceilings are derived quantities -
roof square metres come back out of `kWp = area x acceptance x eta` - so they
are computed here from the same objects the LP uses rather than transcribed
from an older note.

Read-only. Builds the network, reports, writes nothing but its own artifact.

    python scripts/layout_resource_ceilings.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "verification",
                   "layout_resource_ceilings.json")


def main() -> int:
    econ = load_economics()
    net = load_optimised_network()
    nodes = list(net.nodes.values()) if hasattr(net.nodes, "values") else list(net.nodes)

    out = {"cells": len(nodes), "rooftop_module_efficiency": float(net.rooftop_module_efficiency)}

    def try_call(label, fn):
        try:
            out[label] = float(fn())
            print("  %-34s %,.1f".replace(",", ",") % (label, out[label]))
        except Exception as exc:                      # noqa: BLE001
            out[label] = None
            print("  %-34s UNAVAILABLE (%s)" % (label, type(exc).__name__))

    print("RESOURCE CEILINGS the frozen layout hands the energy layer\n")
    try_call("solar_thermal_roof_cap_m2", lambda: net.solar_thermal_roof_cap_m2(econ))

    # Deployable capacity by mount, summed off the cells themselves.
    tot = {}
    for n in nodes:
        for attr in ("deployable_pv_kwp", "carport_kwp",
                     "floating_pv_deployable_kwp", "canal_pv_deployable_kwp"):
            v = getattr(n, attr, None)
            if v:
                tot[attr] = tot.get(attr, 0.0) + float(v)
    for k, v in sorted(tot.items()):
        print("  %-34s %12.1f kWp" % (k, v))
    out["deployable_kwp_by_mount"] = tot

    # The roof the rooftop ceiling implies, inverted through the same identity
    # the LP's roof-competition constraint uses.
    eta = float(net.rooftop_module_efficiency)
    if tot.get("deployable_pv_kwp"):
        out["implied_roof_m2_at_full_acceptance"] = tot["deployable_pv_kwp"] / eta * 1000.0 / 1000.0
        print("  %-34s %12.0f m2 (kWp / eta)"
              % ("implied roof area", out["implied_roof_m2_at_full_acceptance"]))

    for label, fn in (("biomass_straw_t_per_year",
                       lambda: econ.biomass_straw_tonnes_per_year()),
                      ("wte_msw_t_per_year",
                       lambda: econ.wte_msw_tonnes_per_year())):
        try_call(label, fn)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
