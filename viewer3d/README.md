# DISTRICT_v3 3D viewer

Presentation-style deck.gl viewer for the generated 3D GeoJSON layouts.

## Generate data

From the project root:

```powershell
uv run --no-project --with pyyaml python -m core.export_3d
```

This writes:

- `outputs/geojson3d/chandigarh_sector.geojson`
- `outputs/geojson3d/dispersed_low.geojson`
- `outputs/geojson3d/compact_centre.geojson`
- `outputs/geojson3d/radial.geojson`
- `outputs/geojson3d/manifest.json`

To include the simulated-annealing result in the viewer dropdown, run:

```powershell
uv run --no-project --with pyyaml python -m core.export_3d --include-optimised
```

This also writes `outputs/geojson3d/optimised_sa.geojson`. It takes longer
because it runs the optimiser before exporting.

## Open the viewer

Serve the project root, then open `viewer3d/`:

```powershell
uv run --no-project python -m http.server 8000
```

Then visit:

```text
http://localhost:8000/viewer3d/
```

The viewer loads deck.gl from a CDN, so it needs internet access on first load.

## Permeability convention

The viewer shows every land-use cell, but routing permeability follows the
model convention in `config/district_composition.yaml`: `ROAD` cells are the
only cells treated as vehicle-accessible transport corridors.

This matters for interpretation:

- Vehicle movement is assumed to happen through `ROAD` cells.
- Future HV-cable / feeder routing should also use `ROAD` cells unless a later
  energy model explicitly adds a different right-of-way layer.
- Other land uses may contain paths, courtyards, service yards, or setbacks in
  the visual model, but they are not routing-permeable in the current district
  logic.

At 200 m grid resolution, a `ROAD` cell represents a transport corridor, not a
literal fully paved 200 m square.

## Sun-time convention

The date and time-of-day sliders are interpreted as **site-local solar time**
(apparent solar time at the site's own meridian), not UTC and not Indian
Standard Time. At the case-study site (30.64 °N, 76.82 °E), 12:00 on the
slider corresponds to local solar noon — when the sun is highest in the sky.

IST is measured against the 82.5 °E standard meridian, so for our site IST
runs about 22.7 minutes ahead of local solar time. The viewer does not apply
that offset; if you compare a slider value to a wall clock you will see this
gap.

The exported `outputs/geojson3d/manifest.json` carries a `solar_time` block
that captures the convention machine-readably:

```json
"solar_time": {
  "convention": "site_local_solar",
  "standard_meridian_deg": 76.82
}
```

Each per-layout GeoJSON's `metadata.solar_time` repeats it. A future viewer
build could read `standard_meridian_deg` and add a civil-time toggle; today
the value equals site longitude, which means the longitude correction in the
sun-position math is zero. See `_spec/architecture.md` and
`tests/test_sun_math.py` for the canonical formula.
