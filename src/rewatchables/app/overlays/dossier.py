"""The per-film dossier: identity, episodes, the film, provenance."""

from collections import Counter

import pandas as pd
import streamlit as st

from rewatchables import images
from rewatchables.app.components import (
    keyword_row, rings_svg, shelf, tape,
)
from rewatchables.app.state import (
    DEFAULT_SECTION, SECTION_LABEL, close_dossier, open_dossier, open_person,
    resolve_section,
)
from views import (
    ANCHOR, CPI_BASE_YEAR, ROOM, clean, html, human_gap, money, plain, stars,
    stat_tile,
)


# The three lookups below are functions rather than lines in render_dossier()
# because the public site's film pages (pipeline step 15) show the same shelves.

def cast_billing(movies_df):
    """How many films each name is top-five billed in, across the catalogue."""
    billing = Counter()
    for names in movies_df["cast_names"]:
        for name in (names[:5] if isinstance(names, list) else []):
            billing[name] += 1
    return billing


def same_director(movies_df, movie):
    """The other films by this film's primary director, oldest first."""
    return movies_df[
        (movies_df["director_primary"] == movie["director_primary"])
        & (movies_df["movie_id"] != movie["movie_id"])
    ].sort_values("year")


def shared_cast(movies_df, movie):
    """Films sharing a top-billed name with this one, most-shared first."""
    cast = set(movie["cast_names"][:5]) if movie["cast_names"] else set()
    if not cast:
        return movies_df.iloc[0:0]
    overlap = movies_df[movies_df["movie_id"] != movie["movie_id"]].copy()
    overlap["shared"] = overlap["cast_names"].apply(
        lambda names: len(cast & set(names[:5])) if isinstance(names, list) else 0
    )
    return overlap[overlap["shared"] > 0].sort_values(
        ["shared", "year"], ascending=[False, True])


