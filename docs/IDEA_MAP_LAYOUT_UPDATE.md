# Idea Map Layout Update

- Main-point boxes now show a concise gist/main point for each paragraph, with explicit labels such as `Paragraph 1 · Main point` and `Paragraph 2 · Main point`.
- Box widths and text wrapping are content-aware so longer text gets more room and rendered text stays inside its box.
- Main connectors now use per-branch vertical positions based on the branch text length, so arrow/gap length adjusts to the content instead of every arrow using one fixed distance.
- Supporting-idea boxes also size their height and wrapping from their actual text length.

## Overlap fix (box sizing no longer fights column width)

Previously, box width had a hard floor (176px) that was applied independently
of the column width each box was centered in. Once there were enough
branches (7-8+) that the canvas had to divide into narrower columns, that
floor could exceed the column width and boxes would silently overlap their
neighbours by tens of pixels.

Column width and box width are now solved together in `_compute_layout`:
- A box always leaves a guaranteed 24px gutter to its column boundary.
- If fitting all branches at the requested canvas width (1100px default)
  would force columns below a readable minimum, the **canvas itself grows**
  (`required_width`) instead of shrinking boxes into overlap. All three
  renderers (`render_structure_svg`, `render_artistic_sketch_svg`,
  `render_combined_svg`) resolve this the same way via `_compute_canvas_size`,
  so they always agree on final dimensions.
- Label/topic/leaf font sizes scale down slightly (a `tightness` factor
  based on column width) as columns get narrower, so wrapped text keeps
  comfortable margins in a tighter box instead of hugging its edges.
- Verified programmatically against generated SVG geometry: 0 box-to-box
  overlaps across essays from 2 up to 12+ paragraphs.

## Arrowhead sizing

Arrowhead markers previously used one fixed size (7x7) for both the thicker
thesis→branch connectors (stroke-width 2.5) and the thinner branch→leaf
connectors (stroke-width 1.8), so the head could look too small on the
thick line or too heavy on the thin one. There are now two marker sizes per
palette color — a larger head for main connectors, a smaller one for leaf
connectors — with `refX` set to the tip of the triangle so the arrow point
lands exactly at the target box's edge instead of overshooting into it or
stopping short with a visible gap.
