"""What the app remembers: the nav rail, the overlays and widget state.

Three things that all come down to session state and the query string, so they
sit together:

  * the rail -- the sections, their slugs and the links minted under older
    names;
  * the overlays -- opening a film, a keyword or an upcoming film, each of
    which is addressable by URL;
  * keep/kept, which carry a widget's value across a run that does not draw it.

Nothing here reads the database. The seeding function is handed the ids it
should accept, so this module stays free of the frames.
"""

import streamlit as st


# The rail, grouped by what the visitor is there to do: find a film, read the
# films, read the show, then the segment. Ordering within a group runs by how
# much of the corpus the section actually speaks to — Keywords covers 3,645
# terms over 453 films and used to sit last; Cruise vs. Hanks covers 125 of 481
# episodes and used to sit mid-rail.
#
# The slug is the identity and the label is presentation. They were the same
# string before, which made the label part of the ?from= URL contract: renaming
# a section silently broke every shared dossier link. Relabel freely now;
# changing a slug is the breaking change, and LEGACY_SECTIONS is what carries
# links minted under the old scheme.
NAV = [
    ("Find", [
        ("overview", "Overview"),
        ("explorer", "Movie Explorer"),
    ]),
    ("The films", [
        ("genres", "Genres"),
        ("directors", "Directors"),
        ("actors", "Actors"),
        ("keywords", "Keywords"),
        ("ratings", "Ratings"),
        ("boxoffice", "Box Office"),
    ]),
    ("The show", [
        ("hosts", "Hosts & Guests"),
        ("timeline", "Timeline & Revisits"),
    ]),
    ("The bits", [
        ("verdicts", "Cruise vs. Hanks"),
    ]),
    # A second source, not a second view of the first. These films have never
    # been on the show, so they belong to neither "The films" (which is the
    # catalogue) nor "The show" (which is the episodes) — folding it into either
    # would misstate what the numbers in that group count.
    ("On deck", [
        ("upcoming", "Upcoming Films"),
    ]),
]

SLUGS = [slug for _, items in NAV for slug, _ in items]
SECTION_LABEL = {slug: label for _, items in NAV for slug, label in items}
SLUG_OF_LABEL = {label: slug for slug, label in SECTION_LABEL.items()}
DEFAULT_SECTION = SLUGS[0]

# Links minted while the label was the key. Revisits is no longer its own
# section, so its links land on the timeline that absorbed it.
LEGACY_SECTIONS = {
    "Overview": "overview",
    "Movie Explorer": "explorer",
    "Genres": "genres",
    # Directors & Cast split into two sections; its links land on Directors.
    "Directors & Cast": "directors",
    "people": "directors",
    "Ratings": "ratings",
    "Cruise vs. Hanks": "verdicts",
    "Timeline": "timeline",
    "Revisits": "timeline",
    "Hosts & Guests": "hosts",
    "Keywords": "keywords",
}


def resolve_section(value):
    """Map a ?from= value — slug or pre-slug label — onto a live section."""
    if value in SECTION_LABEL:
        return value
    return LEGACY_SECTIONS.get(value, DEFAULT_SECTION)


def pick_section(group_index):
    """Radios don't coordinate, so selecting in one group clears the others."""
    def _on_change():
        label = st.session_state.get(f"nav_g{group_index}")
        if label is None:
            return
        st.session_state.nav_section = SLUG_OF_LABEL[label]
        for other in range(len(NAV)):
            if other != group_index:
                st.session_state[f"nav_g{other}"] = None
        close_dossier()
    return _on_change


def go_section(slug):
    """Jump to a section from a control in the body.

    Used as a button callback, which runs before the rerun draws anything: the
    rail's radios are then free to be set. Writing their keys from the body
    itself would be a write to widgets already instantiated this run, which
    Streamlit refuses.
    """
    st.session_state.nav_section = slug
    for gi, (_, items) in enumerate(NAV):
        st.session_state[f"nav_g{gi}"] = next(
            (lbl for s, lbl in items if s == slug), None)
    close_dossier()


def open_person(name):
    """Hand a name from a dossier's room to the Hosts & Guests lookup.

    A callback, like go_section, because that is the one point in a run where
    the lookup's widget key can still be written. The shadow is set as well:
    the picker was not drawn under the dossier, so keep() would otherwise
    restore the pick from before it.
    """
    st.session_state.flt_person = name
    st.session_state["_keep_flt_person"] = name
    go_section("hosts")

