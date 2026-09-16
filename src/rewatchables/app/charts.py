"""Plotly figures, styled the way the app styles them.

plotly_defaults is the one place the chart furniture is decided -- grid, font,
hover, margins -- so a new chart looks like the others by passing through it
rather than by copying a dozen settings. The folding helpers keep a categorical
chart inside the fixed colour series: past its length, the tail becomes one
"other" band rather than cycling colours that then mean two things at once.
"""

import plotly.express as px
import streamlit as st

from rewatchables.app.theme import (
    AMBER, BLUE, INK, INK_2, INK_3, LINE, LINE_2, SEQ, SERIES,
    TAPE, TXT_3, VIOLET,
)


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
