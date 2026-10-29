"""The categories: every award, question and segment, episode by episode.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.categories. They stay off the public site
(APP_ONLY): the entries are rewatchvault.com's text, not ours to republish.
"""

import pandas as pd
import plotly.graph_objects as go

from rewatchables.figures import plotly_defaults
from rewatchables.palette import AMBER, BLUE, MINT_DEEP


FAMILY_LABEL = {"standing": "Standing", "segment": "Segment",
                "most_year": "The most…", "one_off": "One-off award"}
FAMILY_ORDER = ["standing", "segment", "most_year", "one_off"]
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


def day_label(iso):
    if not iso or pd.isna(iso):
        return "date unknown"
    d = pd.Timestamp(iso)
    return f"{d.day} {d:%b %Y}"   # %-d is glibc-only


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
