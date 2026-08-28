# Urja - the resident energy app (v2)

One app per resident of Zirakpur New Town: live solar and usage, peer-to-peer
trading with an AI autopilot, smart EV charging and V2G. Tesla/Powerwall visual
grammar. **Every number is the district_v3 production model** - no mockups.
(v1, the town-level dashboard, was replaced on the author's spec.)

## What it shows

| Tab | Content |
|---|---|
| Home | Live power flow (solar / home / grid / EV), today's totals, self-powered donut, CO2 impact, the town's live grid state |
| Energy | Day / week / month usage + generation charts, from-solar vs from-grid split, modelled end-use breakdown, your home vs the town comparison |
| Trade | Energy wallet, hourly price clock (seasonal ToU bands), AI autopilot with the optimiser's own rules + estimated ₹/month, trade ledger |
| EV | Tier-true EV profile (NITI/RMI 2030 stock shares), smart night-valley charging plan, V2G paddy-peak window + credits, monthly summary |

The home picker is the real master plan: a tappable 50x50 map of the town
(residential cells glow) plus a list. One representative household per cell -
cell energy divided by the households in that cell. Tiers differ genuinely:
an EWS block, a mid-income perimeter block and a kothi have different peaks,
cooling intensities, rooftop shares and tariffs.

## Data pipeline

```
python scripts/app_data_extract.py     # regenerate app/data.js
```

Sources: the production `optimised_sa.geojson` (per-cell households, deployed
rooftop kWp, orientation, shading), `dispatch_results.json` full_stack alpha=0
(864-slice district dispatch, tariffs, EV/V2G params) and the model's own
`demand_by_slice_kw` (per-tier unit profiles: base / cooling / heating, so a
cell's demand rebuilds exactly, including its microclimate multiplier).

**Re-run the extractor after every re-anneal or re-pin** (cell ids change), then
bump `VERSION` in `sw.js` so installed phones refresh.

## Install on iPhone

1. Serve the folder on the same Wi-Fi as the phone:
   `python -m http.server 8123 --directory app` (from `district_v3/`)
2. On the iPhone, open Safari at `http://<laptop-ip>:8123`
3. Share → **Add to Home Screen** → Urja.

The service worker caches everything, so after install the app runs fully
offline - the laptop server can stop.

## Files

- `index.html / styles.css / app.js` - the app (vanilla, no build step)
- `data.js` - extracted model snapshot (regeneratable)
- `sw.js / manifest.webmanifest / icons/` - PWA plumbing
- `scripts/app_data_extract.py` - the extractor
