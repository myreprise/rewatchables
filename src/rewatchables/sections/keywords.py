"""The keyword vocabulary, browsable.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.keywords; step 15 ships them to the public site.
"""

from collections import Counter

from rewatchables.presentation import BROWSE_FLOOR


# Grouped into reach bands rather than shaded by frequency: the band heading
# states the range outright, which a colour ramp can only imply.
BANDS = [
    ("Carried by 40 or more films", 40, 10_000),
    ("25 to 39 films", 25, 39),
    ("17 to 24 films", 17, 24),
    ("12 to 16 films", 12, 16),
    (f"{BROWSE_FLOOR} to 11 films", BROWSE_FLOOR, 11),
]

SIGNATURE_DECADES = range(1970, 2030, 10)


def vocabulary(reach, movies_df):
    """The browsable keywords, commonest first, and the section's headline counts."""
    browsable = sorted(
        (w for w, n in reach.items() if n >= BROWSE_FLOOR),
        key=lambda w: (-reach[w], w),
    )
    singles = sum(1 for n in reach.values() if n == 1)
    # Over the films that carry any: one film has none, and including it drags
    # the median to 16.5, which then prints as 16 and understates the typical row.
    tagged = movies_df["keywords"].apply(len)
    return {
        "browsable": browsable,
        "searchable": len(reach),
        "tail": len(reach) - len(browsable),
        "singles": singles,
        "median_per_film": int(tagged[tagged > 0].median()),
        "single_share": 100 * singles / len(reach),
    }


def search_vocabulary(reach, query, limit=60):
    """Keywords containing `query`, commonest first.

    Search reaches the entire vocabulary, tail included — the rare terms are
    meant to be found, not browsed. Each result shows its reach, so a one-film
    keyword announces itself before you follow it.
    """
    q = query.strip().lower()
    return sorted((w for w in reach if q in w.lower()),
                  key=lambda w: (-reach[w], w))[:limit]


def reach_bands(browsable, reach):
    """(label, low, words) per band, leaving out a band with no words."""
    out = []
    for label, low, high in BANDS:
        band = [w for w in browsable if low <= reach[w] <= high]
        if band:
            out.append((label, low, band))
    return out


def signature_by_decade(movies_df, top=4):
    """(decade, films made in it, its `top` commonest keywords and counts)."""
    out = []
    for decade in SIGNATURE_DECADES:
        in_decade = movies_df[movies_df["decade"] == decade]
        if not len(in_decade):
            continue
        counts = Counter(
            w for ks in in_decade["keywords"] for w in (ks if isinstance(ks, list) else [])
        )
        out.append((decade, len(in_decade), counts.most_common(top)))
    return out
