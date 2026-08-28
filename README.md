# Urja district model

A whole-system model that designs a district master plan and its energy system
together, demonstrated on a 25 km² greenfield site carrying 250,000 people on
the Zirakpur corridor, Punjab. Written for an MSc thesis.

Two layers. The first generates a land-use plan on a 50 by 50 cellular grid by
simulated annealing, under hard constraints and weighted objectives drawn from
statutory planning norms. The second sizes and operates the energy system on
that plan by multi-period linear programming, across three investment periods
and 864 representative time slices, with each asset financed at its owner's
cost of capital.

## What is here

| | |
|---|---|
| `core/` | entities, land use, buildings, the initialisation chain |
| `layout/` | the simulated-annealing layout optimiser and its metrics |
| `energy/` | the multi-period LP: costs, dispatch, network, storage |
| `scripts/` | derivations, audits and the register generator |
| `tests/` | the test suite |
| `config/` | the six configuration files the model reads |
| `viewer3d/` | the 3D district viewer, source only |
| `app/` | the resident application, source only |
| `PARAMETER_REGISTER.md` | all 1,441 parameters with value, units and source |

The register is generated, never hand-written, so it cannot drift from what the
model computes. Regenerate it with:

```bash
python scripts/appendix_c_parameters.py
```

## How a parameter is sourced

A source is attached to a parameter only where that parameter's own entry names
one. Citations are not spread from a parameter to its neighbours, because a
configuration block routinely mixes measured quantities with design choices.

Where no external source applies, the register states the category instead:

- **switch** turns a mechanism on or off
- **shares sum to 1** exhaustive by construction
- **model structure** the study's own resolution and periods
- **derived** computed from a sourced parameter, derivation kept beside it
- **bound** a cap the optimiser may not exceed
- **design choice** a decision the study makes and argues in the thesis

A value that could not be sourced is reported as unsourced rather than given a
plausible citation. 411 of the 1,441 parameters carry a direct source link.

## The two interfaces

The solved results are published as two web applications:

- district viewer, <https://urjatown.netlify.app/>
- resident application, <https://urja-home.netlify.app/>

Both read the model's own output; neither recomputes anything.

## Reproducibility

Two practices are worth naming because they are cheap and uncommon. Every
parameter carries its source, so a result can be weighed against its weakest
input. And the frozen layout carries a checksum that is verified before and
after every solve, which turns "does this result belong to this plan" from an
argument into a mechanical check.

## Running it

Python 3.9 or later, with Pyomo and the HiGHS solver:

```bash
pip install pyomo highspy numpy pyyaml
```

The solved outputs are not in this repository, and neither are the viewer's
demo videos. The two live applications are built from the model's own results
and are the easiest way to see what it produces.

## Licence

No licence is granted. The code is published so that the thesis can be checked,
not for reuse. All rights reserved.
