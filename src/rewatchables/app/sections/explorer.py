"""The filterable grid of every film, and the way into a dossier."""

import pandas as pd
import streamlit as st

from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.overlays.dossier import render_dossier
from rewatchables.app.state import keep, kept


def render(ctx):
    movies_df = ctx.movies
    movies_rated = ctx.rated
    selected_film = st.session_state.get("dt_movie")

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
        render_dossier(ctx, selected_film, siblings=view["movie_id"].tolist())
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
