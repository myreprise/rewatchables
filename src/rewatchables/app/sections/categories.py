"""The categories: every award, question and segment, episode by episode.

The entries come from rewatchvault.com, an independent archive of the show,
by way of steps 16 (fetch, in reviewed batches) and 17 (build). Until every
batch is in they cover part of the show, and the section says how much before
it shows a single number. One entry's card and discussion are drawn by
app/category_cards.py, which the film dossier shares.
"""

import pandas as pd
import streamlit as st

from rewatchables.app.category_cards import (
    FAMILY_LABEL, SOURCE_NOTE, coverage_note, day_label, episode_label, minute,
    render_entries,
)
from rewatchables.app.charts import per_database
from rewatchables.app.components import film_card, masthead, ranked_list, tape
from rewatchables.app.state import keep
from rewatchables.presentation import stat_tile
from rewatchables.sections.categories import (
    ALL, ALL_BUT, EXCLUDE_BY_DEFAULT, FAMILY_COLOUR, LIFESPAN_MIN, RUNNING_DAYS,
    UNCATEGORISED, category_options, lifespan_figure, lifespans, people_ranking,
)

# ── The section ───────────────────────────────────────────────────────────────

def _by_episode(ctx, cats):
    entries = cats.entries
    episodes = (entries.drop_duplicates("rv_episode_slug")
                .sort_values(["air_date", "rv_episode_slug"], ascending=False))
    labels = {r["rv_episode_slug"]: episode_label(r) for _, r in episodes.iterrows()}
    pick = keep(st.selectbox, "Episode", list(labels), format_func=labels.get,
                key="flt_cat_ep")
    chosen = entries[entries["rv_episode_slug"] == pick].sort_values(
        "transcript_seconds", na_position="last")
    first = chosen.iloc[0]

    left, right = st.columns([1, 4.2])
    with left:
        movie = ctx.movies[ctx.movies["movie_id"] == first["movie_id"]]
        if len(movie):
            film_card(movie.iloc[0], subtitle="Open the film", key="cat_ep")
        else:
            st.caption("Not linked to the episode list yet; see report 023.")
    with right:
        n_cats = chosen["category_slug"].nunique()
        st.markdown(
            f'<div class="rw-kw-gridnote"><span>{len(chosen)} entries · {n_cats} categories '
            f'· in the order they aired</span></div>', unsafe_allow_html=True)
        render_entries(cats, chosen)


def _by_category(ctx, cats):
    entries, cats_df = cats.entries, cats.categories.set_index("category_slug")
    options = category_options(cats)

    def label(slug):
        if slug == UNCATEGORISED:
            return f"Uncategorised ({cats.coverage['uncategorised']})"
        row = cats_df.loc[slug]
        return f"{row['display_name']} · {FAMILY_LABEL[row['family']]} · {int(row['entries'])}"

    pick = keep(st.selectbox, "Category", options, format_func=label, key="flt_cat_cat")
    if pick == UNCATEGORISED:
        chosen = entries[entries["category_slug"].isna()]
        st.caption("Entries whose category couldn't be told from the page; "
                   "see step 17's log for each one.")
    else:
        chosen = entries[entries["category_slug"] == pick]
        row = cats_df.loc[pick]
        facts = [f"{int(row['entries'])} entries", f"{int(row['episodes'])} episodes",
                 f"first {day_label(row['first_aired'])}", f"last {day_label(row['last_aired'])}"]
        if row["banners"] > 1:
            facts.append(f"aired under {int(row['banners'])} names")
        st.markdown(f'<div class="rw-kw-gridnote"><span>{" · ".join(facts)}</span></div>',
                    unsafe_allow_html=True)

    table = pd.DataFrame({
        "Aired": pd.to_datetime(chosen["air_date"]),
        "EP": chosen["episode_number"].astype("Int64"),
        "Film": chosen["film_title"],
        "Category as aired": chosen["banner"],
        "Answer": chosen["answer"],
        "Minute": chosen["transcript_seconds"].map(minute),
        "Points": chosen["bullet_count"],
        "Page": chosen["source_url"],
    }).sort_values("Aired", ascending=False)
    st.dataframe(
        table, hide_index=True, use_container_width=True,
        column_config={
            "Aired": st.column_config.DateColumn(format="D MMM YYYY"),
            "Answer": st.column_config.TextColumn(width="large"),
            "Page": st.column_config.LinkColumn(display_text="rewatchvault"),
        },
    )
    # A toggle, not an expander: each entry's discussion is an expander of its
    # own, and Streamlit doesn't nest them.
    if keep(st.toggle, f"Read the discussions ({len(chosen)})", key="flt_cat_read"):
        render_entries(cats, chosen.sort_values("air_date", ascending=False), show_film=True)


