# Interface copy — strings to change in the app

CSS cannot change text. Everything below is a **string in `index.html` or
`app.js`**, so it has to be edited there. I applied all of it to
`viewer/harness.html` so you can see the result, and none of it touches an
`id`, a `class`, a `data-*` or an `aria-*` value — `.cockpit-stage-d-pill` keeps
its class name, only its visible label changes.

Two other things I did **not** touch: your source code comments (several are
informal, e.g. "no axis titles, looks so bad" — dev notes, invisible to users),
and standard industry abbreviations that read as technical rather than internal:
PV, EV, V2G, PPA, ToU, EWS/LIG, MWh, kWp. Say the word if you want those spelled
out too.

## Internal stage names — the main thing you asked about

| Find | Replace |
|---|---|
| `Stage B preview` | `Energy scenarios` |
| `Stage D mode` | `Network detail` |
| `Stage C tech stack (2030 base year)` | `Installed capacity (2030 base year)` |
| `Per-cell` | `Per cell` |
| `Realism checks` | `Model checks` |
| `Equity placeholder` | `Equity` |
| `EWS bill-share pending Path 1` | `EWS bill share, in progress` |
| `Ownership tiers and income-linked discount rates land on the Python side.` | `Ownership tiers and income-linked discount rates are still being modelled.` |
| `Recommended upgrade` | `Suggested upgrade` |
| `optimised_sa` (as a visible chip label) | `Optimised` |

## File and field names showing through to the user

| Find | Replace |
|---|---|
| `dispatch_results.json` (as a value) | `Current model run` |
| `2030 base year period_breakdown` | `2030 base year, period breakdown` |
| `Scenario full_stack alpha 0.00; no fixture headline.` | `Scenario: full stack, carbon weight 0.00. Every figure is read from the run.` |
| `alpha 0.00:` … `alpha 1.00:` | `Carbon weight 0.00:` … `Carbon weight 1.00:` |
| `at alpha 1.00.` | `at carbon weight 1.00.` |
| `the pre-computed A21 sweep` | `the pre-computed price sweep` |
| `gap-sum 1.04` | `Gap sum 1.04` |
| `smallest gap-sum` | `Smallest gap sum` |
| `severity leader` | `Severity leader` |
| `8/18 pass` | `8 of 18 pass` |
| `metric_notes.renewable_share: …` | `Purchased green open-access energy is not counted, so this share understates clean supply. Quote it alongside the green purchase figure.` |
| `dc_ppa_offtake_kwh and dc_ppa_revenue_inr` | (drop) `Data-centre PPA scenarios read from the model run.` |
| `: green-PPA raises emissions.` | `Note: the green PPA raises emissions.` |
| `excludes 21.4 GWh purchased green OA` | `Excludes 21.4 GWh of purchased green open access` |
| `scripts/dispatch_realism_audit.py` reference | `Effective load: demand, plus shifted-in response and EV charging, less reduced response and shifted-out charging.` |
| `Dynamic geom LP scale 0.771-0.998` | `Scale 0.771 to 0.998` |
| `Actual geom PV-bearing values` | `Values run` |

## Shorthand in labels

| Find | Replace |
|---|---|
| `DSR reduce` | `Demand response, reduced` |
| `DSR add` | `Demand response, shifted` |
| `DSR spikes` | `Demand-response spikes` |
| `DSR moves 13.08 MWh a day.` | `Demand response moves 13.08 MWh a day.` |
| `WTE` | `Waste to energy` |
| `P2P guide` | `Peer-to-peer guide` |
| `PPA mode` | `Power purchase agreement` |
| `BAU` (scenario option) | `Business as usual` |
| `BAU continued` | `Business as usual continued` |
| `Annual saved vs BAU` | `Annual saving vs business as usual` |
| `BAU reference 530.95 GWh.` | `Business-as-usual reference 530.95 GWh.` |
| `vs BAU -52.4% cost / -62.0% CO2.` | `Against business as usual: -52.4% cost, -62.0% CO2.` |
| `0 >1.8x` | `None above 1.8x` |
| `seasonal` | `Seasonal` |
| `jun-jul-aug-sep` | `June to September` |

## Sentence polish

Fragments joined into sentences, semicolon chains split, and terminal full stops
added — for example `Dispatch results unavailable; 3D scene loaded without the
energy cockpit.` becomes `Dispatch results unavailable. The 3D scene has loaded
without the energy cockpit.`; `active dispatch; annual x 36.1; price sweep shown
below` becomes `Active dispatch, annual x 36.1. Price sweep shown below.`; and
`Suggested watchlist: high PV rooftops, …` becomes `Worth a look: high-PV
rooftops, …`. The full set is applied in `harness.html` — diff it against your
capture to lift them all.

## Capitalisation

This part **is** done in CSS and needs no app change. The micro-labels were set
in ALL CAPS by the old stylesheet; they are Title Case now
(`text-transform: capitalize`, tracking pulled back), applied to labels only —
every `<strong>` is excluded so a value like `62.4 kWp` is never mangled into
`62.4 KWp`.
