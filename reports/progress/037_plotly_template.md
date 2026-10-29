# 037 — A Plotly template of our own

Date: 2026-10-29. Branch `streamlit-phase-a`.
Previous: [036 — phase A, decouple](036_streamlit_phase_a_decouple.md).

## TL;DR

The "RT vs TMDB" scatter on the live Ratings page has been effectively
invisible. Its 16 genre traces were coloured `#000001`–`#000010`, Streamlit's
placeholders, on a `#101211` plot. Figures are now built on a template made
from the palette, and the scatter folds genres past the series into "Other".
**Only that chart changes** in the export; checked against the phase A
baseline, figure by figure, and in the site preview.

## What changed

- **`figures.py`** builds the `rewatchables` template from the palette and makes
  it Plotly's default, replacing `plotly_template.json` (Streamlit's template,
  vendored in phase A):

  | Template part | Before (Streamlit placeholders) | Now |
  | --- | --- | --- |
  | `layout.colorway` | `#000001`…`#000010` | `SERIES` (6 colours) |
  | sequential colour scale, `coloraxis` | `#000011`…`#000020` | `SEQ` ramp |
  | `heatmap` colour scale | `#000011`… | `SEQ` ramp |
  | scatter marker outline | width 0 | width 0 (kept) |
  | candlestick, contour, sankey, table, waterfall, icicle | placeholders | dropped: no chart uses them, and the site's Plotly bundle doesn't include most |

- **`sections/ratings.py`**: the scatter uses `fold_to_series`, like the
  timeline and genre charts. The six commonest primary genres get the series
  colours and the rest share a grey "Other" (`TXT_3`), so no two genres share
  a colour. Hover still names the film's own genre.

The app picks up the template too: `rewatchables.figures` sets it after
`streamlit` is imported. The app's copy of this scatter now uses the series
colours rather than Streamlit's theme colours.

## Evidence

**Which charts depended on the template.** I went through all 32 figures in
the baseline export (30 in `figures`, 2 nested in `section_data`):

- `ratings/rt_vs_tmdb` was the only one whose traces took their colour from
  the template: 16 traces, placeholder colours.
- Every heatmap sets its own colour scale.
- The two running-margin traces in Cruise vs. Hanks that look uncoloured are
  zero-width lines with explicit `fillcolor`s.

**Export against the phase A baseline:**

| | Result |
| --- | --- |
| Figures with changed data or layout (template aside) | 1: `ratings/rt_vs_tmdb` |
| Non-figure rows | byte-identical |
| `site.sql` | 2,595,221 → 2,509,573 bytes (−86 KB; the placeholder template was larger) |
| `synopses.json`, `theme.css` | identical |

**Site preview** (`site-dev` on port 3200, with the new export swapped in for
the duration and then restored):

- The scatter draws 7 traces: Comedy `#17A87C`, Drama `#C98500`, Action
  `#4A8FE0`, Crime `#E2624F`, Thriller `#9085E9`, Horror `#D55181`, Other
  `#6B736E`. The legend reads and the points are visible (screenshot
  checked). I didn't read the console: that call timed out once the pane
  was hidden.
- I didn't get a screenshot of the Hosts heatmaps. The browser pane was hidden
  again and the page stalls when hidden. Their figure JSON is unchanged apart
  from the template, and they set their own colour scales.

**Tests:** 968 passed, 3 failed, 1 deselected. These are the same three app
tests that fail on master because Streamlit 1.65.0 is installed instead of
the pinned 1.41.1 (report 036).

## Not done

- The live site changes only after this branch is merged and you next
  publish. Step 15 then rewrites `site.sql` and `publish.py` commits it.
