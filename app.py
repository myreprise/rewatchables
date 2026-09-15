"""
Rewatchables Explorer — Streamlit EDA app
"""

import sqlite3
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from itertools import combinations

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from views import (
    ANCHOR, BREAK_EVEN_MULTIPLE, BROWSE_FLOOR, CPI_BASE_YEAR,
    CPI_PROVISIONAL_FROM, LINK_FLOOR, MEASURE_LABEL, RESOLUTION_NOTE, ROOM,
    appearances_by_year, bench, bh_adjust, clean, co_appearances,
    contributor_link, decade_bars, html, human_gap, keyword_chip, lean_phrase,
    lean_value, lineups, money, multiple, parse_tags, permutation_diffs,
    person_name,
    pitch_chips, plain, rank_by_reach, real_usd, region_of, room_long,
    sort_title, stale_notice, stars, stat_tile,
)

# ── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rewatchables Explorer",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent / "rewatchables.db"
# The loaders below are cached, and keyed on the database's modification time
# as well as their ttl, so a pipeline run shows on the next rerun rather than up
# to five minutes later.
DB_STAMP = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
# The episode list's source of truth, for the banner that says the data is
# behind it. See 01_render_source.py.
SOURCE_XLSX = Path(__file__).parent / "data" / "episodes.xlsx"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
TMDB_THUMB = "https://image.tmdb.org/t/p/w185"
TMDB_PROFILE = "https://image.tmdb.org/t/p/w342"

# Publicity portraits for the two subjects of the Cruise vs. Hanks segment,
# resolved once from TMDB /person (Cruise is 500, Hanks is 31) and pinned here.
# TMDB image paths are content-addressed and stable, so hard-coding them keeps
# the section header off the API entirely -- there is no person cache, and one
# lookup per cold start to render two decorative images is not worth building.
CRUISE_PORTRAIT = "/3mShHjSQR7NXOVbdTu5rT2Qd0MN.jpg"
HANKS_PORTRAIT = "/oFvZoKI6lvU03n4YoNGAll9rkas.jpg"

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


# ── Theme ─────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --ink:#0B0D0C; --ink-2:#101211; --ink-3:#171A18; --ink-4:#1E221F;
  --line:#262B28; --line-2:#333934;
  --mint:#2BE8A0; --mint-deep:#17A87C; --mint-dim:#0D6249;
  --tape:#F2EFE6; --tape-2:#D9D5C9; --coral:#E2624F;
  --txt-2:#9AA39D; --txt-3:#6B736E;
}

/* ── Base ─────────────────────────────────────────────────────────────── */
.stApp { background:var(--ink); color:var(--tape); }
html, body, .stApp, .stMarkdown, .stText {
  font-family:'Archivo','Helvetica Neue',Arial,sans-serif;
}
[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:2.4rem; max-width:1500px; }
hr { border-color:var(--line); }
::selection { background:var(--mint); color:var(--ink); }
:focus-visible { outline:2px solid var(--mint); outline-offset:2px; }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; } }

/* ── Sidebar ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] { background:var(--ink-2); border-right:1px solid var(--line); }
.rw-brand { display:flex; align-items:center; gap:10px; padding:2px 0 14px; }
.rw-brand svg { width:30px; height:30px; flex:none; }
.rw-brand b {
  display:block; font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:13px; line-height:1.15; color:var(--tape);
}
.rw-brand span {
  display:block; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:8.5px;
  letter-spacing:.05em; color:var(--txt-3); margin-top:4px; white-space:nowrap;
}
.rw-foot {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  letter-spacing:.06em; color:var(--txt-3); line-height:1.8; text-transform:uppercase;
}

/* Nav — the section radios, restyled as one rail with mono numbering.
   The rail is one radio per group, so the counter is reset on the sidebar and
   not on the radiogroup: a per-group reset restarts the numbering at 01 under
   every heading instead of running 01..09 down the whole rail. */
