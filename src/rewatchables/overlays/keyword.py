"""One keyword's profile across the catalogue. The app's keyword overlay is
rewatchables.app.overlays.keyword.
"""

from collections import Counter

from rewatchables.presentation import region_of


# Partner keywords shown under "Travels with".
PARTNERS = 14


def keyword_profile(movies_df, keywords, keyword):
    """Everything a keyword's page reports, as plain values.

    `films` is the films carrying it, oldest first. A keyword on fewer than
    three films is `thin`: it has no decade shape and no average worth
    printing, so those fields are None and the page says how rare it is.
    """
    movie_ids = keywords.get(keyword, [])
    films = movies_df[movies_df["movie_id"].isin(movie_ids)].sort_values("year")
    out = {
        "films": films,
        "share": 100 * len(films) / len(movies_df),
        "thin": len(films) < 3,
        "peak": None, "avg_tmdb": None, "vs_catalogue": None,
        "decades": None, "peak_share": None, "catalogue_peak_share": None,
        "region": None, "region_films": None, "region_places": None,
    }
    if not out["thin"]:
        spread = Counter(int(y) // 10 * 10 for y in films["year"].dropna())
        peak = max(spread, key=lambda d: spread[d])
        ratings = films["rating_tmdb"].dropna()
        corpus = movies_df["rating_tmdb"].dropna().mean()
        catalogue = Counter(int(y) // 10 * 10 for y in movies_df["year"].dropna())
        out.update(
            peak=peak,
            avg_tmdb=ratings.mean() if len(ratings) else None,
            vs_catalogue=ratings.mean() - corpus if len(ratings) else None,
            decades={d: spread.get(d, 0) for d in range(min(spread), max(spread) + 10, 10)},
            peak_share=100 * spread.get(peak, 0) / len(films),
            catalogue_peak_share=100 * catalogue.get(peak, 0) / len(movies_df),
        )

    # The one mechanical hierarchy in the vocabulary: TMDB writes locations as
    # "city, region". It earns a line, not a browse axis of its own — "usa" is a
    # bucket and some regions have a single child.
    region = region_of(keyword)
    if region:
        siblings = [w for w in keywords if region_of(w) == region]
        if len(siblings) > 1:
            out.update(region=region, region_places=len(siblings),
                       region_films=len({m for w in siblings for m in keywords[w]}))

    partners = Counter()
    for kws in films["keywords"]:
        for word in (kws if isinstance(kws, list) else []):
            if word != keyword:
                partners[word] += 1
    # Ties break alphabetically: most_common keeps insertion order, which
    # follows the database's and changes on a rebuild.
    ranked = sorted(partners.items(), key=lambda kv: (-kv[1], kv[0]))
    out["partners"] = [w for w, _ in ranked[:PARTNERS]]
    return out
