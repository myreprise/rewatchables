// Draws the app's own Plotly figures, exported by pipeline step 15 as JSON.
//
// Separate from ui.js so only the pages with a chart load Plotly. The
// cartesian partial bundle covers every trace type the app draws (bar, box,
// heatmap, histogram, image, pie, scatter) at a third of the full bundle's
// size, 500 KB gzipped against 1.48 MB. Pinned so a build is reproducible.

import Plotly from "npm:plotly.js-cartesian-dist-min@4.1.2";

// One figure at the width it is given; the height is the figure's own, or
// Plotly's 450 as in st.plotly_chart. Use inside resize() so it redraws when
// the page width changes:  display(resize((width) => plot(fig, width)))
export function plot(fig, width) {
  const div = document.createElement("div");
  if (!fig) return div;
  Plotly.newPlot(div, fig.data, {...fig.layout, width},
                 {displayModeBar: false, responsive: false});
  return div;
}
