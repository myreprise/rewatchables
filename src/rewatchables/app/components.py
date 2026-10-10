"""The pieces every section is drawn from: cards, plates, tiles, chips.

Presentation only. Nothing here reads the database or decides what to show --
a caller hands in the row, the list or the numbers. The one exception is the
click: a poster card opens the film's dossier, and a keyword chip opens the
keyword, because a card that does not navigate is not what these are for.
"""

import streamlit as st

from rewatchables import images
from rewatchables.app.state import open_dossier, open_keyword
from rewatchables.app.theme import MINT
from views import LINK_FLOOR, keyword_chip, rank_by_reach


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
    """The plate itself — the w185 poster, or the rings fallback.

    It takes no height: .poster-img sizes it at 2:3 to its column's width, so a
    plate never carries a height of its own to disagree with the poster's shape.
    """
    thumb = images.src(url, "w185")
    if thumb:
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


def stat_tiles(items):
    """A KPI row, items being (label, value) pairs.

    st.metric is what Box Office and Keywords already use for this, so these
    rows inherit the same tile styling rather than introducing a second one.
    """
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)


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


def keyword_row(words, key, reach, cap=None, current=None):
    """A flowing row of keyword chips, most far-reaching first.

    A chip at or above the link floor navigates. Below it the chip still prints
    — it describes the film — but as inert text, because a keyword whose only
    film is the one you are already on is not somewhere to go.

    Every chip carries its reach. That number is the whole point: it says where
    the chip leads before you spend a click on it.
    """
    ranked = rank_by_reach(words, reach)
    if cap:
        ranked = ranked[:cap]
    live = [w for w in ranked if reach.get(w, 0) >= LINK_FLOOR and w != current]
    inert = [w for w in ranked if reach.get(w, 0) < LINK_FLOOR]

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
                    f"{word}  {reach.get(word, 0)}",
                    key=f"btn_kw_{key}_{word}",
                ):
                    open_keyword(word)

    if inert:
        st.markdown(
            '<div class="rw-kw-field">'
            + "".join(keyword_chip(w, reach.get(w, 0), inert=True) for w in inert)
            + "</div>",
            unsafe_allow_html=True,
        )
