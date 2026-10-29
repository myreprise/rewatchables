"""Budgets and grosses, in today's dollars.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.boxoffice; step 15 ships them to the public site.
"""

import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from rewatchables.figures import plotly_defaults
from rewatchables.palette import BLUE, CORAL, MINT_DEEP, TXT_3
from rewatchables.presentation import BREAK_EVEN_MULTIPLE, CPI_BASE_YEAR


# A decade with fewer films than this is named as too thin to read.
THIN_DECADE = 10
# Genres with fewer films than this are left off the median-gross chart.
GENRE_MIN = 5
# Films in each of the best- and worst-return tables.
RETURNS_SHOWN = 10


def money_frames(movies_df):
    """(fin, settled, with_both): films with a gross; those whose figures have
    stopped moving; and those of them with a budget too, so a return."""
    fin = movies_df[movies_df["revenue_real"].notna()].copy()
    settled = fin[~fin["money_provisional"]]
    with_both = settled[settled["multiple"].notna()]
    return fin, settled, with_both


def cost_vs_gross_frame(movies_df):
    _, settled, _ = money_frames(movies_df)
    return settled.dropna(subset=["budget_real", "revenue_real", "multiple"]).copy()


def merit_frame(movies_df):
    fin, _, _ = money_frames(movies_df)
    return fin.dropna(subset=["rating_tmdb", "revenue_real"])


def summary(movies_df):
    """Every number the section prints in a tile or a caption."""
    fin, _, with_both = money_frames(movies_df)
    n_short = int((with_both["multiple"] < BREAK_EVEN_MULTIPLE).sum())
    dec = fin.dropna(subset=["decade"])
    counts = (dec["decade"].astype(int).astype(str) + "s").value_counts()
    scat = cost_vs_gross_frame(movies_df)
    merit = merit_frame(movies_df)
    prov = movies_df[movies_df["money_provisional"] & movies_df["revenue_real"].notna()]
    return {
        "films": len(movies_df),
        "with_gross": len(fin),
        "median_gross": fin["revenue_real"].median(),
        "median_budget": fin["budget_real"].median(),
        "median_return": with_both["multiple"].median(),
        "with_return": len(with_both),
        "under_break_even": n_short,
        "no_gross": len(movies_df) - len(fin),
        "no_budget": int(movies_df["budget_real"].isna().sum()),
        "thin_decades": [(lbl, int(counts[lbl])) for lbl in sorted(counts.index)
                         if counts[lbl] < THIN_DECADE],
        "scatter_films": len(scat),
        "scatter_short": int((scat["multiple"] < BREAK_EVEN_MULTIPLE).sum()),
        "rho": merit["revenue_real"].corr(merit["rating_tmdb"], method="spearman"),
        "merit_films": len(merit),
        "provisional": [(r.title, int(r.year)) for r in prov.itertuples()],
    }


def figures(movies_df):
    """name -> figure, for every chart in the section."""
    fin, _, _ = money_frames(movies_df)
    figs = {}

    # The chart the section exists for. Drawn from CMU it was an artefact of a
    # 2012 Freebase snapshot; drawn nominal it was a picture of CPI.
    dec = fin.dropna(subset=["decade"]).copy()
    dec["decade_label"] = dec["decade"].astype(int).astype(str) + "s"
    fig = go.Figure()
    for label in sorted(dec["decade_label"].unique()):
        vals = dec.loc[dec["decade_label"] == label, "revenue_real"]
        fig.add_trace(go.Box(
            y=vals, name=label, marker_color=MINT_DEEP, line_color=MINT_DEEP,
            fillcolor="rgba(23,168,124,.18)", boxpoints="outliers",
            marker_size=4, showlegend=False,
        ))
    fig.update_layout(
        yaxis_title=f"Worldwide gross ({CPI_BASE_YEAR}$)",
        xaxis_title="Release decade", yaxis_type="log",
    )
    figs["by_decade"] = plotly_defaults(fig)

    scat = cost_vs_gross_frame(movies_df)
    scat["Outcome"] = np.where(
        scat["multiple"] >= BREAK_EVEN_MULTIPLE,
        f"Cleared {BREAK_EVEN_MULTIPLE:g}×", f"Under {BREAK_EVEN_MULTIPLE:g}×")
    fig = px.scatter(
        scat, x="budget_real", y="revenue_real", color="Outcome",
        color_discrete_map={f"Cleared {BREAK_EVEN_MULTIPLE:g}×": MINT_DEEP,
                            f"Under {BREAK_EVEN_MULTIPLE:g}×": CORAL},
        hover_name="title", hover_data={"year": True, "multiple": ":.1f",
                                        "budget_real": False, "revenue_real": False},
        log_x=True, log_y=True,
        labels={"budget_real": f"Budget ({CPI_BASE_YEAR}$)",
                "revenue_real": f"Worldwide gross ({CPI_BASE_YEAR}$)"},
    )
    fig.update_traces(marker=dict(size=7, opacity=0.8, line=dict(width=0)))
    lo = float(scat["budget_real"].min())
    hi = float(scat["budget_real"].max())
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo * BREAK_EVEN_MULTIPLE, hi * BREAK_EVEN_MULTIPLE],
        mode="lines", line=dict(color=TXT_3, width=1, dash="dash"),
        name=f"{BREAK_EVEN_MULTIPLE:g}× break-even", hoverinfo="skip",
    ))
    figs["cost_vs_gross"] = plotly_defaults(fig, legend=True)

    fig = px.scatter(
        merit_frame(movies_df), x="revenue_real", y="rating_tmdb", log_x=True,
        hover_name="title", hover_data={"year": True, "revenue_real": False},
        labels={"revenue_real": f"Worldwide gross ({CPI_BASE_YEAR}$)",
                "rating_tmdb": "TMDB rating"},
    )
    fig.update_traces(marker=dict(size=7, opacity=0.75, color=BLUE,
                                  line=dict(width=0)))
    figs["money_vs_rating"] = plotly_defaults(fig)

    g_long = fin.explode("genres").dropna(subset=["genres"])
    g_stat = (g_long.groupby("genres")
              .agg(median_gross=("revenue_real", "median"), films=("movie_id", "size"))
              .reset_index())
    g_stat = g_stat[g_stat["films"] >= GENRE_MIN].sort_values("median_gross")
    fig = go.Figure(go.Bar(
        x=g_stat["median_gross"], y=g_stat["genres"], orientation="h",
        marker_color=MINT_DEEP, marker_line_width=0,
        customdata=g_stat["films"],
        hovertemplate="%{y}<br>%{x:$,.0f}<br>%{customdata} films<extra></extra>",
    ))
    fig.update_layout(xaxis_title=f"Median gross ({CPI_BASE_YEAR}$)", yaxis_title="")
    figs["by_genre"] = plotly_defaults(fig)
    return figs


def returns(movies_df):
    """(best, worst): the films with the highest and lowest gross ÷ budget."""
    _, _, with_both = money_frames(movies_df)
    return (with_both.nlargest(RETURNS_SHOWN, "multiple"),
            with_both.nsmallest(RETURNS_SHOWN, "multiple"))


def money_table(movies_df):
    """Every film with a gross, highest first."""
    fin, _, _ = money_frames(movies_df)
    return fin.sort_values("revenue_real", ascending=False)
