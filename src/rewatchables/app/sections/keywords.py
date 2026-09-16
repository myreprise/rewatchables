"""The keyword vocabulary, browsable."""

from collections import Counter

import streamlit as st

from rewatchables.app.components import keyword_row, masthead, tape
from rewatchables.app.state import keep
from views import BROWSE_FLOOR


def render(ctx):
    REACH = ctx.reach
    movies_df = ctx.movies

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
            keyword_row(hits, "search", REACH)
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
        keyword_row(band, f"band_{low}", REACH)

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
