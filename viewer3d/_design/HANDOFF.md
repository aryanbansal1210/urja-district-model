# Handoff — DISTRICT_v3 viewer restyle

For whoever picks this up next (Claude Code, or me in a later session). Written
. Everything below is fact about what is in this project, not a plan.

---

## 1. What was asked, in order

The work came in five rounds. Each one changed the target, so read them in
sequence — the later ones override the earlier ones.

1. **Restyle the 3D viewer's cockpit**, CSS only, from a design harness
   (`uploads/viewer_design_harness.html`). Focus on three panels: Trading,
   Impact, Cells. Make it a sibling of the Urja resident app built earlier in
   the same conversation. The attached addendum said: carry the app's hues,
   type, radii and restraint, but **keep the cockpit dark** because it floats
   over a 3D map.
2. Fix the main banner and all the other floating panels to one style.
3. **"Everything's too dark"** — the user reversed the addendum's instruction
   and asked for the app's actual light palette, its font, more weight, and a
   flow diagram with real icons. This is the direction that shipped.
4. Neaten the flow diagram (lines that connect the boxes, value and unit on one
   line), and clean up informal language and capitalisation.
5. Fix the banner wrapping.

## 2. Where things are

```
viewer/
  styles.css        THE DELIVERABLE. Paste over viewer3d/styles.css.
  harness.html      The design harness, restyled. Previewable, no JS.
  review.html       My review page: Live/Trading/Impact/Cells side by side.
                    NOT part of the viewer. Delete it.
  CHANGES.md        What changed in the stylesheet and why.
  COPY_CHANGES.md   Text strings to change in index.html / app.js.
  _append.css       Working file — see §6 before editing anything.
```

The app built earlier in the same conversation is in `app/` and is unrelated to
this restyle except as the visual reference.

## 3. How `styles.css` is put together

This matters more than anything else here. **`styles.css` is generated, not
hand-edited.** It is exactly two pieces concatenated:

```
[ base ]  the harness's original stylesheet, with a value-level palette
          pass applied (every dark/cool literal mapped to the app's paper
          palette). No selector added, removed or renamed.
+
[ append ]  viewer/_append.css — one commented block called PAPER PASS
            plus the sections that follow it. All the structural work.
```

The base half was produced by a find/replace map run over
`uploads/viewer_design_harness.html`'s inline `<style>`. The map is not stored
anywhere except in the conversation, so **if you need to regenerate the base,
the honest path is to work from `viewer/styles.css` as it stands** and treat
everything before the `PAPER PASS` banner as the base. Do not try to re-derive
it from the upload.

To rebuild after editing `_append.css`:

```js
// read harness.html, find the <style> open tag and the
// "HARNESS ONLY - not part of the real viewer" banner,
// keep everything before the PAPER PASS banner as `base`,
// then: css = base + _append.css
// write css back into harness.html between those markers,
// and write the same css to styles.css
```

Two traps in that rebuild, both of which bit me:

- The harness `<head>` now contains a comment with the words `HARNESS ONLY` in
  it (the font `<link>`). Searching for `HARNESS ONLY` finds that first and
  truncates the file. Search for the full string
  `HARNESS ONLY - not part of the real viewer`.
- The harness uses **CRLF** line endings. Any marker string with `\n` in it will
  not match.

## 4. The hard constraints, and how they were kept

The brief was emphatic: the real app is ~500 KB of untested JavaScript that
selects on every id, class and attribute, so a rename breaks silently.

- **CSS only.** No element, `id`, `class`, `data-*` or `aria-*` was added,
  removed, renamed or reordered.
- **No rule deleted.** Values were retuned in place; everything new is appended.
- **No external requests in the stylesheet.** The only `url` in it is inside a
  comment. Node icons are inline `data:` URI SVGs.
- **State classes stay distinct.** `[hidden]`/`.hidden` still
  `display: none !important`; `active` is one ink pill everywhere; the three
  tariff bands are water blue / gold / terracotta; `status-*`, `delta-good`,
  `schema-stale`, `schema-warning`, `collapsed`, `ui-idle` all present.
- **`HARNESS ONLY` block untouched.**

Two exceptions, both deliberate and both outside `styles.css`:

- `harness.html` has a Google Fonts `<link>` added in `<head>`, marked
  HARNESS ONLY. Without it the preview never shows Instrument Sans. Delete it
  when porting; it is not in the stylesheet.
- `harness.html`'s visible **text** was rewritten (80 strings, §7). Structure
  untouched. This is a preview convenience; the real change belongs in
  `app.js`.

## 5. What the restyle actually does

Palette is the Urja app's, verbatim: canvas `#EFEDE7`, card `#FCFBF7`, soft
`#F5F3ED`, hairline `#E4E2DC`, ink `#1B1B1B`, dim `#6E6E6E`, solar `#E8B54E`,
water `#4E7CA8`, grid `#5B84B8`, battery `#7C9A6E`, good `#6E8F5E`, warn
`#B0764A`. Radii 14/20/26. Type Instrument Sans with a system fallback. One
selected state — ink fill, paper text — shared by tool buttons, layout tabs,
segmented controls and cockpit tabs.

