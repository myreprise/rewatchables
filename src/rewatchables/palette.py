"""The palette, taken from the podcast artwork: mint field, ring black, tape white.

The figures use it directly; the stylesheet (rewatchables/app/theme.css, which
step 15 copies to the site) spells the same colours as CSS custom properties,
so the two have to move together.
"""


# Palette — derived from The Rewatchables artwork (mint field, ring black, tape white).
INK, INK_2, INK_3, INK_4 = "#0B0D0C", "#101211", "#171A18", "#1E221F"
LINE, LINE_2 = "#262B28", "#333934"
MINT, MINT_DEEP, MINT_DIM = "#2BE8A0", "#17A87C", "#0D6249"
TAPE, TAPE_2, CORAL = "#F2EFE6", "#D9D5C9", "#E2624F"
TXT_2, TXT_3 = "#9AA39D", "#6B736E"

# Categorical series, assigned in this fixed order and never cycled. The ordering
# was chosen by running candidates through a colour-vision validator: worst
# adjacent pair scores dE 10.2 under protanopia against the #101211 surface.
AMBER, BLUE, VIOLET, MAGENTA = "#C98500", "#4A8FE0", "#9085E9", "#D55181"
SERIES = [MINT_DEEP, AMBER, BLUE, CORAL, VIOLET, MAGENTA]

# Sequential ramp for magnitude — one hue, receding into the surface at the low end.
SEQ = ["#0D6249", "#14906C", "#1CBD8C", "#43D9A7", "#79E9C2", "#B6F5DC"]