section[data-testid="stSidebar"] { counter-reset:rwnav; }
section[data-testid="stSidebar"] div[role="radiogroup"] {
  display:flex; flex-direction:column; gap:2px;
}
.rw-navgroup {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--txt-3);
  margin:16px 0 5px 3px;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label {
  display:flex; align-items:center; gap:9px; padding:8px 10px; margin:0;
  border-radius:5px; cursor:pointer; background:transparent;
  transition:background .15s;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label::before {
  counter-increment:rwnav; content:counter(rwnav,decimal-leading-zero);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px;
  color:var(--txt-3); width:16px; flex:none;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child { display:none; }
section[data-testid="stSidebar"] div[role="radiogroup"] p {
  font-size:13.5px !important; font-weight:500 !important; color:var(--txt-2);
  margin:0 !important; line-height:1.3;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover { background:var(--ink-3); }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover p { color:var(--tape); }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
  background:var(--mint); box-shadow:2px 2px 0 rgba(0,0,0,.4);
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
  color:var(--ink); font-weight:700 !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked)::before {
  color:rgba(11,13,12,.55);
}

/* ── Masthead ─────────────────────────────────────────────────────────── */
.rw-masthead {
  position:relative; overflow:hidden; padding:24px 26px 20px; margin:0 0 4px;
  border:1px solid var(--line); border-radius:8px;
  background:linear-gradient(180deg,#14231D 0%,#0B0D0C 100%);
}
.rw-masthead h1 {
  position:relative; margin:0; padding:0;
  font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:30px; line-height:1.1; letter-spacing:-.02em; color:var(--tape);
}
.rw-masthead p {
  position:relative; margin:8px 0 0; max-width:60ch;
  font-size:13.5px; color:var(--txt-2); line-height:1.5;
}
.rw-watermark {
  position:absolute; right:-46px; top:-64px; width:250px; height:250px;
  opacity:.10; pointer-events:none;
}

/* ── Tape-strip section headings ──────────────────────────────────────── */
.rw-tape-row { margin:26px 0 10px; }
.rw-tape {
  display:inline-block; position:relative; background:var(--tape); color:var(--ink);
  font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:13px; letter-spacing:.02em; text-transform:uppercase;
  padding:7px 15px; transform:rotate(-.9deg);
  box-shadow:2px 2px 0 rgba(0,0,0,.45);
}
.rw-tape::before, .rw-tape::after {
  content:""; position:absolute; left:0; right:0; height:3px;
  background:repeating-linear-gradient(90deg,#0B0D0C 0 3px,transparent 3px 6px);
  opacity:.45;
}
.rw-tape::before { top:0; }
.rw-tape::after { bottom:0; }
.rw-tape.alt { transform:rotate(.7deg); }

/* ── Headings ─────────────────────────────────────────────────────────── */
h1, h2 {
  font-family:'Archivo Black',Arial Black,sans-serif !important; font-weight:400 !important;
  color:var(--tape) !important; letter-spacing:-.015em;
}
h3 { color:var(--tape) !important; font-size:1.02rem !important; font-weight:700 !important; }

/* ── Metric tiles ─────────────────────────────────────────────────────── */
[data-testid="stMetric"], div[data-testid="metric-container"] {
  background:var(--ink-2); border:1px solid var(--line); border-radius:7px;
  padding:13px 14px 12px; position:relative; overflow:hidden;
}
[data-testid="stMetric"]::after, div[data-testid="metric-container"]::after {
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--mint-dim);
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {
  font-family:'IBM Plex Mono',ui-monospace,monospace !important;
  font-size:9.5px !important; letter-spacing:.13em; text-transform:uppercase;
  color:var(--txt-3) !important;
  /* Streamlit clips a metric label to one line with an ellipsis, which turns
     "Median gross (2024$)" into "Median gross (2..." — dropping the half that
     says which dollars. Let it wrap instead; the tiles are a fixed grid and
     already have the vertical room. */
  white-space:normal !important; overflow:visible !important;
  text-overflow:clip !important; line-height:1.45 !important;
}
.rw-tile {
  background:var(--ink-2); border:1px solid var(--line); border-radius:7px;
  padding:13px 14px 12px; position:relative; overflow:hidden; display:inline-block;
  min-width:180px;
}
.rw-tile::after { content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--coral); }
.rw-tile .k {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3);
}
.rw-tile .v {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:29px; line-height:1.15;
  color:var(--coral); font-variant-numeric:tabular-nums; letter-spacing:-.02em; margin-top:6px;
}
[data-testid="stMetricValue"] {
  font-family:'Archivo Black',Arial Black,sans-serif !important;
  font-size:29px !important; line-height:1.15 !important; color:var(--mint) !important;
  font-variant-numeric:tabular-nums; letter-spacing:-.02em;
}

/* ── Poster cards ─────────────────────────────────────────────────────── */
.poster-card {
  background:var(--ink-3); border:1px solid var(--line); border-radius:6px;
  overflow:hidden; margin-bottom:12px;
  transition:border-color .15s, transform .15s;
}
.poster-card:hover { border-color:var(--mint); transform:translateY(-2px); }
/* Verdict band for poster grids that carry one. It sits between the art and the
   title strip and is the whole tag -- so it is weighted to read as a deliberate
   band across a grid rather than as a hairline. */
.poster-rule { height:5px; }
.poster-rule.cruise { background:#C98500; }
.poster-rule.hanks  { background:#4A8FE0; }
.poster-rule.tie    { background:#6B736E; }
.poster-label { padding:7px 9px 8px; font-size:.72rem; color:var(--txt-3); line-height:1.35; min-height:44px; }
.poster-label strong {
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  color:var(--tape); font-size:.76rem; font-weight:600;
}
.poster-label span {
  color:var(--mint); font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.68rem;
}
.poster-plate {
  position:relative; display:flex; align-items:flex-end; padding:9px; overflow:hidden;
  background:linear-gradient(160deg,#1D2B25 0%,#101211 62%,#0B0D0C 100%);
}
.poster-plate b {
  position:relative; font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:11px; line-height:1.2; text-transform:uppercase; color:var(--tape-2);
}
.poster-plate svg { position:absolute; right:-16px; top:-16px; width:76px; height:76px; opacity:.14; }
/* Every plate is a poster's own 2:3 at its column's width, so the cards in a
   grid share one size and every card in the app shares one shape. A fixed
   pixel height against a fluid column made the box whatever shape the viewport
   produced -- near-square six across, a letterbox strip in a one-film shelf --
   and cover cropped the poster to match. TMDB posters are 2:3 to within 1%
   (644 of 661, the rest within 5%), so cover now trims a sliver off those few. */
.poster-img { box-sizing:border-box; width:100%; aspect-ratio:2/3; }
img.poster-img { display:block; object-fit:cover; }

/* ── Ranked name/count rows (collaborator lists) ──────────────────────── */
.rw-rank { display:flex; align-items:center; gap:10px; padding:5px 0; }
.rw-rank .n { font-size:13px; color:var(--tape-2); width:44%; flex:none;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rw-rank .bar { flex:1; height:14px; background:var(--ink-3); border-radius:2px; overflow:hidden; }
.rw-rank .bar i { display:block; height:14px; background:var(--mint-deep); }
/* Three-name lineups ("Chris Ryan + Mallory Rubin + Sean Fennessey") ran to
   an ellipsis at 64% in a two-fifths column; the bar only has to show rank. */
.rw-rank.wide .n { width:74%; }
.rw-rank .c {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
  color:var(--txt-2); width:22px; flex:none; text-align:right;
  font-variant-numeric:tabular-nums;
}

/* ── Chips & badges ───────────────────────────────────────────────────── */
.badge {
  display:inline-flex; align-items:center; padding:3px 8px; margin:2px 3px 2px 0;
  border-radius:3px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:10px; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
  background:var(--ink-3); border:1px solid var(--line-2); color:var(--txt-2);
}
.badge-mint { background:rgba(43,232,160,.13); border-color:rgba(43,232,160,.35); color:var(--mint); }
.badge-revisit { background:rgba(226,98,79,.16); border-color:rgba(226,98,79,.42); color:var(--coral); }
.chip-row { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }

/* ── Controls ─────────────────────────────────────────────────────────── */
.stButton > button {
  background:var(--ink-3); color:var(--tape); border:1px solid var(--line-2);
  border-radius:5px; font-weight:600; transition:border-color .15s, color .15s;
}
.stButton > button:hover { border-color:var(--mint); color:var(--mint); }
[data-baseweb="tag"] { background:var(--mint) !important; color:var(--ink) !important; }
[data-baseweb="tag"] span { color:var(--ink) !important; }

/* Selects and multiselects. Stock BaseWeb ships them as #101211 on a #0B0D0C
   page with a border the same colour as their own fill -- a control with no
   edge, set in Source Sans, which is the one typeface the rest of the page
   never uses. They read as gaps in the layout rather than as things to click.
   Given the same treatment as .stButton so every control on the page is
   recognisably the same family. !important throughout: BaseWeb sets these
   inline, and an inline style beats a stylesheet regardless of specificity. */
[data-baseweb="select"] > div {
  background:var(--ink-3) !important; border:1px solid var(--line-2) !important;
  border-radius:5px !important; transition:border-color .15s;
}
[data-baseweb="select"] > div:hover { border-color:var(--mint) !important; }
[data-baseweb="select"] > div:focus-within {
  border-color:var(--mint) !important;
  box-shadow:0 0 0 3px rgba(43,232,160,.15) !important;
}
[data-baseweb="select"] input, [data-baseweb="select"] div[value] {
  font-family:'IBM Plex Mono',ui-monospace,monospace !important;
  font-size:12px !important; letter-spacing:.04em;
}
/* The chevron is the one saturated mark in an otherwise monochrome row, which
   is what the eye lands on. Scoped to the control: the tag close crosses on a
   multiselect are svgs too, and they sit on mint already. */
[data-baseweb="select"] > div > div:last-child svg { color:var(--mint); }

/* The menu, which otherwise floats edgeless over the poster grid. */
[data-baseweb="popover"] ul {
  background:var(--ink-2) !important; border:1px solid var(--line-2) !important;
  border-radius:5px !important;
}
[data-baseweb="popover"] li {
  font-family:'IBM Plex Mono',ui-monospace,monospace !important;
  font-size:12px !important; color:var(--txt-2) !important;
}
[data-baseweb="popover"] li[aria-selected="true"] {
  background:rgba(43,232,160,.13) !important; color:var(--mint) !important;
}

/* Widget labels, as the mono micro-caps every other piece of furniture uses.
   Matches .rw-kw-eyebrow, so the sidebar filters and the sort picker announce
   themselves the same way a section eyebrow does. */
[data-testid="stWidgetLabel"] p {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.18em; text-transform:uppercase; color:var(--txt-3);
}

/* ── Tables ───────────────────────────────────────────────────────────── */
.stDataFrame { background:var(--ink-2); border:1px solid var(--line); border-radius:7px; }
[data-testid="stTable"] { background:var(--ink-2); }

/* ── Cruise vs. Hanks ─────────────────────────────────────────────────── */
/* Amber/blue are the SERIES slots already assigned to the two camps; the
   scoreboard, the guest splits and the streak cards all read off the same
   two hues so the pairing never has to be re-learned mid-section. */

/* Fight-card header. Two portraits squared off across the running score, each
   backed by a rail of posters from THAT actor's films the podcast has actually
   covered -- 18 for Cruise, 11 for Hanks -- so the art is drawn from the same
   dataset as the charts rather than being decoration bolted on top. */
.ch-hero {
  position:relative; overflow:hidden; border:1px solid var(--line); border-radius:8px;
  background:linear-gradient(180deg,#14231D 0%,#0B0D0C 100%);
  padding:22px 26px; margin-bottom:4px; min-height:196px;
  display:flex; align-items:center;
}
.ch-rail {
  position:absolute; top:50%; transform:translateY(-50%); width:44%;
  display:flex; gap:5px; align-items:center; pointer-events:none;
  opacity:.34; user-select:none;
}
.ch-rail img { height:230px; width:auto; flex:none; filter:grayscale(.72) contrast(1.02); }
/* Scrim between the rails and the type. The posters are texture, not content --
   without this the captions sit on top of poster lettering and stop being
   readable, which is the usual way a photo header goes wrong. */
.ch-hero::before {
  content:""; position:absolute; inset:0; z-index:1; pointer-events:none;
  background:linear-gradient(90deg,
    rgba(11,13,12,.42) 0%, rgba(11,13,12,.86) 20%, rgba(11,13,12,.93) 50%,
    rgba(11,13,12,.86) 80%, rgba(11,13,12,.42) 100%);
}
/* Fade each rail out toward the centre so the portraits and score stay legible. */
.ch-rail.l { left:0;
  -webkit-mask-image:linear-gradient(90deg,#000 0%,#000 42%,transparent 92%);
          mask-image:linear-gradient(90deg,#000 0%,#000 42%,transparent 92%); }
.ch-rail.r { right:0; justify-content:flex-end;
  -webkit-mask-image:linear-gradient(270deg,#000 0%,#000 42%,transparent 92%);
          mask-image:linear-gradient(270deg,#000 0%,#000 42%,transparent 92%); }

.ch-hero-inner {
  position:relative; z-index:2; width:100%;
  display:flex; align-items:center; justify-content:space-between; gap:22px;
}
/* The two fighters hold their size; the centre column is the one that gives, so
   a narrow viewport squeezes the blurb rather than pushing a portrait out of
   the overflow:hidden container. */
.ch-fighter { display:flex; align-items:center; gap:15px; flex:0 0 auto; min-width:0; }
.ch-fighter.r { flex-direction:row-reverse; text-align:right; }
/* Duotone: a greyscale portrait blended onto the camp's own colour plate, so
   the two men carry the same amber/blue coding as every chart below. */
.ch-face {
  width:108px; height:152px; flex:none; border-radius:5px; overflow:hidden;
  position:relative; isolation:isolate; box-shadow:0 10px 26px rgba(0,0,0,.6);
}
.ch-face.c { background:#C98500; }
.ch-face.h { background:#4A8FE0; }
.ch-face img {
  width:100%; height:100%; object-fit:cover; object-position:center 12%; display:block;
  filter:grayscale(1) contrast(1.06); mix-blend-mode:luminosity;
}
.ch-name {
  font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:25px; line-height:1; letter-spacing:-.02em;
}
.ch-name.c { color:#E8A21F; }
.ch-name.h { color:#7BB0EE; }
.ch-tally {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:38px; line-height:1;
  color:var(--tape); font-variant-numeric:tabular-nums; margin-top:7px;
}
.ch-sub {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.11em; text-transform:uppercase; color:var(--txt-3); margin-top:7px;
}
.ch-vs { text-align:center; flex:1 1 auto; min-width:0; padding:0 6px; }
/* Never break "Who ya got?" across lines -- it shrinks with the viewport
   instead, because the phrase is the section's name and reads as damaged split. */
.ch-vs .q {
  font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:clamp(17px,2.1vw,31px); line-height:1.02; color:var(--tape);
  letter-spacing:-.02em; white-space:nowrap;
}
.ch-vs .bolt {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px; font-weight:600;
  letter-spacing:.26em; color:var(--txt-3); margin-bottom:9px; white-space:nowrap;
}
.ch-vs .blurb {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--txt-3); margin-top:11px;
}
@media (max-width:1100px) { .ch-rail { display:none; } }
@media (max-width:820px) {
  .ch-hero-inner { flex-direction:column; gap:16px; }
  .ch-fighter, .ch-fighter.r { flex-direction:column; text-align:center; }
}
.ch-score { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; margin-bottom:10px; }
.ch-score .who {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:34px; line-height:1;
  letter-spacing:-.02em;
}
.ch-score .cruise { color:#E8A21F; }
.ch-score .hanks  { color:#7BB0EE; }
.ch-score .cnt {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12.5px;
  color:var(--txt-2); margin-top:6px; letter-spacing:.04em;
}
.ch-score .r { text-align:right; }
.ch-score .mid {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  color:var(--txt-3); letter-spacing:.12em; padding-bottom:6px; white-space:nowrap;
}
.ch-tug { display:flex; height:42px; border:1px solid var(--line-2); overflow:hidden; }
.ch-tug div {
  display:flex; align-items:center; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:13px; font-weight:600; color:var(--ink);
}
.ch-tug .c { background:#C98500; padding-left:13px; }
.ch-tug .t { background:var(--txt-3); justify-content:center; font-size:11px; }
.ch-tug .h { background:#4A8FE0; justify-content:flex-end; padding-right:13px; }

.ch-note { font-size:13px; color:var(--txt-3); margin:10px 0 0; max-width:74ch; line-height:1.55; }
.ch-note b { color:var(--txt-2); font-weight:600; }

.ch-null {
  margin-top:14px; padding:13px 16px; background:var(--ink-3);
  border-left:2px solid var(--coral); font-size:13.5px; color:var(--tape-2); line-height:1.55;
}
.ch-null b { color:var(--tape); }

.ch-streak {
  background:var(--ink-3); border:1px solid var(--line); padding:13px 15px;
  border-radius:5px; height:100%;
}
.ch-streak .n {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:25px; line-height:1;
}
.ch-streak .lbl {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.11em; color:var(--txt-3); margin:6px 0 8px;
}
.ch-streak .films { font-size:12px; color:var(--txt-2); line-height:1.5; }

.ch-guest { display:flex; align-items:center; gap:12px; padding:5px 0; }
.ch-guest .gn { font-size:13px; color:var(--tape-2); width:150px; flex:none; }
.ch-guest .bar { display:flex; height:18px; flex:1; overflow:hidden; }
.ch-guest .bar i { display:block; height:18px; }
.ch-guest .num {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
  color:var(--txt-3); width:104px; flex:none; text-align:right;
}

/* ── Film dossier ─────────────────────────────────────────────────────── */
/* The per-film detail view. Nothing here restyles an existing class; the
   dossier borrows the masthead gradient, the tape strips, the metric-tile
   grammar and the amber/blue Cruise-Hanks pairing already defined above. */

/* Poster grids: the title strip under each plate is a real st.button, flattened
   so a grid of them still reads as a grid. Scoped by the marker span the card
   emits, so the sidebar and Surprise-me buttons keep their own styling. */
.rw-cardmark { display:none; }
/* Streamlit sizes a column's contents from a pixel width it measured itself --
   on the inner block and each element container by class, and on the element
   inside (stMarkdown, stButton) by inline style -- and after a section change
   those can hold a width that is not the column's: seen at 742px inside a
   103px column. Plates are sized by width, so a stale width shows as a 740x1111
   poster spilling over its neighbours. Each level carries its own width, so
   clamping the block alone is not enough; all three are held to the column. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark),
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) > div[data-testid="stElementContainer"],
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) > div[data-testid="stElementContainer"] > div {
  width:100% !important; max-width:100%;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button {
  background:var(--ink-3); border:1px solid var(--line); border-top:0;
  border-radius:0 0 6px 6px; margin-top:-13px; margin-bottom:12px;
  padding:7px 9px 8px; display:flex; flex-direction:column; gap:2px;
  align-items:flex-start; justify-content:flex-start; text-align:left;
  /* Matches the min-height the old .poster-label carried, so a two-line title
     in one column does not push the next row of that column out of step. */
  min-height:46px;
  white-space:normal; transition:border-color .15s, color .15s, background .15s;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button:hover {
  border-color:var(--mint); background:var(--ink-4);
}
/* The button's own box is only the title strip, but the whole card is one
   target: this reaches the hit area up over the plate so a click anywhere on
   the poster opens the dossier. The button stays a real button with its text
   label, so keyboard and screen-reader behaviour is unchanged.
   How far up is one plate height, and a plate is 2:3 at its column's width --
   which is the button's width too. A percentage margin resolves against the
   containing block's width even when it is vertical, so -150% reaches exactly
   one plate up at any column count. The 12px is the button's own -13px margin
   less its border; it undershoots by a pixel deliberately, because a dead
   hairline at the top of a plate is invisible where an overlay reaching into
   the row above would steal that card's clicks. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button {
  position:relative;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button::after {
  content:''; position:absolute; left:0; right:0; top:0; bottom:0; z-index:2;
  margin-top:calc(-150% + 12px);
}
/* A verdict band sits between the plate and the strip, so a toned card
   reaches 5px further. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark.toned) div[data-testid="stButton"] button::after { margin-top:calc(-150% + 7px); }
/* With the plate covered, .poster-card:hover can no longer fire -- the pointer
   is over the button. Drive both halves off the button so the card and its
   strip light up and lift together instead of one at a time. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark):has(div[data-testid="stButton"] button:hover) .poster-card {
  border-color:var(--mint); transform:translateY(-2px);
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button:hover {
  transform:translateY(-2px);
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button p {
  margin:0 !important; font-size:.76rem !important; font-weight:600 !important;
  line-height:1.3 !important; color:var(--tape) !important;
}
/* The caption line keeps the mono treatment the poster label used. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button p + p {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.68rem !important;
  font-weight:400 !important; color:var(--mint) !important;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-cardmark) div[data-testid="stButton"] button:hover p {
  color:var(--mint) !important;
}

/* Return bar */
.rw-dt-bar { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:6px; }
.rw-dt-count {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  letter-spacing:.12em; text-transform:uppercase; color:var(--txt-3);
}

/* Hero */
.rw-dt-hero {
  position:relative; overflow:hidden; border:1px solid var(--line); border-radius:8px;
  background:linear-gradient(180deg,#14231D 0%,#0B0D0C 100%);
  display:grid; grid-template-columns:186px 1fr; gap:26px; padding:24px 26px;
}
.rw-dt-hero .rw-watermark { right:-52px; top:-70px; width:266px; height:266px; }
.rw-dt-poster {
  position:relative; width:186px; border-radius:5px; overflow:hidden;
  border:1px solid var(--line-2); box-shadow:5px 5px 0 rgba(0,0,0,.5); align-self:start;
}
.rw-dt-poster img { width:100%; display:block; }
.rw-dt-poster .poster-plate { height:275px; }
.rw-dt-id { position:relative; min-width:0; }
.rw-dt-id h1 {
  font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:clamp(26px,3.4vw,40px); line-height:1.04; letter-spacing:-.025em;
  color:var(--tape); margin:0; text-wrap:balance;
}
.rw-dt-id h1 span { color:var(--txt-3); font-size:.62em; letter-spacing:-.01em; }
.rw-dt-cred {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11.5px;
  letter-spacing:.06em; color:var(--txt-2); margin:12px 0 0;
}
.rw-dt-cred i { color:var(--txt-3); font-style:normal; padding:0 7px; }

/* Stat rail — the metric tile, sized down to sit inside the hero */
.rw-dt-rail {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
  gap:9px; margin-top:20px;
}
.rw-dt-stat {
  background:rgba(11,13,12,.55); border:1px solid var(--line); border-radius:6px;
  padding:10px 12px 11px; position:relative; overflow:hidden;
}
.rw-dt-stat::after {
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--mint-dim);
}
.rw-dt-stat.is-coral::after { background:var(--coral); }
.rw-dt-stat .k {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:8.5px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3); display:block;
}
.rw-dt-stat .v {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:21px; line-height:1.15;
  color:var(--mint); font-variant-numeric:tabular-nums; letter-spacing:-.02em;
  margin-top:5px; display:block;
}
.rw-dt-stat.is-coral .v { color:var(--coral); }
.rw-dt-stat .u { font-size:.55em; color:var(--txt-3); letter-spacing:0; }
.rw-dt-stat .miss {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:14px;
  color:var(--txt-3); margin-top:9px; display:block; letter-spacing:.1em;
}

/* Episode spine */
.rw-dt-spine { position:relative; margin-top:6px; padding-left:26px; }
.rw-dt-spine::before {
  content:""; position:absolute; left:6px; top:14px; bottom:14px; width:1px;
  background:linear-gradient(180deg,var(--mint-dim),var(--line));
}
.rw-dt-ep { position:relative; margin-bottom:11px; }
.rw-dt-ep::before {
  content:""; position:absolute; left:-24px; top:19px; width:9px; height:9px;
  border-radius:50%; background:var(--ink); border:2px solid var(--mint-deep);
}
.rw-dt-ep.is-revisit::before { border-color:var(--coral); }
.rw-dt-epcard {
  background:var(--ink-2); border:1px solid var(--line); border-radius:6px;
  padding:14px 17px 15px;
}
.rw-dt-ephead { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
.rw-dt-epno {
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:19px; color:var(--tape);
  font-variant-numeric:tabular-nums; letter-spacing:-.02em;
}
.rw-dt-epno span { color:var(--txt-3); font-size:.62em; }
.rw-dt-epdate {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
  letter-spacing:.07em; color:var(--txt-2);
}
.rw-dt-epflags { margin-left:auto; display:flex; gap:5px; flex-wrap:wrap; }
.rw-dt-eproom {
  display:flex; flex-wrap:wrap; align-items:center; gap:7px; margin-top:11px;
  font-size:13px; color:var(--tape-2);
}
.rw-dt-eproom .lbl {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3); margin-right:2px;
}
.rw-dt-person {
  display:inline-flex; align-items:center; gap:6px; padding:3px 9px 3px 5px;
  background:var(--ink-3); border:1px solid var(--line); border-radius:20px; font-size:12.5px;
}
.rw-dt-person i {
  width:17px; height:17px; border-radius:50%; background:var(--mint-dim); color:var(--ink);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:8.5px; font-style:normal;
  font-weight:600; display:inline-flex; align-items:center; justify-content:center;
}
.rw-dt-person.is-host i { background:var(--mint); }
.rw-dt-epnote {
  margin-top:11px; padding:9px 13px; background:var(--ink-3);
  border-left:2px solid #C98500; font-size:12.5px; color:var(--tape-2); line-height:1.55;
}
.rw-dt-epnote .lbl {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3);
  display:block; margin-bottom:3px;
}
.rw-dt-gap {
  display:flex; align-items:center; gap:9px; margin:0 0 11px -24px; padding-left:24px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--txt-3);
}
.rw-dt-gap::before { content:"\\2304"; color:var(--mint-dim); font-size:13px; line-height:1; }

/* Cruise / Hanks verdict badges — the pairing established in section 6 */
.badge-cruise { background:rgba(201,133,0,.16); border-color:rgba(201,133,0,.45); color:#E8A21F; }
.badge-hanks  { background:rgba(74,143,224,.16); border-color:rgba(74,143,224,.45); color:#7BB0EE; }

/* Lower half */
.rw-dt-panel {
  background:var(--ink-2); border:1px solid var(--line); border-radius:7px;
  padding:17px 19px 19px; margin-bottom:16px;
}
.rw-dt-loose {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--txt-3) !important;
  margin:4px 0 10px; font-weight:500 !important;
}
.rw-dt-panel > h4 {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--txt-3);
  margin:0 0 12px; font-weight:500;
}
.rw-dt-logline { font-size:15px; line-height:1.62; color:var(--tape); margin:0; max-width:66ch; }
.rw-dt-kw { display:flex; flex-wrap:wrap; gap:5px; }
.rw-dt-kw span {
  padding:2px 8px; border-radius:3px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:10px; letter-spacing:.05em; background:rgba(13,98,73,.24);
  border:1px solid rgba(23,168,124,.28); color:#79E9C2;
}
.rw-dt-cast { display:flex; flex-wrap:wrap; gap:6px; }
.rw-dt-cast span {
  padding:4px 10px; background:var(--ink-3); border:1px solid var(--line);
  border-radius:20px; font-size:12.5px; color:var(--tape-2);
}
.rw-dt-cast span b {
  color:var(--txt-3); font-weight:500;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px; margin-left:4px;
}

/* Provenance footer */
.rw-dt-prov {
  margin-top:4px; padding:13px 17px; background:var(--ink-2);
  border:1px solid var(--line); border-radius:7px;
  display:flex; flex-wrap:wrap; gap:9px 28px; align-items:center;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.1em; text-transform:uppercase; color:var(--txt-3);
}
.rw-dt-prov b { color:var(--txt-2); font-weight:500; }
.rw-dt-prov a { color:var(--mint-deep); text-decoration:none; border-bottom:1px solid rgba(23,168,124,.35); }
.rw-dt-prov a:hover { color:var(--mint); }
.rw-dt-prov .conf { color:var(--mint); }

@media (max-width:860px) {
  .rw-dt-hero { grid-template-columns:1fr; }
  .rw-dt-poster { width:150px; }
}

/* ── Keyword index ────────────────────────────────────────────────────── */
/* The chip is the shared unit of both keyword surfaces. It always carries its
   reach, because that number is what tells you whether following it is worth
   the click — the job a consolidated vocabulary would otherwise have to do. */
.rw-kw-field { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.rw-kw-chip {
  display:inline-flex; align-items:baseline; gap:7px;
  padding:5px 11px; border-radius:4px;
  font-size:13px; line-height:1.2; color:var(--tape-2);
  background:var(--ink-3); border:1px solid var(--line);
}
.rw-kw-chip b {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  font-weight:500; color:var(--txt-3); font-variant-numeric:tabular-nums;
}
.rw-kw-chip.b1 { background:rgba(43,232,160,.15); border-color:rgba(43,232,160,.45); color:var(--tape); font-size:15px; font-weight:600; }
.rw-kw-chip.b2 { background:rgba(28,189,140,.12); border-color:rgba(28,189,140,.36); color:var(--tape); font-size:14px; font-weight:600; }
.rw-kw-chip.b3 { background:rgba(23,168,124,.09); border-color:rgba(23,168,124,.28); color:var(--tape-2); font-size:13.5px; }
.rw-kw-chip.b4 { background:rgba(13,98,73,.16); border-color:rgba(13,98,73,.42); }
.rw-kw-chip.b5 { background:var(--ink-3); border-color:var(--line); font-size:12.5px; color:var(--txt-2); }
.rw-kw-chip.is-here { background:var(--mint); border-color:var(--mint); color:var(--ink); font-weight:700; }
.rw-kw-chip.is-here b { color:rgba(11,13,12,.6); }
/* A keyword reaching only the film you are already on is still worth printing —
   it describes the film. It just must not look like a door. */
.rw-kw-chip.is-inert {
  background:transparent; border-style:dashed; border-color:var(--line-2);
  color:var(--txt-3); font-size:12.5px;
}
.rw-kw-chip.is-inert b { color:var(--txt-3); }

/* Clickable chips are buttons. Streamlit stacks block children vertically, so
   the marker's block is flipped to a wrapping row and its element containers
   are released from full width — that is what makes buttons read as a chip
   field rather than a column of bars. */
.rw-kwmark { display:none; }
/* Plain inline flow rather than a flex row: the block inherits flex:1 1 0 from
   Streamlit's own layout, and flipping its direction collapses it to zero width
   while the chips spill out one per line. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark) {
  display:block; width:100%; gap:0;
}
/* max-width rather than width: Streamlit's own rule sets the container to 100%
   and outranks a plain width:auto here, but capping it at the content width
   shrinks it to the chip regardless of who wins on width. */
/* Both widths carry !important. Streamlit sets the element container and the
   button wrapper to 100% from its own stylesheet and wins the cascade here;
   without overriding both, the chip re-inflates to the full row and every one
   lands on its own line. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark)
  > div[data-testid="stElementContainer"] {
  display:inline-block; width:auto !important; vertical-align:top; margin:0 6px 6px 0;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark)
  div[data-testid="stButton"] { width:auto !important; }
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark) div[data-testid="stButton"] button {
  background:var(--ink-3); border:1px solid var(--line); border-radius:4px;
  padding:5px 11px; min-height:0; width:auto;
  font-size:13px; line-height:1.2; font-weight:500; color:var(--tape-2);
  white-space:nowrap; transition:border-color .15s, color .15s, background .15s;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark) div[data-testid="stButton"] button:hover {
  border-color:var(--mint); color:var(--mint); background:var(--ink-4);
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > .rw-kwmark) div[data-testid="stButton"] button p {
  font-size:13px !important; margin:0 !important; white-space:nowrap;
}

.rw-kw-legend {
  display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 12px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3);
}
.rw-kw-legend i { display:block; width:22px; height:9px; border-radius:2px; }
.rw-kw-legend .l1 { background:rgba(43,232,160,.55); }
.rw-kw-legend .l2 { background:rgba(28,189,140,.42); }
.rw-kw-legend .l3 { background:rgba(23,168,124,.3); }
.rw-kw-legend .l4 { background:rgba(13,98,73,.45); }
.rw-kw-legend .l5 { background:var(--line-2); }

/* The long tail, stated rather than hidden */
.rw-kw-tail {
  margin-top:16px; padding:12px 16px; background:var(--ink-3);
  border-left:2px solid var(--mint-dim); font-size:13px; color:var(--tape-2);
  line-height:1.6; max-width:78ch;
}
.rw-kw-tail b { color:var(--tape); }

.rw-kw-decades { display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:12px; }
.rw-kw-dec {
  background:var(--ink-2); border:1px solid var(--line); border-radius:7px;
  padding:13px 15px 14px; position:relative; overflow:hidden;
}
.rw-kw-dec::after { content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--mint-dim); }
.rw-kw-dec h5 {
  margin:0 0 2px; font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:19px; letter-spacing:-.02em; color:var(--tape);
}
.rw-kw-dec .n {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3);
  display:block; margin-bottom:10px;
}
.rw-kw-dec ol { margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:5px; }
.rw-kw-dec li { display:flex; align-items:baseline; gap:8px; font-size:12.5px; color:var(--tape-2); }
.rw-kw-dec li span { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rw-kw-dec li b {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px; font-weight:500;
  color:var(--mint-deep); font-variant-numeric:tabular-nums;
}

/* Keyword header */
.rw-kw-head {
  position:relative; overflow:hidden; border:1px solid var(--line); border-radius:8px;
  background:linear-gradient(180deg,#14231D 0%,#0B0D0C 100%); padding:24px 26px 22px;
}
.rw-kw-head .rw-watermark { right:-46px; top:-64px; width:250px; height:250px; }
.rw-kw-eyebrow {
  position:relative; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.18em; text-transform:uppercase; color:var(--txt-3); margin:0 0 8px;
}
.rw-kw-head h1 {
  position:relative; margin:0; font-family:'Archivo Black',Arial Black,sans-serif;
  font-weight:400; font-size:clamp(28px,4vw,44px); line-height:1.02;
  letter-spacing:-.03em; color:var(--tape); text-wrap:balance;
}
.rw-kw-rail {
  position:relative; display:grid; grid-template-columns:repeat(auto-fit,minmax(122px,1fr));
  gap:9px; margin-top:20px;
}

/* Decade signature. The bar sits in a track of definite height: a percentage
   set on the flex item itself resolves against the row and is then clamped by
   whatever space the labels leave, flattening the tallest bar. */
.rw-kw-bars { display:flex; align-items:flex-end; gap:10px; padding-top:6px; }
.rw-kw-bar { flex:1; display:flex; flex-direction:column; gap:6px; }
.rw-kw-bar .track { display:flex; align-items:flex-end; height:96px; }
.rw-kw-bar i { display:block; width:100%; background:var(--mint-deep); border-radius:2px 2px 0 0; }
.rw-kw-bar.is-peak i { background:var(--mint); }
.rw-kw-bar .v {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
  color:var(--tape-2); text-align:center; font-variant-numeric:tabular-nums;
}
.rw-kw-bar .d {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.1em; color:var(--txt-3); text-align:center; padding-top:5px;
  border-top:1px solid var(--line);
}
.rw-kw-bar.is-peak .d { color:var(--mint); }
.rw-kw-caption {
  margin:12px 0 0; font-size:13px; color:var(--txt-2); line-height:1.6; max-width:74ch;
}
.rw-kw-caption b { color:var(--tape-2); font-weight:600; }

.rw-kw-gridnote {
  display:flex; align-items:baseline; justify-content:space-between; gap:14px;
  flex-wrap:wrap; margin-bottom:4px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  letter-spacing:.12em; text-transform:uppercase; color:var(--txt-3);
}

/* ── Upcoming films ───────────────────────────────────────────────────── */
/* A requested film has none of the furniture an aired one does: no episode
   number, no room, no verdict. What it has is a reason someone wants it, so
   the reason is what the card is built around rather than a metadata strip
   with three empty slots. */
.rw-up-why {
  margin:6px 0 0; padding:9px 11px; background:var(--ink-2);
  border:1px solid var(--line); border-left:2px solid var(--mint-dim);
  border-radius:0 5px 5px 0; font-size:12.5px; line-height:1.5;
  color:var(--tape-2);
}
.rw-up-why .who {
  display:block; margin-top:6px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.11em; text-transform:uppercase; color:var(--txt-3);
}
.rw-up-why .who a { color:var(--mint-deep); text-decoration:none; }
.rw-up-why .who a:hover { color:var(--mint); }
.rw-up-tags { display:flex; flex-wrap:wrap; gap:5px; }
.rw-up-tag {
  padding:2px 8px; border-radius:3px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  letter-spacing:.05em; background:rgba(13,98,73,.24);
  border:1px solid rgba(23,168,124,.28); color:#79E9C2;
}
/* An unresolved row is not an error to be hidden. Two of them are TV series on
   a list of films and one has no year — all three are true things about the
   source, so the card prints and says which. */
.rw-up-unres {
  display:inline-block; margin-top:6px; padding:2px 8px; border-radius:3px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.1em; text-transform:uppercase;
  color:var(--txt-3); border:1px dashed var(--line-2);
}
/* The graduates. Coral, because it is the one thing on this page that has
   stopped being a request — the same colour the dossier gives a revisit. */
.rw-up-grad {
  display:flex; gap:13px; align-items:center; padding:11px 13px;
  background:var(--ink-2); border:1px solid var(--line);
  border-left:3px solid var(--coral); border-radius:0 6px 6px 0;
  margin-bottom:9px;
}
.rw-up-grad img { width:44px; height:66px; object-fit:cover; border-radius:3px; flex:none; }
.rw-up-grad .b { min-width:0; }
.rw-up-grad .t { display:block; font-weight:600; color:var(--tape); font-size:14px; }
.rw-up-grad .m {
  display:block; margin-top:3px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  letter-spacing:.1em; text-transform:uppercase; color:var(--txt-3);
}
.rw-up-grad .m b { color:var(--coral); font-weight:500; }
.rw-up-note {
  margin:10px 0 0; font-size:13px; color:var(--txt-2); line-height:1.6; max-width:74ch;
}
.rw-up-note b { color:var(--tape-2); font-weight:600; }

/* ── Overview ─────────────────────────────────────────────────────────── */
/* The regulars: one card per person, ranked by how often they were in the
   room across the host and guest columns together. There is no person image
   cache, so an initials disc stands in for a portrait. Bill Simmons is left
   out: he is on nine episodes in ten. */
/* Six fixed columns rather than auto-fit: the row is exactly six people, and
   an auto-fit grid dropped the sixth onto a line of his own at 1400px. */
.rw-reg-row { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:9px; }
@media (max-width:1100px) { .rw-reg-row { grid-template-columns:repeat(3,minmax(0,1fr)); } }
.rw-reg {
  display:flex; gap:9px; align-items:center; padding:10px 11px; min-width:0;
  background:var(--ink-2); border:1px solid var(--line); border-radius:7px;
}
.rw-reg .d {
  flex:none; width:34px; height:34px; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  background:var(--ink-4); border:1px solid var(--line-2);
  font-family:'Archivo Black',Arial Black,sans-serif; font-size:12px;
  letter-spacing:.02em; color:var(--mint);
}
.rw-reg .b { min-width:0; flex:1; }
.rw-reg .n { display:block; font-weight:600; color:var(--tape); font-size:13px; line-height:1.2; }
.rw-reg .m {
  display:block; margin-top:2px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:9px; letter-spacing:.1em; text-transform:uppercase; color:var(--txt-3);
}
.rw-reg .m b { color:var(--mint); font-weight:500; }
.rw-reg .bar { height:3px; margin-top:7px; border-radius:2px; overflow:hidden; background:var(--ink-4); }
.rw-reg .bar i { display:block; height:100%; background:var(--mint-deep); }

/* ── Hosts & guests ───────────────────────────────────────────────────── */
/* One row per regular: name and episode count, then the leans that survived
   the correction as badges. A row with none says so rather than sitting
   empty -- "no detectable lean" is a finding, not a gap. */
.rw-lean {
  display:flex; gap:16px; align-items:baseline; padding:9px 0;
  border-top:1px solid var(--line);
}
.rw-lean:first-child { border-top:0; }
.rw-lean .n { width:180px; flex:none; font-weight:600; color:var(--tape); font-size:13.5px; }
.rw-lean .n span {
  display:block; margin-top:2px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:9px; font-weight:400; letter-spacing:.1em; text-transform:uppercase;
  color:var(--txt-3);
}
.rw-lean .l { flex:1; min-width:0; display:flex; flex-wrap:wrap; align-items:center; }
.rw-lean-none { font-size:12.5px; color:var(--txt-3); }

/* ── Stale-data banner ────────────────────────────────────────────────── */
/* Coral, the colour the app already uses for "look at this" (revisits, the
   episode tile), and set above every page including an open dossier. */
.rw-stale {
  margin:0 0 16px; padding:10px 14px; border-radius:6px; font-size:13px;
  line-height:1.55; color:var(--tape-2);
  background:rgba(226,98,79,.12); border:1px solid rgba(226,98,79,.42);
}
.rw-stale b { color:var(--tape); font-weight:600; }
.rw-stale code {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12px;
  color:var(--coral); background:rgba(0,0,0,.25); padding:1px 5px; border-radius:3px;
}

/* A note that sits under a block or beside a control on the same row. */
.rw-ov-note { margin:6px 0 0; font-size:13px; color:var(--txt-2); line-height:1.6; max-width:74ch; }
.rw-ov-note b { color:var(--tape-2); font-weight:600; }

/* The cadence panel's reading of the chart beside it. */
.rw-ov-read { margin:0; padding:0; list-style:none; }
.rw-ov-read li {
  padding:9px 0; border-top:1px solid var(--line); font-size:12.5px;
  color:var(--txt-2); line-height:1.5;
}
.rw-ov-read li:first-child { border-top:0; padding-top:0; }
.rw-ov-read b {
  display:block; font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:17px; color:var(--mint); letter-spacing:-.02em; font-variant-numeric:tabular-nums;
}

/* Section doors. Each card fronts one section of the rail and carries one
   number and one sentence, which is what the rail's bare labels cannot. The
   card is markup; the button beneath is the real control, flattened onto the
   card exactly the way film_card's title strip is, and scoped by the same
   marker trick so no other button picks up the styling. */
.rw-doormark { display:none; }
.rw-door {
  position:relative; overflow:hidden; min-height:124px;
  padding:13px 15px 8px 17px; margin-bottom:0;
  background:var(--ink-2); border:1px solid var(--line); border-bottom:0;
  border-radius:7px 7px 0 0;
}
.rw-door::after {
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--mint-dim);
}
.rw-door .k {
  display:block; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:8.5px;
  letter-spacing:.13em; text-transform:uppercase; color:var(--txt-3);
}
.rw-door .v {
  display:block; margin-top:6px; font-family:'Archivo Black',Arial Black,sans-serif;
  font-weight:400; font-size:22px; line-height:1.1; color:var(--mint);
  letter-spacing:-.02em; font-variant-numeric:tabular-nums;
}
.rw-door .v small {
  font-size:.5em; color:var(--txt-3); letter-spacing:0; margin-left:4px;
  font-family:'IBM Plex Mono',ui-monospace,monospace;
}
.rw-door .t { display:block; margin-top:4px; font-weight:600; font-size:13.5px; color:var(--tape); }
.rw-door p { margin:4px 0 0; font-size:12px; line-height:1.5; color:var(--txt-2); }
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-doormark) div[data-testid="stButton"] button {
  background:var(--ink-2); border:1px solid var(--line); border-top:0;
  border-radius:0 0 7px 7px; margin-top:-13px; margin-bottom:12px;
  padding:6px 15px 9px 17px; min-height:0; display:flex; justify-content:flex-start;
  transition:border-color .15s, background .15s;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-doormark) div[data-testid="stButton"] button p {
  margin:0 !important; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:10px !important; letter-spacing:.12em; text-transform:uppercase;
  color:var(--mint-deep) !important; font-weight:500 !important;
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-doormark) div[data-testid="stButton"] button:hover {
  border-color:var(--mint); background:var(--ink-4);
}
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-doormark) div[data-testid="stButton"] button:hover p {
  color:var(--mint) !important;
}
/* The whole card lights when the strip is hovered, not only the strip. */
div[data-testid="stVerticalBlock"]:has(> div > div > div > div > .rw-doormark):has(div[data-testid="stButton"] button:hover) .rw-door {
  border-color:var(--mint);
}

/* Random spotlight, set in the dossier's panel grammar. */
.rw-spot { display:grid; grid-template-columns:150px 1fr; gap:20px; align-items:start; }
.rw-spot img { width:150px; border-radius:5px; display:block; border:1px solid var(--line); }
.rw-spot .h {
  margin:0; font-family:'Archivo Black',Arial Black,sans-serif; font-weight:400;
  font-size:21px; line-height:1.15; letter-spacing:-.02em; color:var(--tape);
}
.rw-spot .h small { color:var(--txt-3); font-size:.7em; margin-left:6px; letter-spacing:0; }
.rw-spot .m {
  display:block; margin-top:7px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:9.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--txt-3);
}
.rw-spot .m b { color:var(--mint); font-weight:500; }
.rw-spot p { margin:11px 0 0; font-size:13.5px; line-height:1.62; color:var(--txt-2); max-width:66ch; }
@media (max-width:860px) { .rw-spot { grid-template-columns:1fr; } .rw-spot img { width:120px; } }
</style>
""", unsafe_allow_html=True)

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data(db_stamp=None):
    # db_stamp is never read: it is part of the cache key, so a rebuilt
    # database is a cache miss. Callers pass DB_STAMP.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Core movies
    movies = pd.read_sql("""
        SELECT movie_id, tmdb_id, title, year,
               directors, genres, keywords, runtime_minutes,
               rating_tmdb, popularity_tmdb, cast_names,
               budget_tmdb, revenue_tmdb,
               plot_summary, plot_summary_wiki, plot_summary_wiki_words,
               poster_url_tmdb,
               wikipedia_url, wikidata_qid, enriched_at,
               first_episode_date, last_episode_date,
               total_episodes_featured, revisit_count,
               canonical_key_confidence
        FROM curated_movies
        ORDER BY year
    """, conn, parse_dates=["first_episode_date", "last_episode_date"])

    # `revisited` is curated ground truth from the source sheet, carried through
    # raw -> staging -> curated. Prefer it over the derived revisit_count, which
    # is only a cross-check. Selected separately so a database built before the
    # column existed still loads, falling back to the derived value.
    movie_cols = {r[1] for r in conn.execute("PRAGMA table_info(curated_movies)")}
    if "revisited_flag" in movie_cols:
        flags = pd.read_sql(
            "SELECT movie_id, revisited_flag FROM curated_movies", conn)
        movies = movies.merge(flags, on="movie_id", how="left")
        # A film the sheet never flagged falls back to the derived count.
        movies["revisited_flag"] = (
            movies["revisited_flag"]
            .fillna((movies["revisit_count"] > 0).astype(int))
            .astype(int)
        )
    else:
        movies["revisited_flag"] = (movies["revisit_count"] > 0).astype(int)

    # Episodes. raw_episodes_current pins to the newest ingest snapshot — the
    # raw table keeps one full copy per run — and exposes episode_date with the
    # source sheet's M/D/YYYY values normalised to ISO. Both traps are documented
    # in sql/schemas/raw_zone.sql; read the view, not the table.
    episodes = pd.read_sql("""
        SELECT raw_episode_id, ep, title, episode_date AS date,
               host, guest1, guest2, guest3, guest4,
               ebert, tomatoes_score, cruise_hanks,
               rating, ebert_stars, notes
        FROM raw_episodes_current
        WHERE is_film = 1
        ORDER BY episode_date
    """, conn, parse_dates=["date"])

    # Canary: the view should leave nothing unparseable, but a new date format
    # appearing upstream must not silently vanish from the time series again.
    unparsed = int(episodes["date"].isna().sum())
    if unparsed:
        st.warning(
            f"{unparsed} episode dates could not be parsed and are excluded "
            "from the time-based charts."
        )

    # Episode-movie links (for join). guest4 and notes are carried for the film
    # dossier, which shows the full room and the sheet's episode annotations.
    # raw_episode_id is the only per-airing key: the sheet reuses an episode
    # number when a film is revisited, so Hosts & Guests counts rooms by this.
    links = pd.read_sql("""
        SELECT re.raw_episode_id,
               cem.movie_id, cem.episode_number, cem.episode_date,
               cem.is_revisit, cem.revisit_sequence, cem.revisit_type,
               re.host, re.guest1, re.guest2, re.guest3, re.guest4,
               re.ebert, re.tomatoes_score, re.cruise_hanks,
               re.rating, re.ebert_stars, re.notes
        FROM curated_episode_movies cem
        JOIN staging_episodes se ON se.staging_episode_id = cem.staging_episode_id
        JOIN raw_episodes re ON re.raw_episode_id = se.raw_episode_id
    """, conn, parse_dates=["episode_date"])

    # CMU box office, kept only as a cross-check against TMDB on the provenance
    # side. It is NOT what the app charts: CMU's Freebase snapshot froze in
    # 2012, so its coverage runs ~92% before 2010 and 0% after 2019, and a
    # decade trend drawn from it measures the snapshot date rather than the
    # films. TMDB covers 447 of 454 evenly across every decade. Where both know
    # a film they agree (median ratio 1.000, 341 of 376 within 10%); the
    # outliers are CMU recording a domestic gross against TMDB's worldwide one.
    box_office = pd.read_sql(
        "SELECT movie_id, box_office_revenue FROM v_movie_cmu", conn)

    # Cruise vs. Hanks verdicts. Episode-grained -- the verdict belongs to the
    # episode, not the film, so a revisit can carry a different verdict. The view
    # joins the film on episode_number rather than raw_episode_id; see the comment
    # block on v_cruise_hanks in sql/schemas/curated_zone.sql for why the id path
    # silently returns zero rows.
    ch = pd.read_sql("""
        SELECT episode_number, episode_date, verdict,
               host, guest1, guest2, guest3, guest4,
               tomatoes_score, ebert_stars,
               movie_id, movie_title, movie_year, movie_decade,
               genres, directors, runtime_minutes, rating_tmdb, poster_url_tmdb,
               is_revisit
        FROM v_cruise_hanks
        ORDER BY episode_number
    """, conn, parse_dates=["episode_date"])

    conn.close()

    # Parse JSON columns
    for col in ["directors", "genres", "keywords", "cast_names"]:
        movies[col] = movies[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )

    # Derive director_primary / genre_primary
    movies["director_primary"] = movies["directors"].apply(
        lambda x: x[0] if x else "Unknown"
    )
    movies["genre_list"] = movies["genres"]  # alias
    movies["genre_primary"] = movies["genres"].apply(
        lambda x: x[0] if x else "Unknown"
    )

    # Alphabetical sort key: 'The Blind Side' -> 'Blind Side, The'. Derived here
    # rather than at the point of sorting so every frame downstream of movies_df
    # files a film in the same place.
    movies["sort_title"] = movies["title"].apply(sort_title)

    # Decade
    movies["decade"] = (movies["year"] // 10 * 10).astype("Int64")

    # Box office joins one-to-one; films missing from CMU keep NaN.
    movies = movies.merge(
        box_office.drop_duplicates("movie_id"), on="movie_id", how="left")

    # Money, in CPI_BASE_YEAR dollars. Derived once here rather than per chart:
    # every user-facing figure has to be the adjusted one, and a single
    # unadjusted series slipping into a decade comparison is exactly the bug
    # that makes inflation look like a change in taste.
    movies["revenue_real"] = [
        real_usd(r, y) for r, y in zip(movies["revenue_tmdb"], movies["year"])]
    movies["budget_real"] = [
        real_usd(b, y) for b, y in zip(movies["budget_tmdb"], movies["year"])]
    # The ratio is scale-free, so it takes the nominal pair — adjusting both
    # sides by the same year's CPI cancels out and only adds rounding.
    movies["multiple"] = [
        multiple(r, b)
        for r, b in zip(movies["revenue_tmdb"], movies["budget_tmdb"])]
    # A film still in release has neither a settled gross nor, often, a real
    # budget: TMDB carries a $750K placeholder for a 2026 title that has taken
    # $506M. Flagged rather than dropped, and kept out of the leaderboards.
    movies["money_provisional"] = movies["year"] >= CPI_PROVISIONAL_FROM

    # Parse numeric ratings in episodes
    episodes["tomatoes_num"] = pd.to_numeric(
        episodes["tomatoes_score"], errors="coerce"
    )
    episodes["ebert_num"] = pd.to_numeric(
        episodes["ebert_stars"], errors="coerce"
    )
    episodes["rating_num"] = pd.to_numeric(
        episodes["rating"], errors="coerce"
    )

    # Same for links
    links["tomatoes_num"] = pd.to_numeric(links["tomatoes_score"], errors="coerce")
    links["ebert_num"] = pd.to_numeric(links["ebert_stars"], errors="coerce")
    links["rating_num"] = pd.to_numeric(links["rating"], errors="coerce")

    # Merge movies + links for enriched table
    merged = links.merge(
        movies[[
            "movie_id", "title", "year", "decade", "directors",
            "director_primary", "genres", "genre_primary", "runtime_minutes",
            "rating_tmdb", "cast_names", "poster_url_tmdb",
            "total_episodes_featured", "revisit_count"
        ]],
        on="movie_id", how="left"
    )

    # Same JSON columns on the Cruise/Hanks frame, plus numeric ratings.
    for col in ["directors", "genres"]:
        ch[col] = ch[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )
    ch["tomatoes_num"] = pd.to_numeric(ch["tomatoes_score"], errors="coerce")
    ch["ebert_num"] = pd.to_numeric(ch["ebert_stars"], errors="coerce")

    # Names are normalised once, here, so every section that reads the room --
    # the dossier, the overview, Cruise vs. Hanks, Hosts & Guests -- counts
    # the same people. The sheet is the source of truth and writes "Mallory
    # Rubin*" on one episode; see person_name().
    for frame in (episodes, links, merged, ch):
        for chair in ROOM:
            frame[chair] = frame[chair].map(person_name)

    return movies, episodes, links, merged, ch


movies_df, episodes_df, links_df, merged_df, ch_df = load_data(DB_STAMP)


@st.cache_data(ttl=300)
def load_people(db_stamp=None):
    """The people dimension: one row per credited person, with their gender.

    Cached separately from load_data() for the same reason load_upcoming() is:
    a database built before 09_enrich_metadata collected person ids has no
    curated_people table, and folding this query into load_data() would take
    every section down with it rather than just the gender split. An empty
    frame degrades the Actors section to the ungendered view it had before.
    """
    if not DB_PATH.exists():
        return pd.DataFrame(columns=["name", "gender"])

    conn = sqlite3.connect(DB_PATH)
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "curated_people" not in have:
        conn.close()
        return pd.DataFrame(columns=["name", "gender"])
    people = pd.read_sql(
        "SELECT name, gender FROM curated_people WHERE name IS NOT NULL", conn)
    conn.close()
    return people


# The genders the app charts, in the order it charts them, plus their labels.
# 'unknown' is a real category and is never folded into either of the other
# two: TMDB leaves gender unset on about 1% of billed credits, and quietly
# assigning those would overstate whichever side received them.
GENDERS = ("M", "F", "NB", "unknown")
GENDER_LABEL = {"M": "Men", "F": "Women", "NB": "Non-binary",
                "unknown": "Not recorded"}


def gender_from_people(people):
    """name -> gender, for the names the app groups actor statistics by.

    Keyed on name rather than on tmdb_person_id because every actor statistic
    in the app groups by name -- one bar is one name. Where two different
    people share a name and TMDB records different genders for them, that bar
    is genuinely two people and the honest answer is 'unknown', not whichever
    row the lookup reached first. curated_movies.cast_ids exists so a future
    person-grained version of these panels can drop the name key entirely.
    """
    if people.empty:
        return {}
    rows = people.copy()
    rows["gender"] = rows["gender"].fillna("unknown")
    agreed = rows.groupby("name")["gender"].nunique()
    first = rows.drop_duplicates("name").set_index("name")["gender"]
    return {name: (first[name] if agreed[name] == 1 else "unknown")
            for name in agreed.index}


GENDER_MAP = gender_from_people(load_people(DB_STAMP))


@st.cache_data(ttl=300)
def load_upcoming(db_stamp=None):
    """Films listeners have put forward for future episodes.

    Cached separately from load_data() rather than folded into it, for two
    reasons. It is a genuinely independent source — a different file, its own
    raw and curated tables, nothing joined to an episode — and a database built
    before step 13 existed has none of those tables. Returning empty frames
    there keeps every other section rendering; adding the query to load_data()
    would take the whole app down with it.

    Returns (pending, graduated). `pending` is the films still waiting: the
    v_upcoming_pending view already excludes anything that has become a real
    episode, so no caller has to remember to filter.
    """
    empty = (pd.DataFrame(), pd.DataFrame())
    if not DB_PATH.exists():
        return empty

    conn = sqlite3.connect(DB_PATH)
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    if not {"v_upcoming_pending", "v_upcoming_graduated"} <= have:
        conn.close()
        return empty

    pending = pd.read_sql("""
        SELECT upcoming_film_id, title, year_raw, year, contributor,
               mention_note, pitch_tags, tmdb_id, resolution_method,
               genres, keywords, runtime_minutes, cast_names, plot_summary,
               poster_url_tmdb, rating_tmdb, directors, source_row_number
        FROM v_upcoming_pending
        ORDER BY source_row_number
    """, conn)

    graduated = pd.read_sql("""
        SELECT upcoming_film_id, requested_title, year_raw, contributor,
               mention_note, pitch_tags, movie_id, movie_title, movie_year,
               poster_url_tmdb, first_episode_date, total_episodes_featured
        FROM v_upcoming_graduated
        ORDER BY first_episode_date
    """, conn, parse_dates=["first_episode_date"])
    conn.close()

    if pending.empty:
        return pending, graduated

    for col in ["genres", "keywords", "cast_names", "directors"]:
        pending[col] = pending[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )
    pending["tags"] = pending["pitch_tags"].apply(parse_tags)
    pending["sort_title"] = pending["title"].apply(sort_title)
    # year_raw is the source text and holds two ranges and a blank; `year` is
    # the parsed value and is NULL for exactly those rows. Decade is derived
    # from the parsed one, so an unresolvable row lands in "Unknown" rather
    # than in 1984 because its range happened to start there.
    pending["decade"] = (pending["year"] // 10 * 10).astype("Int64")
    pending["resolved"] = pending["resolution_method"] == "auto_tmdb"
    return pending, graduated


upcoming_df, graduated_df = load_upcoming(DB_STAMP)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Concentric rewind rings from the podcast artwork, reused as a watermark and as
# the poster fallback plate.
def rings_svg(css_class="rw-watermark", color=MINT):
    circles = "".join(
        f'<circle cx="50" cy="50" r="{r}"/>' for r in (9, 16, 23, 30, 37, 44)
    )
    return (
        f'<svg class="{css_class}" viewBox="0 0 100 100" aria-hidden="true">'
        f'<g fill="none" stroke="{color}" stroke-width="4">{circles}</g>'
        f'<path d="M55 3 L46 11 L55 19 M65 3 L56 11 L65 19" fill="none" '
        f'stroke="{color}" stroke-width="4.5" stroke-linecap="round" '
        f'stroke-linejoin="round"/></svg>'
    )


def masthead(title, subtitle=""):
    """Section title on the ink gradient, with the rewind rings as a watermark."""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="rw-masthead">{rings_svg()}<h1>{title}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


_tape_count = [0]


def tape(text):
    """Section heading set on a perforated tape strip; the tilt alternates."""
    _tape_count[0] += 1
    cls = "rw-tape alt" if _tape_count[0] % 2 == 0 else "rw-tape"
    st.markdown(
        f'<div class="rw-tape-row"><span class="{cls}">{text}</span></div>',
        unsafe_allow_html=True,
    )


def poster_art(url, title):
    """The plate itself — the TMDB thumbnail, or the rings fallback.

    It takes no height: .poster-img sizes it at 2:3 to its column's width, so a
    plate never carries a height of its own to disagree with the poster's shape.
    """
    if url:
        # Use w185 thumbnail for grids
        thumb = url.replace("/w500/", "/w185/") if "/w500/" in url else url
        return f'<img class="poster-img" src="{thumb}" alt="">'
    return (
        f'<div class="poster-plate poster-img">'
        f'{rings_svg("")}<b>{title}</b></div>'
    )


def poster_html(url, title, subtitle="", label=True, tone=""):
    """A poster card. With label=False the caller supplies the strip instead —
    film_card() puts a button there so the whole card opens the dossier.

    `tone` tags the card with one of the categorical colours ("cruise", "hanks",
    "tie") as a band under the art, so a grid stays scannable at a glance. The
    band is decoration only: the caller is expected to put the same value in
    words into the caption, so the tag never rests on colour vision alone.
    """
    if label:
        strip = f"""
      <div class="poster-label">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>"""
        style = ""
    else:
        # The marker lets the stylesheet find the button that follows this card
        # without restyling every button in the app. "toned" rides along because
        # the verdict band makes the card 5px taller than its plate, and the rule
        # that stretches the button's hit area over the plate has to reach past it.
        strip = f'<span class="rw-cardmark{" toned" if tone else ""}"></span>'
        style = ' style="border-bottom:0;border-radius:6px 6px 0 0;margin-bottom:0;"'
    rule = f'<div class="poster-rule {tone}"></div>' if tone else ""
    return f"""
    <div class="poster-card"{style}>
      {poster_art(url, title)}{rule}{strip}
    </div>"""


def film_card(movie, subtitle="", key="", tone=""):
    """A poster card that opens that film's dossier when clicked anywhere.

    Every poster grid goes through here, so click-through is uniform across
    sections and a film is always one click from its episodes. `tone` is passed
    to poster_html for grids that carry a verdict band.
    """
    st.markdown(
        poster_html(movie["poster_url_tmdb"], movie["title"],
                    label=False, tone=tone),
        unsafe_allow_html=True,
    )
    caption = f"{movie['title']}\n\n{subtitle}" if subtitle else movie["title"]
    if st.button(
        caption,
        key=f"btn_film_{key}_{movie['movie_id']}",
        use_container_width=True,
    ):
        open_dossier(movie["movie_id"])


# ── Film dossier ──────────────────────────────────────────────────────────────

def open_dossier(movie_id):
    """Select a film and mirror it into the URL so the view is linkable."""
    st.session_state.dt_movie = movie_id
    st.session_state.kw_word = None
    st.query_params.clear()
    st.query_params["movie"] = movie_id
    st.query_params["from"] = st.session_state.get("nav_section", DEFAULT_SECTION)
    st.rerun()


def open_keyword(keyword):
    """Select a keyword. Commas and spaces survive the round trip through the
    query string untouched, so the keyword needs no slug of its own."""
    st.session_state.kw_word = keyword
    st.session_state.dt_movie = None
    st.query_params.clear()
    st.query_params["keyword"] = keyword
    st.query_params["from"] = st.session_state.get("nav_section", DEFAULT_SECTION)
    st.rerun()


def open_prospect(upcoming_film_id):
    """Select an upcoming film. Addressed by ?upcoming= so it links like a film.

    A requested film gets its own overlay rather than the dossier: render_dossier
    is built around episodes, the room, Ebert stars and revisit chronology, none
    of which exist for a film that has not aired. Reusing it would mean a page
    that is mostly empty slots.
    """
    st.session_state.up_film = upcoming_film_id
    st.session_state.dt_movie = None
    st.session_state.kw_word = None
    st.query_params.clear()
    st.query_params["upcoming"] = upcoming_film_id
    st.rerun()


def close_dossier():
    """Return to the section that was on screen when an overlay opened."""
    st.session_state.dt_movie = None
    st.session_state.kw_word = None
    st.session_state.up_film = None
    st.query_params.clear()


def keep(widget, *args, key, **kwargs):
    """Render a widget whose value survives runs where it isn't drawn.

    Streamlit discards session_state for any widget it did not render, so a
    dossier covering a section would reset that section's selectors on the way
    back. A shadow copy is written after each render and read back only when the
    real key has gone missing — restoring it unconditionally would override the
    value arriving from the browser and pin the widget to its first setting.
    """
    shadow = f"_keep_{key}"
    if key not in st.session_state and shadow in st.session_state:
        st.session_state[key] = st.session_state[shadow]
    value = widget(*args, key=key, **kwargs)
    st.session_state[shadow] = value
    return value


def kept(key, default=None):
    """The value keep() last saw for `key`, on a run that does not draw it.

    Movie Explorer needs its sort order above the dossier gate -- the step
    arrows walk the sorted result set -- but draws the picker below it, so on a
    dossier run there is no widget to read. The shadow is the only surviving
    copy by then: Streamlit has already discarded the widget's own entry.
    """
    return st.session_state.get(key, st.session_state.get(f"_keep_{key}", default))


def render_dossier(movie_id, siblings=None):
    """The per-film detail view: identity, episodes, the film, provenance.

    `siblings` is the result set the film was clicked from, so the step arrows
    walk the same filtered list the grid was showing.
    """
    movie = movies_df[movies_df["movie_id"] == movie_id].iloc[0]
    origin = SECTION_LABEL[
        resolve_section(st.session_state.get("nav_section", DEFAULT_SECTION))]

    # ── Return bar ──
    siblings = list(siblings) if siblings is not None else []
    position = siblings.index(movie_id) if movie_id in siblings else None
    cols = st.columns([3, 0.5, 0.5, 4])
    if cols[0].button(f"← Back to {origin}", key="btn_dt_back", use_container_width=True):
        close_dossier()
        st.rerun()
    if position is not None:
        if cols[1].button("‹", key="btn_dt_prev", use_container_width=True,
                          disabled=position == 0):
            open_dossier(siblings[position - 1])
        if cols[2].button("›", key="btn_dt_next", use_container_width=True,
                          disabled=position == len(siblings) - 1):
            open_dossier(siblings[position + 1])
        cols[3].markdown(
            f'<div class="rw-dt-count">Film {position + 1} of {len(siblings)}</div>',
            unsafe_allow_html=True,
        )

    # ── Hero ──
    episodes = links_df[links_df["movie_id"] == movie_id].sort_values("episode_number")
    directors = " &middot; ".join(movie["directors"]) or "Director unknown"
    genres = " &middot; ".join(movie["genres"]) or "Ungenred"
    runtime = f"{int(movie['runtime_minutes'])} min" if pd.notna(movie["runtime_minutes"]) else "runtime unknown"

    chips = []
    if movie["revisited_flag"] == 1:
        revisits = max(int(movie["total_episodes_featured"]) - 1, 1)
        chips.append(f'<span class="badge badge-revisit">Revisited &times;{revisits}</span>')
    chips.append(
        f'<span class="badge badge-mint">{int(movie["total_episodes_featured"])} '
        f'episode{"s" if movie["total_episodes_featured"] != 1 else ""}</span>'
    )
    if pd.notna(movie["first_episode_date"]):
        span = movie["first_episode_date"].strftime("%b %Y")
        if pd.notna(movie["last_episode_date"]) and movie["last_episode_date"] != movie["first_episode_date"]:
            span += " &rarr; " + movie["last_episode_date"].strftime("%b %Y")
        chips.append(f'<span class="badge">{span}</span>')

    # RT and Ebert are film attributes in the source sheet — verified constant
    # across every one of the 26 multi-episode films — so they belong here in
    # the hero, not repeated onto each episode card as if they had moved.
    rt = episodes["tomatoes_num"].dropna()
    ebert = episodes["ebert_num"].dropna()
    # Box office is the adjusted figure, so the tile can be read against any
    # other film in the catalogue without doing CPI arithmetic in your head.
    box = movie.get("revenue_real")
    mult = movie.get("multiple")
    rail = "".join([
        stat_tile("TMDB", f"{movie['rating_tmdb']:.1f}" if pd.notna(movie["rating_tmdb"]) else None, "/10"),
        stat_tile("Rotten Tomatoes", f"{rt.iloc[0] * 100:.0f}" if len(rt) else None, "%"),
        stat_tile("Ebert", stars(ebert.iloc[0]) if len(ebert) else None),
        stat_tile(f"Box office ({CPI_BASE_YEAR}$)", money(box) if pd.notna(box) else None),
        stat_tile("Return", f"{mult:.1f}" if pd.notna(mult) else None, "&times;"),
        stat_tile("Episodes", int(movie["total_episodes_featured"]), coral=True),
    ])

    poster = movie["poster_url_tmdb"]
    plate = (
        f'<img src="{poster.replace("/w500/", "/w342/")}" alt="">' if poster
        else f'<div class="poster-plate">{rings_svg("")}<b>{movie["title"]}</b></div>'
    )
    st.markdown(html(f"""
    <div class="rw-dt-hero">
      {rings_svg()}
      <div class="rw-dt-poster">{plate}</div>
      <div class="rw-dt-id">
        <h1>{movie['title']} <span>{movie['year']}</span></h1>
        <p class="rw-dt-cred">{directors}<i>&middot;</i>{runtime}<i>&middot;</i>{genres}</p>
        <div class="chip-row">{''.join(chips)}</div>
        <div class="rw-dt-rail">{rail}</div>
      </div>
    </div>"""), unsafe_allow_html=True)

    # ── Episode spine ──
    tape(f"On the show &mdash; {len(episodes)} episode{'s' if len(episodes) != 1 else ''}")

    spine, previous_date = [], None
    for _, ep in episodes.iterrows():
        if previous_date is not None and pd.notna(ep["episode_date"]):
            gap = (ep["episode_date"] - previous_date).days
            if gap > 0:
                spine.append(f'<div class="rw-dt-gap">{human_gap(gap)}</div>')
        previous_date = ep["episode_date"]

        flags = []
        if ep["is_revisit"]:
            kind = (clean(ep["revisit_type"]) or "revisit").replace("_", " ")
            flags.append(
                f'<span class="badge badge-revisit">Revisit {int(ep["revisit_sequence"])} '
                f'&middot; {kind.replace(" revisit", "")}</span>'
            )
        else:
            flags.append('<span class="badge badge-mint">First watch</span>')
        # The verdict is genuinely episode-grained — it differs across episodes
        # for 8 of the 26 multi-episode films — so it rides on the card.
        verdict = clean(ep["cruise_hanks"])
        if verdict:
            tone = "cruise" if verdict.lower().startswith("cruise") else "hanks"
            flags.append(f'<span class="badge badge-{tone}">{verdict}</span>')

        room = []
        host = clean(ep["host"])
        if host:
            room.append(f'<span class="rw-dt-person is-host"><i>H</i>{host}</span>')
        for slot in ("guest1", "guest2", "guest3", "guest4"):
            guest = clean(ep.get(slot))
            if guest:
                room.append(f'<span class="rw-dt-person"><i>G</i>{guest}</span>')

        note = clean(ep["notes"])
        note_html = (
            f'<div class="rw-dt-epnote"><span class="lbl">Sheet note</span>{note}</div>'
            if note else ""
        )
        # %-d is glibc-only; build the unpadded day by hand so this runs on Windows.
        date = (
            f'{ep["episode_date"].day} {ep["episode_date"]:%b %Y}'
            if pd.notna(ep["episode_date"]) else "date unknown"
        )

        spine.append(html(f"""
        <div class="rw-dt-ep{' is-revisit' if ep['is_revisit'] else ''}">
          <div class="rw-dt-epcard">
            <div class="rw-dt-ephead">
              <span class="rw-dt-epno"><span>EP</span> {int(ep['episode_number']):03d}</span>
              <span class="rw-dt-epdate">{date}</span>
              <span class="rw-dt-epflags">{''.join(flags)}</span>
            </div>
            <div class="rw-dt-eproom"><span class="lbl">Room</span>{''.join(room)}</div>
            {note_html}
          </div>
        </div>"""))

    st.markdown(f'<div class="rw-dt-spine">{"".join(spine)}</div>', unsafe_allow_html=True)

    # Everyone in the room across this film's episodes, Bill aside, as a way
    # into the Hosts & Guests lookup. Buttons rather than links on the chips
    # above: a link reloads the session, and with it every filter behind the
    # dossier.
    seated = list(dict.fromkeys(
        name for _, ep in episodes.iterrows() for name in (ep[c] for c in ROOM)
        if isinstance(name, str) and name != ANCHOR))
    if seated:
        st.markdown(
            '<div class="rw-kw-gridnote"><span>Look up who was in the room</span></div>',
            unsafe_allow_html=True)
        per_row = 6
        for start in range(0, len(seated), per_row):
            cols = st.columns(per_row)
            for offset, (col, name) in enumerate(zip(cols, seated[start:start + per_row])):
                col.button(name, key=f"btn_dt_person_{start + offset}",
                           use_container_width=True, on_click=open_person, args=(name,))

    # ── The film ──
    tape("The film")
    left, right = st.columns([1.65, 1])

    with left:
        st.markdown(
            '<div class="rw-dt-panel"><h4>Plot</h4>'
            f'<p class="rw-dt-logline">'
            f'{plain(movie["plot_summary"]) or "No summary on file."}</p></div>',
            unsafe_allow_html=True,
        )
        synopsis = clean(movie["plot_summary_wiki"])
        if synopsis:
            words = movie["plot_summary_wiki_words"]
            with st.expander(f"Full Wikipedia synopsis — {int(words):,} words"):
                st.markdown(plain(synopsis))
        if movie["keywords"]:
            words = movie["keywords"]
            st.markdown('<h4 class="rw-dt-loose">Keywords</h4>', unsafe_allow_html=True)
            # Ranked by reach and capped, so the chips that go somewhere come
            # first. Unranked and uncapped, 31% of them would lead to a page
            # holding only this film; at eight it is 7%.
            keyword_row(words, key=f"film_{movie_id}", cap=8)
            if len(words) > 8:
                with st.expander(f"All {len(words)} keywords"):
                    keyword_row(words, key=f"filmall_{movie_id}")

    with right:
        if movie["cast_names"]:
            # How often each name turns up elsewhere on the show — the number is
            # the reason to click through, so it only shows when it is above one.
            billing = Counter()
            for names in movies_df["cast_names"]:
                for name in (names[:5] if isinstance(names, list) else []):
                    billing[name] += 1
            chips = "".join(
                f'<span>{name}'
                + (f" <b>{billing[name]}</b>" if billing.get(name, 0) > 1 else "")
                + "</span>"
                for name in movie["cast_names"][:10]
            )
            st.markdown(
                f'<div class="rw-dt-panel"><h4>Cast &mdash; top billed</h4>'
                f'<div class="rw-dt-cast">{chips}</div></div>',
                unsafe_allow_html=True,
            )

        director = movie["director_primary"]
        same_director = movies_df[
            (movies_df["director_primary"] == director)
            & (movies_df["movie_id"] != movie_id)
        ].sort_values("year")
        if len(same_director):
            st.markdown(f"##### Also on the show — {director}")
            shelf(same_director.head(4), key=f"dir_{movie_id}")

        # Films sharing a top-billed name, most-shared first.
        cast = set(movie["cast_names"][:5]) if movie["cast_names"] else set()
        if cast:
            overlap = movies_df[movies_df["movie_id"] != movie_id].copy()
            overlap["shared"] = overlap["cast_names"].apply(
                lambda names: len(cast & set(names[:5])) if isinstance(names, list) else 0
            )
            overlap = overlap[overlap["shared"] > 0].sort_values(
                ["shared", "year"], ascending=[False, True])
            if len(overlap):
                st.markdown("##### Shared cast")
                shelf(overlap.head(4), key=f"cast_{movie_id}")

    # ── Provenance ──
    facts = [f'Key confidence <span class="conf">{movie["canonical_key_confidence"]}</span>']
    if clean(movie["enriched_at"]):
        facts.append(f'Enriched <b>{str(movie["enriched_at"])[:10]}</b>')
    if pd.notna(movie["tmdb_id"]):
        facts.append(
            f'<a href="https://www.themoviedb.org/movie/{int(movie["tmdb_id"])}" '
            f'target="_blank">TMDB {int(movie["tmdb_id"])}</a>'
        )
    if clean(movie["wikipedia_url"]):
        facts.append(f'<a href="{movie["wikipedia_url"]}" target="_blank">Wikipedia</a>')
    if clean(movie["wikidata_qid"]):
        facts.append(
            f'<a href="https://www.wikidata.org/wiki/{movie["wikidata_qid"]}" '
            f'target="_blank">Wikidata {movie["wikidata_qid"]}</a>'
        )
    st.markdown(
        '<div class="rw-dt-prov">' + "".join(f"<span>{f}</span>" for f in facts) + "</div>",
        unsafe_allow_html=True,
    )


# ── Upcoming films ────────────────────────────────────────────────────────────

def why_html(row):
    """The reason a film is on the list, and who put it there.

    Every card leads with this rather than with metadata. A requested film has
    no episode, no room and no verdict, so the justification is the only thing
    on the card that is actually about this film rather than about the movie —
    and it is the thing a reader is here for.
    """
    note = clean(row.get("mention_note"))
    tags = row.get("tags") or []
    label, href = contributor_link(row.get("contributor"))

    if note:
        body = plain(note)
    elif tags:
        body = pitch_chips(tags)
    else:
        # Three rows carry neither. Saying so is better than an empty box.
        body = '<i style="color:var(--txt-3)">No reason recorded.</i>'

    who = ""
    if label:
        who = (f'<span class="who">Put forward by '
               f'<a href="{href}" target="_blank" rel="noopener">{label}</a></span>')
    return f'<div class="rw-up-why">{body}{who}</div>'


def prospect_card(row, key=""):
    """A poster whose strip opens that requested film's panel.

    Deliberately the same shape as film_card, so the grid reads as the same kind
    of object as every other poster grid in the app — the difference between a
    film that aired and a film that might is a matter of what the card says, not
    of how it is built.
    """
    st.markdown(
        poster_html(row["poster_url_tmdb"], row["title"], label=False),
        unsafe_allow_html=True,
    )
    # Same two-line caption film_card uses: the blank line is what makes the
    # year read as a subtitle rather than as part of the title.
    caption = "{}\n\n{}".format(row["title"], row["year_raw"] or "—")
    if st.button(
        caption,
        key=f"btn_up_{key}_{row['upcoming_film_id']}",
        use_container_width=True,
    ):
        open_prospect(row["upcoming_film_id"])


def render_prospect(upcoming_film_id):
    """The detail panel for one requested film.

    Half a dossier by design: identity, the pitch, and the film itself. There is
    no episode spine because there is no episode — that is the whole distinction
    this section exists to draw.
    """
    match = upcoming_df[upcoming_df["upcoming_film_id"] == upcoming_film_id]
    if match.empty:
        # The list is rebuilt every pipeline run, so a shared link can outlive
        # its row -- most likely because the film became a real episode.
        st.warning("That film is no longer on the upcoming list. It may have "
                   "become an episode.")
        if st.button("← Back to Upcoming Films", key="btn_up_back_missing"):
            close_dossier()
            st.rerun()
        return
    row = match.iloc[0]

    if st.button("← Back to Upcoming Films", key="btn_up_back"):
        close_dossier()
        st.rerun()

    directors = " · ".join(row["directors"]) if row["directors"] else None
    genres = " · ".join(row["genres"]) if row["genres"] else None
    cred = " <i>/</i> ".join(x for x in (directors, genres) if x)

    rail = [stat_tile("Year", row["year_raw"] or None)]
    rail.append(stat_tile("Runtime", int(row["runtime_minutes"]) if pd.notna(
        row["runtime_minutes"]) else None, " min"))
    rail.append(stat_tile("TMDB", f"{row['rating_tmdb']:.1f}" if pd.notna(
        row["rating_tmdb"]) else None, "/10"))
    rail.append(stat_tile("Status", "Requested", coral=True))

    st.markdown(html(f"""
    <div class="rw-dt-hero">
      {rings_svg()}
      <div class="rw-dt-poster">
        {poster_art(row["poster_url_tmdb"], row["title"])}
      </div>
      <div class="rw-dt-id">
        <p class="rw-dt-loose">Upcoming &middot; not yet an episode</p>
        <h1>{row["title"]} <span>{row["year_raw"] or ""}</span></h1>
        <div class="rw-dt-cred">{cred}</div>
        <div class="rw-dt-rail">{"".join(rail)}</div>
      </div>
    </div>"""), unsafe_allow_html=True)

    if not row["resolved"]:
        st.markdown(
            f'<div class="rw-up-unres">Unmatched &mdash; '
            f'{RESOLUTION_NOTE.get(row["resolution_method"], "not matched")}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="rw-dt-panel"><h4>Why it is on the list</h4>'
                + why_html(row) + "</div>", unsafe_allow_html=True)

    if row["tags"] and clean(row.get("mention_note")):
        # Both populated is rare -- the source columns are alternatives -- but
        # when it happens the tags are additional, not a duplicate of the note.
        st.markdown('<div class="rw-dt-panel"><h4>Pitched as</h4>'
                    + pitch_chips(row["tags"]) + "</div>", unsafe_allow_html=True)

    if clean(row.get("plot_summary")):
        st.markdown(
            '<div class="rw-dt-panel"><h4>The film</h4>'
            f'<p class="rw-dt-logline">{plain(row["plot_summary"])}</p></div>',
            unsafe_allow_html=True,
        )

    if row["cast_names"]:
        cast = "".join(f"<span>{name}</span>" for name in row["cast_names"][:10])
        st.markdown(
            '<div class="rw-dt-panel"><h4>Cast</h4>'
            f'<div class="rw-dt-cast">{cast}</div></div>',
            unsafe_allow_html=True,
        )

    tmdb_link = (f'<a href="https://www.themoviedb.org/movie/{int(row["tmdb_id"])}" '
                 f'target="_blank" rel="noopener">TMDB</a>'
                 if pd.notna(row["tmdb_id"]) else "<b>no TMDB match</b>")
    st.markdown(
        f'<div class="rw-dt-prov"><span>Source <b>data/upcoming.csv</b></span>'
        f'<span>Match <b>{row["resolution_method"]}</b></span>'
        f'<span>{tmdb_link}</span></div>',
        unsafe_allow_html=True,
    )


def shelf(films, key):
    """A short row of clickable posters, used for the dossier's related films.

    Always four columns, however many films there are. A card takes its
    column's width, so a column per film made a one-film shelf a single poster
    the width of the whole panel.
    """
    cols = st.columns(4)
    for col, (_, film) in zip(cols, films.iterrows()):
        with col:
            film_card(film, str(film["year"]), key=key)


# ── Keyword index ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def keyword_index():
    """keyword -> the movie_ids carrying it, built once for the whole session.

    7,734 pairs. It also supplies the reach count behind every chip, so ranking
    a film's keywords costs nothing at render time.
    """
    index = {}
    for movie_id, keywords in zip(movies_df["movie_id"], movies_df["keywords"]):
        for word in (keywords if isinstance(keywords, list) else []):
            index.setdefault(word, []).append(movie_id)
    return index


KEYWORDS = keyword_index()
REACH = {word: len(ids) for word, ids in KEYWORDS.items()}


def keyword_row(words, key, cap=None, current=None):
    """A flowing row of keyword chips, most far-reaching first.

    A chip at or above the link floor navigates. Below it the chip still prints
    — it describes the film — but as inert text, because a keyword whose only
    film is the one you are already on is not somewhere to go.

    Every chip carries its reach. That number is the whole point: it says where
    the chip leads before you spend a click on it.
    """
    ranked = rank_by_reach(words, REACH)
    if cap:
        ranked = ranked[:cap]
    live = [w for w in ranked if REACH.get(w, 0) >= LINK_FLOOR and w != current]
    inert = [w for w in ranked if REACH.get(w, 0) < LINK_FLOOR]

    if live:
        # Plain buttons rather than st.pills: pills cannot be driven from a
        # Streamlit test in this version, and these are the app's main means of
        # navigation, so they need to stay under test. The stylesheet turns the
        # block they sit in into a wrapping row, so they still read as chips.
        with st.container():
            # A div, not a span: markdown wraps a bare inline element in a <p>,
            # which adds a level the stylesheet's child chain does not expect.
            st.markdown('<div class="rw-kwmark"></div>', unsafe_allow_html=True)
            for word in live:
                if st.button(
                    f"{word}  {REACH.get(word, 0)}",
                    key=f"btn_kw_{key}_{word}",
                ):
                    open_keyword(word)

    if inert:
        st.markdown(
            '<div class="rw-kw-field">'
            + "".join(keyword_chip(w, REACH.get(w, 0), inert=True) for w in inert)
            + "</div>",
            unsafe_allow_html=True,
        )


def render_keyword(keyword):
    """Every film carrying one keyword, plus where to go next.

    A keyword page must hold up even when the keyword has a single film, since
    search and shared links reach the thin ones too. The partner panel is what
    guarantees that: no keyword in the catalogue has an empty one, because the
    median film carries 17 keywords and every one of them is an exit.
    """
    movie_ids = KEYWORDS.get(keyword, [])
    films = movies_df[movies_df["movie_id"].isin(movie_ids)].sort_values("year")
    origin = SECTION_LABEL[
        resolve_section(st.session_state.get("nav_section", DEFAULT_SECTION))]

    if st.button(f"← Back to {origin}", key="btn_kw_back"):
        close_dossier()
        st.rerun()

    # ── Header ──
    share = 100 * len(films) / len(movies_df)
    rail = [
        stat_tile("Films", len(films)),
        stat_tile("Of the catalogue", f"{share:.1f}", "%"),
    ]
    thin = len(films) < 3
    if thin:
        # No decade shape and no meaningful average from one or two films, so
        # the rail says how rare the keyword is instead of inventing precision.
        rail.append(stat_tile("Rarity", len(films), f" of {len(movies_df)}", coral=True))
    else:
        decades = Counter(int(y) // 10 * 10 for y in films["year"].dropna())
        peak = max(decades, key=lambda d: decades[d])
        ratings = films["rating_tmdb"].dropna()
        corpus = movies_df["rating_tmdb"].dropna().mean()
        rail.append(stat_tile("Peak decade", peak, "s"))
        rail.append(stat_tile("Avg TMDB", f"{ratings.mean():.1f}" if len(ratings) else None, "/10"))
        if len(ratings):
            rail.append(stat_tile("vs. catalogue", f"{ratings.mean() - corpus:+.1f}", coral=True))

    st.markdown(html(f"""
    <div class="rw-kw-head">
      {rings_svg()}
      <p class="rw-kw-eyebrow">Keyword</p>
      <h1>{keyword}</h1>
      <div class="rw-kw-rail">{''.join(rail)}</div>
    </div>"""), unsafe_allow_html=True)

    # The one mechanical hierarchy in the vocabulary: TMDB writes locations as
    # "city, region". It earns a line, not a browse axis of its own — "usa" is a
    # bucket and some regions have a single child.
    region = region_of(keyword)
    if region:
        siblings = [w for w in KEYWORDS if region_of(w) == region]
        if len(siblings) > 1:
            total = len({m for w in siblings for m in KEYWORDS[w]})
            st.markdown(
                f'<div class="rw-kw-tail">Part of <b>{region.title()}</b>: '
                f'{total} films across {len(siblings)} places.</div>',
                unsafe_allow_html=True,
            )

    # ── Decade signature ──
    if not thin:
        tape("When these films were made")
        spread = Counter(int(y) // 10 * 10 for y in films["year"].dropna())
        full = {d: spread.get(d, 0) for d in range(min(spread), max(spread) + 10, 10)}
        st.markdown(decade_bars(full), unsafe_allow_html=True)
        catalogue = Counter(int(y) // 10 * 10 for y in movies_df["year"].dropna())
        here = 100 * full.get(peak, 0) / len(films)
        house = 100 * catalogue.get(peak, 0) / len(movies_df)
        st.markdown(
            f'<p class="rw-kw-caption">The {peak}s hold <b>{here:.0f}%</b> of these '
            f'films, against <b>{house:.0f}%</b> of the catalogue as a whole. '
            'Read the gap between those two numbers, not the shape on its own '
            '— the show covers some decades far more than others.</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="rw-kw-tail">Only {len(films)} film'
            f'{"s" if len(films) != 1 else ""} carries this keyword, so there is no '
            'decade shape and no average worth printing. Below is the film, and '
            'the keywords it shares with the rest of the catalogue.</div>',
            unsafe_allow_html=True,
        )

    # ── Travels with ──
    partners = Counter()
    for movie_id in movie_ids:
        row = movies_df[movies_df["movie_id"] == movie_id].iloc[0]
        for word in (row["keywords"] if isinstance(row["keywords"], list) else []):
            if word != keyword:
                partners[word] += 1
    if partners:
        tape("Travels with" if not thin else "Where to go from here")
        top = [w for w, _ in partners.most_common(14)]
        keyword_row(top, key="partners", current=keyword)

    # ── The films ──
    tape(f"The {len(films)} film{'s' if len(films) != 1 else ''}")
    st.markdown(
        '<div class="rw-kw-gridnote"><span>Ordered by year · oldest first</span>'
        "<span>Every poster opens that film's dossier</span></div>",
        unsafe_allow_html=True,
    )
    COLS = 8
    for start in range(0, len(films), COLS):
        cols = st.columns(COLS)
        for col, (_, film) in zip(cols, films.iloc[start:start + COLS].iterrows()):
            with col:
                rating = f"{film['rating_tmdb']:.1f}" if pd.notna(film["rating_tmdb"]) else ""
                film_card(film, f"{film['year']} {rating}", key="kw")


def explode_genres(df):
    """Return long-form DataFrame with one genre per row."""
    rows = []
    for _, row in df.iterrows():
        for g in (row["genres"] if isinstance(row["genres"], list) else []):
            rows.append({**row.to_dict(), "genre": g})
    return pd.DataFrame(rows)


# "In this film" counts the whole cast list curated_movies stores, which TMDB
# caps at ten (453 of 454 films carry exactly ten; one carries nine). The slice
# is kept rather than dropped so a future deeper cast list cannot silently
# redefine every actor statistic in the app.
BILLED = 10


def explode_cast(df, top_n=50, gender=None, gender_map=None):
    """Ranked (actor, count) over the stored cast lists.

    `gender` narrows the population to one of GENDERS before ranking, using
    GENDER_MAP unless a map is passed in. A name with no person row counts as
    'unknown', so the four genders partition the credits exactly -- any
    headline share is then computed over the population it claims.
    """
    lookup = GENDER_MAP if gender_map is None else gender_map
    counts = Counter()
    for cast in df["cast_names"]:
        if isinstance(cast, list):
            for name in cast[:BILLED]:  # the full stored cast
                if gender is not None and lookup.get(name, "unknown") != gender:
                    continue
                counts[name] += 1
    return pd.DataFrame(counts.most_common(top_n), columns=["actor", "count"])


# Per-film critic scores, averaged over a film's airings. Built once: the Movie
# Explorer, Directors and Actors sections all need the same numbers, and
# recomputing the groupby per section drifted the moment one of them changed.
EP_RATINGS = (
    merged_df.groupby("movie_id")
    .agg(tomatoes_avg=("tomatoes_num", "mean"), ebert_avg=("ebert_num", "mean"))
    .reset_index()
)
movies_rated = movies_df.merge(EP_RATINGS, on="movie_id", how="left")


def films_by_director(name):
    return movies_rated[movies_rated["director_primary"] == name]


def films_by_actor(name):
    return movies_rated[movies_rated["cast_names"].apply(
        lambda c: isinstance(c, list) and name in c[:BILLED])]


def billed_long(df):
    """One row per (film, credited actor).

    The actor-side analogue of director_primary: it turns cast into a plain
    column so actor statistics are a single groupby, the same shape as the
    director ones. Scanning the frame once per actor instead cost ~0.3s on
    every rerun, which Streamlit pays on every widget change.
    """
    out = df.copy()
    out["actor"] = out["cast_names"].apply(
        lambda c: c[:BILLED] if isinstance(c, list) else [])
    return out.explode("actor").dropna(subset=["actor"])


PERSON_AGG = dict(
    films=("movie_id", "count"),
    avg_tmdb=("rating_tmdb", "mean"),
    avg_runtime=("runtime_minutes", "mean"),
    avg_rt=("tomatoes_avg", "mean"),
    first_year=("year", "min"),
    last_year=("year", "max"),
)


# ── Shared people-section components ──────────────────────────────────────────
# The Directors and Actors sections are the same report over two different
# populations, so every panel they share is rendered from here. Splitting them
# into two hand-maintained blocks is how the pair would drift apart.

def _leaderboard_fig(counts, name_col, colour, xmax=None):
    """The ranked-bar figure itself, without the heading or the render.

    Split out so the gender-paired leaderboards can draw two of these on one
    shared `xmax`. Two charts on their own auto-scaled axes put an 18-film bar
    and a 7-film bar at the same width, which reads as parity and is the exact
    opposite of what the data says.
    """
    fig = px.bar(
        counts, x="films", y=name_col, orientation="h",
        color_discrete_sequence=[colour], text="films",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis=dict(autorange="reversed", title=""),
        xaxis=dict(title="Films covered",
                   range=[0, xmax * 1.12] if xmax else None),
        height=26 * len(counts) + 90,
    )
    plotly_defaults(fig)
    return fig


def people_leaderboard(counts, name_col, title, colour=MINT_DEEP):
    """Ranked horizontal bars — who turns up most."""
    tape(title)
    st.plotly_chart(_leaderboard_fig(counts, name_col, colour),
                    use_container_width=True)


GENDER_COLOUR = {"M": BLUE, "F": AMBER, "NB": VIOLET, "unknown": TXT_3}


def gender_split_leaderboards(df, title, top_n=15, genders=("M", "F")):
    """The same leaderboard once per gender, side by side on a shared axis.

    Why a pair and not one chart coloured by gender: the combined top 20 is 19
    men and one woman, so colouring a single ranking shows one stray bar and no
    women's ranking at all. Two columns give each population its own ranking;
    the shared axis is what keeps the comparison honest.

    `genders` defaults to the two TMDB records for nearly every credit here.
    Non-binary and unrecorded credits are counted in the tiles above rather
    than given a column of their own, which at these volumes would be a chart
    of two or three names.
    """
    tape(title)
    ranked = {g: explode_cast(df, top_n=top_n, gender=g).rename(
        columns={"count": "films"}) for g in genders}
    present = [g for g in genders if not ranked[g].empty]
    if not present:
        st.caption("No gender is recorded for any credited actor — run "
                   "scripts/09_enrich_metadata.py to fill curated_people.")
        return
    xmax = max(ranked[g]["films"].max() for g in present)

    for col, g in zip(st.columns(len(present)), present):
        with col:
            st.markdown(
                f'<p class="ch-note" style="margin:0 0 2px">'
                f'<b>{GENDER_LABEL[g]}</b> &middot; '
                f'{len(explode_cast(df, top_n=100_000, gender=g)):,} actors'
                f'</p>', unsafe_allow_html=True)
            st.plotly_chart(
                _leaderboard_fig(ranked[g], "actor", GENDER_COLOUR[g], xmax=xmax),
                use_container_width=True, key=f"lb_gender_{g}")


def stat_tiles(items):
    """A KPI row, items being (label, value) pairs.

    st.metric is what Box Office and Keywords already use for this, so these
    rows inherit the same tile styling rather than introducing a second one.
    """
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)


def person_stats(films):
    """The headline numbers for one person's body of covered work.

    First and latest are separate tiles rather than one "1983-2022" range: a
    metric value that long is truncated to an ellipsis at a sixth of the width.
    """
    years = films["year"].dropna()
    rt = films["tomatoes_avg"].dropna()
    tmdb = films["rating_tmdb"].dropna()
    return [
        ("Films covered", len(films)),
        ("Episodes", int(films["total_episodes_featured"].fillna(0).sum())),
        ("First film", int(years.min()) if len(years) else "—"),
        ("Latest film", int(years.max()) if len(years) else "—"),
        ("Avg RT", f"{rt.mean()*100:.0f}%" if len(rt) else "—"),
        ("Avg TMDB", f"{tmdb.mean():.2f}" if len(tmdb) else "—"),
    ]


def ranked_list(pairs, empty_msg, note="", wide=False):
    """A compact ranked name/count list — used where a bar chart would be
    overkill for three or four rows. `wide` gives the name more of the row,
    for labels that are several names long."""
    if not pairs:
        st.caption(empty_msg)
        return
    top = max(n for _, n in pairs)
    cls = "rw-rank wide" if wide else "rw-rank"
    rows = "".join(
        f'<div class="{cls}"><span class="n">{name}</span>'
        f'<span class="bar"><i style="width:{100*n/top}%"></i></span>'
        f'<span class="c">{n}</span></div>'
        for name, n in pairs
    )
    st.markdown(rows, unsafe_allow_html=True)
    if note:
        st.caption(note)


# ── Hosts & Guests ────────────────────────────────────────────────────────────

# A regular, for the lean tests: anyone on at least this many episodes. Ten
# people clear it; below it a person's episodes are too few for anything short
# of a landslide to be told from chance.
LEAN_FLOOR = 15
# Genres tested for a lean: those on at least this many episodes (seven do).
# Every extra test raises the bar the correction sets for all the others, and
# a genre on a handful of episodes cannot move far enough to clear it.
GENRE_FLOOR = 40
LEAN_Q = 0.05
N_PERM = 4000
# The bench table stops here. The one- and two-timers are most of the names
# and none of the pattern, and the lookup still has every one of them.
BENCH_FLOOR = 3
WHEN_TOP = 15
RING_TOP = 12
# Verdict episodes needed before a person's Cruise vs. Hanks split is read at
# all. Shared with that section so the two never disagree.
VERDICT_FLOOR = 8


@st.cache_data(ttl=300)
def room_leans(measures, members):
    """Every regular against everyone else, on every measure, with q-values.

    `measures` is one column per metric and `members` one boolean column per
    regular, both one row per airing.
    """
    out = permutation_diffs(
        {c: measures[c].to_numpy() for c in measures.columns},
        {p: members[p].to_numpy() for p in members.columns},
        n_perm=N_PERM,
    )
    out["q"] = bh_adjust(out["p"])
    return out


def lean_chips(rows):
    """One person's leans that survived the correction, as badges.

    Mint marks a measure above the rest of the show and grey one below. The
    words carry the direction too, so colour is never the only cue.
    """
    if rows.empty:
        return '<span class="rw-lean-none">No detectable lean</span>'
    return "".join(
        f'<span class="badge{" badge-mint" if r.diff > 0 else ""}">'
        f"{lean_phrase(r.metric, r.mean_in, r.mean_out, r.diff)}</span>"
        for r in rows.sort_values("q").itertuples()
    )


def person_shelf(name):
    """Every airing a person was on, newest first.

    One definition for two readers: the lookup draws its poster grid in this
    order, and the dossier's step arrows walk it in the same order. Computed
    from merged_df rather than read off the grid because the dossier gate runs
    before the section, on a run where the grid is never drawn.
    """
    room = room_long(merged_df, "raw_episode_id",
                     keep=("episode_number", "episode_date", "movie_id"))
    return (room[room["person"] == name]
            .sort_values(["episode_date", "episode_number"], ascending=False))


def person_spotlight(films, key, collab_title, collab_pairs, collab_empty,
                     collab_note=""):
    """Everything about one person: headline numbers, the posters, the shape of
    the work. Identical for a director and for an actor by design."""
    stat_tiles(person_stats(films))
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    ordered = films.sort_values("year")
    COLS = 8
    for i in range(0, len(ordered), COLS):
        cols = st.columns(COLS)
        for col, (_, m) in zip(cols, ordered.iloc[i : i + COLS].iterrows()):
            with col:
                rt = (f"RT {m['tomatoes_avg']*100:.0f}%"
                      if pd.notna(m["tomatoes_avg"]) else "")
                film_card(m, f"{int(m['year'])} {rt}".strip(), key=key)

    # Genre and decade are always populated; the collaborator column often is
    # not, because recurring pairings are genuinely rare in this catalogue.
    c_genre, c_decade, c_collab = st.columns(3)
    with c_genre:
        st.markdown("###### Genre mix")
        g = explode_genres(ordered)["genre"].value_counts().reset_index()
        g.columns = ["genre", "count"]
        g, cmap, order = fold_counts(g, "genre", "count")
        fig = px.pie(
            g, values="count", names="genre", color="genre",
            color_discrete_map=cmap, category_orders={"genre": order}, hole=0.45,
        )
        fig.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2,
                          height=270, margin=dict(t=10, b=10, l=10, r=10),
                          showlegend=False)
        fig.update_traces(textinfo="label+percent", textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)
    with c_decade:
        st.markdown("###### Films by decade")
        dec = (ordered["year"].dropna() // 10 * 10).astype(int).value_counts().sort_index()
        fig = px.bar(
            x=[f"{d}s" for d in dec.index], y=dec.to_numpy(),
            color_discrete_sequence=[MINT_DEEP], text=dec.to_numpy(),
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=270, margin=dict(t=10, b=10, l=10, r=10),
                          xaxis_title="", yaxis_title="", yaxis_visible=False)
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    with c_collab:
        st.markdown(f"###### {collab_title}")
        ranked_list(collab_pairs, collab_empty, collab_note)


def people_scatter(stats, name_col, label, name_from=4):
    """Volume against reception, one bubble per person.

    Only the people at or past `name_from` films are labelled. The population is
    bottom-heavy -- most sit at the two- or three-film left edge -- and labelling
    every point there piles a few hundred names into an unreadable smear. The
    rest keep their identity on hover.
    """
    plot = stats.copy()
    plot["tag"] = plot[name_col].where(plot["films"] >= name_from, "")
    fig = px.scatter(
        plot, x="films", y="avg_tmdb", size="avg_runtime", text="tag",
        color="avg_tmdb", color_continuous_scale=SEQ,
        custom_data=[name_col, "films", "avg_runtime"],
        labels={"films": "Films covered", "avg_tmdb": "Avg TMDB rating"},
    )
    fig.update_traces(
        textposition="top center", textfont_size=9,
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} films"
                      "<br>avg TMDB %{y:.2f}<br>avg runtime %{customdata[2]:.0f} min"
                      "<extra></extra>",
    )
    fig.update_layout(coloraxis_showscale=False)
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)


def fold_to_series(values, keep=len(SERIES)):
    """Cap a categorical column at the palette's length.

    Series hues are assigned in a fixed order and never cycled, so anything past
    the last slot folds into a neutral "Other" instead of reusing slot 1.
    Returns (folded values, colour map, category order).
    """
    top = list(values.value_counts().head(keep).index)
    folded = values.where(values.isin(top), "Other")
    cmap = {name: SERIES[i] for i, name in enumerate(top)}
    order = list(top)
    if (folded == "Other").any():
        cmap["Other"] = TXT_3
        order.append("Other")
    return folded, cmap, order


def fold_counts(df, name_col, count_col, keep=len(SERIES)):
    """fold_to_series for a frame that is already aggregated to (name, count)."""
    ranked = df.sort_values(count_col, ascending=False)
    top = list(ranked[name_col].head(keep))
    out = ranked.copy()
    out[name_col] = out[name_col].where(out[name_col].isin(top), "Other")
    out = out.groupby(name_col, as_index=False)[count_col].sum()
    cmap = {name: SERIES[i] for i, name in enumerate(top)}
    order = list(top)
    if "Other" in set(out[name_col]):
        cmap["Other"] = TXT_3
        order.append("Other")
    return out.set_index(name_col).loc[order].reset_index(), cmap, order


def plotly_defaults(fig, legend=False):
    fig.update_layout(
        paper_bgcolor=INK,
        plot_bgcolor=INK_2,
        font_color=TAPE,
        font_family="Archivo, Helvetica Neue, Arial, sans-serif",
        # Plotly 6.x renders title_font_color as a title object with text=undefined
        # when no title is set — use explicit empty title to suppress it.
        title=dict(text="", font=dict(color=TAPE)),
        legend_bgcolor=INK_2,
        legend_bordercolor=LINE,
        legend_borderwidth=1,
        showlegend=legend,
        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE),
        yaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE),
        margin=dict(t=30, r=20, b=40, l=60),
        hoverlabel=dict(
            bgcolor=INK_3, bordercolor=LINE_2, font_color=TAPE,
            font_family="IBM Plex Mono, ui-monospace, monospace",
        ),
    )
    if not legend:
        fig.update_traces(showlegend=False)
    return fig


# ── Sidebar nav ───────────────────────────────────────────────────────────────

# The rail, grouped by what the visitor is there to do: find a film, read the
# films, read the show, then the segment. Ordering within a group runs by how
# much of the corpus the section actually speaks to — Keywords covers 3,645
# terms over 453 films and used to sit last; Cruise vs. Hanks covers 125 of 481
# episodes and used to sit mid-rail.
#
# The slug is the identity and the label is presentation. They were the same
# string before, which made the label part of the ?from= URL contract: renaming
# a section silently broke every shared dossier link. Relabel freely now;
# changing a slug is the breaking change, and LEGACY_SECTIONS is what carries
# links minted under the old scheme.
NAV = [
    ("Find", [
        ("overview", "Overview"),
        ("explorer", "Movie Explorer"),
    ]),
    ("The films", [
        ("genres", "Genres"),
        ("directors", "Directors"),
        ("actors", "Actors"),
        ("keywords", "Keywords"),
        ("ratings", "Ratings"),
        ("boxoffice", "Box Office"),
    ]),
    ("The show", [
        ("hosts", "Hosts & Guests"),
        ("timeline", "Timeline & Revisits"),
    ]),
    ("The bits", [
        ("verdicts", "Cruise vs. Hanks"),
    ]),
    # A second source, not a second view of the first. These films have never
    # been on the show, so they belong to neither "The films" (which is the
    # catalogue) nor "The show" (which is the episodes) — folding it into either
    # would misstate what the numbers in that group count.
    ("On deck", [
        ("upcoming", "Upcoming Films"),
    ]),
]

SLUGS = [slug for _, items in NAV for slug, _ in items]
SECTION_LABEL = {slug: label for _, items in NAV for slug, label in items}
SLUG_OF_LABEL = {label: slug for slug, label in SECTION_LABEL.items()}
DEFAULT_SECTION = SLUGS[0]

# Links minted while the label was the key. Revisits is no longer its own
# section, so its links land on the timeline that absorbed it.
LEGACY_SECTIONS = {
    "Overview": "overview",
    "Movie Explorer": "explorer",
    "Genres": "genres",
    # Directors & Cast split into two sections; its links land on Directors.
    "Directors & Cast": "directors",
    "people": "directors",
    "Ratings": "ratings",
    "Cruise vs. Hanks": "verdicts",
    "Timeline": "timeline",
    "Revisits": "timeline",
    "Hosts & Guests": "hosts",
    "Keywords": "keywords",
}


def resolve_section(value):
    """Map a ?from= value — slug or pre-slug label — onto a live section."""
    if value in SECTION_LABEL:
        return value
    return LEGACY_SECTIONS.get(value, DEFAULT_SECTION)


def pick_section(group_index):
    """Radios don't coordinate, so selecting in one group clears the others."""
    def _on_change():
        label = st.session_state.get(f"nav_g{group_index}")
        if label is None:
            return
        st.session_state.nav_section = SLUG_OF_LABEL[label]
        for other in range(len(NAV)):
            if other != group_index:
                st.session_state[f"nav_g{other}"] = None
        close_dossier()
    return _on_change


def go_section(slug):
    """Jump to a section from a control in the body.

    Used as a button callback, which runs before the rerun draws anything: the
    rail's radios are then free to be set. Writing their keys from the body
    itself would be a write to widgets already instantiated this run, which
    Streamlit refuses.
    """
    st.session_state.nav_section = slug
    for gi, (_, items) in enumerate(NAV):
        st.session_state[f"nav_g{gi}"] = next(
            (lbl for s, lbl in items if s == slug), None)
    close_dossier()


def open_person(name):
    """Hand a name from a dossier's room to the Hosts & Guests lookup.

    A callback, like go_section, because that is the one point in a run where
    the lookup's widget key can still be written. The shadow is set as well:
    the picker was not drawn under the dossier, so keep() would otherwise
    restore the pick from before it.
    """
    st.session_state.flt_person = name
    st.session_state["_keep_flt_person"] = name
    go_section("hosts")

# A dossier is addressed by ?movie=<movie_id>, so a film can be linked directly
# and the browser Back button steps out of it. On a cold load the URL wins; from
# then on the click handler keeps the two in step.
_VALID_IDS = set(movies_df["movie_id"])
_VALID_UPCOMING = set(upcoming_df["upcoming_film_id"]) if len(upcoming_df) else set()
_VALID_PEOPLE = set(room_long(merged_df, "raw_episode_id")["person"]) - {ANCHOR}
if "dt_movie" not in st.session_state:
    _qp = st.query_params.get("movie")
    _kw = st.query_params.get("keyword")
    _up = st.query_params.get("upcoming")
    st.session_state.dt_movie = _qp if _qp in _VALID_IDS else None
    st.session_state.kw_word = _kw if _kw in KEYWORDS else None
    st.session_state.up_film = _up if _up in _VALID_UPCOMING else None
    if st.session_state.dt_movie or st.session_state.kw_word:
        st.session_state.nav_section = resolve_section(st.query_params.get("from"))
    elif st.session_state.up_film:
        # An upcoming film only ever belongs to its own section, so there is no
        # ?from= to carry -- unlike a dossier, which can be opened from any of
        # nine and has to remember which.
        st.session_state.nav_section = "upcoming"
    elif st.query_params.get("person") in _VALID_PEOPLE:
        # A lookup is addressed by ?person=<name> and, like an upcoming film,
        # belongs to one section. Seeded here, before the picker is drawn --
        # the only point in the run at which its key may be written.
        st.session_state.nav_section = "hosts"
        st.session_state.flt_person = st.query_params.get("person")

with st.sidebar:
    st.markdown(
        '<div class="rw-brand">'
        + rings_svg("")
        + "<div><b>THE<br>REWATCHABLES</b>"
        + f"<span>{len(movies_df)} FILMS &middot; {len(episodes_df)} EPS</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Seed the per-group widget state from the selected slug once. After this
    # the callbacks own it; re-deriving it every run would fight the click.
    st.session_state.setdefault("nav_section", DEFAULT_SECTION)
    for _gi, (_, _items) in enumerate(NAV):
        if f"nav_g{_gi}" not in st.session_state:
            st.session_state[f"nav_g{_gi}"] = next(
                (lbl for slug, lbl in _items if slug == st.session_state.nav_section),
                None,
            )

    for _gi, (_group, _items) in enumerate(NAV):
        st.markdown(
            '<div class="rw-navgroup"'
            + (' style="margin-top:0"' if _gi == 0 else "")
            + f">{_group}</div>",
            unsafe_allow_html=True,
        )
        st.radio(
            _group, [lbl for _, lbl in _items], key=f"nav_g{_gi}", index=None,
            on_change=pick_section(_gi), label_visibility="collapsed",
        )

    section = st.session_state.nav_section
    st.markdown("---")
    st.markdown(
        '<div class="rw-foot">SQLite &middot; TMDB</div>', unsafe_allow_html=True
    )


# ── Source freshness ──────────────────────────────────────────────────────────
# data/episodes.xlsx is the file that gets edited, but the app reads the
# database, which only moves when the pipeline runs. Until it does, every page
# says so, with the command that closes the gap. Read on every run rather than
# cached: it is one stat() and one indexed MAX().

def last_load_utc():
    """When step 02 last loaded the episode list, as naive UTC, or None."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        stamp = conn.execute(
            "SELECT MAX(sync_timestamp) FROM raw_ingest_runs").fetchone()[0]
    except sqlite3.Error:
        stamp = None
    finally:
        conn.close()
    return datetime.fromisoformat(stamp) if stamp else None


_saved = (datetime.fromtimestamp(SOURCE_XLSX.stat().st_mtime, tz=timezone.utc)
          .replace(tzinfo=None) if SOURCE_XLSX.exists() else None)
_notice = stale_notice(_saved, last_load_utc())
if _notice:
    st.markdown(_notice, unsafe_allow_html=True)


# ── Dossier overlay ───────────────────────────────────────────────────────────
# A selected film replaces the section body while the nav rail stays put, so
# Back lands you where you were. Movie Explorer handles its own gate further
# down: its filters live in the sidebar and have to keep rendering, and its
# result set is what the dossier's step arrows walk.

selected_film = st.session_state.get("dt_movie")
selected_keyword = st.session_state.get("kw_word")

# A keyword overlay covers every section, Movie Explorer included: it has no
# result set of its own to preserve, so there is nothing to keep rendering.
if selected_keyword:
    render_keyword(selected_keyword)
    st.stop()

if selected_film and section != "explorer":
    # A film opened from the Hosts & Guests lookup steps through that person's
    # films. A revisit puts one film on a shelf twice; the arrows visit it
    # once, at its newest airing. A film opened from elsewhere on the page --
    # the Without Bill grid -- is usually not on the shelf and gets no arrows.
    siblings = None
    if section == "hosts" and kept("flt_person") in _VALID_PEOPLE:
        siblings = list(dict.fromkeys(person_shelf(kept("flt_person"))["movie_id"]))
    render_dossier(selected_film, siblings=siblings)
    st.stop()

selected_prospect = st.session_state.get("up_film")
if selected_prospect:
    render_prospect(selected_prospect)
    st.stop()


# The blocks below dispatch on slug, so the file order no longer has to match
# the rail order — the banner numbers give each block's position in NAV, and
# reordering the rail means editing NAV alone. Search by slug, not by number.

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

if section == "overview":
    masthead(
        "Every film they&rsquo;ve rewatched",
        f"{len(episodes_df):,} film episodes joined to TMDB metadata, "
        "Rotten Tomatoes scores and Ebert stars. Where the show is now, who is "
        "in the room, and a door into each part of the catalogue.",
    )

    # ── Where the show is now ──
    # The tiles carry what characterises the show rather than what sizes the
    # database. A director count says nothing a visitor can picture; "the
    # median film is 27 years old" is the whole premise in one number. The
    # catalogue's own counts sit on the doors at the bottom.
    latest_air = episodes_df["date"].max()
    n_last_year = int((episodes_df["date"] > latest_air - pd.Timedelta(days=365)).sum())
    film_age = (merged_df["episode_date"].dt.year - merged_df["year"]).dropna()
    share_90s = 100 * float((movies_df["decade"] == 1990).mean())
    gaps = episodes_df["date"].sort_values().diff().dt.days.dropna()

    st.markdown(
        '<div class="rw-dt-rail">'
        + stat_tile("Episodes", f"{len(episodes_df):,}")
        + stat_tile("Films", f"{len(movies_df):,}")
        + stat_tile("Last 12 months", n_last_year)
        + stat_tile("Median film age", f"{film_age.median():.0f}", " yrs")
        + stat_tile("From the 1990s", f"{share_90s:.0f}", "%")
        + stat_tile("Between episodes", f"{gaps.median():.0f}", " days")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Latest episodes ──
    # The one block with a reason to change from week to week. Newest first,
    # one card per film: a film that has aired twice recently appears once,
    # under its most recent episode.
    tape("Latest episodes")
    recent = (
        links_df.sort_values("episode_date", ascending=False)
        .drop_duplicates("movie_id")
        .head(8)
        .merge(movies_df[["movie_id", "title", "year", "poster_url_tmdb"]], on="movie_id")
    )
    st.markdown(
        f'<div class="rw-kw-gridnote"><span>as of {latest_air:%B} {latest_air.day}, '
        f'{latest_air.year}</span><span>click a poster for its episodes</span></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(8)
    for col, (_, row) in zip(cols, recent.iterrows()):
        with col:
            aired = row["episode_date"]
            film_card(
                row,
                f"Ep {int(row['episode_number'])} · {aired:%b} {aired.day}",
                key="latest",
            )

    st.markdown("---")

    # ── The regulars ──
    # Everyone but Bill Simmons, counted across all five chairs so a guest who
    # sometimes hosts is credited for every episode they were in. He is on
    # nine episodes in ten; a row led by him would say only that.
    tape("The regulars")
    seats = room_long(episodes_df, "raw_episode_id")
    n_eps = len(episodes_df)
    n_anchor = int((seats["person"] == ANCHOR).sum())
    seats = seats[seats["person"] != ANCHOR]
    in_room = seats["person"].value_counts()
    hosted = seats.loc[seats["chair"] == "host", "person"].value_counts()

    reg_cards = []
    for name, n in in_room.head(6).items():
        h = int(hosted.get(name, 0))
        hosted_txt = f" &middot; hosted {h}" if h else ""
        initials = "".join(w[0] for w in name.split()[:2]).upper()
        reg_cards.append(html(f'''
            <div class="rw-reg">
              <span class="d">{initials}</span>
              <div class="b">
                <span class="n">{name}</span>
                <span class="m"><b>{n}</b> of {n_eps}{hosted_txt}</span>
                <div class="bar"><i style="width:{100 * n / n_eps:.0f}%"></i></div>
              </div>
            </div>'''))
    st.markdown('<div class="rw-reg-row">' + "".join(reg_cards) + "</div>",
                unsafe_allow_html=True)

    note_col, go_col = st.columns([4, 1], vertical_alignment="center")
    with note_col:
        st.markdown(
            f'<p class="rw-ov-note"><b>{len(in_room)}</b> people besides Bill '
            f"Simmons have been in the room. He is on {n_anchor} of {n_eps} "
            "episodes, so he is left out of the ranking. The bar is the share of "
            "episodes each was in.</p>",
            unsafe_allow_html=True,
        )
    with go_col:
        st.button("Full room →", key="btn_ov_hosts", use_container_width=True,
                  on_click=go_section, args=("hosts",))

    st.markdown("---")

    # ── The ones they came back to ──
    # Every film with more than one episode, and nothing else. The grid used to
    # show a top twenty, but only sixteen films have ever had a second episode
    # and the maximum is three, so rows two and three were single-episode films
    # in arbitrary order dressed as a ranking.
    tape("The ones they came back to")
    again = movies_df[movies_df["total_episodes_featured"] > 1].sort_values(
        ["total_episodes_featured", "last_episode_date"], ascending=[False, False])
    n_flagged = int((movies_df["revisited_flag"] == 1).sum())
    st.markdown(
        f'<p class="rw-ov-note"><b>{len(again)}</b> films have more than one '
        f'episode. The source sheet marks <b>{n_flagged}</b> films as revisits '
        'by hand; the episode count is derived from the feed, and the two are '
        'deliberately not reconciled &mdash; a second episode is not always a '
        'revisit.</p>',
        unsafe_allow_html=True,
    )
    per_row = 8
    again_rows = list(again.iterrows())
    for start in range(0, len(again_rows), per_row):
        cols = st.columns(per_row)
        for col, (_, row) in zip(cols, again_rows[start:start + per_row]):
            with col:
                last = row["last_episode_date"]
                # Eight across leaves ~100px per strip: "2× · 2026" holds one
                # line, anything carrying a month wraps on half the cards.
                when = f"{last:%Y}" if pd.notna(last) else "—"
                film_card(
                    row,
                    f"{int(row['total_episodes_featured'])}× · {when}",
                    key="again",
                )

    st.markdown("---")

    # ── Episodes per year ──
    # One chart, the one that tells the show's history at a glance. Genre and
    # decade bars used to sit here too; they are the first two charts on
    # Genres and Timeline, and a front page that repeats its own sections is a
    # front page nobody scrolls.
    tape("Episodes per year")
    ep_year = (
        episodes_df.set_index("date").resample("YE").size().reset_index(name="count")
    )
    ep_year["year"] = ep_year["date"].dt.year
    # The current year is a partial count, drawn dim so the drop at the right
    # edge reads as "so far" rather than as a decline.
    bar_colors = [MINT_DEEP] * (len(ep_year) - 1) + [MINT_DIM]
    first_full = ep_year[ep_year["count"] >= 50]["year"].min()

    chart_col, read_col = st.columns([3, 1.15])
    with chart_col:
        fig = go.Figure(go.Bar(
            x=ep_year["year"], y=ep_year["count"],
            marker_color=bar_colors, marker_line_width=0,
            text=ep_year["count"], textposition="outside",
            textfont=dict(family="IBM Plex Mono, ui-monospace, monospace", size=11),
            hovertemplate="%{x}: %{y} episodes<extra></extra>",
        ))
        fig.update_layout(
            height=280, xaxis=dict(dtick=1, title=None),
            # Headroom for the outside labels; autorange clips the tallest one.
            yaxis=dict(title="Episodes", range=[0, ep_year["count"].max() * 1.18]),
            margin=dict(t=36, r=10, b=30, l=50),
        )
        fig.add_annotation(
            x=ep_year["year"].iloc[-1], y=ep_year["count"].iloc[-1],
            text="to date", showarrow=False, yshift=26,
            font=dict(family="IBM Plex Mono, ui-monospace, monospace", size=10, color=TXT_3),
        )
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    with read_col:
        first_air = episodes_df["date"].min()
        st.markdown(
            html(f'''
            <div class="rw-dt-panel" style="margin-top:8px">
              <p class="rw-dt-loose">Reading the chart</p>
              <ul class="rw-ov-read">
                <li><b>{first_air:%b %Y}</b>first film episode</li>
                <li><b>{int(first_full) if pd.notna(first_full) else "&mdash;"}</b>first year at fifty or more</li>
                <li><b>{gaps.median():.0f} days</b>median gap between episodes</li>
                <li><b>{int(ep_year["count"].iloc[-1])}</b>so far in {int(ep_year["year"].iloc[-1])}</li>
              </ul>
            </div>'''),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Go deeper ──
    # One door per section of the rail, in rail order and with the rail's
    # numbering, each carrying the one number that says what is behind it.
    tape("Go deeper")
    group_of = {slug: group for group, items in NAV for slug, _ in items}
    n_genres = explode_genres(movies_df)["genre"].nunique()
    yr_min = int(episodes_df["date"].dt.year.min())
    yr_max = int(episodes_df["date"].dt.year.max())
    rt_median = episodes_df["tomatoes_num"].median()
    doors = [
        ("explorer", f"{len(movies_df):,}", "films",
         "Filter the whole catalogue by decade, genre, director, rating and runtime."),
        ("genres", f"{n_genres}", "genres",
         "How the mix shifts across the decades they cover, and which genres travel together."),
        ("directors", f"{movies_df['director_primary'].nunique()}", "directors",
         "Who gets called back to the chair, their genre range and each one's run on the show."),
        ("actors", f"{len(explode_cast(movies_df, top_n=100_000)):,}", "actors",
         "Who keeps turning up on screen, the films they carry and the directors they work with."),
        ("keywords", f"{len(KEYWORDS):,}", "terms",
         "TMDB's keyword tags across every film: the themes, settings and tropes that recur."),
        ("ratings", f"{rt_median * 100:.0f}", "% median RT",
         "Tomatometer, Ebert stars and TMDB scores, and where the critics and the audience split."),
        ("boxoffice", f"{int(movies_df['revenue_real'].notna().sum())}", "with a gross",
         "Budgets and grosses in today's dollars, and which films made their money back."),
        ("hosts", f"{len(in_room)}", "besides Bill",
         "Look anyone up, see who sits together, and what each regular gets booked on."),
        ("timeline", f"{yr_min}&ndash;{yr_max}", "",
         "The show year by year, how old the films were when featured, and the revisits."),
        ("verdicts", f"{len(ch_df)}", "verdicts",
         "The recurring bit: which of the two is the bigger star, episode by episode."),
        ("upcoming", f"{len(upcoming_df):,}", "in the queue",
         "Listener requests that have not aired yet, with the reason each is on the list."),
    ]
    # Four across: eleven doors over rows of five left a single door stranded.
    per_row = 4
    for start in range(0, len(doors), per_row):
        cols = st.columns(per_row)
        for col, (slug, number, unit, blurb) in zip(cols, doors[start:start + per_row]):
            with col:
                unit_html = f"<small>{unit}</small>" if unit else ""
                st.markdown(
                    html(f'''
                    <div class="rw-door"><span class="rw-doormark"></span>
                      <span class="k">{group_of[slug]} &middot; {SLUGS.index(slug) + 1:02d}</span>
                      <span class="v">{number}{unit_html}</span>
                      <span class="t">{SECTION_LABEL[slug]}</span>
                      <p>{blurb}</p>
                    </div>'''),
                    unsafe_allow_html=True,
                )
                st.button("Open →", key=f"btn_door_{slug}", use_container_width=True,
                          on_click=go_section, args=(slug,))

    st.markdown("---")

    # ── Random spotlight ──
    # Rerolled through a seed in session state. The button used to clear
    # st.cache_data, which threw away the whole database load to pick one
    # random row.
    tape("Random spotlight")
    if "spot_seed" not in st.session_state:
        st.session_state.spot_seed = random.randrange(1 << 30)

    def _reroll():
        st.session_state.spot_seed = random.randrange(1 << 30)

    spotlight = movies_df.sample(1, random_state=st.session_state.spot_seed).iloc[0]

    def _esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    poster = (
        f'<img src="{spotlight["poster_url_tmdb"].replace("/w500/", "/w342/")}" alt="">'
        if spotlight["poster_url_tmdb"] else
        f'<div class="poster-plate" style="height:225px;width:150px">{rings_svg("")}'
        f'<b>{_esc(spotlight["title"])}</b></div>'
    )
    meta = [m for m in [
        " &middot; ".join(spotlight["directors"]) if spotlight["directors"] else "",
        " &middot; ".join(spotlight["genres"]) if spotlight["genres"] else "",
        f"{int(spotlight['runtime_minutes'])} min" if pd.notna(spotlight["runtime_minutes"]) else "",
    ] if m]
    scores = []
    if pd.notna(spotlight["rating_tmdb"]):
        scores.append(f"TMDB <b>{spotlight['rating_tmdb']:.1f}</b>/10")
    scores.append(f"featured <b>{int(spotlight['total_episodes_featured'])}&times;</b>")
    summary = spotlight["plot_summary"] or ""
    if len(summary) > 320:
        summary = summary[:320].rsplit(" ", 1)[0] + "…"
    st.markdown(
        html(f'''
        <div class="rw-dt-panel"><div class="rw-spot">{poster}
          <div>
            <p class="h">{_esc(spotlight["title"])}<small>{spotlight["year"]}</small></p>
            <span class="m">{" &middot; ".join(meta)}</span>
            <span class="m">{" &middot; ".join(scores)}</span>
            <p>{_esc(summary) if summary else "No plot summary on file."}</p>
          </div>
        </div></div>'''),
        unsafe_allow_html=True,
    )
    b1, b2, _ = st.columns([1.2, 1.2, 4])
    with b1:
        st.button("🎲 Surprise me", key="btn_spot_reroll", use_container_width=True,
                  on_click=_reroll)
    with b2:
        if st.button("Open dossier →", key="btn_spotlight", use_container_width=True):
            open_dossier(spotlight["movie_id"])


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — MOVIE EXPLORER
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "explorer":
    # The filter widgets render on every run of this section, dossier or not.
    # Streamlit discards state for widgets it did not draw, so hiding them
    # behind the gate is what would actually lose the filter set.
    # Sidebar filters. Every one carries an explicit key: a keyless widget is
    # identified partly by where it sits in the element tree, so opening a
    # dossier — which rebuilds the main area — was enough to sever a filter from
    # its value and silently reset it to the default.
    with st.sidebar:
        st.markdown("### Filters")
        all_genres = sorted({g for genres in movies_df["genres"] for g in genres})
        sel_genres = keep(st.multiselect, "Genre", all_genres, key="flt_genres")

        all_decades = sorted(movies_df["decade"].dropna().unique())
        decade_labels = {int(d): f"{int(d)}s" for d in all_decades}
        sel_decades = keep(
            st.multiselect, "Decade", list(decade_labels.values()), key="flt_decades")

        all_directors = sorted(movies_df["director_primary"].unique())
        sel_directors = keep(st.multiselect, "Director", all_directors, key="flt_directors")

        rt_range = keep(st.slider, "RT Score", 0, 100, (0, 100), key="flt_rt")
        tmdb_range = keep(
            st.slider, "TMDB Rating", 0.0, 10.0, (0.0, 10.0), 0.1, key="flt_tmdb")

        search = keep(st.text_input, "Search title", key="flt_search")

    # movies_rated is movies_df with the per-film episode ratings already joined;
    # Directors and Actors read the same frame. Every step below rebinds `view`
    # to a filtered copy rather than mutating it.
    view = movies_rated

    # Apply filters
    if search:
        view = view[view["title"].str.contains(search, case=False, na=False)]
    if sel_genres:
        view = view[view["genres"].apply(lambda g: any(x in g for x in sel_genres))]
    if sel_decades:
        selected_d = [int(d.replace("s", "")) for d in sel_decades]
        view = view[view["decade"].isin(selected_d)]
    if sel_directors:
        view = view[view["director_primary"].isin(sel_directors)]

    view = view[view["tomatoes_avg"].isna() | (view["tomatoes_avg"] * 100 >= rt_range[0])]
    view = view[view["tomatoes_avg"].isna() | (view["tomatoes_avg"] * 100 <= rt_range[1])]
    view = view[view["rating_tmdb"].isna() | (view["rating_tmdb"] >= tmdb_range[0])]
    view = view[view["rating_tmdb"].isna() | (view["rating_tmdb"] <= tmdb_range[1])]

    # first_episode_date is the min over a film's airings, set when the curated
    # row is built, so a film covered more than once sorts by the date it was
    # first discussed rather than appearing at each of its dates.
    sort_map = {
        "Episode date (newest)": ("first_episode_date", False),
        "Episode date (oldest)": ("first_episode_date", True),
        "Title": ("sort_title", True),
        "Year (newest)": ("year", False),
        "Year (oldest)": ("year", True),
        "TMDB Rating": ("rating_tmdb", False),
        "RT Score": ("tomatoes_avg", False),
        "Ebert Score": ("ebert_avg", False),
        "Runtime": ("runtime_minutes", False),
    }
    # Ties are the rule, not the exception -- Ebert stars take 8 distinct values
    # across 373 films -- and sort_values is not stable, so a single-key sort
    # reshuffled hundreds of cards between runs. Every key but the date itself
    # breaks ties on first airing.
    # The picker sits in the main pane beside the film count, which is below
    # the dossier gate -- but the order is needed above it, because the step
    # arrows walk this result set. So the value is read from state here and the
    # widget that owns it is drawn later. On the run where the reader changes
    # it, session_state already holds the new label, so the two never disagree.
    sort_by = kept("flt_sort", next(iter(sort_map)))
    if sort_by not in sort_map:
        # A stored session value naming an option that no longer exists.
        sort_by = next(iter(sort_map))
    col_s, asc_s = sort_map[sort_by]
    keys = [col_s] if col_s == "first_episode_date" else [col_s, "first_episode_date"]
    order = [asc_s] if len(keys) == 1 else [asc_s, False]
    view = view.sort_values(keys, ascending=order, na_position="last")

    if selected_film:
        render_dossier(selected_film, siblings=view["movie_id"].tolist())
        st.stop()

    masthead("Movie Explorer", "Filter and search every film they have covered.")
    # 7:3 rather than 3:1 -- measured, the select needs ~200px for its widest
    # option ("Episode date (newest)", 147px of text plus padding and chevron)
    # and 3:1 left it 187px, which truncated the default label to an ellipsis.
    head, picker = st.columns([7, 3], vertical_alignment="center")
    with head:
        # The same mono micro-caps every other poster grid puts over itself,
        # rather than st.caption's Source Sans. It leaves the picker as the one
        # bright thing in the row, which is the point: the count is the label
        # and the picker is the control.
        st.markdown(
            f'<div class="rw-kw-gridnote"><span>{len(view)} films match your '
            f"filters</span></div>",
            unsafe_allow_html=True,
        )
    with picker:
        # Same key the read above used. keep() re-seeds it from the shadow on
        # the run after a dossier, which is exactly the run where Streamlit has
        # dropped the widget's own state. The return value goes unused: the
        # sort ran above, on the value this widget is about to display.
        keep(st.selectbox, "Sort by", list(sort_map), key="flt_sort")

    # Poster grid
    COLS = 8
    # The sort key belongs on the card, but eight across leaves a 63px caption
    # strip that holds two facts, not three: measured in the browser, both
    # "1986 RT 93%" and "1986 * Aug 2026" run to two lines, while
    # "1986 * RT 93% * Aug 2026" runs to three and would grow every card in the
    # grid. So sorting by episode date swaps the RT figure out for the airdate
    # rather than appending it. Trimming the date further buys nothing -- a
    # two-digit year measures the same two lines -- so it keeps the full one.
    dated = sort_map[sort_by][0] == "first_episode_date"
    rows = [view.iloc[i : i + COLS] for i in range(0, len(view), COLS)]
    for row_df in rows:
        cols = st.columns(COLS)
        for j, (_, m) in enumerate(row_df.iterrows()):
            with cols[j]:
                if dated:
                    aired = m["first_episode_date"]
                    note = f"· {aired:%b %Y}" if pd.notna(aired) else ""
                else:
                    note = (f"RT {m['tomatoes_avg']*100:.0f}%"
                            if pd.notna(m["tomatoes_avg"]) else "")
                film_card(m, f"{m['year']} {note}".strip(), key="explore")

    st.markdown("---")
    tape("Data table")
    # first_episode_date earns a column because it is the default sort key:
    # ordering by a field the reader cannot see reads as no order at all.
    display_cols = ["title", "year", "first_episode_date", "director_primary",
                    "runtime_minutes", "rating_tmdb", "tomatoes_avg",
                    "ebert_avg", "total_episodes_featured"]
    st.dataframe(
        view[display_cols].assign(
            # Date, not datetime: the column is midnight on every row and the
            # 00:00:00 is noise.
            first_episode_date=view["first_episode_date"].dt.date,
        ).rename(columns={
            "first_episode_date": "first episode",
            "director_primary": "director",
            "runtime_minutes": "runtime",
            "rating_tmdb": "TMDB",
            "tomatoes_avg": "RT score",
            "ebert_avg": "Ebert",
            "total_episodes_featured": "episodes",
        }),
        use_container_width=True,
        hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GENRES
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "genres":
    masthead("Genres", "How the mix shifts across the decades they cover.")

    g_long = explode_genres(movies_df)

    # Row 1: distribution + pie
    col_a, col_b = st.columns([3, 2])

    with col_a:
        tape("Genre frequency")
        g_counts = g_long["genre"].value_counts().reset_index()
        g_counts.columns = ["genre", "count"]
        fig = px.bar(
            g_counts, x="genre", y="count",
            color_discrete_sequence=[MINT_DEEP],
            text="count",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(xaxis_tickangle=-35)
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        tape("Share of films with each genre")
        share, cmap, order = fold_counts(g_counts, "genre", "count")
        fig = px.pie(
            share, values="count", names="genre",
            color="genre", color_discrete_map=cmap,
            category_orders={"genre": order},
            hole=0.4,
        )
        fig.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre by decade heatmap
    tape("Genre popularity by decade")
    g_decade = (
        explode_genres(movies_df)
        .groupby(["decade", "genre"])
        .size()
        .reset_index(name="count")
    )
    top8 = g_counts.head(10)["genre"].tolist()
    g_decade_f = g_decade[g_decade["genre"].isin(top8)]
    pivot = g_decade_f.pivot_table(index="genre", columns="decade", values="count", fill_value=0)
    pivot.columns = [f"{int(c)}s" for c in pivot.columns]

    fig = px.imshow(
        pivot,
        color_continuous_scale=SEQ,
        text_auto=True,
        aspect="auto",
    )
    fig.update_layout(
        paper_bgcolor=INK,
        font_color=TAPE,
        coloraxis_showscale=False,
        margin=dict(t=30, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre co-occurrence
    tape("Genre co-occurrence (films with both genres)")
    genre_pairs = Counter()
    for genres in movies_df["genres"]:
        for pair in combinations(sorted(genres), 2):
            genre_pairs[pair] += 1

    if genre_pairs:
        pair_df = pd.DataFrame(
            [(a, b, n) for (a, b), n in genre_pairs.most_common(20)],
            columns=["genre_a", "genre_b", "count"],
        )
        fig = px.bar(
            pair_df,
            x="count", y=pair_df["genre_a"] + " + " + pair_df["genre_b"],
            orientation="h",
            color_discrete_sequence=[MINT_DEEP],
            text="count",
        )
        fig.update_layout(yaxis_title="")
        fig.update_traces(textposition="outside")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre-specific poster shelf
    tape("Browse by genre")
    chosen_genre = keep(
        st.selectbox, "Pick a genre", sorted(set(g_long["genre"])), key="flt_genre_shelf")
    genre_movies = movies_df[movies_df["genres"].apply(lambda g: chosen_genre in g)].sort_values("rating_tmdb", ascending=False)
    st.caption(f"{len(genre_movies)} films tagged {chosen_genre}")

    cols = st.columns(10)
    for i, (_, m) in enumerate(genre_movies.head(30).iterrows()):
        with cols[i % 10]:
            film_card(m, str(m["year"]), key="genre")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DIRECTORS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "directors":
    masthead(
        "Directors",
        "Who gets called back to the chair, and what their covered work looks like.",
    )

    # Every curated film carries exactly one director, so director_primary is
    # the director -- no credit-splitting to reconcile.
    dir_counts = movies_rated["director_primary"].value_counts()
    dir_counts = dir_counts[dir_counts.index != "Unknown"]

    # Numbers only: the leaderboard immediately below already names who leads,
    # and a name set in the tile's display face wraps and breaks the row.
    stat_tiles([
        ("Directors", f"{dir_counts.size:,}"),
        ("Just one film", f"{int((dir_counts == 1).sum()):,}"),
        ("Two or more", f"{int((dir_counts >= 2).sum()):,}"),
        ("Four or more", f"{int((dir_counts >= 4).sum()):,}"),
        ("Films covered", f"{len(movies_rated):,}"),
    ])

    st.markdown("---")

    top_dirs = dir_counts.head(20)
    top_dirs = pd.DataFrame(
        {"director": top_dirs.index, "films": top_dirs.to_numpy()})
    people_leaderboard(top_dirs, "director", "Most-featured directors")
    st.markdown(
        f'<p class="ch-note">{int((dir_counts >= 2).sum())} directors have more '
        f"than one film covered, out of {dir_counts.size:,}. The long tail is "
        "most of the catalogue &mdash; the show ranges wider than it repeats.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Director spotlight")
    sel_dir = keep(
        st.selectbox, "Director", top_dirs["director"].tolist(), key="flt_dir_pick")
    dir_films = films_by_director(sel_dir)

    regulars = Counter(
        name
        for cast in dir_films["cast_names"]
        for name in (cast[:BILLED] if isinstance(cast, list) else [])
    )
    person_spotlight(
        dir_films,
        key="director",
        collab_title="Actors they bring back",
        collab_pairs=[(n, k) for n, k in regulars.most_common(6) if k >= 2],
        collab_empty=f"No actor is credited on more than one {sel_dir} film here.",
        collab_note="Credited on two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    dir_stats = (
        movies_rated[movies_rated["director_primary"] != "Unknown"]
        .groupby("director_primary").agg(**PERSON_AGG).reset_index()
        .rename(columns={"director_primary": "director"})
    )
    people_scatter(dir_stats[dir_stats["films"] >= 2], "director", "director")
    st.markdown(
        '<p class="ch-note">Directors with two or more covered films; bubble size '
        "is average runtime. Only those with four or more are named &mdash; the rest "
        "are on hover. Being covered often and being rated well are weakly related "
        "for directors &mdash; <b>r = 0.30</b> across these 97 &mdash; so the show "
        "does lean slightly toward the better-reviewed, but it explains little of "
        "the spread.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every director, ranked")
    st.dataframe(
        dir_stats.sort_values(["films", "avg_tmdb"], ascending=[False, False])
        # tomatoes_avg is a 0-1 fraction; the column format appends the sign but
        # does not scale, so 0.75 would print as "1%".
        .assign(avg_rt=lambda d: d["avg_rt"] * 100)
        .rename(columns={
            "director": "Director", "films": "Films", "avg_tmdb": "Avg TMDB",
            "avg_rt": "Avg RT", "avg_runtime": "Avg runtime",
            "first_year": "First", "last_year": "Last",
        }),
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Avg TMDB": st.column_config.NumberColumn(format="%.2f"),
            "Avg RT": st.column_config.NumberColumn(format="%.0f%%"),
            "Avg runtime": st.column_config.NumberColumn(format="%.0f"),
            "First": st.column_config.NumberColumn(format="%d"),
            "Last": st.column_config.NumberColumn(format="%d"),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — ACTORS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "actors":
    masthead(
        "Actors",
        "Who keeps turning up on screen, and the films they turn up in.",
    )

    # Counts every name in the stored cast list, so supporting and minor roles
    # land in an actor's filmography alongside the leads.
    cast_all = explode_cast(movies_rated, top_n=100_000)

    stat_tiles([
        ("Actors", f"{len(cast_all):,}"),
        ("Just one film", f"{int((cast_all['count'] == 1).sum()):,}"),
        ("Three or more", f"{int((cast_all['count'] >= 3).sum()):,}"),
        ("Five or more", f"{int((cast_all['count'] >= 5).sum()):,}"),
        ("Films covered", f"{len(movies_rated):,}"),
    ])

    # The gender row. Counted in credits, not people: a film's billed cast is
    # ten slots, and "who gets cast" is a question about slots. Rendered only
    # when the dimension is populated, so a database that has not been through
    # the cast_ids pass keeps the ungendered section it had before.
    by_gender = {g: explode_cast(movies_rated, top_n=100_000, gender=g)
                 for g in GENDERS}
    credits_by_gender = {g: int(by_gender[g]["count"].sum()) for g in GENDERS}
    credits_total = sum(credits_by_gender.values())
    if credits_total and credits_by_gender["unknown"] < credits_total:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        # Every gender with a credit gets a tile, including the two the split
        # below has no column for. Four non-binary credits is a small number to
        # print, and printing it is the difference between a split that omits
        # them and one that pretends they are not there. Actor counts are not
        # repeated here -- they head the two columns below.
        tiles = [(GENDER_LABEL[g],
                  f"{credits_by_gender[g]:,} · {credits_by_gender[g]/credits_total:.0%}")
                 for g in ("M", "F")]
        if credits_by_gender["NB"]:
            tiles.append((GENDER_LABEL["NB"], f"{credits_by_gender['NB']:,}"))
        tiles.append((GENDER_LABEL["unknown"], f"{credits_by_gender['unknown']:,}"))
        stat_tiles(tiles)
        st.markdown(
            '<p class="ch-note">Billed credits, not people: a film contributes '
            "ten cast slots, and who gets cast is a question about slots. One "
            "actor in five films is five credits.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    top_actors = cast_all.head(20).rename(columns={"count": "films"})
    people_leaderboard(top_actors, "actor", "Most-featured actors", colour=AMBER)
    st.markdown(
        '<p class="ch-note">Every credited name TMDB lists, so a supporting turn '
        "counts the same as a lead. That widens the field considerably: "
        f"{int((cast_all['count'] == 1).sum()):,} of these "
        f"{len(cast_all):,} appear in a single film.</p>",
        unsafe_allow_html=True,
    )

    if credits_total and credits_by_gender["unknown"] < credits_total:
        st.markdown("---")

        gender_split_leaderboards(
            movies_rated, "Most-featured actors, by gender", top_n=15)

        # The two figures the pair is for: where the first woman lands in the
        # combined ranking, and how far apart the two peaks are.
        ranked_names = list(cast_all["actor"])
        first_woman = next(
            (i + 1 for i, n in enumerate(ranked_names)
             if GENDER_MAP.get(n) == "F"), None)
        men_top = by_gender["M"]["count"].max() if len(by_gender["M"]) else 0
        women_top = by_gender["F"]["count"].max() if len(by_gender["F"]) else 0
        st.markdown(
            '<p class="ch-note">Both columns share one x-axis, so the gap is '
            "the finding rather than a rendering accident: the most-featured "
            f"man has <b>{men_top}</b> covered films against "
            f"<b>{women_top}</b> for the most-featured woman. "
            + (f"The first woman in the combined ranking above is at "
               f"<b>#{first_woman}</b>. " if first_woman else "")
            + "Gender is what TMDB records for the credited performer; "
            f"{credits_by_gender['unknown']:,} of {credits_total:,} credits "
            "have none recorded and are counted in neither column.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    tape("Actor spotlight")
    sel_actor = keep(
        st.selectbox, "Actor", top_actors["actor"].tolist(), key="flt_actor_pick")
    actor_films = films_by_actor(sel_actor)

    worked_with = Counter(actor_films["director_primary"])
    worked_with.pop("Unknown", None)
    # Same "two or more" rule as the Directors spotlight. Listing the one-film
    # pairings too would fill the panel with rows that say nothing -- recurring
    # director/actor pairs are rare here, and that is the finding.
    person_spotlight(
        actor_films,
        key="actor",
        collab_title="Directors they return to",
        collab_pairs=[(n, k) for n, k in worked_with.most_common(6) if k >= 2],
        collab_empty=f"{sel_actor} has one film with each of these directors — "
                     "no repeat pairing in the catalogue.",
        collab_note="Directors of two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    actor_stats = (
        billed_long(movies_rated).groupby("actor").agg(**PERSON_AGG).reset_index()
    )
    actor_stats = actor_stats[actor_stats["films"] >= 3]
    people_scatter(actor_stats, "actor", "actor", name_from=8)
    st.markdown(
        '<p class="ch-note">Actors with three or more covered films; bubble size '
        "is average runtime. Only those with eight or more are named &mdash; the "
        "rest are on hover. For actors the link between being cast often and being "
        "in well-rated films is <b>absent &mdash; r = 0.08</b>. Of "
        f"{len(cast_all):,} actors, {int((cast_all['count'] >= 8).sum())} clear "
        "eight films.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every actor with 3+ films")
    # Gender comes in as a column here rather than as a filter: the table is
    # already sortable and searchable, so a column lets the reader slice it
    # without another widget to keep in session state.
    st.dataframe(
        actor_stats.sort_values(["films", "avg_tmdb"], ascending=[False, False])
        .assign(avg_rt=lambda d: d["avg_rt"] * 100,   # see note in Directors
                gender=lambda d: d["actor"].map(
                    lambda n: GENDER_LABEL.get(GENDER_MAP.get(n, "unknown"))))
        .rename(columns={
            "actor": "Actor", "gender": "Gender", "films": "Films",
            "avg_tmdb": "Avg TMDB",
            "avg_rt": "Avg RT", "avg_runtime": "Avg runtime",
            "first_year": "First", "last_year": "Last",
        })[["Actor", "Gender", "Films", "Avg TMDB", "Avg RT", "Avg runtime",
            "First", "Last"]],
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Avg TMDB": st.column_config.NumberColumn(format="%.2f"),
            "Avg RT": st.column_config.NumberColumn(format="%.0f%%"),
            "Avg runtime": st.column_config.NumberColumn(format="%.0f"),
            "First": st.column_config.NumberColumn(format="%d"),
            "Last": st.column_config.NumberColumn(format="%d"),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — RATINGS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "ratings":
    masthead(
        "Ratings",
        "Rotten Tomatoes, Ebert stars and TMDB audience scores, side by side.",
    )

    # Build per-episode ratings merged with movie data
    rated = merged_df.dropna(subset=["movie_id"]).copy()

    # Row 1: distribution histograms
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        tape("Rotten Tomatoes scores")
        rt_vals = rated["tomatoes_num"].dropna()
        fig = px.histogram(
            rt_vals * 100, nbins=20,
            color_discrete_sequence=[MINT_DEEP],
            labels={"value": "RT Score %"},
        )
        fig.add_vline(x=float(rt_vals.mean() * 100), line_dash="dash", line_color=TAPE,
                      annotation_text=f"avg {rt_vals.mean()*100:.1f}%")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        tape("Ebert star ratings")
        ebert_vals = rated["ebert_num"].dropna()
        counts = ebert_vals.value_counts().sort_index().reset_index()
        counts.columns = ["stars", "count"]
        counts["stars"] = counts["stars"].apply(lambda x: f"{'★' * int(x)}{'½' if x % 1 else ''}")
        fig = px.bar(counts, x="stars", y="count", color_discrete_sequence=[MINT_DEEP])
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_c:
        tape("TMDB audience rating")
        tmdb_vals = movies_df["rating_tmdb"].dropna()
        fig = px.histogram(
            tmdb_vals, nbins=20,
            color_discrete_sequence=[AMBER],
            labels={"value": "TMDB Rating"},
        )
        fig.add_vline(x=float(tmdb_vals.mean()), line_dash="dash", line_color=TAPE,
                      annotation_text=f"avg {tmdb_vals.mean():.2f}")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # RT vs TMDB scatter
    tape("Rotten Tomatoes vs TMDB rating")
    scatter_data = rated.dropna(subset=["tomatoes_num", "rating_tmdb"]).drop_duplicates("movie_id").copy()
    fig = px.scatter(
        scatter_data,
        x="tomatoes_num", y="rating_tmdb",
        color="genre_primary",
        hover_name="title",
        hover_data={"year": True, "tomatoes_num": ":.0%", "rating_tmdb": ":.1f"},
        labels={"tomatoes_num": "RT Score", "rating_tmdb": "TMDB Rating"},
        opacity=0.8,
        size_max=10,
    )
    fig.update_layout(
        paper_bgcolor=INK,
        plot_bgcolor=INK_2,
        font_color=TAPE,
        legend_bgcolor=INK_2,
        xaxis=dict(gridcolor=LINE, tickformat=".0%"),
        yaxis=dict(gridcolor=LINE),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre vs ratings box plots
    tape("RT score distribution by genre")
    g_rated = explode_genres(rated.dropna(subset=["tomatoes_num"]))
    top10_genres = g_rated["genre"].value_counts().head(10).index
    g_rated_f = g_rated[g_rated["genre"].isin(top10_genres)]
    fig = px.box(
        g_rated_f.sort_values("genre"),
        x="genre", y="tomatoes_num",
        color_discrete_sequence=[MINT_DEEP],
        labels={"tomatoes_num": "RT Score", "genre": ""},
        points="outliers",
    )
    fig.update_layout(showlegend=False, yaxis_tickformat=".0%")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Outlier table — high RT + low TMDB or vice versa
    tape("Ratings divergence — critics vs audience")
    div = scatter_data.copy()
    div["rt_pct"] = div["tomatoes_num"] * 100
    div["diff"] = div["rt_pct"] - (div["rating_tmdb"] * 10)
    top_critic = div.nlargest(5, "diff")[["title", "year", "rt_pct", "rating_tmdb", "diff"]]
    top_audience = div.nsmallest(5, "diff")[["title", "year", "rt_pct", "rating_tmdb", "diff"]]

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.markdown("**Critics love, audiences cooler on**")
        st.dataframe(
            top_critic.rename(columns={"rt_pct": "RT %", "rating_tmdb": "TMDB", "diff": "Δ"}),
            hide_index=True, use_container_width=True,
        )
    with col_d2:
        st.markdown("**Audiences love, critics cooler on**")
        st.dataframe(
            top_audience.rename(columns={"rt_pct": "RT %", "rating_tmdb": "TMDB", "diff": "Δ"}),
            hide_index=True, use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — BOX OFFICE
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "boxoffice":
    masthead(
        "Box Office",
        f"What these films cost, what they took, and what came back &mdash; "
        f"every figure in {CPI_BASE_YEAR} dollars.",
    )

    fin = movies_df[movies_df["revenue_real"].notna()].copy()
    settled = fin[~fin["money_provisional"]]
    with_both = settled[settled["multiple"].notna()]
    n_short = int((with_both["multiple"] < BREAK_EVEN_MULTIPLE).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Films with a gross", f"{len(fin)} / {len(movies_df)}")
    c2.metric(f"Median gross ({CPI_BASE_YEAR}$)", money(fin["revenue_real"].median()))
    c3.metric(f"Median budget ({CPI_BASE_YEAR}$)", money(fin["budget_real"].median()))
    c4.metric("Median return", f"{with_both['multiple'].median():.1f}×")
    c5.metric("Under break-even", f"{n_short} / {len(with_both)}")

    st.caption(
        f"Gross and budget come from TMDB and are worldwide theatrical, "
        f"converted to {CPI_BASE_YEAR} dollars with US CPI-U. Return is gross ÷ "
        f"budget: it is not profit, since neither figure includes marketing or "
        f"the exhibitor's share, so the break-even line is drawn at the "
        f"industry rule of thumb of {BREAK_EVEN_MULTIPLE:g}×, not 1×. "
        f"{len(movies_df) - len(fin)} films have no published gross and "
        f"{int(movies_df['budget_real'].isna().sum())} no budget; they are "
        f"absent from these charts rather than counted as zero."
    )

    st.markdown("---")

    # ── Gross by decade ──
    # The chart the section exists for. Drawn from CMU it was an artefact of a
    # 2012 Freebase snapshot; drawn nominal it was a picture of CPI.
    tape(f"Gross by release decade ({CPI_BASE_YEAR} dollars)")
    dec = fin.dropna(subset=["decade"]).copy()
    dec["decade_label"] = dec["decade"].astype(int).astype(str) + "s"
    counts = dec["decade_label"].value_counts()
    order = sorted(dec["decade_label"].unique())

    fig = go.Figure()
    for label in order:
        vals = dec.loc[dec["decade_label"] == label, "revenue_real"]
        fig.add_trace(go.Box(
            y=vals, name=label, marker_color=MINT_DEEP, line_color=MINT_DEEP,
            fillcolor="rgba(23,168,124,.18)", boxpoints="outliers",
            marker_size=4, showlegend=False,
        ))
    fig.update_layout(
        yaxis_title=f"Worldwide gross ({CPI_BASE_YEAR}$)",
        xaxis_title="Release decade", yaxis_type="log",
    )
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    thin = [f"{lbl} ({counts[lbl]})" for lbl in order if counts[lbl] < 10]
    if thin:
        st.caption(
            "Log scale. Decades carrying fewer than ten films — "
            + ", ".join(thin)
            + " — are too thin to read as a trend."
        )

    st.markdown("---")

    # ── Budget against gross ──
    tape("What it cost against what it took")
    scat = settled.dropna(subset=["budget_real", "revenue_real", "multiple"]).copy()
    scat["Outcome"] = np.where(
        scat["multiple"] >= BREAK_EVEN_MULTIPLE,
        f"Cleared {BREAK_EVEN_MULTIPLE:g}×", f"Under {BREAK_EVEN_MULTIPLE:g}×")
    fig = px.scatter(
        scat, x="budget_real", y="revenue_real", color="Outcome",
        color_discrete_map={f"Cleared {BREAK_EVEN_MULTIPLE:g}×": MINT_DEEP,
                            f"Under {BREAK_EVEN_MULTIPLE:g}×": CORAL},
        hover_name="title", hover_data={"year": True, "multiple": ":.1f",
                                        "budget_real": False, "revenue_real": False},
        log_x=True, log_y=True,
        labels={"budget_real": f"Budget ({CPI_BASE_YEAR}$)",
                "revenue_real": f"Worldwide gross ({CPI_BASE_YEAR}$)"},
    )
    fig.update_traces(marker=dict(size=7, opacity=0.8, line=dict(width=0)))
    lo = float(scat["budget_real"].min())
    hi = float(scat["budget_real"].max())
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo * BREAK_EVEN_MULTIPLE, hi * BREAK_EVEN_MULTIPLE],
        mode="lines", line=dict(color=TXT_3, width=1, dash="dash"),
        name=f"{BREAK_EVEN_MULTIPLE:g}× break-even", hoverinfo="skip",
    ))
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Both axes log. {len(scat) - n_short} of {len(scat)} films cleared the "
        f"line; the {n_short} below it are the ones the show likes anyway."
    )

    st.markdown("---")

    # ── The multiple, both ends ──
    tape("The best returns, and the worst")
    lead, lag = st.columns(2)
    with lead:
        st.markdown("**Most returned per dollar spent**")
        top = with_both.nlargest(10, "multiple")
        st.dataframe(
            pd.DataFrame({
                "Film": top["title"],
                "Year": top["year"],
                "Budget": top["budget_real"].map(money),
                "Gross": top["revenue_real"].map(money),
                "Return": top["multiple"].map(lambda v: f"{v:,.0f}×"),
            }), hide_index=True, use_container_width=True)
    with lag:
        st.markdown("**Lost the most, and got an episode anyway**")
        bot = with_both.nsmallest(10, "multiple")
        st.dataframe(
            pd.DataFrame({
                "Film": bot["title"],
                "Year": bot["year"],
                "Budget": bot["budget_real"].map(money),
                "Gross": bot["revenue_real"].map(money),
                "Return": bot["multiple"].map(lambda v: f"{v:.2f}×"),
            }), hide_index=True, use_container_width=True)

    prov = movies_df[movies_df["money_provisional"] & movies_df["revenue_real"].notna()]
    if len(prov):
        st.caption(
            "Excludes " + ", ".join(f"{r.title} ({int(r.year)})"
                                    for r in prov.itertuples())
            + f" — released {CPI_PROVISIONAL_FROM} or later, so the gross is "
            "still moving and the budget is often a placeholder. TMDB has one "
            "of them at a $750K budget against a $506M gross."
        )

    st.markdown("---")

    # ── Money against merit ──
    tape("Does the money track the rating?")
    merit = fin.dropna(subset=["rating_tmdb", "revenue_real"])
    rho = merit["revenue_real"].corr(merit["rating_tmdb"], method="spearman")
    fig = px.scatter(
        merit, x="revenue_real", y="rating_tmdb", log_x=True,
        hover_name="title", hover_data={"year": True, "revenue_real": False},
        labels={"revenue_real": f"Worldwide gross ({CPI_BASE_YEAR}$)",
                "rating_tmdb": "TMDB rating"},
    )
    fig.update_traces(marker=dict(size=7, opacity=0.75, color=BLUE,
                                  line=dict(width=0)))
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Spearman ρ = {rho:.2f} over {len(merit)} films — a weak positive "
        "relationship. Money and merit are close to independent here, which is "
        "the whole premise of a show that will spend an hour on a film that "
        "lost its studio money."
    )

    st.markdown("---")

    # ── Genre ──
    tape(f"Median gross by genre ({CPI_BASE_YEAR} dollars)")
    g_long = fin.explode("genres").dropna(subset=["genres"])
    g_stat = (g_long.groupby("genres")
              .agg(median_gross=("revenue_real", "median"), films=("movie_id", "size"))
              .reset_index())
    g_stat = g_stat[g_stat["films"] >= 5].sort_values("median_gross")
    fig = go.Figure(go.Bar(
        x=g_stat["median_gross"], y=g_stat["genres"], orientation="h",
        marker_color=MINT_DEEP, marker_line_width=0,
        customdata=g_stat["films"],
        hovertemplate="%{y}<br>%{x:$,.0f}<br>%{customdata} films<extra></extra>",
    ))
    fig.update_layout(xaxis_title=f"Median gross ({CPI_BASE_YEAR}$)", yaxis_title="")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Genres carrying fewer than five films are omitted.")

    st.markdown("---")

    # ── Table ──
    tape("Data table")
    table = fin.sort_values("revenue_real", ascending=False)
    st.dataframe(
        pd.DataFrame({
            "Film": table["title"],
            "Year": table["year"],
            f"Budget ({CPI_BASE_YEAR}$)": table["budget_real"].map(money),
            f"Gross ({CPI_BASE_YEAR}$)": table["revenue_real"].map(money),
            "Return": table["multiple"].map(
                lambda v: f"{v:,.1f}×" if pd.notna(v) else "—"),
            "TMDB": table["rating_tmdb"].round(1),
            "Episodes": table["total_episodes_featured"],
        }), hide_index=True, use_container_width=True, height=420)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — CRUISE VS. HANKS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "verdicts":
    n_ch = len(ch_df)
    n_cruise = int((ch_df["verdict"] == "Cruise").sum())
    n_hanks = int((ch_df["verdict"] == "Hanks").sum())
    n_tie = int((ch_df["verdict"] == "Tie").sum())

    # The bit is a modern-era feature: all but one verdict falls in a contiguous
    # run from ep 350 (Mar 2024). The lone earlier one -- ep 105 -- stays in the
    # ledger but is kept out of the time series, which would otherwise draw a
    # five-year flat line to a single stray point.
    RUN_START = 350
    run = ch_df[ch_df["episode_number"] >= RUN_START].sort_values("episode_number")
    n_early = n_ch - len(run)

    # ── Fight-card header ─────────────────────────────────────────────────────
    # The poster rails are each actor's own films as covered by the podcast,
    # ranked by TMDB popularity so "most iconic" is read off the data rather
    # than hand-picked. Both men are well represented: 18 films and 11.
    def _films_with(actor, limit=7):
        hits = movies_df[movies_df["cast_names"].apply(lambda c: actor in c)]
        hits = hits.dropna(subset=["poster_url_tmdb"])
        return hits.nlargest(limit, "popularity_tmdb")

    def _rail(actor, side):
        posters = "".join(
            f'<img src="{r.poster_url_tmdb.replace("/w500/", "/w342/")}" '
            f'alt="" loading="lazy">'
            for r in _films_with(actor).itertuples()
        )
        return f'<div class="ch-rail {side}">{posters}</div>'

    n_cruise_films = int(movies_df["cast_names"].apply(lambda c: "Tom Cruise" in c).sum())
    n_hanks_films = int(movies_df["cast_names"].apply(lambda c: "Tom Hanks" in c).sum())

    st.markdown(
        '<div class="ch-hero">'
        + _rail("Tom Cruise", "l")
        + _rail("Tom Hanks", "r")
        + '<div class="ch-hero-inner">'
        + '<div class="ch-fighter">'
        + f'<div class="ch-face c"><img src="{TMDB_PROFILE}{CRUISE_PORTRAIT}" '
          'alt="Tom Cruise"></div>'
        + f'<div><div class="ch-name c">TOM<br>CRUISE</div>'
          f'<div class="ch-tally">{n_cruise}</div>'
          f'<div class="ch-sub">{n_cruise_films} films covered</div></div>'
        + "</div>"
        + '<div class="ch-vs">'
          f'<div class="bolt">EP {int(ch_df["episode_number"].min())} &ndash; '
          f'{int(ch_df["episode_number"].max())}</div>'
          '<div class="q">Who ya got?</div>'
          f'<div class="blurb">{n_tie} ties</div></div>'
        + '<div class="ch-fighter r">'
        + f'<div class="ch-face h"><img src="{TMDB_PROFILE}{HANKS_PORTRAIT}" '
          'alt="Tom Hanks"></div>'
        + f'<div><div class="ch-name h">TOM<br>HANKS</div>'
          f'<div class="ch-tally">{n_hanks}</div>'
          f'<div class="ch-sub">{n_hanks_films} films covered</div></div>'
        + "</div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="ch-note" style="margin-top:14px">At the end of an episode the '
        "room picks which of the two would have been better in the film. "
        f"<b>{n_ch} verdicts</b> on the board, and it is very nearly a tie.</p>",
        unsafe_allow_html=True,
    )

    # ── Scoreboard ────────────────────────────────────────────────────────────
    # The header carries the two totals, so this is just the proportion.
    tape("The standing")
    pc, ph, pt = (100 * n / n_ch for n in (n_cruise, n_hanks, n_tie))
    st.markdown(
        f'<div class="ch-tug">'
        f'<div class="c" style="width:{pc}%">{n_cruise} &nbsp;CRUISE</div>'
        f'<div class="t" style="width:{pt}%">{n_tie}</div>'
        f'<div class="h" style="width:{ph}%">HANKS&nbsp; {n_hanks}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="ch-note">A {abs(n_cruise - n_hanks)}-verdict margin across '
        f"{n_ch} episodes. <b>Nothing here is a landslide</b> &mdash; which is why "
        "the running margin below is the more interesting picture.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Running margin ────────────────────────────────────────────────────────
    # Cumulative Cruise-minus-Hanks. A donut can only ever show the final total;
    # this is the chart that shows the lead changing hands.
    tape(f"Running margin, ep {RUN_START} &rarr; {int(run['episode_number'].max())}")
    marg = run.copy()
    marg["step"] = marg["verdict"].map({"Cruise": 1, "Hanks": -1, "Tie": 0})
    marg["margin"] = marg["step"].cumsum()
    lead_changes = int((np.sign(marg["margin"]).diff().fillna(0) != 0).sum())

    # Expand to explicit step vertices so the fill can be split at zero. The
    # series only ever crosses zero on a vertical segment (x is constant there),
    # so clipping with maximum/minimum is exact -- no interpolation needed, and
    # the area above the line reads amber for Cruise, below it blue for Hanks.
    xs = np.repeat(marg["episode_number"].to_numpy(), 2)[1:]
    ys = np.repeat(marg["margin"].to_numpy(), 2)[:-1]

    fig = go.Figure()
    for clip, colour in ((np.maximum(ys, 0), "rgba(201,133,0,.28)"),
                         (np.minimum(ys, 0), "rgba(74,143,224,.28)")):
        fig.add_trace(go.Scatter(
            x=xs, y=clip, mode="lines", line=dict(width=0),
            fill="tozeroy", fillcolor=colour, hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=marg["episode_number"], y=marg["margin"],
        line_shape="hv", mode="lines", line=dict(color=TAPE, width=1.6),
        customdata=np.stack([marg["movie_title"], marg["verdict"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>ep %{x} · %{customdata[1]}"
                      "<br>margin %{y:+d}<extra></extra>",
        showlegend=False, name="",
    ))
    fig.add_hline(y=0, line_color=LINE_2, line_width=1.4)
    fig.update_yaxes(title_text="← Hanks     Cruise →", zeroline=False)
    fig.update_xaxes(title_text="Episode")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
    excluded = (
        f" Excludes {n_early} earlier verdict"
        f"{'' if n_early == 1 else 's'} before ep {RUN_START}."
        if n_early else ""
    )
    st.markdown(
        f'<p class="ch-note">Cumulative Cruise wins minus Hanks wins. The lead '
        f"changed hands <b>{lead_changes} times</b>; neither man was ever more than "
        f"<b>{int(marg['margin'].abs().max())} verdicts</b> clear.{excluded}</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Genre lean — the one dimension that actually separates the camps ──────
    tape("What actually decides it: genre")
    g_ch = ch_df.explode("genres").dropna(subset=["genres"])
    g_tab = (
        g_ch.pivot_table(index="genres", columns="verdict",
                         aggfunc="size", fill_value=0)
        .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
    )
    g_tab["n"] = g_tab.sum(axis=1)
    g_tab = g_tab[g_tab["n"] >= 8].copy()
    g_tab["lean"] = (g_tab["Cruise"] - g_tab["Hanks"]) / g_tab["n"]
    # Ascending lean puts the most Hanks-leaning genre first, and Plotly draws
    # the first horizontal category at the BOTTOM -- so the chart runs Cruise at
    # the top down to Hanks at the bottom.
    g_tab = g_tab.sort_values("lean")

    # Cruise reads left, Hanks right, matching the header portraits and the
    # standing bar. Cruise therefore takes the negative half of the axis.
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=g_tab.index, x=-g_tab["Cruise"], orientation="h",
        marker_color=AMBER, name="Cruise",
        text=g_tab["Cruise"], textposition="inside", insidetextanchor="start",
        hovertemplate="%{y} · Cruise %{text}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=g_tab.index, x=g_tab["Hanks"], orientation="h",
        marker_color=BLUE, name="Hanks",
        text=g_tab["Hanks"], textposition="inside", insidetextanchor="end",
        hovertemplate="%{y} · Hanks %{text}<extra></extra>",
    ))
    fig.update_layout(barmode="relative", bargap=0.3, height=34 * len(g_tab) + 120)
    fig.update_xaxes(
        title_text="← CRUISE          HANKS →",
        tickvals=[-30, -20, -10, 0, 10, 20, 30],
        ticktext=["30", "20", "10", "0", "10", "20", "30"],
    )
    fig.update_yaxes(title_text="")
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        '<p class="ch-note">Genres with 8+ verdicts. <b>The pattern is '
        "typecasting:</b> Cruise takes the action and thriller slots, Hanks takes "
        "comedy, and everything else is close to even. Films carry multiple genres, "
        "so these buckets overlap &mdash; read it as one pattern, not one finding "
        "per row.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Tale of the tape — reported as the null result it is ──────────────────
    tape("Tale of the tape")
    tape_rows = [
        ("Release year", "movie_year", "{:.1f}"),
        ("Runtime (min)", "runtime_minutes", "{:.1f}"),
        ("TMDB rating", "rating_tmdb", "{:.2f}"),
        ("Rotten Tomatoes", "tomatoes_num", "{:.1%}"),
        ("Ebert stars", "ebert_num", "{:.2f}"),
    ]
    # Every gap here is small against the spread *within* each camp, which is the
    # honest way to show a null without pulling in a hypothesis-test dependency.
    # Ratios are quoted rather than asserted so this stays true as data changes.
    tot, ratios = [], []
    for label, col, fmt in tape_rows:
        cv = ch_df.loc[ch_df["verdict"] == "Cruise", col].dropna()
        hv = ch_df.loc[ch_df["verdict"] == "Hanks", col].dropna()
        gap = abs(cv.mean() - hv.mean())
        spread = float(pd.concat([cv, hv]).std())
        ratios.append(gap / spread if spread else 0.0)
        tot.append({
            "Average film in each camp": label,
            "Cruise": fmt.format(cv.mean()),
            "Hanks": fmt.format(hv.mean()),
            "Gap": fmt.format(gap),
            "Spread (SD)": fmt.format(spread),
            "Gap ÷ SD": f"{ratios[-1]:.2f}",
            "Films rated": f"{len(cv)} / {len(hv)}",
        })
    st.dataframe(pd.DataFrame(tot), hide_index=True, use_container_width=True)
    st.markdown(
        '<div class="ch-null"><b>Reported as a null result.</b> Era, length and '
        "quality do not separate the two camps: the largest gap is "
        f"<b>{max(ratios):.2f} standard deviations</b>, and the rest are smaller. "
        "Differences this size are what you would expect from two random halves of "
        "the same pile. Genre is the only dimension that moves the verdict.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Longest runs ──────────────────────────────────────────────────────────
    tape("Longest runs")
    seq = run.reset_index(drop=True)
    streaks, start = [], 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq.loc[i, "verdict"] != seq.loc[start, "verdict"]:
            streaks.append((seq.loc[start, "verdict"], i - start, start, i - 1))
            start = i
    streaks = [s for s in streaks if s[0] != "Tie"]
    streaks.sort(key=lambda t: -t[1])

    cols = st.columns(4)
    for col, (verdict, length, a, b) in zip(cols, streaks[:4]):
        colour = "#E8A21F" if verdict == "Cruise" else "#7BB0EE"
        films = " &middot; ".join(seq.loc[a:b, "movie_title"])
        with col:
            st.markdown(
                f'<div class="ch-streak"><div class="n" style="color:{colour}">'
                f"{length}</div>"
                f'<div class="lbl">{verdict.upper()} &middot; EP '
                f'{int(seq.loc[a, "episode_number"])}&ndash;'
                f'{int(seq.loc[b, "episode_number"])}</div>'
                f'<div class="films">{films}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Who's in the room ─────────────────────────────────────────────────────
    tape("Who&rsquo;s in the room")
    guests = (
        ch_df.melt(
            id_vars=["episode_number", "verdict"],
            value_vars=["guest1", "guest2", "guest3", "guest4"],
            value_name="guest",
        )
        .dropna(subset=["guest"])
    )
    guests = guests[~guests["guest"].isin(["nan", ""])]
    g_tab2 = (
        guests.pivot_table(index="guest", columns="verdict",
                           aggfunc="size", fill_value=0)
        .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
    )
    g_tab2["n"] = g_tab2.sum(axis=1)
    g_tab2 = g_tab2[g_tab2["n"] >= VERDICT_FLOOR].sort_values("n", ascending=False)

    for name, r in g_tab2.iterrows():
        c, h, t, n = int(r["Cruise"]), int(r["Hanks"]), int(r["Tie"]), int(r["n"])
        st.markdown(
            f'<div class="ch-guest"><div class="gn">{name}</div>'
            f'<div class="bar">'
            f'<i style="width:{100*c/n}%;background:{AMBER}"></i>'
            f'<i style="width:{100*t/n}%;background:{TXT_3}"></i>'
            f'<i style="width:{100*h/n}%;background:{BLUE}"></i></div>'
            f'<div class="num">{c}&ndash;{h} &middot; n={n}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<p class="ch-note">Guests in {VERDICT_FLOOR}+ verdict episodes. The leans are '
        "<b>suggestive, not established</b> &mdash; at these sample sizes a couple "
        "of episodes moves any of these bars noticeably.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── The full ledger ───────────────────────────────────────────────────────
    tape("The full ledger")
    f1, f2 = st.columns([1, 2])
    with f1:
        pick = keep(st.selectbox, "Verdict", ["All", "Cruise", "Hanks", "Tie"], key="flt_verdict")
    with f2:
        term = st.text_input("Filter by title", "")

    led = ch_df.sort_values("episode_number", ascending=False)
    if pick != "All":
        led = led[led["verdict"] == pick]
    if term:
        led = led[led["movie_title"].str.contains(term, case=False, na=False)]

    st.caption(f"{len(led)} of {n_ch} verdicts &middot; newest first")

    if led.empty:
        st.info("No verdicts match those filters.")
    else:
        # film_card wants the curated column names, and the ledger carries the
        # movie_ prefixed ones from the view.
        grid = led.rename(columns={"movie_title": "title", "movie_year": "year"})
        # Six, not the eight the other grids use: this caption carries an episode
        # number as well as a year, and at eight the titles wrap to three lines
        # and the rows go ragged.
        COLS = 6
        for i in range(0, len(grid), COLS):
            cols = st.columns(COLS)
            for col, (_, m) in zip(cols, grid.iloc[i : i + COLS].iterrows()):
                with col:
                    ep = int(m["episode_number"])
                    # The verdict rides in the caption rather than on a
                    # tooltip: the whole card is a click target now, so a
                    # title= on the plate would never surface -- and hover is
                    # not a carrier that exists on touch anyway. The band still
                    # does the scanning work; this is the text form of it, so
                    # the tag is not left to colour vision alone.
                    stamp = (f"ep {ep} · {int(m['year'])}"
                             if pd.notna(m["year"]) else f"ep {ep}")
                    film_card(
                        m, f"{stamp} · {m['verdict']}",
                        # Episode-grained: two airings of one film would collide
                        # on movie_id alone, so the episode number owns the key.
                        key=f"ledger{ep}",
                        tone=m["verdict"].lower(),
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — TIMELINE & REVISITS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "timeline":
    masthead(
        "Timeline &amp; Revisits",
        "When the episodes landed, how old the films were when they did, and "
        "the few they came back to.",
    )

    # Episode cadence by year (line)
    tape("Episodes per year")
    ep_year = (
        episodes_df.set_index("date").resample("YE").size().reset_index(name="count")
    )
    ep_year["year"] = ep_year["date"].dt.year
    fig = px.line(
        ep_year, x="year", y="count",
        markers=True, color_discrete_sequence=[MINT],
        labels={"year": "Year", "count": "Episodes"},
    )
    fig.update_traces(marker_size=8)
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Movie release decade stacked by genre
    tape("Films by release decade and genre")
    g_long_d = explode_genres(movies_df[movies_df["decade"].notna()].copy())
    g_long_d["genre_cat"], cmap, order = fold_to_series(g_long_d["genre"])
    decade_genre = (
        g_long_d.groupby(["decade", "genre_cat"]).size().reset_index(name="count")
    )
    decade_genre["decade_label"] = decade_genre["decade"].apply(lambda x: f"{int(x)}s")
    fig = px.bar(
        decade_genre, x="decade_label", y="count", color="genre_cat",
        color_discrete_map=cmap, category_orders={"genre_cat": order},
        labels={"decade_label": "Decade", "count": "Films", "genre_cat": "Genre"},
    )
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Gap between film release year and episode year
    tape("How old were films when featured? (episode year − release year)")
    ep_with_year = merged_df.dropna(subset=["episode_date"]).copy()
    ep_with_year["ep_year"] = ep_with_year["episode_date"].dt.year
    ep_with_year["age_gap"] = ep_with_year["ep_year"] - ep_with_year["year"]
    age_valid = ep_with_year[ep_with_year["age_gap"].between(0, 60)]

    col_e, col_f = st.columns(2)
    with col_e:
        fig = px.histogram(
            age_valid, x="age_gap", nbins=30,
            color_discrete_sequence=[MINT_DEEP],
            labels={"age_gap": "Years since release"},
        )
        fig.add_vline(x=float(age_valid["age_gap"].median()), line_dash="dash",
                      line_color=TAPE,
                      annotation_text=f"median {age_valid['age_gap'].median():.0f} yrs")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    with col_f:
        tape("Oldest films discussed")
        oldest = (
            ep_with_year
            .nlargest(10, "age_gap")[["title", "year", "ep_year", "age_gap"]]
            .drop_duplicates("title")
        )
        st.dataframe(
            oldest.rename(columns={"ep_year": "Episode year", "age_gap": "Age (yrs)"}),
            hide_index=True, use_container_width=True,
        )

    st.markdown("---")

    # TMDB rating over decades
    tape("Average TMDB rating by release decade")
    dec_rating = (
        movies_df.groupby("decade")["rating_tmdb"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    dec_rating.columns = ["decade", "mean", "std", "count"]
    dec_rating["decade_label"] = dec_rating["decade"].apply(lambda x: f"{int(x)}s")
    dec_rating["lower"] = dec_rating["mean"] - dec_rating["std"]
    dec_rating["upper"] = dec_rating["mean"] + dec_rating["std"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["upper"],
        fill=None, mode="lines", line_color="rgba(43,232,160,0.12)", name="",
    ))
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["lower"],
        fill="tonexty", fillcolor="rgba(245,197,24,0.15)",
        mode="lines", line_color="rgba(43,232,160,0.12)", name="±1 std",
    ))
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["mean"],
        mode="lines+markers", line_color=MINT,
        marker_size=10, name="Mean TMDB",
    ))
    plotly_defaults(fig)
    fig.update_layout(showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # New episodes over calendar time with genre colouring
    tape("Episode timeline colored by primary genre")
    ep_genre = merged_df.dropna(subset=["episode_date", "genre_primary"]).drop_duplicates("episode_date").copy()
    ep_genre["genre_cat"], cmap, order = fold_to_series(ep_genre["genre_primary"])
    fig = px.strip(
        ep_genre.sort_values("episode_date"),
        x="episode_date", y="genre_cat",
        color="genre_cat",
        color_discrete_map=cmap, category_orders={"genre_cat": order},
        hover_data=["title"],
        labels={"episode_date": "", "genre_cat": ""},
    )
    fig.update_traces(marker_size=6, opacity=0.75)
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)

    # ── Revisits ──
    # Was its own section; the nine films the sheet flags read better as the
    # closing movement of the timeline than as a peer of Movie Explorer.
    st.markdown("---")
    tape("Films they came back to")

    revisited = movies_df[movies_df["revisited_flag"] == 1].sort_values(
        "total_episodes_featured", ascending=False
    )
    st.markdown(
        '<div class="rw-tile"><div class="k">Revisited films</div>'
        f'<div class="v">{len(revisited)}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Poster grid of revisited movies
    tape("The Rewatchables hall of fame (revisited films)")
    cols = st.columns(10)
    for i, (_, m) in enumerate(revisited.iterrows()):
        with cols[i % 10]:
            film_card(
                m,
                f"{m['year']} · {m['total_episodes_featured']}×",
                key="revisit",
            )

    st.markdown("---")

    # Revisits over time
    tape("When did revisits happen?")
    # Scope to films the sheet flags as revisited, so the timeline agrees with
    # the count above even if the derived is_revisit ever drifts from it.
    rev_links = merged_df[
        (merged_df["is_revisit"] == 1)
        & (merged_df["movie_id"].isin(revisited["movie_id"]))
    ].copy()
    if len(rev_links) > 0:
        rev_links["ep_year"] = rev_links["episode_date"].dt.year
        fig = px.scatter(
            rev_links,
            x="episode_date", y="title",
            color="revisit_sequence",
            color_continuous_scale=SEQ,
            size_max=12,
            hover_data=["year", "episode_date"],
            labels={"episode_date": "Episode date", "title": "", "revisit_sequence": "Revisit #"},
        )
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No revisit episode links found.")

    st.markdown("---")

    # Time between first and last episode for revisited films
    tape("Time between first and last episode")
    revisited_gap = revisited.copy()
    revisited_gap["gap_days"] = (
        revisited_gap["last_episode_date"] - revisited_gap["first_episode_date"]
    ).dt.days
    revisited_gap = revisited_gap.dropna(subset=["gap_days"]).sort_values("gap_days", ascending=False)

    fig = px.bar(
        revisited_gap.head(20),
        x="gap_days", y="title",
        orientation="h",
        color_discrete_sequence=[MINT_DEEP],
        text=revisited_gap.head(20)["gap_days"].apply(lambda d: f"{d//365}y {(d%365)//30}m"),
        labels={"gap_days": "Days between episodes", "title": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Revisit genres
    tape("Genre breakdown of revisited films")
    rev_g = explode_genres(revisited)
    g_rev_counts = rev_g["genre"].value_counts().reset_index()
    g_rev_counts.columns = ["genre", "count"]
    fig = px.bar(
        g_rev_counts, x="genre", y="count",
        color_discrete_sequence=[MINT_DEEP],
        text="count",
    )
    fig.update_traces(textposition="outside")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — HOSTS & GUESTS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "hosts":
    masthead(
        "Hosts &amp; Guests",
        "Everyone who sits in with Bill Simmons: look anyone up, see when they "
        "were on, who they sit with, and which films they get booked on.",
    )

    # merged_df is one row per airing -- a revisit is its own row -- and it
    # carries the film, which the lookup's posters need.
    eps = merged_df
    n_eps = len(eps)
    room = room_long(eps, "raw_episode_id",
                     keep=("episode_number", "episode_date", "movie_id"))
    is_anchor = room["person"] == ANCHOR
    with_anchor = set(room.loc[is_anchor, "raw_episode_id"])
    anchor_hosted = int((is_anchor & (room["chair"] == "host")).sum())
    others = room[~is_anchor]
    board = bench(others, "raw_episode_id", "episode_date")
    n_without = n_eps - len(with_anchor)

    # The leans feed the lookup as well as their own panel, so they are worked
    # out up front. Cached: the permutation tests take about a second.
    regulars = board.index[board["episodes"] >= LEAN_FLOOR].tolist()
    reach = Counter(g for gs in eps["genres"] if isinstance(gs, list) for g in gs)
    tested = [g for g, n in reach.most_common() if n >= GENRE_FLOOR]
    film_year = pd.to_numeric(eps["year"], errors="coerce")
    measures = pd.DataFrame({
        "rt": eps["tomatoes_num"].astype(float).to_numpy(),
        "age": (eps["episode_date"].dt.year - film_year).astype(float).to_numpy(),
    })
    for g in tested:
        measures[g] = eps["genres"].map(
            lambda gs, g=g: isinstance(gs, list) and g in gs).astype(float).to_numpy()
    on_ids = others.groupby("person")["raw_episode_id"].agg(set)
    members = pd.DataFrame({
        p: eps["raw_episode_id"].isin(on_ids[p]).to_numpy() for p in regulars})
    leans = room_leans(measures, members)
    held = leans[leans["q"] < LEAN_Q]

    stat_tiles([
        ("Film episodes", f"{n_eps}"),
        ("With Bill Simmons", f"{len(with_anchor) / n_eps:.0%}"),
        ("Without him", f"{n_without}"),
        ("Everyone else", f"{len(board)}"),
        ("On five or more", f"{int((board['episodes'] >= 5).sum())}"),
    ])
    st.markdown(
        f'<p class="ch-note">Bill Simmons is on <b>{len(with_anchor)} of {n_eps}</b> '
        f"film episodes and hosts {anchor_hosted} of them, so a chart that counts "
        "him is mostly a chart of him. Every panel below leaves him out. The host "
        f"chair only tells you something on the {n_without} episodes he is not on, "
        "which close the page.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Look someone up ──
    tape("Look someone up")
    names = board.index.tolist()
    # A stored pick naming someone no longer in the room -- a guest renamed in
    # the sheet, say -- would make the picker raise. Drop it; the top name wins.
    for k in ("flt_person", "_keep_flt_person"):
        if k in st.session_state and st.session_state[k] not in names:
            del st.session_state[k]
    pick_col, _ = st.columns([2, 3])
    with pick_col:
        who = keep(
            st.selectbox, "Person", names, key="flt_person",
            format_func=lambda n: f"{n} ({int(board.loc[n, 'episodes'])})",
        )
    # Mirrored into the URL, as a dossier is, so a lookup can be shared.
    st.query_params["person"] = who

    me = board.loc[who]
    share = me["episodes"] / n_eps
    stat_tiles([
        ("Episodes", f"{int(me['episodes'])}"),
        ("Of all episodes", f"{share:.0%}" if share >= 0.005 else "<1%"),
        ("In the host chair", f"{int(me['hosted'])}"),
        ("First on", f"{me['first']:%b %Y}"),
        ("Latest", f"{me['last']:%b %Y}"),
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    mine = person_shelf(who).merge(
        movies_df[["movie_id", "title", "poster_url_tmdb"]], on="movie_id", how="left")
    COLS = 8
    for start in range(0, len(mine), COLS):
        cols = st.columns(COLS)
        for offset, (col, (_, m)) in enumerate(
                zip(cols, mine.iloc[start:start + COLS].iterrows())):
            with col:
                # Keyed by position, not by film: a revisit can put one film on
                # a person's shelf twice.
                film_card(
                    m, f"Ep {int(m['episode_number'])} · {m['episode_date']:%b %Y}",
                    key=f"person{start + offset}")

    ids = set(mine["raw_episode_id"])
    c_company, c_record = st.columns(2)
    with c_company:
        st.markdown("###### Who they sit with")
        company = others.loc[others["raw_episode_id"].isin(ids)
                             & (others["person"] != who), "person"].value_counts()
        ranked_list(
            [(n, int(k)) for n, k in company.head(6).items()],
            f"{who} has only ever been on with Bill.",
            note="Episodes shared, Bill aside.",
        )
    with c_record:
        st.markdown("###### What they get booked on")
        if who in regulars:
            st.markdown(
                f'<div class="chip-row">{lean_chips(held[held["person"] == who])}</div>',
                unsafe_allow_html=True)
        else:
            st.caption(f"Fewer than {LEAN_FLOOR} episodes: too few to compare with "
                       "the rest of the show.")

        st.markdown("###### Cruise vs. Hanks")
        verdicts = eps.loc[eps["raw_episode_id"].isin(ids), "cruise_hanks"].map(clean)
        tally = verdicts.dropna().value_counts()
        n_v = int(tally.sum())
        if n_v >= VERDICT_FLOOR:
            ties = int(tally.get("Tie", 0))
            tie_txt = f", {ties} tie{'s' if ties != 1 else ''}" if ties else ""
            st.markdown(
                f'<p class="ch-note"><b>Cruise {int(tally.get("Cruise", 0))} &ndash; '
                f'Hanks {int(tally.get("Hanks", 0))}</b>{tie_txt}, across {n_v} '
                "verdict episodes.</p>",
                unsafe_allow_html=True)
        else:
            st.caption(f"{n_v} verdict episode{'s' if n_v != 1 else ''}; a record "
                       f"is read from {VERDICT_FLOOR}.")

    st.markdown("---")

    # ── The bench ──
    tape("The bench")
    listed = board[board["episodes"] >= BENCH_FLOOR].reset_index()
    st.dataframe(
        pd.DataFrame({
            "Person": listed["person"],
            "Episodes": listed["episodes"],
            "Share": listed["episodes"] / n_eps * 100,
            "Hosted": listed["hosted"],
            "First on": listed["first"],
            "Latest": listed["last"],
        }),
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Episodes": st.column_config.ProgressColumn(
                format="%d", min_value=0, max_value=int(board["episodes"].max())),
            "Share": st.column_config.NumberColumn(format="%.1f%%"),
            "First on": st.column_config.DateColumn(format="MMM YYYY"),
            "Latest": st.column_config.DateColumn(format="MMM YYYY"),
        },
    )
    st.markdown(
        f'<p class="ch-note">Everyone on {BENCH_FLOOR} or more episodes. The other '
        f"{int((board['episodes'] < BENCH_FLOOR).sum())} have been on once or twice "
        f"&mdash; {int((board['episodes'] == 1).sum())} of them just once &mdash; and "
        "every one is in the lookup above.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Who's on when ──
    tape("Who&rsquo;s on when")
    on, aired = appearances_by_year(others, eps, "raw_episode_id", "episode_date")
    cast = board.head(WHEN_TOP).sort_values("first").index.tolist()
    counts = on.reindex(cast).fillna(0)
    years = [str(int(y)) for y in aired.index]
    fig = go.Figure(go.Heatmap(
        z=counts.to_numpy() / aired.to_numpy() * 100,
        x=years, y=cast,
        customdata=np.dstack([counts.to_numpy(),
                              np.tile(aired.to_numpy(), (len(cast), 1))]),
        hovertemplate="%{y}, %{x}<br>%{customdata[0]:.0f} of %{customdata[1]:.0f} "
                      "episodes (%{z:.0f}%)<extra></extra>",
        # Zero gets the surface colour and anything above it the first step,
        # so "never on that year" and "on once" do not blur together.
        colorscale=[[0, INK_3], [0.001, SEQ[0]], [0.2, SEQ[1]], [0.4, SEQ[2]],
                    [0.6, SEQ[3]], [0.8, SEQ[4]], [1, SEQ[5]]],
        zmin=0, zmax=80, xgap=2, ygap=2,
        colorbar=dict(ticksuffix="%", outlinewidth=0, thickness=10,
                      tickfont=dict(color=TXT_2)),
    ))
    plotly_defaults(fig)
    fig.update_layout(
        height=30 * len(cast) + 120,
        yaxis=dict(autorange="reversed", gridcolor=INK, title=""),
        xaxis=dict(tickvals=years, gridcolor=INK, title="",
                   ticktext=[f"{y}<br>{int(n)} eps" for y, n in zip(years, aired)]),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        f'<p class="ch-note">The {len(cast)} people on the most episodes, in the order '
        "they first appeared. A cell is the share of that year&rsquo;s film episodes "
        "they were on, so a light year and a busy one read on the same scale; the "
        "count under each year is how many aired. The colour tops out at 80%.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Who sits together ──
    tape("Who sits together")
    ring = board.head(RING_TOP).index.tolist()
    pairs = co_appearances(others, "raw_episode_id")
    shared = np.array([[np.nan if a == b else pairs.get(tuple(sorted((a, b))), 0)
                        for b in ring] for a in ring], dtype=float)
    c_grid, c_lineup = st.columns([3, 2])
    with c_grid:
        fig = go.Figure(go.Heatmap(
            # Square-root colour: the top pair shares three times the episodes
            # of the next, so a linear ramp lights one cell and leaves the rest
            # near black.
            z=np.sqrt(shared), x=ring, y=ring, customdata=shared,
            text=[["" if not v or np.isnan(v) else f"{v:.0f}" for v in row]
                  for row in shared],
            texttemplate="%{text}", textfont=dict(color=TAPE, size=11),
            hovertemplate="%{y} + %{x}<br>%{customdata:.0f} episodes together"
                          "<extra></extra>",
            hoverongaps=False,
            colorscale=[[0, INK_3], [0.001, MINT_DIM], [1, SEQ[1]]],
            showscale=False, xgap=2, ygap=2,
        ))
        plotly_defaults(fig)
        fig.update_layout(
            height=34 * len(ring) + 130,
            yaxis=dict(autorange="reversed", gridcolor=INK, title=""),
            xaxis=dict(tickangle=-40, gridcolor=INK, title=""),
        )
        st.plotly_chart(fig, use_container_width=True)
    with c_lineup:
        st.markdown("###### Most common lineups")
        ranked_list(
            [(n, int(k)) for n, k in lineups(others, "raw_episode_id").head(10).items()],
            "No lineup has repeated.", wide=True,
        )
    st.markdown(
        f'<p class="ch-note">The {len(ring)} people on the most episodes. A cell is the '
        "number of episodes a pair shared; an empty one is a pair who have never been "
        "in the room together. A lineup is everyone in the room except Bill, so a "
        "single name is that person with Bill.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── What each regular gets booked on ──
    tape("What each regular gets booked on")
    st.markdown(
        "".join(
            f'<div class="rw-lean"><div class="n">{p}'
            f'<span>{int(board.loc[p, "episodes"])} episodes</span></div>'
            f'<div class="l">{lean_chips(held[held["person"] == p])}</div></div>'
            for p in regulars),
        unsafe_allow_html=True,
    )
    quiet = [p for p in regulars if p not in set(held["person"])]
    if len(quiet) > 1:
        quiet_txt = f"{', '.join(quiet[:-1])} and {quiet[-1]} show none. "
    elif quiet:
        quiet_txt = f"{quiet[0]} shows none. "
    else:
        quiet_txt = ""
    st.markdown(
        '<p class="ch-note">The sheet doesn&rsquo;t record who picked a film, so this is '
        "what each person gets <b>booked on</b>, not what they like: a guest brought in "
        "for a month of rom-coms shows a romance lean whether or not they chose the "
        f"films. Each of the {len(regulars)} people on {LEAN_FLOOR}+ episodes is "
        "compared with every episode they were not on &mdash; on Rotten Tomatoes "
        "score, the film&rsquo;s age when it aired, and the share of episodes in each "
        f"of the {len(tested)} genres on {GENRE_FLOOR}+ episodes. That is "
        f"{len(leans)} comparisons, each a {N_PERM:,}-shuffle permutation test, and a "
        "lean is shown only if it survives a Benjamini&ndash;Hochberg correction at "
        f"q &lt; {LEAN_Q}: <b>{len(held)} of {len(leans)}</b> do. {quiet_txt}"
        "Films carry several genres, so the genre comparisons overlap. Mint is above "
        "the rest of the show, grey below.</p>",
        unsafe_allow_html=True,
    )
    with st.expander(f"All {len(leans)} comparisons"):
        ordered = leans.sort_values("p")
        st.dataframe(
            pd.DataFrame({
                "Person": ordered["person"],
                "Measure": ordered["metric"].map(
                    lambda m: MEASURE_LABEL.get(m, f"{m} share")),
                "Episodes": ordered["n"],
                "Their episodes": [lean_value(m, v) for m, v
                                   in zip(ordered["metric"], ordered["mean_in"])],
                "Everyone else": [lean_value(m, v) for m, v
                                  in zip(ordered["metric"], ordered["mean_out"])],
                "Gap": [lean_value(m, v, signed=True) for m, v
                        in zip(ordered["metric"], ordered["diff"])],
                "p": ordered["p"],
                "q": ordered["q"],
                "Shown": ordered["q"] < LEAN_Q,
            }),
            hide_index=True, use_container_width=True, height=420,
            column_config={
                "p": st.column_config.NumberColumn(format="%.4f"),
                "q": st.column_config.NumberColumn(format="%.4f"),
            },
        )

    st.markdown("---")

    # ── Without Bill ──
    solo = eps[~eps["raw_episode_id"].isin(with_anchor)].sort_values("episode_date")
    tape(f"Without Bill &mdash; {len(solo)} episodes")
    st.markdown(
        '<p class="ch-note">The only episodes where the host chair says something. '
        "Grouped by who hosted, busiest first; oldest episode first within each.</p>",
        unsafe_allow_html=True,
    )
    solo_host = solo["host"].fillna("No host listed")
    for host, count in solo_host.value_counts().items():
        group = solo[solo_host == host]
        st.markdown(
            f'<div class="rw-kw-gridnote"><span>{host} hosting &middot; {count} '
            f'episode{"s" if count != 1 else ""}</span></div>',
            unsafe_allow_html=True,
        )
        for start in range(0, len(group), COLS):
            cols = st.columns(COLS)
            for col, (_, m) in zip(cols, group.iloc[start:start + COLS].iterrows()):
                with col:
                    film_card(
                        m, f"Ep {int(m['episode_number'])} · {m['episode_date']:%b %Y}",
                        key=f"solo{m['raw_episode_id']}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — KEYWORDS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "keywords":
    masthead(
        "Keywords",
        "What the films are about, in the words TMDB uses. "
        "Pick one to see every film that carries it.",
    )

    browsable = sorted(
        (w for w, n in REACH.items() if n >= BROWSE_FLOOR),
        key=lambda w: (-REACH[w], w),
    )
    tail = len(REACH) - len(browsable)
    singles = sum(1 for n in REACH.values() if n == 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Browsable here", f"{len(browsable):,}")
    c2.metric("Searchable", f"{len(REACH):,}")
    # Over the films that carry any: one film has none, and including it drags
    # the median to 16.5, which then prints as 16 and understates the typical row.
    tagged = movies_df["keywords"].apply(len)
    c3.metric("Median per film", int(tagged[tagged > 0].median()))
    c4.metric("On one film only", f"{100 * singles / len(REACH):.0f}%")

    st.markdown("---")

    tape("Find a keyword")
    query = keep(st.text_input, "Search the whole vocabulary",
                 placeholder="heist, brooklyn, writer's block…", key="kw_search")
    if query:
        # Search reaches the entire vocabulary, tail included — the rare terms
        # are meant to be found, not browsed. Each result shows its reach, so a
        # one-film keyword announces itself before you follow it.
        hits = sorted(
            (w for w in REACH if query.strip().lower() in w.lower()),
            key=lambda w: (-REACH[w], w),
        )[:60]
        if hits:
            st.caption(f"{len(hits)} of the {len(REACH):,} keywords match")
            keyword_row(hits, key="search")
        else:
            st.caption("Nothing in the vocabulary matches that.")

    st.markdown("---")

    # Grouped into reach bands rather than shaded by frequency: the band heading
    # states the range outright, which a colour ramp can only imply.
    tape("The common vocabulary")
    st.caption(
        f"The {len(browsable)} keywords carried by {BROWSE_FLOOR} films or more. "
        f"Every one leads somewhere."
    )
    BANDS = [
        ("Carried by 40 or more films", 40, 10_000),
        ("25 to 39 films", 25, 39),
        ("17 to 24 films", 17, 24),
        ("12 to 16 films", 12, 16),
        (f"{BROWSE_FLOOR} to 11 films", BROWSE_FLOOR, 11),
    ]
    for label, low, high in BANDS:
        band = [w for w in browsable if low <= REACH[w] <= high]
        if not band:
            continue
        st.markdown(
            f'<div class="rw-kw-legend"><span>{label}</span>'
            f'<span style="color:var(--mint-deep);">{len(band)} keywords</span></div>',
            unsafe_allow_html=True,
        )
        keyword_row(band, key=f"band_{low}")

    st.markdown(
        f'<div class="rw-kw-tail">The other <b>{tail:,}</b> keywords — including '
        f'the <b>{singles:,}</b> that belong to a single film — are reachable '
        'through the search above. They are genuine concepts rather than untidy '
        'duplicates, so nothing is gained by merging them away; they are simply '
        'found rather than browsed.</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Signature by decade")
    decade_cols = st.columns(len(range(1970, 2030, 10)))
    for col, decade in zip(decade_cols, range(1970, 2030, 10)):
        in_decade = movies_df[movies_df["decade"] == decade]
        if not len(in_decade):
            continue
        counts = Counter(
            w for ks in in_decade["keywords"] for w in (ks if isinstance(ks, list) else [])
        )
        rows = "".join(
            f"<li><span>{w}</span><b>{n}</b></li>" for w, n in counts.most_common(4)
        )
        with col:
            st.markdown(
                f'<div class="rw-kw-dec"><h5>{decade}s</h5>'
                f'<span class="n">{len(in_decade)} films</span><ol>{rows}</ol></div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — UPCOMING FILMS
# ═══════════════════════════════════════════════════════════════════════════════

elif section == "upcoming":
    masthead(
        "Films still in the queue",
        "Listener-contributed requests for future episodes, with the reason "
        "each one is on the list.",
    )

    if not len(upcoming_df) and not len(graduated_df):
        # A database built before step 13 ran. Say what is missing rather than
        # rendering an empty section that looks like an empty list.
        st.info(
            "No upcoming-films data in this database yet. Build it with:\n\n"
            "`python scripts/orchestrate.py --stages upcoming`"
        )
        st.stop()

    n_resolved = int(upcoming_df["resolved"].sum())
    years = upcoming_df["year"].dropna()
    contributors = upcoming_df["contributor"].dropna().nunique()

    st.markdown(
        '<div class="rw-dt-rail">'
        + stat_tile("In contention", f"{len(upcoming_df):,}")
        + stat_tile("Already made", len(graduated_df), coral=True)
        + stat_tile(
            "Span",
            f"{int(years.min())}&ndash;{int(years.max())}" if len(years) else None)
        + stat_tile("Contributors", contributors)
        + stat_tile("Matched to TMDB", f"{100 * n_resolved / len(upcoming_df):.0f}", "%")
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Filters ──
    # In the body rather than the sidebar. The sidebar belongs to Movie
    # Explorer, whose widgets must keep rendering for its result set to
    # survive; a second set of sidebar filters here would render alongside them
    # on every run of this section.
    f1, f2, f3, f4 = st.columns([2, 1, 1.3, 1.3])

    with f1:
        query = keep(st.text_input, "Search title or reason",
                     placeholder="e.g. Fincher, mailbag, blockbuster",
                     key="flt_up_q")

    decades_present = sorted(int(d) for d in upcoming_df["decade"].dropna().unique())
    with f2:
        decade_pick = keep(
            st.selectbox, "Decade",
            ["All"] + [f"{d}s" for d in decades_present],
            key="flt_up_decade")

    # Only tags reaching more than one film are offered. A tag with a single
    # film is a caption, not an axis -- it filters the grid down to the card you
    # would have had to already be looking at to pick it.
    tag_counts = Counter(t for tags in upcoming_df["tags"] for t in tags)
    shared_tags = sorted(t for t, n in tag_counts.items() if n > 1)
    with f3:
        tag_pick = keep(st.selectbox, "Pitched as", ["All"] + shared_tags,
                        key="flt_up_tag")

    with f4:
        sort_pick = keep(
            st.selectbox, "Sort by",
            ["Source order", "Title", "Year (newest)", "Year (oldest)",
             "TMDB rating"],
            key="flt_up_sort")

    view = upcoming_df
    if query:
        needle = query.strip().lower()
        view = view[
            view["title"].str.lower().str.contains(needle, regex=False)
            | view["mention_note"].fillna("").str.lower().str.contains(needle, regex=False)
            | view["pitch_tags"].fillna("").str.lower().str.contains(needle, regex=False)
            | view["contributor"].fillna("").str.lower().str.contains(needle, regex=False)
        ]
    if decade_pick != "All":
        view = view[view["decade"] == int(decade_pick[:-1])]
    if tag_pick != "All":
        view = view[view["tags"].apply(lambda ts: tag_pick in ts)]

    if sort_pick == "Title":
        view = view.sort_values("sort_title")
    elif sort_pick == "Year (newest)":
        view = view.sort_values("year", ascending=False, na_position="last")
    elif sort_pick == "Year (oldest)":
        view = view.sort_values("year", ascending=True, na_position="last")
    elif sort_pick == "TMDB rating":
        view = view.sort_values("rating_tmdb", ascending=False, na_position="last")

    st.markdown(
        f'<div class="rw-kw-gridnote"><span>{len(view)} of '
        f'{len(upcoming_df)} films</span><span>click a poster for the pitch</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    if not len(view):
        st.info("No requested film matches those filters.")
    else:
        # Eight across, like Movie Explorer. Plates are 2:3 at column width, so
        # six across made each card nearly 300px tall.
        per_row = 8
        rows = list(view.iterrows())
        for start in range(0, len(rows), per_row):
            cols = st.columns(per_row)
            for col, (_, row) in zip(cols, rows[start:start + per_row]):
                with col:
                    prospect_card(row, key="grid")

    st.markdown("---")

    # ── The pitch, in full ──
    tape("Why these films")
    st.markdown(
        '<p class="rw-up-note">Every request carries either a note citing where '
        'the film came up on air, or a comma-separated pitch. They are '
        'alternatives, not both &mdash; the source records one or the other. '
        f'<b>{int(upcoming_df["mention_note"].notna().sum())}</b> films have a '
        f'note, <b>{int(upcoming_df["pitch_tags"].notna().sum())}</b> have '
        'tags.</p>',
        unsafe_allow_html=True,
    )

    show = view.head(12)
    note_cols = st.columns(2)
    for i, (_, row) in enumerate(show.iterrows()):
        with note_cols[i % 2]:
            st.markdown(
                f'<div class="rw-dt-panel" style="padding:13px 15px 15px">'
                f'<h4>{row["title"]} &middot; {row["year_raw"] or "—"}</h4>'
                + why_html(row) + "</div>",
                unsafe_allow_html=True,
            )
    if len(view) > len(show):
        st.caption(f"Showing the first {len(show)} of {len(view)}. "
                   "Narrow the filters above to reach the rest.")

    # ── The most-pitched angles ──
    if shared_tags:
        st.markdown("---")
        tape("The angles people pitch")
        top_tags = tag_counts.most_common(24)
        st.markdown(
            '<div class="rw-kw-field">'
            + "".join(keyword_chip(t, n) for t, n in top_tags)
            + "</div>",
            unsafe_allow_html=True,
        )

    # ── The graduates ──
    st.markdown("---")
    tape("They actually made these")
    if not len(graduated_df):
        st.markdown(
            '<p class="rw-up-note">Nothing on the list has become an episode '
            'yet. When one does it moves here automatically, and stops '
            'appearing above.</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p class="rw-up-note"><b>{len(graduated_df)}</b> requested films '
            'have since been covered. They are matched on TMDB id rather than '
            'on title &mdash; the list also holds a different <i>Crash</i>, a '
            'different <i>Heat</i> and a different <i>Miami Vice</i> from the '
            'ones in the catalogue, and matching on title would have removed '
            'all three.</p>',
            unsafe_allow_html=True,
        )
        for _, row in graduated_df.iterrows():
            aired = row["first_episode_date"]
            when = aired.strftime("%b %Y") if pd.notna(aired) else "—"
            poster = (
                f'<img src="{row["poster_url_tmdb"].replace("/w500/", "/w185/")}" '
                f'alt="">' if row["poster_url_tmdb"] else ""
            )
            # The card and its exit sit side by side. A full-width button under
            # a horizontal card reads as a second row rather than as part of it.
            card_col, go_col = st.columns([4, 1], vertical_alignment="center")
            with card_col:
                st.markdown(
                    html(f'''
                    <div class="rw-up-grad">{poster}
                      <div class="b">
                        <span class="t">{row["movie_title"]} ({row["movie_year"]})</span>
                        <span class="m">Requested as <b>{row["requested_title"]}</b>
                          &middot; aired {when}
                          &middot; {row["total_episodes_featured"]}&times;</span>
                      </div>
                    </div>'''),
                    unsafe_allow_html=True,
                )
            with go_col:
                if st.button("Open dossier →",
                             key=f"btn_grad_{row['upcoming_film_id']}",
                             use_container_width=True):
                    open_dossier(row["movie_id"])

    # ── What did not resolve ──
    unmatched = upcoming_df[~upcoming_df["resolved"]]
    if len(unmatched):
        st.markdown("---")
        tape("Not matched to a film")
        st.markdown(
            f'<p class="rw-up-note"><b>{len(unmatched)}</b> requests carry no '
            'TMDB match, so they show without a poster. Two are TV series on a '
            'list of films, one gives no year, and the rest are titles TMDB '
            'spells differently. They are kept rather than hidden &mdash; each '
            'is a real request &mdash; and a film with no id can never be '
            'mistaken for one that has already aired.</p>',
            unsafe_allow_html=True,
        )
        for _, row in unmatched.iterrows():
            year_suffix = f" ({row['year_raw']})" if row["year_raw"] else ""
            note = RESOLUTION_NOTE.get(row["resolution_method"], "not matched")
            st.markdown(
                f'<div class="rw-up-grad" style="border-left-color:var(--line-2)">'
                f'<div class="b"><span class="t">{row["title"]}{year_suffix}</span>'
                f'<span class="m">{note}</span></div></div>',
                unsafe_allow_html=True,
            )
