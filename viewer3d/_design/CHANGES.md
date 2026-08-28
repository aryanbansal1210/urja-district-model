# viewer/styles.css — what changed and why

CSS only. No element, `id`, `class`, `data-*` or `aria-*` was added, removed,
renamed or reordered. No selector was deleted — values were retuned in place and
one commented block, `PAPER PASS`, is appended at the end. One file, plain CSS,
no imports and no network requests. The `HARNESS ONLY` block is untouched.

Files: `styles.css` (the deliverable — paste over `viewer3d/styles.css`),
`harness.html` (the harness, restyled, still previewable), `review.html` (my
review page showing Trading / Impact / Cells side by side; not part of the
viewer — delete it).

## The change of direction

The first pass kept the cockpit dark, per the addendum. Your instruction
overrode that: make it the app. So the viewer is now on the Urja app's own
surface — warm paper `#EFEDE7`, cards `#FCFBF7`, ink `#1B1B1B`, dim `#6E6E6E`,
hairlines `#E4E2DC`, one gold accent `#E8B54E`, and the meaning hues
(`--water #4E7CA8`, `--grid-hue #5B84B8`, `--batt #7C9A6E`, `--good #6E8F5E`,
`--warn #B0764A`) doing the same jobs they do on the phone. Radii are the app's
14 / 20 / 26 px. Every literal in the old sheet — the blue-blacks `#090b0d`,
`#101417`, `#0f172a`, the cool greys `#93a4b8`, `#64748b`, the blue accents —
was mapped to that palette, and the translucent white washes became the same
alphas in ink, so they read as paper tints rather than glass.

Weight went up throughout: 600 on every heading and value, 20 px panel titles,
28 px on the Impact headline pair, 24 px on the Trading prices, tabular figures
and `ss01` on.

## Type

`font-family` is Instrument Sans first, then the system stack. There is
deliberately **no `@font-face` in the stylesheet**: an earlier draft declared one
with a `local`-only `src`, and when the font is absent that face enters an
error state and — because it claims the whole 400–700 range for the family name
— silently shadows any other face registered under the same name, including a
Google `<link>` or a self-hosted `@font-face` added later. Exactly the
breaks-with-no-error failure this project worries about, so it is gone.

To guarantee the font, add one of these and change nothing else:

```css
@font-face { font-family:"Instrument Sans"; font-weight:400 700;
             font-display:swap;
             src:url("InstrumentSans.woff2") format("woff2-variations"); }
```

or the same Google family `<link>` the resident app uses, if the viewer is
allowed a network. The harness and the review page both load that `<link>` (in
the harness it sits above the `<style>`, marked HARNESS ONLY), so the previews
show the real typeface; `styles.css` itself still makes no request.

## Label case

The micro-labels were ALL CAPS — a dark-cockpit device that shouts on paper.
They are Title Case now via `text-transform: capitalize`, tracking pulled back,
sizes lifted to 10.5px. Applied to labels only: every `<strong>` is excluded, so
`62.4 kWp` is never mangled to `62.4 KWp`.

## Interface copy

See `COPY_CHANGES.md`. CSS cannot change text, so the informal strings — `Stage
B/C/D`, `DSR`, `WTE`, `BAU`, `placeholder`, `alpha`, `period_breakdown`,
`dispatch_results.json`, "land on the Python side" — are listed there as exact
find/replace pairs for `index.html` and `app.js`. All of them are applied in
`harness.html` so you can see the result, and none touches an `id`, `class`,
`data-*` or `aria-*` value.

## Live energy flow

Rebuilt to read like the app's home hero rather than a neon schematic:

- The hero is a paper card at 26 px with a warm gold wash behind the hub, the
  same `--glow` the app uses.
- Rails are 8 px hairlines in `#DFDACE`; the flows keep the state colour app.js
  assigns them (that is how import/export/charging stay tellable apart) but the
  drop-shadow glow is gone, the dash is the app's `4 10`, and a light
  `saturate(.78)` pulls the hues into the app's muted family.
- Every node is a small paper chip on the app's radius with a soft shadow and
  **its own icon**, drawn as an inline data-URI SVG so nothing is fetched: sun
  for Solar, pylon for Grid, house for the District hub, building for Load,
  server rack for the data centre, battery for Flex, water drop for Canal-top.
- The hub is the subject — larger, gold-ringed, ink house mark — so the eye
  starts in the middle and follows the dashes out.

**Geometry.** The rails are drawn in the markup inside a 320×260 viewBox and
cannot be redrawn from CSS, but the boxes can be moved onto them — which was the
real problem: they were placed by eye, so the rails stopped in mid air at
unequal lengths.

Worth knowing before touching this: `.flow-svg` is an absolutely-positioned
*replaced* element with an intrinsic 320:260 ratio and `width/height: auto`, so
setting all four insets does **not** stretch it. The ratio wins, the used height
is derived from the width, and the box stays pinned to the top — which means the
hero's height does not move the drawing at all. The scale is width-derived
(328/320 = 1.025) and the origin is fixed at the inset plus the 1px border:

    x = 13 + viewBoxX × 1.025
    y = 11 + viewBoxY × 1.025

Every node sits on its own rail's outer endpoint under that mapping, and the hub
is wider than the gap between the four inner endpoints, so each rail runs from a
box edge to under the hub. Nothing floats. The hero height only has to clear the
lowest box: Flex tops out at 221px, so 296px leaves a 5px margin.

