-- A section's charts, as Plotly specs (JSON text).
SELECT name, spec FROM figures WHERE section = ?
