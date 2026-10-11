"""The Keywords section's numbers, stored in site.db's section_data.

The vocabulary itself is site.db's keywords table; a keyword on LINK_FLOOR
films or more has an address there, the same rule that makes its chip a link
in the app.
"""


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