Boxes are 88×70 (hub 92×92) and `.flow-node strong` is `white-space: nowrap`
with the old `max-width` removed, so value and unit stay on one line —
`190.2 MW` was previously breaking across two.

One caveat: the markup's rails are not symmetric about the hub (the bottom rail
is 11 viewBox units shorter than the top), so the visible stub below the hub is
shorter than the other three. Evening that out means editing the path `d`
attributes.

## The main banner

Paper, one hairline, the title separated from the controls by a rule rather than
by a gap, and the old 82px minimum height dropped so the bar is as tall as its
contents rather than a fixed slab.

On width, be aware of what it can and cannot do. `.control-row` holds eleven
controls with real words on them, and the original sheet gave several of them
fixed minimums — `min-width: min(520px, 100%)` on the layout field for two tabs
that need 300, a 118px floor on a readout that needs 95, and (after this pass
put them in cards) 294px per slider. That totalled ~1497px of intrinsic width,
so the row only ever fitted above ~2100px and broke to two, three or four lines
on every normal display. Those minimums are now removed, the long layout tab is
capped at 120px and elided (the full name stays in the DOM for its tooltip), and
the sliders are trimmed to ~221px each. The row's intrinsic width is ~1244px,
so the bar sits on **one line from about 1680px up**. Below that it wraps to two
rows, with a `row-gap` so that reads as deliberate — eleven labelled controls
genuinely do not fit 1177px, and a clean second row is a better answer than
squeezing them. Every control is a 34 px pill;
selected state is an ink fill with paper text, used identically for tool
buttons, layout tabs, segmented controls and cockpit tabs, so "selected" means
one thing everywhere. The range inputs had no track styling at all and were
drawing the near-black UA default on the new light bar — they now use the app's
slider: ink thumb, tariff hue on the Time thumb.

The two banner sliders also needed the surface the app gives them. In the app a
slider sits inside a white card; here they sat directly on the panel, so a 4px
`#E4E2DC` track scored about 1.04:1 against it — invisible, leaving a lone dot
with no range to drag along. `.slider-field` is now a proper card (`--card`
fill, hairline, pill radius, padding), which both gives the track something to
read against and reunites the label, track and readout into one control instead
of three drifting parts. The track itself is a new `--track: #BFB9AB` — the same
warm family, about 1.9:1 on the card — because a 4px boundary needs more than a
hairline's worth of contrast. `#D5D1C6`, used elsewhere for chart axes, only
reaches ~1.15:1 and was not enough. The three
tariff classes also land on the Time slider's `<label>`, where a fill and a
border had nothing to sit on and read as a hard-cornered slab across the
toolbar; the fill is now scoped to `.tariff-status`, and the slider field shows
its band through the readout colour and the thumb instead.

## Trading

Buy and sell take opposite hues with a 3 px edge marker and equal weight at
24 px. The tariff block reads as a section with its own gold wash. Net trade is
the page's conclusion at 25 px in terracotta; the two windows below carry gold
values.

## Impact

Eleven equal boxes became three tiers from the same markup: the two carbon
figures as a gold-washed headline pair at 28 px; `:nth-child(n+3)` as evidence
on the soft fill at 16 px; and the two mode pills as metadata with no fill,
spanning the grid. The pill rules are written `> div.cockpit-stage-d-pill` so
they outrank the evidence tier on specificity rather than on source order.

## Cells

Four to twenty rows, so the stats are a reflowing hairline list
(`repeat(auto-fill, minmax(140px, 1fr))`), label left, value right, tabular
figures. Both extremes look deliberate. The flow chart takes the gold through
`currentColor`; runtime-filled containers collapse while `:empty`.

## Chart furniture

Axis labels, ticks and gridlines are SVG presentation attributes in the markup,
which is off-limits — a CSS declaration outranks them, so a block scoped to
`<text>` and `<line>` brings them onto paper: labels `#6E6E6E`, gridlines
`#E4E2DC`, axes `#D9D5CB`, and the selected-time marker ink so it stays the most
legible line. Data series are `polyline`/`path`/`polygon` and are untouched
apart from one `saturate(.84)` on the svg, which softens the app's brighter
series colours without changing which is which. The source-mix stack gets the
same treatment for the same reason.

## State classes — all still distinct

`hidden` / `[hidden]` untouched (`display: none !important`); `active` is the ink
pill everywhere; `collapsed` untouched; `ui-idle` now drops to 0.26 rather than
0.10, because paper panels disappear against a pale map long before dark ones
do. Tariff bands stay three clearly different things — off-peak water blue,
shoulder gold, peak terracotta, with border, fill, text and slider thumb moving
together. `status-exporting` gold, `status-importing` terracotta,
`status-charging`/`discharging` green; `delta-good` green; `schema-stale`
terracotta; `schema-warning` gold.

## One thing to watch

The cockpit is now light and it floats over the map — that is what you asked
for, and it matches the app, but it is the opposite of the earlier advice about
glare. If a pale layout (dispersed low, or a bright noon sun) ever makes the
panels hard to separate from the ground, the cheapest fix is to raise
`--panel`'s opacity toward `0.97` rather than to go back to a dark shell.
