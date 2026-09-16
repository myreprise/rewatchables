"""Budgets and grosses, in today's dollars."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rewatchables.app.charts import plotly_defaults
from rewatchables.app.components import masthead, tape
from rewatchables.app.theme import BLUE, CORAL, MINT_DEEP, TXT_3
from views import (
    BREAK_EVEN_MULTIPLE, CPI_BASE_YEAR, CPI_PROVISIONAL_FROM, money,
)


def render(ctx):
    movies_df = ctx.movies

    masthead(
        "Box Office",
        f"What these films cost, what they took, and what came back &mdash; "
        f"every figure in {CPI_BASE_YEAR} dollars.",
    )

    fin = movies_df[movies_df["revenue_real"].notna()].copy()
    settled = fin[~fin["money_provisional"]]
    with_both = settled[settled["multiple"].notna()]
    n_short = int((with_both["multiple"] < BREAK_EVEN_MULTIPLE).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Films with a gross", f"{len(fin)} / {len(movies_df)}")
    c2.metric(f"Median gross ({CPI_BASE_YEAR}$)", money(fin["revenue_real"].median()))
    c3.metric(f"Median budget ({CPI_BASE_YEAR}$)", money(fin["budget_real"].median()))
    c4.metric("Median return", f"{with_both['multiple'].median():.1f}×")
    c5.metric("Under break-even", f"{n_short} / {len(with_both)}")

    st.caption(
        f"Gross and budget come from TMDB and are worldwide theatrical, "
        f"converted to {CPI_BASE_YEAR} dollars with US CPI-U. Return is gross ÷ "
        f"budget: it is not profit, since neither figure includes marketing or "
        f"the exhibitor's share, so the break-even line is drawn at the "
        f"industry rule of thumb of {BREAK_EVEN_MULTIPLE:g}×, not 1×. "
        f"{len(movies_df) - len(fin)} films have no published gross and "
        f"{int(movies_df['budget_real'].isna().sum())} no budget; they are "
        f"absent from these charts rather than counted as zero."
    )

    st.markdown("---")

    # ── Gross by decade ──
    # The chart the section exists for. Drawn from CMU it was an artefact of a
    # 2012 Freebase snapshot; drawn nominal it was a picture of CPI.
    tape(f"Gross by release decade ({CPI_BASE_YEAR} dollars)")
    dec = fin.dropna(subset=["decade"]).copy()
    dec["decade_label"] = dec["decade"].astype(int).astype(str) + "s"
    counts = dec["decade_label"].value_counts()
    order = sorted(dec["decade_label"].unique())

    fig = go.Figure()
    for label in order:
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
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    thin = [f"{lbl} ({counts[lbl]})" for lbl in order if counts[lbl] < 10]
    if thin:
        st.caption(
            "Log scale. Decades carrying fewer than ten films — "
            + ", ".join(thin)
            + " — are too thin to read as a trend."
        )

    st.markdown("---")

    # ── Budget against gross ──
    tape("What it cost against what it took")
    scat = settled.dropna(subset=["budget_real", "revenue_real", "multiple"]).copy()
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
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Both axes log. {len(scat) - n_short} of {len(scat)} films cleared the "
        f"line; the {n_short} below it are the ones the show likes anyway."
    )

    st.markdown("---")

    # ── The multiple, both ends ──
    tape("The best returns, and the worst")
    lead, lag = st.columns(2)
    with lead:
        st.markdown("**Most returned per dollar spent**")
        top = with_both.nlargest(10, "multiple")
        st.dataframe(
            pd.DataFrame({
                "Film": top["title"],
                "Year": top["year"],
                "Budget": top["budget_real"].map(money),
                "Gross": top["revenue_real"].map(money),
                "Return": top["multiple"].map(lambda v: f"{v:,.0f}×"),
            }), hide_index=True, use_container_width=True)
    with lag:
        st.markdown("**Lost the most, and got an episode anyway**")
        bot = with_both.nsmallest(10, "multiple")
        st.dataframe(
            pd.DataFrame({
                "Film": bot["title"],
                "Year": bot["year"],
                "Budget": bot["budget_real"].map(money),
                "Gross": bot["revenue_real"].map(money),
                "Return": bot["multiple"].map(lambda v: f"{v:.2f}×"),
            }), hide_index=True, use_container_width=True)

    prov = movies_df[movies_df["money_provisional"] & movies_df["revenue_real"].notna()]
    if len(prov):
        st.caption(
            "Excludes " + ", ".join(f"{r.title} ({int(r.year)})"
                                    for r in prov.itertuples())
            + f" — released {CPI_PROVISIONAL_FROM} or later, so the gross is "
            "still moving and the budget is often a placeholder. TMDB has one "
            "of them at a $750K budget against a $506M gross."
        )

    st.markdown("---")

    # ── Money against merit ──
    tape("Does the money track the rating?")
    merit = fin.dropna(subset=["rating_tmdb", "revenue_real"])
    rho = merit["revenue_real"].corr(merit["rating_tmdb"], method="spearman")
    fig = px.scatter(
        merit, x="revenue_real", y="rating_tmdb", log_x=True,
        hover_name="title", hover_data={"year": True, "revenue_real": False},
        labels={"revenue_real": f"Worldwide gross ({CPI_BASE_YEAR}$)",
                "rating_tmdb": "TMDB rating"},
    )
    fig.update_traces(marker=dict(size=7, opacity=0.75, color=BLUE,
                                  line=dict(width=0)))
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Spearman ρ = {rho:.2f} over {len(merit)} films — a weak positive "
        "relationship. Money and merit are close to independent here, which is "
        "the whole premise of a show that will spend an hour on a film that "
        "lost its studio money."
    )

    st.markdown("---")

    # ── Genre ──
    tape(f"Median gross by genre ({CPI_BASE_YEAR} dollars)")
    g_long = fin.explode("genres").dropna(subset=["genres"])
    g_stat = (g_long.groupby("genres")
              .agg(median_gross=("revenue_real", "median"), films=("movie_id", "size"))
              .reset_index())
    g_stat = g_stat[g_stat["films"] >= 5].sort_values("median_gross")
    fig = go.Figure(go.Bar(
        x=g_stat["median_gross"], y=g_stat["genres"], orientation="h",
        marker_color=MINT_DEEP, marker_line_width=0,
        customdata=g_stat["films"],
        hovertemplate="%{y}<br>%{x:$,.0f}<br>%{customdata} films<extra></extra>",
    ))
    fig.update_layout(xaxis_title=f"Median gross ({CPI_BASE_YEAR}$)", yaxis_title="")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Genres carrying fewer than five films are omitted.")

    st.markdown("---")

    # ── Table ──
    tape("Data table")
    table = fin.sort_values("revenue_real", ascending=False)
    st.dataframe(
        pd.DataFrame({
            "Film": table["title"],
            "Year": table["year"],
            f"Budget ({CPI_BASE_YEAR}$)": table["budget_real"].map(money),
            f"Gross ({CPI_BASE_YEAR}$)": table["revenue_real"].map(money),
            "Return": table["multiple"].map(
                lambda v: f"{v:,.1f}×" if pd.notna(v) else "—"),
            "TMDB": table["rating_tmdb"].round(1),
            "Episodes": table["total_episodes_featured"],
        }), hide_index=True, use_container_width=True, height=420)
