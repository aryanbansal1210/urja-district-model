# Prompt: redesign the cockpit and the building info panel

Attach `viewer_design_harness.html`. Paste everything between the rules.

This supersedes the general restyle prompt in `BRIEF_FOR_CLAUDE_DESIGN.md` for
the two panels named here. Same hard constraints, sharper target.

---

## THE PROMPT TO PASTE

> Attached is `viewer_design_harness.html`, a static self-contained snapshot of
> a 3D urban-energy master-plan viewer. Real interface, real numbers, captured
> from the running application. No JavaScript and no external requests, so it
> previews as-is.
>
> **Two panels need redesigning. Everything else can stay as it is.**
>
> **1. The building info panel** (`#cell-panel`, headed "Selected cell"). This
> appears when someone clicks a building on the map. Right now it is a flat
> list of about fifteen label-value rows in one uniform style, so the thing a
> reader most wants to know competes for attention with diagnostics they
> probably do not. In the snapshot it is showing a mid-income apartment block.
> The content falls into four groups and the design should make that visible:
>
> - *What this building is*: land use, building type, height tier, storeys,
>   floor area. This is the headline and should read as one.
> - *What it generates*: PV capacity, yield multiplier, shading.
> - *How it compares*: rank and percentile within the layout.
> - *Diagnostics*: entrances, lighting schedule, legacy flags. Secondary.
>   Consider making this group collapsible.
>
> **2. The cockpit** (`#cockpit-panel`), the dark panel on the right. It carries
> a live energy-flow diagram, a grid of metric chips, and several pages
> (Live, Trends, Trading, Impact, Cells, Settings). In this snapshot **all
> pages are unfolded and stacked so you can see them**; in the real application
> one shows at a time and the rest are hidden. Design it for one-page-at-a-time.
> The chips are currently uniform, so a 90 MW demand figure and a 0 kW carport
> figure look equally important. Give the panel a hierarchy.
>
> The whole thing sits over a 3D map and is read on a desktop, dark theme. It
> should feel like an instrument, not a bootstrap dashboard. Numbers are the
> content: they should be the most confident thing on screen.
>
> **Hard constraints, because this is a copy of a working application:**
>
> 1. **CSS only.** Do not add, remove, reorder or rename any element, `id`,
>    `class`, `data-*` or `aria-*` attribute. Application JavaScript selects on
>    all of them, there is no test coverage, and breakage would be silent.
> 2. **Do not delete any existing rule or selector**, even if it looks unused
>    here. Many apply only at runtime. Change declarations freely; add new rules
>    freely.
> 3. **These classes are state, set by JavaScript. They must stay visually
>    distinct:** `hidden` (must remain `display: none`), `active`, `collapsed`,
>    `ui-idle`, `tariff-off` / `tariff-shoulder` / `tariff-peak` (three tariff
>    bands that must be tellable apart at a glance - the snapshot is in `peak`),
>    `status-*`, `delta-good`, `schema-stale`, `schema-warning`.
> 4. **No external resources.** No CDN, no Google Fonts, no imported
>    stylesheets, no remote images. System font stacks, inline SVG or data URIs
>    only. The application runs offline.
> 5. **Plain CSS, one stylesheet.** No framework, no preprocessor, no build.
> 6. Do not touch anything below the `HARNESS ONLY` banner near the end of the
>    stylesheet. It exists to make this snapshot previewable and is deleted when
>    the work is ported back.
> 7. The colour-coded chips carry meaning through a `--chip` custom property
>    set inline per chip. Keep that mechanism working.
>
> **Return:** the complete revised stylesheet as one CSS file, plus a short note
> on what changed and why. Keep the harness previewable so the result can be
> seen.

---

## ON CHANGING THE BUILDINGS

Asked separately, and the answer splits in two.

**Do not let a design tool change building GEOMETRY.** Heights come from
`layout/spine_gradient.py`, the Bertaud density gradient: tall on the arterial
spine, medium through the body, short at the edge, held floor-neutral at two
tall to three short. Footprints are the 50 m cell grid. Those numbers are model
output and the thesis argues from them. If the viewer stops matching the model,
the figure stops being evidence.

**Do let it change how buildings LOOK.** Material response, colour, roof
treatment, edge definition, the deterministic jitter already used for variety
(`buildingHeightJitter`), and how PV hardware reads against the roof. All of
that is rendering, none of it is a claim.

That work belongs to the 3D job, not this one: see `BRIEF_3D_SCENE.md`, and it
edits `app.js`, not `styles.css`.

## WHY THE SNAPSHOT LOOKS SLIGHTLY ODD

Two deliberate differences from the live viewer, both to make design possible:

- Every cockpit page is unfolded and labelled, so all of them can be seen at
  once. The real panel shows one.
- A building is pre-selected so the info panel has content. Normally it is
  hidden until a click.
