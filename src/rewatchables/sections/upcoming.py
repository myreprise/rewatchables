"""Films listeners have put forward, before they have an episode.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.upcoming; step 15 ships them to the public site.
"""

from collections import Counter


# Requests whose full "why" is shown under the grid.
WHY_SHOWN = 12
# Tags in "The angles people pitch".
TOP_TAGS = 24


def queue_summary(upcoming_df, graduated_df):
    """The section's headline numbers."""
    years = upcoming_df["year"].dropna()
    return {
        "in_contention": len(upcoming_df),
        "already_made": len(graduated_df),
        "first_year": int(years.min()) if len(years) else None,
        "last_year": int(years.max()) if len(years) else None,
        "contributors": int(upcoming_df["contributor"].dropna().nunique()),
        "matched": int(upcoming_df["resolved"].sum()),
        "with_note": int(upcoming_df["mention_note"].notna().sum()),
        "with_tags": int(upcoming_df["pitch_tags"].notna().sum()),
    }


def tag_counts(upcoming_df):
    """Pitch tag -> requests carrying it."""
    return Counter(t for tags in upcoming_df["tags"] for t in tags)


def shared_tags(upcoming_df):
    """The tags on more than one request, alphabetically. A tag with a single
    film is a caption, not an axis -- it filters the grid down to the card you
    would have had to already be looking at to pick it."""
    return sorted(t for t, n in tag_counts(upcoming_df).items() if n > 1)


def unmatched(upcoming_df):
    """The requests with no TMDB match."""
    return upcoming_df[~upcoming_df["resolved"]]
