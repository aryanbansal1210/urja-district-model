# Addendum - paste this after the main prompt

Sent once the harness, the main prompt and `APP_DESIGN_TOKENS.md` are already
in the conversation. It resolves the two competing references and guards the
third-party file.

---

> Two more references are attached, and they pull in different directions, so
> here is how to weigh them.
>
> **`APP_DESIGN_TOKENS.md` plus the phone screenshots** are my own product, the
> resident app for this same project. **Colour, type and radii come from here.**
> Carry over the hues, Instrument Sans, the 14 / 20 / 26 px radii and above all
> the restraint: one accent, everything else desaturated, colour only where it
> carries meaning.
>
> Do **not** carry over its light background. The cockpit stays dark because it
> floats over a 3D map, and a pale panel would glare and hide the map beneath.
> Rebuild the same warmth on a dark base instead: warm dark greys rather than
> blue-blacks, off-white text rather than pure white, the same gold as the
> single accent.
>
> **`metropolis_reference.html` is visual reference ONLY.** Take from it the
> layout thinking, the restraint and the atmosphere. Do **not** take its
> palette, and do **not** copy its code, class names or structure into my file.
> It is 2D canvas and isometric; mine is deck.gl and perspective, so none of its
> technique transfers. It is also someone else's published work.
>
> The specific thing worth learning from it is its control panel, bottom left:
> small, translucent, tinted to sit inside the scene rather than on top of it,
> two sliders and a time readout and nothing else. Compare that with my cockpit,
> which is a tall opaque slab with nine metric chips at equal weight. That
> contrast is the brief.
>
> To be explicit about the result I want: my viewer should look like it and my
> resident app were designed by the same person, in the same week, for the same
> project. One is a phone app on warm paper and the other is an instrument panel
> over a dark map, but they should be recognisably siblings.
