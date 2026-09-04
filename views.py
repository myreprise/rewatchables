"""
Presentation helpers for the views in app.py.

These are the parts of the dossier and the keyword index that turn database
values into markup, kept free of Streamlit so they can be tested directly.
Everything here is pure: given the same input it returns the same string.
"""

import math


def clean(value):
    """Normalise a source-sheet cell to a real value or None.

    The spreadsheet writes empty cells as the literal string 'nan', which flows
    all the way through raw -> staging -> curated. Rendered as-is it puts a
    guest called "nan" in the room and an empty note under every episode.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return None if text.lower() in ("nan", "none", "") else text


def stars(value):
    """Ebert's half-star scale, drawn rather than printed as a decimal."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    value = float(value)
    return "&#9733;" * int(value) + ("&frac12;" if value % 1 else "")


def human_gap(days):
    """The distance between two episodes, at the resolution people think in.

    Deliberately coarse: the point of the marker is that a film came back years
    later, not the exact interval, which the episode dates already carry.
    """
    days = int(days)
    years, rest = divmod(days, 365)
    months = rest // 30
    if years and months:
        return f"{years} yr {months} mo later"
    if years:
        return f"{years} yr later"
    if months:
        return f"{months} mo later"
    return f"{days} days later"


def stat_tile(label, value, unit="", coral=False):
    """A metric tile for the hero rail.

    A missing value reads as n/a. Coverage is genuinely partial — 7 films have
    no box office, 16 no budget and 81 no Ebert star — and rendering those as 0
    would state something the data does not.
    """
    css = "rw-dt-stat is-coral" if coral else "rw-dt-stat"
    body = (
        f'<span class="v">{value}<span class="u">{unit}</span></span>'
        if value is not None else '<span class="miss">&mdash; n/a</span>'
    )
    return f'<div class="{css}"><span class="k">{label}</span>{body}</div>'


def html(markup):
    """Flatten generated markup onto one line before handing it to st.markdown.

    Markdown reads a line indented four spaces as a code block, which silently
    swallowed every episode card but the first when the blocks were written out
    at their natural indentation.
    """
    return "".join(line.strip() for line in markup.splitlines())


# ── Keyword index ─────────────────────────────────────────────────────────────

# Reach bands for a keyword chip, commonest first. Only the fill and the rule
# move between bands; the label stays legible, so a rare keyword is never harder
# to read than a common one.
CHIP_BANDS = ((40, "b1"), (25, "b2"), (17, "b3"), (12, "b4"))

# A keyword must reach at least this many films before it is offered as a link.
# Below it the chip still prints — it describes the film — but as inert text.
# Measured: at the 8-chip cap this leaves 93% of chips clickable.
LINK_FLOOR = 2

# The browse surface shows keywords at or above this reach; 330 of 3,645 qualify.
# The rest are reachable through search, which matches the whole vocabulary.
BROWSE_FLOOR = 5


def chip_band(reach):
    """Which of the five weight bands a keyword's chip belongs in."""
    for threshold, band in CHIP_BANDS:
        if reach >= threshold:
            return band
    return "b5"


def keyword_chip(keyword, reach, inert=False, current=False):
    """A keyword chip carrying its reach.

    The count is the point: it says where the chip goes before you click it,
    which is the job a consolidated vocabulary would otherwise have to do.
    """
    classes = ["rw-kw-chip", chip_band(reach)]
    if current:
        classes.append("is-here")
    if inert:
        classes = ["rw-kw-chip", "is-inert"]
    return (
        f'<span class="{" ".join(classes)}">{keyword} <b>{reach}</b></span>'
    )


def region_of(keyword):
    """The parent region of a `place, region` keyword, or None.

    TMDB writes locations as "los angeles, california". Splitting on the last
    comma is mechanical and needs no curated map — but the results are uneven
    ("usa" is a bucket, "illinois" has one child), so this only ever adds a line
    to a keyword's page. It never becomes a browse axis of its own.
    """
    if not keyword or "," not in keyword:
        return None
    region = keyword.rsplit(",", 1)[1].strip()
    return region or None


