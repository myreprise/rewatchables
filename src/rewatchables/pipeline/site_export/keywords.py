"""keywords.json, the Keywords section, and one file per keyword page.

A keyword gets a page when it reaches LINK_FLOOR films, the same rule that
makes its chip a link in the app. The whole vocabulary goes into
keywords.json all the same, so search still finds the one-film keywords and
shows them as inert chips, as the app does.
"""

from rewatchables.pipeline.site_export.common import card, plain_value


def chip(word, reach, addresses):
    """A keyword chip: its reach, its weight band, and its page if it has one."""
    from views import chip_band

    n = reach.get(word, 0)
    return {"word": word, "reach": n, "band": chip_band(n), "id": addresses.keyword(word)}


def keywords_index(ctx, addresses):
    """The Keywords section: headline counts, bands, the vocabulary for search,
    and each decade's signature."""
    from rewatchables.app.sections.keywords import (
        reach_bands, signature_by_decade, vocabulary,
    )
    from views import BROWSE_FLOOR

    reach = ctx.reach
    vocab = vocabulary(reach, ctx.movies)
    everything = sorted(reach, key=lambda w: (-reach[w], w))
    return {
        "tiles": {
            "browsable": len(vocab["browsable"]),
            "searchable": vocab["searchable"],
            "median_per_film": vocab["median_per_film"],
            "single_share": round(vocab["single_share"]),
        },
        "browse_floor": BROWSE_FLOOR,
        "tail": vocab["tail"],
        "singles": vocab["singles"],
        "bands": [{"label": label, "words": words}
                  for label, _, words in reach_bands(vocab["browsable"], reach)],
        "signature": [
            {"decade": d, "films": n, "top": [{"word": w, "n": c} for w, c in top]}
            for d, n, top in signature_by_decade(ctx.movies)
        ],
        # Commonest first, which is the order search shows its hits in.
        "vocabulary": [chip(w, reach, addresses) for w in everything],
    }


def keyword_page(word, ctx, addresses):
    """Everything one keyword's page shows, precomputed."""
    from rewatchables.app.overlays.keyword import keyword_profile

    prof = keyword_profile(ctx.movies, ctx.keywords, word)
    films = prof["films"].sort_values(["year", "slug"], kind="mergesort")

    def rounded(value, places=1):
        return None if value is None else round(float(value), places)

    return {
        "word": word,
        "id": addresses.keyword(word),
        "catalogue": len(ctx.movies),
        "share": rounded(prof["share"]),
        "thin": prof["thin"],
        "peak": prof["peak"],
        "avg_tmdb": rounded(prof["avg_tmdb"]),
        "vs_catalogue": rounded(prof["vs_catalogue"]),
        "decades": ([{"decade": d, "n": n} for d, n in prof["decades"].items()]
                    if prof["decades"] else None),
        "peak_share": rounded(prof["peak_share"], 0),
        "catalogue_peak_share": rounded(prof["catalogue_peak_share"], 0),
        "region": prof["region"],
        "region_films": prof["region_films"],
        "region_places": prof["region_places"],
        "partners": [chip(w, ctx.reach, addresses) for w in prof["partners"]],
        "films": [{**card(m), "tmdb": plain_value(m["rating_tmdb"])}
                  for _, m in films.iterrows()],
    }


def keyword_pages(ctx, addresses):
    """address -> page, for every keyword that has one."""
    return {slug: keyword_page(word, ctx, addresses)
            for word, slug in addresses.keywords.items()}
