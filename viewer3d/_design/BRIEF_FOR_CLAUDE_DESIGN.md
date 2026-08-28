# Brief: restyling the DISTRICT_v3 3D viewer

Paste everything between the rules below into Claude Design, and attach
`viewer_design_harness.html`.

---

## THE PROMPT TO PASTE

> Attached is `viewer_design_harness.html`: a static, self-contained snapshot of
> the interface of a 3D urban-energy master-plan viewer. It is a real screen
> with real numbers in it, captured from the running application. There is no
> JavaScript in it and there are no external requests, so it previews as-is.
>
> I want the visual design upgraded. Please improve typography, spacing,
> hierarchy, colour, depth and the general feel of the panels. Make it look
> like a considered piece of software rather than a dashboard someone
> assembled. It is viewed on a desktop, dark theme, over a 3D map.
>
> **Hard constraints, because this file is a copy of a working application:**
>
> 1. **Change CSS only.** Do not add, remove, reorder or rename any HTML
>    element, `id`, `class`, `data-*` attribute or `aria-*` attribute. I have to
>    paste your stylesheet back into an application whose JavaScript selects on
>    all of those, and it has no test coverage, so anything you change silently
>    breaks with no warning.
>
> 2. **Do not delete any existing CSS rule or selector**, even if it looks
>    unused in this snapshot. Many are applied at runtime. You may freely
>    change the *declarations* inside a rule and you may add new rules.
>
> 3. **These classes are state, toggled by JavaScript. Their styling must stay
>    visually distinct from the base state:**
>    `hidden` (must remain `display: none`), `active`, `collapsed`, `ui-idle`,
>    `tariff-off` / `tariff-shoulder` / `tariff-peak` (three tariff bands that
>    must stay tellable apart at a glance), `status-*`, `delta-good`,
>    `schema-stale`, `schema-warning`.
>
> 4. **No external resources.** No CDN, no Google Fonts, no imported
>    stylesheets, no remote images. System font stacks or inline SVG or data
>    URIs only. The real application runs offline.
>
> 5. **Keep it one stylesheet.** No CSS frameworks, no build step, no
>    preprocessor syntax. Plain CSS that a browser reads directly.
>
> 6. Do not touch anything below the `HARNESS ONLY` banner near the end of the
>    stylesheet. That block exists to make this snapshot previewable and is
>    deleted when I port your work back.
>
> **What to give me back:** the complete revised stylesheet as one CSS file, and
> a short list of what you changed and why. Please also keep the updated
> harness previewable so I can see it.

---

## WHY A HARNESS AND NOT THE REAL FILES

Worth knowing if the tool asks for more, or offers to "just fix the app".

| | |
|---|---|
| `app.js` | **487 KB**, ~7,000 lines, no test coverage. Any regeneration risks silent damage. Do not upload it. |
| deck.gl | Loaded from `unpkg.com`. Claude artifacts block every external host, so the 3D layer cannot run there at all. |
| The data | Arrives via `fetch` from `../outputs/geojson3d` and five other paths. None of it exists on the other side. |

So the harness carries the **rendered** DOM, with the real stylesheet inlined
and no script at all. It is the only form of this interface that a design tool
can actually open and preview.

## WHAT COMES BACK, AND HOW IT LANDS

The only file that changes in the repo is `viewer3d/styles.css`. Nothing else
is touched. If the result is wrong, `styles.css.bak.*` backups already exist
next to it and the previous look is one file copy away.

Check after porting: the three tariff bands still read differently, panels
still collapse, the cockpit still switches pages, and the layout tabs still
show which one is active. Those are the four things a CSS-only change can
plausibly break.

## REBUILDING THE HARNESS

If the viewer's markup changes and the harness needs refreshing, the capture is
scripted end to end. See `build_harness.py` in the session scratchpad: it reads
a live DOM dump plus `styles.css` and emits the single file. The DOM dump is
taken from the running viewer, because most of the interface is injected by
`app.js` at runtime and a copy of `index.html` alone renders as empty boxes.