def render(ctx):
    cats = ctx.categories
    masthead(
        "The categories",
        "Every award, question and segment the show hands out, with what was "
        "picked and how the room argued about it.",
    )

    if cats.entries.empty:
        # A database built before step 17, or before any batch was fetched.
        st.info(
            "No category data in this database yet. Fetch a batch, then build:\n\n"
            "`python scripts/16_load_categories.py --batch pilot`\n\n"
            "`python scripts/orchestrate.py --stages categories`"
        )
        st.stop()

    cov = cats.coverage
    note = coverage_note(cov)
    if note:
        st.markdown(note, unsafe_allow_html=True)

    people = int((cats.mentions["kind"] == "person").sum()) if len(cats.mentions) else 0
    st.markdown(
        '<div class="rw-dt-rail">'
        + stat_tile("Entries", f"{cov['entries']:,}")
        + stat_tile("Episodes", cov["episodes_covered"], coral=True)
        + stat_tile("Categories", len(cats.categories))
        + stat_tile("Names linked", f"{people:,}")
        + stat_tile("Hosts' picks", len(cats.picks))
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    view = keep(st.radio, "View", ["By episode", "By category", "Totals"], horizontal=True,
                key="flt_cat_view", label_visibility="collapsed")
    if view == "By episode":
        _by_episode(ctx, cats)
    elif view == "By category":
        _by_category(ctx, cats)
    else:
        _totals(ctx, cats)

    st.markdown(f'<p class="rw-cat-source">{SOURCE_NOTE}</p>', unsafe_allow_html=True)

# ── Totals (phase 4, report 033) ──────────────────────────────────────────────
# Two things are deliberately not here. Hosts' agreement on "Who Won the
# Movie?": 61% of picks have no identified speaker, and the likeliest pair
# (Bill and Chris) picked on the same page 7 times. Films referenced in
# discussion: 1,781 of 2,094 film links are the episode's own film, and the
# most-cited other film comes up in 3 episodes. Neither is enough to rank.

def _totals(ctx, cats):
    latest = cats.entries["air_date"].max()
    spans = lifespans(cats.categories, latest)
    running = int(spans["running"].sum())
    tape("How long each category has run")
    st.markdown(
        f'<div class="rw-kw-gridnote"><span>{len(spans)} recurring categories · '
        f'{running} still running · {len(spans) - running} retired</span></div>',
        unsafe_allow_html=True)
    st.plotly_chart(per_database("categories:lifespans", ctx.stamp,
                                 lambda: lifespan_figure(spans)),
                    use_container_width=True)
    st.caption(f"Standing categories, segments and \"the most…\" with {LIFESPAN_MIN} or more "
               f"entries. Still running means aired in the last {RUNNING_DAYS} days before "
               f"the latest episode ({day_label(latest)}).")

    tape("Who the categories name")
    cats_df = cats.categories.set_index("category_slug")
    named = sorted(
        (s for s in cats_df.index
         if cats_df.loc[s, "family"] in FAMILY_COLOUR and cats_df.loc[s, "entries"] >= LIFESPAN_MIN
         and not s.endswith("-proposal")),
        key=lambda s: cats_df.loc[s, "display_name"])

    def label(opt):
        if opt == ALL_BUT:
            return "All categories but Cruise or Hanks?"
        if opt == ALL:
            return "All categories"
        return cats_df.loc[opt, "display_name"]

    pick = keep(st.selectbox, "In", [ALL_BUT, ALL] + named, format_func=label,
                key="flt_cat_people")
    if pick == ALL_BUT:
        chosen = cats.entries[~cats.entries["category_slug"].isin(EXCLUDE_BY_DEFAULT)]
    elif pick == ALL:
        chosen = cats.entries
    else:
        chosen = cats.entries[cats.entries["category_slug"] == pick]

    left, right = st.columns(2)
    with left:
        st.markdown("##### Named in the answer")
        rows = people_ranking(chosen, cats.mentions, {"answer"})
        ranked_list([(name, eps) for name, eps, _ in rows], "No one is linked in these answers.",
                    note="Episodes in which the answer names them.")
    with right:
        st.markdown("##### Named anywhere in the discussion")
        rows = people_ranking(chosen, cats.mentions, {"answer", "bullet", "pick"})
        ranked_list([(name, eps) for name, eps, _ in rows], "No one is linked here.",
                    note="Episodes in which the answer, a discussion point or a pick names them.")
    st.caption("Film people only: the show's hosts and guests aren't counted, nor is a "
               "category's namesake inside it (Roger Ebert in his review segment). Hosts' "
               "agreement and the other films brought up are left out: too little data to "
               "rank (report 033).")
