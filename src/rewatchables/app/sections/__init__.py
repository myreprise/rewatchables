"""One module per section of the rail, each with a render(ctx).

A section is handed the context and draws itself. The rail's order and
its labels live in rewatchables.app.state; this is only the mapping from
slug to renderer, which app.py dispatches through.
"""

from rewatchables.app.sections import overview
from rewatchables.app.sections import explorer
from rewatchables.app.sections import genres
from rewatchables.app.sections import directors
from rewatchables.app.sections import actors
from rewatchables.app.sections import ratings
from rewatchables.app.sections import boxoffice
from rewatchables.app.sections import verdicts
from rewatchables.app.sections import timeline
from rewatchables.app.sections import hosts
from rewatchables.app.sections import keywords
from rewatchables.app.sections import upcoming
from rewatchables.app.sections import categories

RENDERERS = {
    "overview": overview.render,
    "explorer": explorer.render,
    "genres": genres.render,
    "directors": directors.render,
    "actors": actors.render,
    "ratings": ratings.render,
    "boxoffice": boxoffice.render,
    "verdicts": verdicts.render,
    "timeline": timeline.render,
    "hosts": hosts.render,
    "keywords": keywords.render,
    "upcoming": upcoming.render,
    "categories": categories.render,
}
