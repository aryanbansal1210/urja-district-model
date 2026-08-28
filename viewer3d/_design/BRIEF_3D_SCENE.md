# Brief: upgrading the 3D scene (NOT the UI panels)

There are two separate redesign jobs and they touch different files. Mixing
them is how the working viewer gets broken.

| Job | Changes | Artifact | Brief |
|---|---|---|---|
| UI panels: cockpit, legend, topbar | `viewer3d/styles.css` | `viewer_design_harness.html` | `BRIEF_FOR_CLAUDE_DESIGN.md` |
| **3D scene: lighting, materials, sky** | **`viewer3d/app.js`** | **`scene_code_extract.js` + `current_look/`** | **this file** |

## WHAT TO UPLOAD

Use "upload the files directly". **Do not connect the GitHub repo and do not
attach the local codebase.** Either of those hands over 475 KB of `app.js` that
has no test coverage, and the scene appearance is a 10 KB fraction of it.

- `scene_code_extract.js` - lighting, sun direction, sky gradient, building
  height scaling, night lighting and surface colour, pulled out by name with
  original `app.js` line numbers kept in each header.
- `current_look/1_noon.png`, `2_golden_hour.png`, `3_night.png` - the same
  district under the three lighting conditions that matter.

## FORM ANSWERS

| Question | Answer | Why |
|---|---|---|
| Built with | deck.gl | deck.gl 9, no basemap; the district is drawn from its own GeoJSON over a CSS sky gradient |
| More appealing means | Lighting and shadows; Materials and surfaces; Sky, water, greenery; Colour grading | The four that live in the extracted code |
| *not* | On-screen UI and labels | That is the other job. Ticking it invites edits to code already covered by the harness |
| *not* | Guided tour, camera moves, performance | Out of scope for a thesis figure; camera work is a separate change with its own risk |
| Who is it for | Academic or conference presentation | MSc thesis, viva and written submission |
| Target look | **Stylised / diagrammatic** | See below |

## WHY NOT PHOTOREAL

The geometry is extruded cells on a 50 m grid, with heights derived from floor
area ratio rather than from designed buildings. There are no facades, no window
openings, no roof detail and no terrain. A photoreal treatment would imply a
level of architectural resolution the model never produced, which is a claim
the thesis cannot support at viva. Stylised is the honest register and the
achievable one.

## WHAT THE SCENE HAS AND HAS NOT GOT

- **Has:** altitude-driven sun colour (2700 K dawn to near-white noon), ambient
  and fill lights, a sky gradient keyed to sun altitude, per-surface material
  (ambient / diffuse / shininess / specular), night streetlight and window
  lighting, PV panels drawn as separate geometry on roofs.
- **Has not:** terrain, a water surface, vegetation geometry. Trees and greenery
  are flat coloured cells today, and in the screenshots they read as saturated
  green blobs. That is probably the single biggest visual win available.
- **Broken:** native deck.gl shadows are disabled (`_shadow: false`). They
  caused a draw-time white-out in the browser on and were turned off
  pending debugging. Shadows currently come from a legacy flat-ground shadow
  layer. If a proposal depends on real shadows, that bug has to be fixed first.

## CONSTRAINTS TO GIVE IT

> 1. Return changed **functions only**, each one named, so they can be dropped
>    back into `app.js` at the line numbers given in the extract. Do not return
>    a rewritten file and do not reorganise the code.
> 2. Do not rename any function, change any signature, or change what a
>    function returns. Other code calls all of these.
> 3. deck.gl 9 API only. No new libraries, no CDN, no external textures or
>    HDRIs. The viewer runs offline.
> 4. Keep every appearance driven by `state.sun.altitudeDeg` as it is now: the
>    scene has to stay correct from before dawn to after dusk, not just look
>    good at noon.
> 5. The colour tables carry meaning. Land use, tariff band and the PV overlays
>    are read against a legend, so hues may be refined but categories must stay
>    distinguishable and must not be merged.

## PORTING BACK

Changes land in `viewer3d/app.js` only. Back it up first - the folder already
holds `app.js.bak.*` from previous visual passes, so follow that convention:

    cp app.js app.js.bak.pre-design-YYYYMMDD

Then check, in this order: the viewer still loads, the sun slider still changes
the sky from dawn to night, the legend still matches the map colours, and the
PV / Shade / Deploy / Grid overlays still read correctly. Those are what a
scene change can plausibly break.