def render_dossier(ctx, movie_id, siblings=None):
    """The per-film detail view: identity, episodes, the film, provenance.

    `siblings` is the result set the film was clicked from, so the step arrows
    walk the same filtered list the grid was showing.
    """
    movies_df, links_df = ctx.movies, ctx.links
    REACH = ctx.reach

    movie = movies_df[movies_df["movie_id"] == movie_id].iloc[0]
    origin = SECTION_LABEL[
        resolve_section(st.session_state.get("nav_section", DEFAULT_SECTION))]

    # ── Return bar ──
    siblings = list(siblings) if siblings is not None else []
    position = siblings.index(movie_id) if movie_id in siblings else None
    cols = st.columns([3, 0.5, 0.5, 4])
    if cols[0].button(f"← Back to {origin}", key="btn_dt_back", use_container_width=True):
        close_dossier()
        st.rerun()
    if position is not None:
        if cols[1].button("‹", key="btn_dt_prev", use_container_width=True,
                          disabled=position == 0):
            open_dossier(siblings[position - 1])
        if cols[2].button("›", key="btn_dt_next", use_container_width=True,
                          disabled=position == len(siblings) - 1):
            open_dossier(siblings[position + 1])
        cols[3].markdown(
            f'<div class="rw-dt-count">Film {position + 1} of {len(siblings)}</div>',
            unsafe_allow_html=True,
        )

    # ── Hero ──
    episodes = links_df[links_df["movie_id"] == movie_id].sort_values("episode_number")
    directors = " &middot; ".join(movie["directors"]) or "Director unknown"
    genres = " &middot; ".join(movie["genres"]) or "Ungenred"
    runtime = f"{int(movie['runtime_minutes'])} min" if pd.notna(movie["runtime_minutes"]) else "runtime unknown"

    chips = []
    if movie["revisited_flag"] == 1:
        revisits = max(int(movie["total_episodes_featured"]) - 1, 1)
        chips.append(f'<span class="badge badge-revisit">Revisited &times;{revisits}</span>')
    chips.append(
        f'<span class="badge badge-mint">{int(movie["total_episodes_featured"])} '
        f'episode{"s" if movie["total_episodes_featured"] != 1 else ""}</span>'
    )
    if pd.notna(movie["first_episode_date"]):
        span = movie["first_episode_date"].strftime("%b %Y")
        if pd.notna(movie["last_episode_date"]) and movie["last_episode_date"] != movie["first_episode_date"]:
            span += " &rarr; " + movie["last_episode_date"].strftime("%b %Y")
        chips.append(f'<span class="badge">{span}</span>')

    # RT and Ebert are film attributes in the source sheet — verified constant
    # across every one of the 26 multi-episode films — so they belong here in
    # the hero, not repeated onto each episode card as if they had moved.
    rt = episodes["tomatoes_num"].dropna()
    ebert = episodes["ebert_num"].dropna()
    # Box office is the adjusted figure, so the tile can be read against any
    # other film in the catalogue without doing CPI arithmetic in your head.
    box = movie.get("revenue_real")
    mult = movie.get("multiple")
    rail = "".join([
        stat_tile("TMDB", f"{movie['rating_tmdb']:.1f}" if pd.notna(movie["rating_tmdb"]) else None, "/10"),
        stat_tile("Rotten Tomatoes", f"{rt.iloc[0] * 100:.0f}" if len(rt) else None, "%"),
        stat_tile("Ebert", stars(ebert.iloc[0]) if len(ebert) else None),
        stat_tile(f"Box office ({CPI_BASE_YEAR}$)", money(box) if pd.notna(box) else None),
        stat_tile("Return", f"{mult:.1f}" if pd.notna(mult) else None, "&times;"),
        stat_tile("Episodes", int(movie["total_episodes_featured"]), coral=True),
    ])

    poster = images.src(movie["poster_url_tmdb"], "w342")
    plate = (
        f'<img src="{poster}" alt="">' if poster
        else f'<div class="poster-plate">{rings_svg("")}<b>{movie["title"]}</b></div>'
    )
    st.markdown(html(f"""
    <div class="rw-dt-hero">
      {rings_svg()}
      <div class="rw-dt-poster">{plate}</div>
      <div class="rw-dt-id">
        <h1>{movie['title']} <span>{movie['year']}</span></h1>
        <p class="rw-dt-cred">{directors}<i>&middot;</i>{runtime}<i>&middot;</i>{genres}</p>
        <div class="chip-row">{''.join(chips)}</div>
        <div class="rw-dt-rail">{rail}</div>
      </div>
    </div>"""), unsafe_allow_html=True)

    # ── Episode spine ──
    tape(f"On the show &mdash; {len(episodes)} episode{'s' if len(episodes) != 1 else ''}")

    spine, previous_date = [], None
    for _, ep in episodes.iterrows():
        if previous_date is not None and pd.notna(ep["episode_date"]):
            gap = (ep["episode_date"] - previous_date).days
            if gap > 0:
                spine.append(f'<div class="rw-dt-gap">{human_gap(gap)}</div>')
        previous_date = ep["episode_date"]

        flags = []
        if ep["is_revisit"]:
            kind = (clean(ep["revisit_type"]) or "revisit").replace("_", " ")
            flags.append(
                f'<span class="badge badge-revisit">Revisit {int(ep["revisit_sequence"])} '
                f'&middot; {kind.replace(" revisit", "")}</span>'
            )
        else:
            flags.append('<span class="badge badge-mint">First watch</span>')
        # The verdict is genuinely episode-grained — it differs across episodes
        # for 8 of the 26 multi-episode films — so it rides on the card.
        verdict = clean(ep["cruise_hanks"])
        if verdict:
            tone = "cruise" if verdict.lower().startswith("cruise") else "hanks"
            flags.append(f'<span class="badge badge-{tone}">{verdict}</span>')

        room = []
        host = clean(ep["host"])
        if host:
            room.append(f'<span class="rw-dt-person is-host"><i>H</i>{host}</span>')
        for slot in ("guest1", "guest2", "guest3", "guest4"):
            guest = clean(ep.get(slot))
            if guest:
                room.append(f'<span class="rw-dt-person"><i>G</i>{guest}</span>')

        note = clean(ep["notes"])
        note_html = (
            f'<div class="rw-dt-epnote"><span class="lbl">Sheet note</span>{note}</div>'
            if note else ""
        )
        # %-d is glibc-only; build the unpadded day by hand so this runs on Windows.
        date = (
            f'{ep["episode_date"].day} {ep["episode_date"]:%b %Y}'
            if pd.notna(ep["episode_date"]) else "date unknown"
        )

        spine.append(html(f"""
        <div class="rw-dt-ep{' is-revisit' if ep['is_revisit'] else ''}">
          <div class="rw-dt-epcard">
            <div class="rw-dt-ephead">
              <span class="rw-dt-epno"><span>EP</span> {int(ep['episode_number']):03d}</span>
              <span class="rw-dt-epdate">{date}</span>
              <span class="rw-dt-epflags">{''.join(flags)}</span>
            </div>
            <div class="rw-dt-eproom"><span class="lbl">Room</span>{''.join(room)}</div>
            {note_html}
          </div>
        </div>"""))

    st.markdown(f'<div class="rw-dt-spine">{"".join(spine)}</div>', unsafe_allow_html=True)

    # Everyone in the room across this film's episodes, Bill aside, as a way
    # into the Hosts & Guests lookup. Buttons rather than links on the chips
    # above: a link reloads the session, and with it every filter behind the
    # dossier.
    seated = list(dict.fromkeys(
        name for _, ep in episodes.iterrows() for name in (ep[c] for c in ROOM)
        if isinstance(name, str) and name != ANCHOR))
    if seated:
        st.markdown(
            '<div class="rw-kw-gridnote"><span>Look up who was in the room</span></div>',
            unsafe_allow_html=True)
        per_row = 6
        for start in range(0, len(seated), per_row):
            cols = st.columns(per_row)
            for offset, (col, name) in enumerate(zip(cols, seated[start:start + per_row])):
                col.button(name, key=f"btn_dt_person_{start + offset}",
                           use_container_width=True, on_click=open_person, args=(name,))

    # ── The film ──
    tape("The film")
    left, right = st.columns([1.65, 1])

    with left:
        st.markdown(
            '<div class="rw-dt-panel"><h4>Plot</h4>'
            f'<p class="rw-dt-logline">'
            f'{plain(movie["plot_summary"]) or "No summary on file."}</p></div>',
            unsafe_allow_html=True,
        )
        synopsis = clean(movie["plot_summary_wiki"])
        if synopsis:
            words = movie["plot_summary_wiki_words"]
            with st.expander(f"Full Wikipedia synopsis — {int(words):,} words"):
                st.markdown(plain(synopsis))
        if movie["keywords"]:
            words = movie["keywords"]
            st.markdown('<h4 class="rw-dt-loose">Keywords</h4>', unsafe_allow_html=True)
            # Ranked by reach and capped, so the chips that go somewhere come
            # first. Unranked and uncapped, 31% of them would lead to a page
            # holding only this film; at eight it is 7%.
            keyword_row(words, f"film_{movie_id}", REACH, cap=8)
            if len(words) > 8:
                with st.expander(f"All {len(words)} keywords"):
                    keyword_row(words, f"filmall_{movie_id}", REACH)

    with right:
        if movie["cast_names"]:
            # How often each name turns up elsewhere on the show — the number is
            # the reason to click through, so it only shows when it is above one.
            billing = cast_billing(movies_df)
            chips = "".join(
                f'<span>{name}'
                + (f" <b>{billing[name]}</b>" if billing.get(name, 0) > 1 else "")
                + "</span>"
                for name in movie["cast_names"][:10]
            )
            st.markdown(
                f'<div class="rw-dt-panel"><h4>Cast &mdash; top billed</h4>'
                f'<div class="rw-dt-cast">{chips}</div></div>',
                unsafe_allow_html=True,
            )

        director = movie["director_primary"]
        by_director = same_director(movies_df, movie)
        if len(by_director):
            st.markdown(f"##### Also on the show — {director}")
            shelf(by_director.head(4), key=f"dir_{movie_id}")

        overlap = shared_cast(movies_df, movie)
        if len(overlap):
            st.markdown("##### Shared cast")
            shelf(overlap.head(4), key=f"cast_{movie_id}")

    # ── Provenance ──
    facts = [f'Key confidence <span class="conf">{movie["canonical_key_confidence"]}</span>']
    if clean(movie["enriched_at"]):
        facts.append(f'Enriched <b>{str(movie["enriched_at"])[:10]}</b>')
    if pd.notna(movie["tmdb_id"]):
        facts.append(
            f'<a href="https://www.themoviedb.org/movie/{int(movie["tmdb_id"])}" '
            f'target="_blank">TMDB {int(movie["tmdb_id"])}</a>'
        )
    if clean(movie["wikipedia_url"]):
        facts.append(f'<a href="{movie["wikipedia_url"]}" target="_blank">Wikipedia</a>')
    if clean(movie["wikidata_qid"]):
        facts.append(
            f'<a href="https://www.wikidata.org/wiki/{movie["wikidata_qid"]}" '
            f'target="_blank">Wikidata {movie["wikidata_qid"]}</a>'
        )
    st.markdown(
        '<div class="rw-dt-prov">' + "".join(f"<span>{f}</span>" for f in facts) + "</div>",
        unsafe_allow_html=True,
    )
