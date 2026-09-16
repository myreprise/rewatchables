"""A film listeners have put forward, before it has an episode."""

import pandas as pd
import streamlit as st

from rewatchables.app.components import (
    poster_art, poster_html, rings_svg,
)
from rewatchables.app.state import close_dossier, open_prospect
from views import (
    RESOLUTION_NOTE, clean, contributor_link, html, pitch_chips, plain,
    stat_tile,
)

def why_html(row):
    """The reason a film is on the list, and who put it there.

    Every card leads with this rather than with metadata. A requested film has
    no episode, no room and no verdict, so the justification is the only thing
    on the card that is actually about this film rather than about the movie —
    and it is the thing a reader is here for.
    """

    note = clean(row.get("mention_note"))
    tags = row.get("tags") or []
    label, href = contributor_link(row.get("contributor"))

    if note:
        body = plain(note)
    elif tags:
        body = pitch_chips(tags)
    else:
        # Three rows carry neither. Saying so is better than an empty box.
        body = '<i style="color:var(--txt-3)">No reason recorded.</i>'

    who = ""
    if label:
        who = (f'<span class="who">Put forward by '
               f'<a href="{href}" target="_blank" rel="noopener">{label}</a></span>')
    return f'<div class="rw-up-why">{body}{who}</div>'


def prospect_card(row, key=""):
    """A poster whose strip opens that requested film's panel.

    Deliberately the same shape as film_card, so the grid reads as the same kind
    of object as every other poster grid in the app — the difference between a
    film that aired and a film that might is a matter of what the card says, not
    of how it is built.
    """
    st.markdown(
        poster_html(row["poster_url_tmdb"], row["title"], label=False),
        unsafe_allow_html=True,
    )
    # Same two-line caption film_card uses: the blank line is what makes the
    # year read as a subtitle rather than as part of the title.
    caption = "{}\n\n{}".format(row["title"], row["year_raw"] or "—")
    if st.button(
        caption,
        key=f"btn_up_{key}_{row['upcoming_film_id']}",
        use_container_width=True,
    ):
        open_prospect(row["upcoming_film_id"])


def render_prospect(ctx, upcoming_film_id):
    """The detail panel for one requested film.

    Half a dossier by design: identity, the pitch, and the film itself. There is
    no episode spine because there is no episode — that is the whole distinction
    this section exists to draw.
    """
    upcoming_df = ctx.upcoming

    match = upcoming_df[upcoming_df["upcoming_film_id"] == upcoming_film_id]
    if match.empty:
        # The list is rebuilt every pipeline run, so a shared link can outlive
        # its row -- most likely because the film became a real episode.
        st.warning("That film is no longer on the upcoming list. It may have "
                   "become an episode.")
        if st.button("← Back to Upcoming Films", key="btn_up_back_missing"):
            close_dossier()
            st.rerun()
        return
    row = match.iloc[0]

    if st.button("← Back to Upcoming Films", key="btn_up_back"):
        close_dossier()
        st.rerun()

    directors = " · ".join(row["directors"]) if row["directors"] else None
    genres = " · ".join(row["genres"]) if row["genres"] else None
    cred = " <i>/</i> ".join(x for x in (directors, genres) if x)

    rail = [stat_tile("Year", row["year_raw"] or None)]
    rail.append(stat_tile("Runtime", int(row["runtime_minutes"]) if pd.notna(
        row["runtime_minutes"]) else None, " min"))
    rail.append(stat_tile("TMDB", f"{row['rating_tmdb']:.1f}" if pd.notna(
        row["rating_tmdb"]) else None, "/10"))
    rail.append(stat_tile("Status", "Requested", coral=True))

    st.markdown(html(f"""
    <div class="rw-dt-hero">
      {rings_svg()}
      <div class="rw-dt-poster">
        {poster_art(row["poster_url_tmdb"], row["title"])}
      </div>
      <div class="rw-dt-id">
        <p class="rw-dt-loose">Upcoming &middot; not yet an episode</p>
        <h1>{row["title"]} <span>{row["year_raw"] or ""}</span></h1>
        <div class="rw-dt-cred">{cred}</div>
        <div class="rw-dt-rail">{"".join(rail)}</div>
      </div>
    </div>"""), unsafe_allow_html=True)

    if not row["resolved"]:
        st.markdown(
            f'<div class="rw-up-unres">Unmatched &mdash; '
            f'{RESOLUTION_NOTE.get(row["resolution_method"], "not matched")}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="rw-dt-panel"><h4>Why it is on the list</h4>'
                + why_html(row) + "</div>", unsafe_allow_html=True)

    if row["tags"] and clean(row.get("mention_note")):
        # Both populated is rare -- the source columns are alternatives -- but
        # when it happens the tags are additional, not a duplicate of the note.
        st.markdown('<div class="rw-dt-panel"><h4>Pitched as</h4>'
                    + pitch_chips(row["tags"]) + "</div>", unsafe_allow_html=True)

    if clean(row.get("plot_summary")):
        st.markdown(
            '<div class="rw-dt-panel"><h4>The film</h4>'
            f'<p class="rw-dt-logline">{plain(row["plot_summary"])}</p></div>',
            unsafe_allow_html=True,
        )

    if row["cast_names"]:
        cast = "".join(f"<span>{name}</span>" for name in row["cast_names"][:10])
        st.markdown(
            '<div class="rw-dt-panel"><h4>Cast</h4>'
            f'<div class="rw-dt-cast">{cast}</div></div>',
            unsafe_allow_html=True,
        )

    tmdb_link = (f'<a href="https://www.themoviedb.org/movie/{int(row["tmdb_id"])}" '
                 f'target="_blank" rel="noopener">TMDB</a>'
                 if pd.notna(row["tmdb_id"]) else "<b>no TMDB match</b>")
    st.markdown(
        f'<div class="rw-dt-prov"><span>Source <b>data/upcoming.csv</b></span>'
        f'<span>Match <b>{row["resolution_method"]}</b></span>'
        f'<span>{tmdb_link}</span></div>',
        unsafe_allow_html=True,
    )