def rank_by_reach(keywords, reach):
    """A film's keywords, most far-reaching first.

    TMDB returns them in its own order, which buries the useful ones. Ranking by
    reach is what drops the dead-end rate on a film page from 31% to 7%; ties
    break alphabetically so the order is stable between runs.
    """
    return sorted(keywords, key=lambda k: (-reach.get(k, 0), k))


def decade_bars(counts):
    """A decade histogram as bar markup, scaled to its own tallest column.

    Percentages are set against a track of definite height in the stylesheet;
    a percentage on the flex item itself gets clamped by whatever space the
    labels leave, which silently flattens the tallest bar.
    """
    if not counts:
        return ""
    peak = max(counts.values())
    bars = []
    for decade in sorted(counts):
        n = counts[decade]
        height = round(100 * n / peak) if peak else 0
        cls = "rw-kw-bar is-peak" if n == peak and n else "rw-kw-bar"
        bars.append(
            f'<div class="{cls}"><span class="v">{n}</span>'
            f'<span class="track"><i style="height:{height}%"></i></span>'
            f'<span class="d">{decade}s</span></div>'
        )
    return f'<div class="rw-kw-bars">{"".join(bars)}</div>'


def plain(text):
    """Neutralise markdown that plot text triggers by accident.

    Streamlit reads a pair of dollar signs as LaTeX, so a synopsis containing
    "$1.6 million ... $20,000" silently renders the span between them as maths —
    losing the spaces and italicising the lot. Escaping the dollars is enough;
    nothing in this corpus wants real LaTeX.
    """
    return (text or "").replace("$", r"\$")


# ── Money ─────────────────────────────────────────────────────────────────────
# Box office is reported in the dollars of its release year, so a straight
# comparison across the catalogue measures inflation more than it measures
# audience. The 1980s median gross is $67M against the 2000s' $169M, and most
# of that gap is CPI, not popularity. Everything user-facing is therefore
# converted to CPI_BASE_YEAR dollars before it is charted or ranked.

CPI_BASE_YEAR = 2024

# US CPI-U, annual averages, 1982-84 = 100 (BLS series CUUR0000SA0). The
# catalogue starts in 1968, so the table does too.
CPI_U = {
    1968: 34.8, 1969: 36.7, 1970: 38.8, 1971: 40.5, 1972: 41.8, 1973: 44.4,
    1974: 49.3, 1975: 53.8, 1976: 56.9, 1977: 60.6, 1978: 65.2, 1979: 72.6,
    1980: 82.4, 1981: 90.9, 1982: 96.5, 1983: 99.6, 1984: 103.9, 1985: 107.6,
    1986: 109.6, 1987: 113.6, 1988: 118.3, 1989: 124.0, 1990: 130.7,
    1991: 136.2, 1992: 140.3, 1993: 144.5, 1994: 148.2, 1995: 152.4,
    1996: 156.9, 1997: 160.5, 1998: 163.0, 1999: 166.6, 2000: 172.2,
    2001: 177.1, 2002: 179.9, 2003: 184.0, 2004: 188.9, 2005: 195.3,
    2006: 201.6, 2007: 207.3, 2008: 215.3, 2009: 214.5, 2010: 218.1,
    2011: 224.9, 2012: 229.6, 2013: 233.0, 2014: 236.7, 2015: 237.0,
    2016: 240.0, 2017: 245.1, 2018: 251.1, 2019: 255.7, 2020: 258.8,
    2021: 271.0, 2022: 292.7, 2023: 304.7, 2024: 313.7,
    # Provisional. Three films in the catalogue are released into these years,
    # and each is flagged in the app rather than quietly averaged in.
    2025: 322.0, 2026: 330.0,
}

CPI_PROVISIONAL_FROM = 2025


def real_usd(nominal, year):
    """Convert nominal dollars from `year` into CPI_BASE_YEAR dollars.

    Returns None when the amount is missing or the year sits outside the CPI
    table, rather than silently passing the nominal figure through — an
    unadjusted number mixed into an adjusted series is the failure that makes a
    decade trend look like a taste trend.
    """
    if nominal is None:
        return None
    try:
        nominal = float(nominal)
        year = int(year)
    except (TypeError, ValueError):
        return None
    if nominal <= 0 or year not in CPI_U:
        return None
    return nominal * CPI_U[CPI_BASE_YEAR] / CPI_U[year]


