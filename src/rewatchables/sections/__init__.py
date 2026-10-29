"""The sections, their slugs and their order, shared by both front ends.

Each module here holds one section's numbers and figures, free of any front
end; the app's rendering of it is the module of the same name under
rewatchables.app.sections.
"""


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
        ("categories", "Categories"),
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

# Sections the app has and the public site deliberately does not. Categories
# shows rewatchvault.com's discussion text, which stays local until its
# authors have said it may be republished (reports 021-024). The site export
# leaves these out and numbers its sections without them.
APP_ONLY = {"categories"}
SITE_SLUGS = [slug for slug in SLUGS if slug not in APP_ONLY]
SECTION_LABEL = {slug: label for _, items in NAV for slug, label in items}
SLUG_OF_LABEL = {label: slug for slug, label in SECTION_LABEL.items()}
DEFAULT_SECTION = SLUGS[0]
