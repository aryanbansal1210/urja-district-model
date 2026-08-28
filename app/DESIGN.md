> **STALE (v1).** This designed the town-level dashboard replaced by the RESIDENT app (Urja v2,, the author spec). Kept for the visual-grammar tokens only; the v2 contract lives in README.md + scripts/app_data_extract.py.

# Zirakpur 250k - the resident/investor energy app (register Q22)

> Parallel track (F_SERIES_ROADMAP "APP" row): a PWA dashboard that READS the
> model's outputs and never touches the model. New `app/` dir - separate from
> `viewer3d/` (Codex's). Written against the baseline; every
> number the app shows is read at runtime from the JSON, so the- re-pin
> changes what it DISPLAYS without changing a line of app code.

## 1. What it is

A Tesla-app-class energy dashboard for the 25 km² / 250,000-person new town
near Zirakpur, Punjab: the town's live power flow, its money and carbon
story vs business-as-usual, the 2030 → 2042 → 2055 build-out, and who saves
what (equity). One screen, four stacked panels, phone-first dark UI - the
visual language of the Tesla Powerwall / solar-home apps (dark cards, one
hero flow animation, big rounded numerals, restrained accent colours).

**Audience:** the author's viva/demo audience + anyone he hands the phone to.
**Non-goals:** editing the model, running solves, replacing the 3D viewer.

## 2. Data contract (REAL field names - the app hardcodes NO numbers)

| Panel | Source | Fields |
|---|---|---|
| Headline cards | `outputs/data/energy/dispatch_results.json` → `scenarios[]` entry `name=="full_stack" && alpha==0` (first match) | `annual_cost_inr`, `annual_emissions_kgco2`, `lifetime_cost_inr`, `annual_demand_kwh`, `renewable_share`, `lcoe_inr_per_kwh` (net cost/kWh) |
| vs-BAU chips | same file → `scenarios[]` entry `name=="bau"` | computed: `1 - full_stack/bau` on cost + emissions |
| Live power flow | `full_stack.by_slice[{month}_{wd\|we\|fs}_{HH}]` + top-level `slices[]` metadata (`hours_per_year` per slice id) | `demand_kwh`, `pv_kwh`, `grid_import_kwh`, `grid_export_kwh`, `battery_charge/discharge_kwh`, `biomass_kwh`, `wte_kwh`, `biogas_kwh`, `v2g_discharge_kwh`, `dsr_reduce/add_kwh`, `ev_shift_in/out_kwh` → average kW = kWh ÷ `hours_per_year`. Device clock picks the slice (month + weekday/weekend + 2-h daypart); a scrubber overrides. Flow panel is labelled "model year 2030" (the by_slice export is base-year operations). |
| Day curve | 12 dayparts of the selected month/day-type from `by_slice` | stacked PV / bio / battery / V2G / grid vs demand line |
| Build-out timeline | `full_stack.period_breakdown["2030"/"2042"/"2055"]` | `installed_capacities.{solar_farm_kwp, rooftop_pv_kwp, carport_kwp, floating_pv_kwp, bipv_kwp, battery_kwh, v2g_units, biomass_kw_e, wte_kw_e}` + `annual_cost_inr`, `annual_emissions_kgco2`, `annual_demand_kwh`, `grid_import_kwh`, `grid_export_kwh`, `pv_generation_kwh` |
| Equity ("who saves") | `outputs/data/energy/equity_report.json` → `by_class` | per tier: `savings_pct`, `savings_vs_bau_inr`, `households`, `effective_tariff_inr_per_kwh`; plus `totals.total_savings_pct` |
| Town mini-map (opt-in tap - the file is ~14 MB) | `outputs/geojson3d/optimised_sa.geojson` | per-parcel `land_use`, `height_m`, `amenity_subtype`, `road_class`; metadata `road_network` + `walkability`/ when present |

Current reference values (for SANITY-CHECKING a render, never for
hardcoding; they will move at the- re-pin): cost ₹3,314.1 M/yr, CO₂
242.5 kt, lifetime ₹126.64 B, vs-BAU −45.0%/−54.2%, renewable 57.6%, net
₹3.68/kWh, battery 0 → 150.2 MWh → 1,094.6 MWh, farm 271.2 → 385 → 402.5
MWp, equity ordering EWS 48% > industrial 31% > commercial 26% > high 20% >
mid 11% (source: CODEX_HANDOFF §13 close-out, Tier 3 model
output).

## 3. Screen layout (phone-first, one scroll)

1. **Header** - town name, "LIVE MODEL" status dot, period pill selector
   (2030 / 2042 / 2055; drives panels 4-5).
2. **Power flow hero** (the Powerwall moment) - five nodes (Solar, Grid,
   Battery+V2G, Bio, Town) with animated flow dots along SVG paths; dot
   speed ∝ average MW on that leg for the selected slice; big centre
   numeral = town demand MW now. Time scrubber (month + hour) defaults to
   the device clock.
3. **Impact cards** - ₹/yr, CO₂/yr, vs-BAU chips, renewable %, net ₹/kWh,
   lifetime ₹. Indian formatting (₹ M / kt).
4. **Build-out timeline** - horizontal bars per tech across the three
   periods + demand growth; the "town that grows" story (register B12).
5. **Who saves** - per-tier savings bars ordered by `savings_pct` (the
   progressive-equity thesis finding; households per tier.
6. **Town map (tap to load)** - canvas parcel render coloured by land_use,
   roads by `road_class` width, lanes/paths if present in metadata.
7. **Footer** - provenance: model version + `economics_meta`, file dates,
   "every number read from the model export; nothing hardcoded".

## 4. Look + feel (the Tesla/Powerwall grammar)

- Background #0A0C0F; cards #14171C radius 20px; hairline borders #22262D.
- Text: system font stack (SF Pro on iPhone). Numerals in 600 weight,
  tabular-nums. Labels 11px uppercase letter-spaced #8A939E.
- Accents ONLY by meaning: solar #FDB813, grid #9AA6B2, battery #34C759,
  bio #7CB342, cost #E8EAED, alerts #FF453A. No gradients except the flow
  glow. Motion: 60 fps dot animation, 300 ms card transitions, no parallax.
- Charts are hand-rolled inline SVG (no chart library, no CDN, fully
  offline-capable, crisp on retina).

## 5. iPhone path

**Now (this scaffold): install as a PWA.**
1. Serve the repo root (`python -m http.server 8000` inside district_v3).
2. iPhone on the same Wi-Fi → Safari → `http://<pc-ip>:8000/app/`.
3. Share → **Add to Home Screen** → the app opens standalone (no Safari
   chrome, dark status bar, home-screen icon) - `manifest.webmanifest` +
   the `apple-mobile-web-app-*` meta tags make it feel native.
4. Offline caching (service worker) activates only over HTTPS or
   localhost (iOS rule) - over plain LAN HTTP everything works except
   offline reloads. For full offline + push, front it with any HTTPS
   tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`) and
   Add-to-Home-Screen from that URL instead.

**Later (App Store, if ever wanted):** wrap this exact code in Capacitor
(`npx cap add ios`) - zero rewrite, the web app IS the app. Native is
deliberately deferred (register Q22 decision: PWA first).

## 6. File map

```
app/
  DESIGN.md            this file
  README.md            run + install instructions
  index.html           shell + panels
  styles.css           the Tesla-grammar theme
  app.js               data load + formatting + flow animation + SVG charts
  manifest.webmanifest PWA manifest
  sw.js                app-shell cache (guarded registration)
  icons/               icon-192/512, apple-touch-icon (generated)
```

## 7. Deliberate deferrals

- A slim `app_summary.json` exporter (the full dispatch JSON is ~14 MB;
  fine on LAN, heavy on cellular) - add to `scripts/` when the app leaves
  the LAN.
- Scenario switcher (agile / DC-PPA / Pareto alphas) - the data is already
  in `scenarios[]`; UI deferred until the author wants it.
- Per-cell drill-down (Stage-D fields) - waits for the A4 re-time.
- Push notifications / true offline - needs the HTTPS path above.
