# Urja app - design tokens, as a reference for the viewer

Extracted from `app/styles.css`. This is the "make it feel like my app" input.
Upload this file alongside the harness.

## Palette

| Token | Value | Used for |
|---|---|---|
| `--canvas` | `#EFEDE7` | page background, warm off-white |
| `--card` | `#FCFBF7` | raised surfaces |
| `--soft` | `#F5F3ED` | secondary fills |
| `--line` | `#E4E2DC` | hairline borders |
| `--ink` | `#1B1B1B` | primary text, near-black |
| `--dim` | `#6E6E6E` | secondary text |
| `--solar` | `#E8B54E` | solar, the signature accent |
| `--glow` | `rgba(232,181,78,.16)` | soft halo behind solar |
| `--water` | `#4E7CA8` | water, hot water |
| `--grid` | `#5B84B8` | grid import |
| `--batt` | `#7C9A6E` | battery, storage |
| `--good` | `#6E8F5E` | positive state |
| `--warn` | `#B0764A` | warning, muted terracotta |

Type: **Instrument Sans**, falling back to Helvetica Neue / Helvetica / Arial.
Radii: **14 px / 20 px / 26 px**. Generous, soft, no sharp corners anywhere.

## The vibe, in words

Warm, quiet, unhurried. Off-white paper rather than white. Near-black text
rather than pure black. One confident accent (solar gold) and everything else
desaturated. Lots of space. Large soft radii. Colour is used to *mean*
something - solar, water, grid, battery each own a hue - never for decoration.

## THE CATCH, AND IT NEEDS SAYING EXPLICITLY

**The app is light. The viewer cockpit is dark, and it floats over a 3D map.**
The cream canvas cannot simply be pasted across: white panels over an aerial
view would glare, and the map would stop being readable underneath.

So the instruction to give is:

> Carry over the **hues** (solar gold, water blue, grid blue, battery green,
> terracotta warning), the **type** (Instrument Sans), the **radii** (14 / 20 /
> 26 px) and above all the **restraint** - one accent, everything else
> desaturated, colour only where it carries meaning, generous spacing.
>
> Do **not** carry over the light background. The cockpit stays dark because it
> sits over a map. Rebuild the same warmth on a dark base instead: warm dark
> greys rather than blue-blacks, off-white text rather than pure white, and the
> same gold as the single accent.

Getting that distinction right is most of the job. A designer given only the
app screenshots will tend to produce a light panel, which is wrong for this
context.

## HOW TO ADD SCREENSHOTS

Take two or three on your phone of the app screens you actually like, and
attach them with this file. Say what you want from them, for example "this
spacing and this restraint" rather than "make it look like this", so the tool
does not try to reproduce a phone layout on a desktop panel.

## IF YOU ALSO GIVE IT A SECOND PROJECT FOR INSPIRATION

Worth doing, with one guard. Say this:

> The second attachment is **visual reference only**. Take ideas about layout,
> hierarchy, spacing and colour from it. Do **not** copy its code, class names,
> structure or framework into my file. My file is plain CSS with no build step
> and its class names are read by application JavaScript.

Without that line, a reference project built with Tailwind, styled-components
or a component library tends to arrive as utility classes and imports, which
breaks the plain-CSS constraint and would not survive porting back.

Screenshots of the second project are safer than its source, and usually
sufficient - the point is the look, not the implementation.
