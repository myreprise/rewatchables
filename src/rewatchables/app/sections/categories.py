"""The categories: every award, question and segment, episode by episode.

The entries come from rewatchvault.com, an independent archive of the show,
by way of steps 16 (fetch, in reviewed batches) and 17 (build). Until every
batch is in they cover part of the show, and the section says how much before
it shows a single number. One entry's card and discussion are drawn by
app/category_cards.py, which the film dossier shares.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rewatchables.app.category_cards import (
    FAMILY_LABEL, FAMILY_ORDER, SOURCE_NOTE, day_label, coverage_note, episode_label,
    minute, render_entries,
)
from rewatchables.app.charts import per_database, plotly_defaults
from rewatchables.app.components import film_card, masthead, ranked_list, tape
from rewatchables.app.state import keep
from rewatchables.app.theme import AMBER, BLUE, MINT_DEEP
from views import stat_tile

UNCATEGORISED = "__none__"


# ── The section ───────────────────────────────────────────────────────────────

def category_options(cats):
    """Category slugs in menu order: standing, segments, 'the most…', one-offs;
    busiest first within each. Entries with no category come last."""
    cats_df = cats.categories.copy()
    cats_df["order"] = cats_df["family"].map({f: i for i, f in enumerate(FAMILY_ORDER)})
    ordered = cats_df.sort_values(["order", "entries", "display_name"],
                                  ascending=[True, False, True])["category_slug"].tolist()
    if cats.coverage["uncategorised"]:
        ordered.append(UNCATEGORISED)
    return ordered


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

# A category must have aired this many times to get a lifespan bar: below it,
# a "lifespan" is one or two dots, and the -proposal ids would repeat the
# names of the categories they talk about.
LIFESPAN_MIN = 3
# Last aired this close to the latest episode counts as still running.
RUNNING_DAYS = 60
RANKED = 15
EXCLUDE_BY_DEFAULT = {"cruise-hanks"}     # its answer is one of two people by design
FAMILY_COLOUR = {"standing": MINT_DEEP, "segment": AMBER, "most_year": BLUE}
ALL_BUT = "__all_but__"
ALL = "__all__"


def lifespans(categories_df, latest):
    """The recurring categories, oldest first, with whether each still runs.

    Recurring means standing, segment or "the most…" with LIFESPAN_MIN entries
    or more; -proposal ids are talk about a category, never one (report 031).
    """
    df = categories_df[
        categories_df["family"].isin(FAMILY_COLOUR)
        & (categories_df["entries"] >= LIFESPAN_MIN)
        & ~categories_df["category_slug"].str.endswith("-proposal")
    ].copy()
    df["first"] = pd.to_datetime(df["first_aired"])
    df["last"] = pd.to_datetime(df["last_aired"])
    df["running"] = (pd.Timestamp(latest) - df["last"]).dt.days <= RUNNING_DAYS
    return df.sort_values(["first", "display_name"]).reset_index(drop=True)


def display_names(mentions):
    """{slug: the fullest name it appears under}. The site links "Pacino" and
    "Al Pacino" to one person; the most words wins, then the commonest."""
    counts = mentions.groupby(["slug", "name"]).size().reset_index(name="n")
    counts["words"] = counts["name"].str.split().str.len()
    best = counts.sort_values(["slug", "words", "n"], ascending=[True, False, False])
    return best.drop_duplicates("slug").set_index("slug")["name"].to_dict()


def people_ranking(entries, mentions, locations, exclude=(), top=RANKED):
    """Film people linked in `locations` (answer / bullet / pick), ranked by the
    episodes they're named in, then by entries. [(name, episodes, entries)].

    Two kinds of link are not counted, because they say nothing about the film:
      * the show's own people -- hosts and guests have rewatchvault person
        pages (bill-simmons), film people have film-person: ids;
      * a category's namesake inside it: Roger Ebert in "Roger Ebert's review"
        (79 of his 85 links), Dion Waiters in his own award (76 of 105);
      * a link on a word with no capital letter: rewatchvault's linker turned
        "more common modern depictions" into the actor Common (49 times), and
        likewise "usher", "flea", "prince" and "50" -- 69 links in all.
    """
    people = mentions[(mentions["kind"] == "person") & mentions["location"].isin(locations)
                      & mentions["slug"].fillna("").str.startswith("film-person:")
                      & mentions["name"].fillna("").str.contains(r"[A-Z]")]
    keep_entries = entries[~entries["category_slug"].isin(exclude)]
    joined = people.merge(keep_entries[["discussion_slug", "rv_episode_slug", "banner"]],
                          on="discussion_slug")
    if joined.empty:
        return []
    names = display_names(people)
    full = joined["slug"].map(names)
    namesake = [isinstance(b, str) and (n.lower() in b.lower() or f.lower() in b.lower())
                for n, f, b in zip(joined["name"], full, joined["banner"])]
    joined = joined[~pd.Series(namesake, index=joined.index)]
    if joined.empty:
        return []
    agg = (joined.groupby("slug")
           .agg(episodes=("rv_episode_slug", "nunique"), entries=("discussion_slug", "nunique"))
           .reset_index())
    agg["name"] = agg["slug"].map(names)
    agg = agg.sort_values(["episodes", "entries", "name"], ascending=[False, False, True]).head(top)
    return list(agg[["name", "episodes", "entries"]].itertuples(index=False, name=None))


LABEL_CHARS = 30


def short_label(name, limit=LABEL_CHARS):
    """An axis label that leaves the timeline room: no leading "The ", cut at a
    word boundary with an ellipsis. The full name stays in the hover."""
    name = name[4:] if name.startswith("The ") else name
    if len(name) <= limit:
        return name
    cut = name[:limit].rsplit(" ", 1)[0].rstrip(" ,:/–-")
    return cut + "…"


def lifespan_figure(spans):
    """One row per recurring category: a line from first to last aired, a dot at
    each end, coloured by family. The category names on the axis carry identity
    as well as the colour; the hover gives the dates and counts."""
    fig = go.Figure()
    # Short labels must stay distinct, or two categories would share a row.
    labels, seen = {}, {}
    for name in spans["display_name"]:
        short = short_label(name)
        seen[short] = seen.get(short, 0) + 1
        labels[name] = short if seen[short] == 1 else f"{short} ({seen[short]})"
    for family, colour in FAMILY_COLOUR.items():
        part = spans[spans["family"] == family]
        if part.empty:
            continue
        xs, ys, tips = [], [], []
        for r in part.itertuples():
            status = "still running" if r.running else f"last aired {day_label(r.last_aired)}"
            tip = (f"<b>{r.display_name}</b><br>{FAMILY_LABEL[family]} · {r.entries} entries"
                   f"<br>first {day_label(r.first_aired)} · {status}")
            xs += [r.first, r.last, None]
            ys += [labels[r.display_name], labels[r.display_name], None]
            tips += [tip, tip, None]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers", name=FAMILY_LABEL[family],
            line=dict(color=colour, width=2), marker=dict(color=colour, size=8),
            hovertext=tips, hoverinfo="text", connectgaps=False,
        ))
    order = [labels[n] for n in spans["display_name"]]
    fig.update_layout(
        height=24 * len(spans) + 110,
        yaxis=dict(categoryorder="array", categoryarray=order[::-1], title=""),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=60, r=20, b=40, l=10),
    )
    plotly_defaults(fig, legend=True)
    return fig


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