def open_dossier(movie_id):
    """Select a film and mirror it into the URL so the view is linkable."""
    st.session_state.dt_movie = movie_id
    st.session_state.kw_word = None
    st.query_params.clear()
    st.query_params["movie"] = movie_id
    st.query_params["from"] = st.session_state.get("nav_section", DEFAULT_SECTION)
    st.rerun()


def open_keyword(keyword):
    """Select a keyword. Commas and spaces survive the round trip through the
    query string untouched, so the keyword needs no slug of its own."""
    st.session_state.kw_word = keyword
    st.session_state.dt_movie = None
    st.query_params.clear()
    st.query_params["keyword"] = keyword
    st.query_params["from"] = st.session_state.get("nav_section", DEFAULT_SECTION)
    st.rerun()


def open_prospect(upcoming_film_id):
    """Select an upcoming film. Addressed by ?upcoming= so it links like a film.

    A requested film gets its own overlay rather than the dossier: render_dossier
    is built around episodes, the room, Ebert stars and revisit chronology, none
    of which exist for a film that has not aired. Reusing it would mean a page
    that is mostly empty slots.
    """
    st.session_state.up_film = upcoming_film_id
    st.session_state.dt_movie = None
    st.session_state.kw_word = None
    st.query_params.clear()
    st.query_params["upcoming"] = upcoming_film_id
    st.rerun()


def close_dossier():
    """Return to the section that was on screen when an overlay opened."""
    st.session_state.dt_movie = None
    st.session_state.kw_word = None
    st.session_state.up_film = None
    st.query_params.clear()


def keep(widget, *args, key, **kwargs):
    """Render a widget whose value survives runs where it isn't drawn.

    Streamlit discards session_state for any widget it did not render, so a
    dossier covering a section would reset that section's selectors on the way
    back. A shadow copy is written after each render and read back only when the
    real key has gone missing — restoring it unconditionally would override the
    value arriving from the browser and pin the widget to its first setting.
    """
    shadow = f"_keep_{key}"
    if key not in st.session_state and shadow in st.session_state:
        st.session_state[key] = st.session_state[shadow]
    value = widget(*args, key=key, **kwargs)
    st.session_state[shadow] = value
    return value


def kept(key, default=None):
    """The value keep() last saw for `key`, on a run that does not draw it.

    Movie Explorer needs its sort order above the dossier gate -- the step
    arrows walk the sorted result set -- but draws the picker below it, so on a
    dossier run there is no widget to read. The shadow is the only surviving
    copy by then: Streamlit has already discarded the widget's own entry.
    """
    return st.session_state.get(key, st.session_state.get(f"_keep_{key}", default))


def seed_from_url(movie_ids, keywords, upcoming_ids, people):
    """Open whatever the query string addresses, once per session.

    A dossier is addressed by ?movie=<movie_id>, so a film can be linked
    directly and the browser Back button steps out of it. On a cold load the
    URL wins; from then on the click handlers keep the two in step. Each id is
    checked against what actually exists, so a stale link falls back to the
    section rather than opening an empty overlay.
    """
    if "dt_movie" not in st.session_state:
        _qp = st.query_params.get("movie")
        _kw = st.query_params.get("keyword")
        _up = st.query_params.get("upcoming")
        st.session_state.dt_movie = _qp if _qp in movie_ids else None
        st.session_state.kw_word = _kw if _kw in keywords else None
        st.session_state.up_film = _up if _up in upcoming_ids else None
        if st.session_state.dt_movie or st.session_state.kw_word:
            st.session_state.nav_section = resolve_section(st.query_params.get("from"))
        elif st.session_state.up_film:
            # An upcoming film only ever belongs to its own section, so there is no
            # ?from= to carry -- unlike a dossier, which can be opened from any of
            # nine and has to remember which.
            st.session_state.nav_section = "upcoming"
        elif st.query_params.get("person") in people:
            # A lookup is addressed by ?person=<name> and, like an upcoming film,
            # belongs to one section. Seeded here, before the picker is drawn --
            # the only point in the run at which its key may be written.
            st.session_state.nav_section = "hosts"
            st.session_state.flt_person = st.query_params.get("person")