- **Banner and panels** — one recipe for all ten floating panels.
- **Trading** — buy and sell in opposite hues at equal weight; the tariff block
  reads as a section; net trade is the conclusion.
- **Impact** — the eleven equal boxes became three tiers from the same markup:
  headline pair (`:nth-child(-n+2)`), evidence (`:nth-child(n+3)`), and the two
  mode pills as metadata with no fill.
- **Cells** — a reflowing hairline list, `repeat(auto-fill, minmax(140px, 1fr))`,
  which works at four rows and at twenty.
- **Live flow** — paper card, gold wash behind the hub, hairline rails, and a
  data-URI icon per node (sun, pylon, house, building, server rack, battery,
  water drop). Laid out as a 3x3 ring, see below.
- **Banner** — every forced minimum removed so the control row stops wrapping
  on normal displays; the two sliders are cards so their tracks are visible.
- **Chart furniture** — axis labels and gridlines are SVG presentation
  attributes in the markup, which was off limits; a CSS declaration outranks
  them, so a block scoped to `<text>` and `<line>` brings them onto paper. Data
  series (`polyline`/`path`/`polygon`) are untouched apart from one
  `saturate(.84)` on the svg.

### The flow ring, final numbers

Hero is 354 x 322 in the cockpit. Boxes are 88 x 70, the hub 92 x 92, hub
centre (177, 161). Every box sits with its near edge **60px from the hub
centre**, a uniform 14px gap outside the hub on all four sides:

| Box | top | horizontal |
|---|---|---|
| Canal-Top | 31 | `left: 29` |
| Solar | 31 | centred |
| Data Centre | 31 | `right: 29` |
| Grid | 126 | `left: 29` |
| Hub | 115 | centred |
| Load | 126 | `right: 29` |
| Flex | 221 | centred |

Why 60 and not each rail's own tip: measured in hero pixels the rail tips are
72px above the hub centre, 74px either side and only **60px below**. Putting
each box on its own tip made the ring visibly lopsided, so the shortest rail
sets the radius and the three longer rails run a few pixels further under their
box, which is invisible. All six still connect — tips (177,89), (103,161),
(251,161), (177,221), (257,57) and (116,75) each fall on or inside their box.

`.flow-node strong` is `white-space: nowrap` with the old `max-width` removed,
so value and unit stay on one line; all seven measure 14px tall.

### Banner width

`.control-row` holds eleven controls with real words on them. The original
sheet gave several fixed minimums — `min-width: min(520px, 100%)` on the layout
field for two tabs needing 300, a 118px floor on a readout needing 95, and
(once this pass put them in cards) 294px per slider — totalling ~1497px, so the
row only fitted above ~2100px. Those minimums are gone, the long layout tab is
capped at 120px with an ellipsis (full name still in the DOM for its tooltip),
and the sliders are ~221px. Intrinsic width is now ~1244px: **one line from
about 1680px up**, two tidy rows below that with a `row-gap` so it reads as
deliberate.

### Slider fields

In the app a slider sits inside a white card. Dropped straight onto the panel a
4px `#E4E2DC` track scored ~1.04:1 and was invisible — a lone thumb with no
range. `.slider-field` is now a card (`--card` fill, hairline, pill radius,
padding), which also reunites the label, track and readout into one control, and
the track is `--track: #BFB9AB` (~1.9:1 on the card). `#D5D1C6`, used elsewhere
for chart axes, only reaches ~1.15:1 and was not enough.

### Label case

The micro-labels were ALL CAPS, a dark-cockpit device that shouts on paper.
`text-transform: capitalize` with the tracking pulled back and sizes at 10.5px,
applied to labels only — every `<strong>` is excluded, so `62.4 kWp` is never
mangled into `62.4 KWp`.

## 6. Things that fought back — read before editing

**`.flow-svg` does not stretch.** It is an absolutely-positioned *replaced*
element with an intrinsic 320:260 viewBox and `width/height: auto`. Setting all
four insets does **not** resize it: the ratio wins, the used height derives from
the width, and the box stays pinned to the top. So the hero's height has no
effect on where the drawing sits. The mapping from viewBox to hero pixels is
fixed:

```
x = 13 + viewBoxX * 1.025      (1.025 = 328/320, width-derived)
y = 11 + viewBoxY * 1.025      (11 = 10px inset + 1px border)
```

I got this wrong twice by assuming the SVG would fill the box, which put every
node 9–10px below its rail. If you move any node, measure the rail endpoint with
`getPointAtLength` + `getScreenCTM` first; do not compute it from the hero size.

**Rail geometry is not symmetric.** The bottom rail is 11 viewBox units shorter
than the top, so the visible stub below the hub is shorter than the other three.
Evening that up needs an edit to the path `d` attributes, i.e. `app.js`.

**Inline styles beat the stylesheet.** `.flow-path` strokes carry
`style="stroke: rgb(...)"` set per state by `app.js`, and chart series colours
are presentation attributes. I did not override them — that state is how
import/export/charging stay tellable apart — only softened them with
`saturate`. Any attempt to force the app's hues onto them destroys the state
signal.

