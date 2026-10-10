"""Films listeners have put forward, before they have an episode."""

from collections import Counter

import pandas as pd
import streamlit as st

from rewatchables import images
from rewatchables.app.components import masthead, tape
from rewatchables.app.overlays.prospect import prospect_card, why_html
from rewatchables.app.state import keep, open_dossier
from views import RESOLUTION_NOTE, html, keyword_chip, stat_tile


def render(ctx):
    graduated_df = ctx.graduated
    upcoming_df = ctx.upcoming

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
            art = images.src(row["poster_url_tmdb"], "w185")
            poster = f'<img src="{art}" alt="">' if art else ""
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
