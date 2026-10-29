"""Budgets and grosses, in today's dollars."""

import pandas as pd
import streamlit as st

from rewatchables.app.components import masthead, tape
from rewatchables.presentation import (
    BREAK_EVEN_MULTIPLE, CPI_BASE_YEAR, CPI_PROVISIONAL_FROM, money,
)
from rewatchables.sections.boxoffice import figures, money_table, returns, summary

def render(ctx):
    movies_df = ctx.movies
    s = summary(movies_df)
    figs = figures(movies_df)

    masthead(
        "Box Office",
        f"What these films cost, what they took, and what came back &mdash; "
        f"every figure in {CPI_BASE_YEAR} dollars.",
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Films with a gross", f"{s['with_gross']} / {s['films']}")
    c2.metric(f"Median gross ({CPI_BASE_YEAR}$)", money(s["median_gross"]))
    c3.metric(f"Median budget ({CPI_BASE_YEAR}$)", money(s["median_budget"]))
    c4.metric("Median return", f"{s['median_return']:.1f}×")
    c5.metric("Under break-even", f"{s['under_break_even']} / {s['with_return']}")

    st.caption(
        f"Gross and budget come from TMDB and are worldwide theatrical, "
        f"converted to {CPI_BASE_YEAR} dollars with US CPI-U. Return is gross ÷ "
        f"budget: it is not profit, since neither figure includes marketing or "
        f"the exhibitor's share, so the break-even line is drawn at the "
        f"industry rule of thumb of {BREAK_EVEN_MULTIPLE:g}×, not 1×. "
        f"{s['no_gross']} films have no published gross and "
        f"{s['no_budget']} no budget; they are "
        f"absent from these charts rather than counted as zero."
    )

    st.markdown("---")

    tape(f"Gross by release decade ({CPI_BASE_YEAR} dollars)")
    st.plotly_chart(figs["by_decade"], use_container_width=True)
    if s["thin_decades"]:
        st.caption(
            "Log scale. Decades carrying fewer than ten films — "
            + ", ".join(f"{lbl} ({n})" for lbl, n in s["thin_decades"])
            + " — are too thin to read as a trend."
        )

    st.markdown("---")

    tape("What it cost against what it took")
    st.plotly_chart(figs["cost_vs_gross"], use_container_width=True)
    st.caption(
        f"Both axes log. {s['scatter_films'] - s['scatter_short']} of "
        f"{s['scatter_films']} films cleared the line; the {s['scatter_short']} "
        "below it are the ones the show likes anyway."
    )

    st.markdown("---")

    # ── The multiple, both ends ──
    tape("The best returns, and the worst")
    top, bot = returns(movies_df)
    lead, lag = st.columns(2)
    with lead:
        st.markdown("**Most returned per dollar spent**")
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
        st.dataframe(
            pd.DataFrame({
                "Film": bot["title"],
                "Year": bot["year"],
                "Budget": bot["budget_real"].map(money),
                "Gross": bot["revenue_real"].map(money),
                "Return": bot["multiple"].map(lambda v: f"{v:.2f}×"),
            }), hide_index=True, use_container_width=True)

    if s["provisional"]:
        st.caption(
            "Excludes " + ", ".join(f"{t} ({y})" for t, y in s["provisional"])
            + f" — released {CPI_PROVISIONAL_FROM} or later, so the gross is "
            "still moving and the budget is often a placeholder. TMDB has one "
            "of them at a $750K budget against a $506M gross."
        )

    st.markdown("---")

    tape("Does the money track the rating?")
    st.plotly_chart(figs["money_vs_rating"], use_container_width=True)
    st.caption(
        f"Spearman ρ = {s['rho']:.2f} over {s['merit_films']} films — a weak positive "
        "relationship. Money and merit are close to independent here, which is "
        "the whole premise of a show that will spend an hour on a film that "
        "lost its studio money."
    )

    st.markdown("---")

    tape(f"Median gross by genre ({CPI_BASE_YEAR} dollars)")
    st.plotly_chart(figs["by_genre"], use_container_width=True)
    st.caption("Genres carrying fewer than five films are omitted.")

    st.markdown("---")

    tape("Data table")
    table = money_table(movies_df)
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