def money(value, precision=1):
    """Compact dollars: $1.2B, $340M, $8.5M, $940K.

    Millions are the unit the whole catalogue lives in, so the scale is chosen
    per value rather than fixed — a $718K release and a $2.2B one both have to
    read at a glance in the same column.
    """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    sign = "-" if value < 0 else ""
    value = abs(value)
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= cut:
            return f"{sign}${value / cut:.{precision}f}{suffix}"
    return f"{sign}${value:.0f}"


def multiple(revenue, budget):
    """Revenue as a multiple of budget, the closest thing to ROI available.

    Neither figure includes marketing spend or the exhibitor's share, so this
    is not profit — the industry's rule of thumb is that a film needs roughly
    2.5x its production budget to break even in theatres, and the app draws
    that line rather than 1x. Returns None unless both sides are known.
    """
    if revenue is None or budget is None:
        return None
    try:
        revenue, budget = float(revenue), float(budget)
    except (TypeError, ValueError):
        return None
    if budget <= 0 or revenue <= 0:
        return None
    return revenue / budget


BREAK_EVEN_MULTIPLE = 2.5


# ── Upcoming films ────────────────────────────────────────────────────────────
# Presentation for the contributed list of films expected in future episodes.
# The data is thinner than an aired film's — no episode, no room, no verdict —
# so what these do is make the two things it DOES have carry the card: who asked
# for it, and why.


def parse_tags(pitch_tags):
    """The pitch column as a list of tags, in source order, de-duplicated.

    48 of the 214 rows pitch a film as a comma-separated list rather than in
    prose ("1980s, John Carpenter, Kurt Russell"). Splitting them is what turns
    that column from a caption into a filter axis; de-duplication is
    case-insensitive because the source is hand-typed.
    """
    if not pitch_tags:
        return []
    seen, out = set(), []
    for tag in str(pitch_tags).split(","):
        tag = tag.strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out


def sort_title(title):
    """'The Blind Side' -> 'Blind Side, The'.

    The source sheet carried this as its own `entry_name` column, differing from
    the title on 39 of 214 rows. It is a pure function of the title, so it is
    derived here rather than stored — a stored copy is one more thing that can
    disagree with the field it describes.
    """
    text = str(title or "").strip()
    for article in ("The ", "A ", "An "):
        if text.startswith(article):
            return f"{text[len(article):]}, {article.strip()}"
    return text


def contributor_link(contributor):
    """(label, href) for the person or thread that put a film on the list.

    The column holds two different things: a Reddit handle for most rows, and
    for 14 of them the URL of the thread the suggestion came out of. Both are
    attribution and both deserve to resolve, so they are told apart by shape
    rather than being flattened to text.
    """
    value = clean(contributor)
    if not value:
        return None, None
    if value.startswith("http://") or value.startswith("https://"):
        return "reddit thread", value
    handle = value[2:] if value.startswith("u/") else value
    return f"u/{handle}", f"https://www.reddit.com/user/{handle}"


# How an upcoming film failed to resolve, in words. The distinction is worth
# printing: "we could not find it" and "it is not a film" are different states,
# and the second is not a bug to be fixed.
RESOLUTION_NOTE = {
    # "no usable year" rather than "no year": two of the three rows here DO give
    # one, as a range, because they are TV series rather than films.
    "unresolved_no_year": "no single release year — not matched, to avoid a wrong film",
    "unresolved_no_match": "TMDB has no film under this title",
    "unresolved_low_confidence": "no confident TMDB match",
    "unresolved_error": "the TMDB lookup failed; it will retry",
}


def pitch_chips(tags):
    """The pitch tags as chips, reusing the keyword field's visual language."""
    if not tags:
        return ""
    chips = "".join(f'<span class="rw-up-tag">{t}</span>' for t in tags)
    return f'<div class="rw-up-tags">{chips}</div>'
