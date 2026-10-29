"""Plotly figures, styled the same way wherever they are shown.

plotly_defaults is the one place the chart furniture is decided -- grid, font,
hover, margins -- so a new chart looks like the others by passing through it
rather than by copying a dozen settings. The folding helpers keep a categorical
chart inside the fixed colour series: past its length, the tail becomes one
"other" band rather than cycling colours that then mean two things at once.

Nothing here draws: the app hands these figures to st.plotly_chart, and step
15 ships them to the public site as Plotly JSON.
"""

import json
from pathlib import Path

import plotly.express as px
import plotly.io as pio

from rewatchables.analysis import explode_cast, explode_genres
from rewatchables.palette import (
    AMBER, BLUE, INK, INK_2, INK_3, LINE, LINE_2, MINT_DEEP, SEQ, SERIES, TAPE, TXT_3,
    VIOLET,
)


# The template every figure is built on, set here so it is explicit. It used to
# arrive by side effect: importing streamlit makes its own template Plotly's
# default, and step 15 imported streamlit through the app's modules, so the
# site's figures carried it. plotly_template.json is that template as it was,
# kept so moving the code out of the app changed no figure. Its colours are
# placeholders (#000001...) that only Streamlit's front end swaps for real
# ones: in the app st.plotly_chart replaces them, but on the site they are
# drawn as they are, so a trace that takes its colour from the template is
# near-black there. See reports/progress/036.
pio.templates["rewatchables"] = json.loads(
    (Path(__file__).parent / "plotly_template.json").read_text(encoding="utf-8"))
pio.templates.default = "rewatchables"


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


GENDER_COLOUR = {"M": BLUE, "F": AMBER, "NB": VIOLET, "unknown": TXT_3}


def people_scatter_fig(stats, name_col, name_from=4):
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
    return plotly_defaults(fig)


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


def gender_leaderboard_figs(df, gender_map, top_n=15, genders=("M", "F")):
    """{gender: (actors counted, figure)}, for the genders with anyone, every
    figure on one shared x-axis."""
    ranked = {g: explode_cast(df, top_n=top_n, gender=g, gender_map=gender_map).rename(
        columns={"count": "films"}) for g in genders}
    present = [g for g in genders if not ranked[g].empty]
    if not present:
        return {}
    xmax = max(ranked[g]["films"].max() for g in present)
    return {g: (len(explode_cast(df, top_n=100_000, gender=g,
                                 gender_map=gender_map)),
                _leaderboard_fig(ranked[g], "actor", GENDER_COLOUR[g], xmax=xmax))
            for g in present}


def spotlight_figures(films):
    """The spotlight's two charts for one person's films: genre mix and decades."""
    ordered = films.sort_values("year")
    g = explode_genres(ordered)["genre"].value_counts().reset_index()
    g.columns = ["genre", "count"]
    g, cmap, order = fold_counts(g, "genre", "count")
    genres = px.pie(
        g, values="count", names="genre", color="genre",
        color_discrete_map=cmap, category_orders={"genre": order}, hole=0.45,
    )
    genres.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2,
                         height=270, margin=dict(t=10, b=10, l=10, r=10),
                         showlegend=False)
    genres.update_traces(textinfo="label+percent", textfont_size=10)

    dec = (ordered["year"].dropna() // 10 * 10).astype(int).value_counts().sort_index()
    decades = px.bar(
        x=[f"{d}s" for d in dec.index], y=dec.to_numpy(),
        color_discrete_sequence=[MINT_DEEP], text=dec.to_numpy(),
    )
    decades.update_traces(textposition="outside", cliponaxis=False)
    decades.update_layout(height=270, margin=dict(t=10, b=10, l=10, r=10),
                          xaxis_title="", yaxis_title="", yaxis_visible=False)
    plotly_defaults(decades)
    return {"genres": genres, "decades": decades}