**Specificity trap.** `.cockpit-impact-grid > div:nth-child(n+3)` is (0,2,1) and
beats `.cockpit-impact-grid .cockpit-stage-d-pill` at (0,2,0) regardless of
source order. The pill rules are written `> div.cockpit-stage-d-pill` for that
reason. Don't "simplify" them.

**A `local`-only `@font-face` is a trap.** I shipped one briefly: when the
font is absent the face enters an error state and, because it claims the whole
400–700 range for the family name, it silently shadows every other face of that
name — including a Google `<link>` or a self-hosted `@font-face` added later.
It is gone. `styles.css` names the family and registers nothing.

**Slider tracks need a surface.** In the app the slider lives in a white card.
Dropped straight onto the panel, a 4px `#E4E2DC` track scores ~1.04:1 and is
invisible. `.slider-field` is now a card and the track is `--track: #BFB9AB`
(~1.9:1 on the card).

**The preview iframe caches hard.** Several times a measurement came back
showing the previous build. If a probe contradicts the file, check the file
first — a cache-busting query string on the linked stylesheet is the quickest
way out (`review.html` links `styles.css?v=9`; bump it).

**The harness stacks all six cockpit pages.** It un-hides every
`.cockpit-page`, so a layout validator will report text overlapping the
toolbar and pages colliding. Those are artefacts of the capture, not defects —
the real cockpit shows one page at a time. Judge the panels in
`review.html`, which renders them side by side at full height.

**html-to-image renders native form controls unfaithfully.** Screenshots paint
the slider thumbs the wrong colour. Trust `getComputedStyle`, not the capture,
for anything involving `input[type="range"]`.

## 7. What I could not do

- **Change any interface text.** CSS cannot. Every informal string —
  `Stage B/C/D`, `DSR`, `WTE`, `BAU`, `placeholder`, `alpha`,
  `period_breakdown`, `dispatch_results.json`, "land on the Python side" — is
  listed in `COPY_CHANGES.md` as an exact find/replace pair for `index.html` and
  `app.js`. All 80 are applied in `harness.html` so the result is visible, and
  none touches an id, class or attribute. Two strings in my list did not match
  the harness and are worth checking by hand: `<span>P2P guide</span>` and
  `<span>Oct/Jun 0.98</span>`.
- **Capitalisation** *is* done in CSS (`text-transform: capitalize` on labels
  only, never on `<strong>`, so `62.4 kWp` is never mangled to `62.4 KWp`).
- **Guarantee the font offline.** I cannot produce a woff2. Drop
  `InstrumentSans.woff2` beside `styles.css` and add one `@font-face` (the
  snippet is in `CHANGES.md`), or add the Google `<link>` if the viewer is
  allowed a network. Until then it falls back to the system stack on any machine
  without the font installed.
- **Fit the banner on one line below ~1680px.** `.control-row` has eleven
  controls with real words on them. I removed every forced minimum
  (`min-width: min(520px,100%)` on the layout field, the 118px readout floor,
  294px slider cards) and capped the long layout tab with an ellipsis, taking
  the row from ~1497px to ~1244px intrinsic. At 1440px it wraps to two rows,
  with a `row-gap` so that reads as deliberate. Fitting 1177px would need
  shorter labels, i.e. a copy change.
- **Redraw the flow rails.** Their `d` attributes are in the markup. I moved the
  boxes onto the existing endpoints instead.
- **Change data-series colours** to the app's hues, for the state reason above.
- **Verify the live 3D map.** deck.gl loads from a CDN and the data arrives by
  `fetch`; neither exists in the harness. The map area is a placeholder
  throughout, so nothing here is validated against a real scene.
- **Even up the bottom rail stub.** The bottom rail is 11 viewBox units shorter
  than the top, so with the ring at a uniform radius its visible stub is
  shorter than the other three. Fixing it means editing that path's `d`.
- **Expand the standard abbreviations.** PV, EV, V2G, PPA, ToU, EWS/LIG were
  left as they are, on the grounds that they read as technical rather than
  internal. Say so if you want them spelled out; they are markup changes.
- **Source-code comments** were left alone. Several are informal dev notes
  ("no axis titles, looks so bad"), invisible to users.

## 8. Known risks when porting

- The Impact tiering uses `:nth-child`, so it assumes that grid keeps its
  current child order. `app.js` writes into fixed ids rather than reordering, so
  it holds — but that is the thing to revisit if the order ever changes.
- The cockpit is now **light and floats over the map**, which is what was asked
  for and matches the app, but it is the opposite of the addendum's advice about
  glare. If a pale layout or a bright noon sun ever makes the panels hard to
  separate from the ground, raise `--panel` toward `0.97` rather than going back
  to a dark shell.
- Four things the brief says a CSS-only change can plausibly break, all checked
  here and worth re-checking after porting: the three tariff bands read
  differently, panels still collapse, the cockpit still switches pages, and the
  layout tabs still show which is active.
