"""
The identity of a source row, shared by every stage that needs to recognise it.

A single episode airing is identified by episode number, air date and title.
That key does three jobs across the pipeline, and all three break if the stages
disagree about it, so it lives here rather than being spelled out twice:

  * 02_load_raw upserts on it -- a row whose key and content are unchanged is
    not re-inserted, so the raw zone stops growing by a full snapshot per load
  * 03_normalize derives deterministic staging ids from it, so manual review
    decisions survive a staging rebuild
  * both must agree on which airing is "the same airing", or a load would
    insert a duplicate that the staging rebuild then treats as a new episode

Why this key and not something simpler:

  `ep` alone is not unique. The podcast reuses an episode number when it
  revisits a film -- American Pie is ep 68 in both 2019 and 2023 -- so keying on
  it silently merges a revisit into its original.

  `source_hash` is too brittle. It covers every column, so editing an unrelated
  field like a Rotten Tomatoes score would present the row as a different
  episode. The hash is still used, but to detect that a row CHANGED, not to say
  which row it is.

  ep + date + title is unique across all 489 source rows and stable against
  edits elsewhere in the row.
"""

import re
import uuid

# Fixed namespace for deterministic staging ids. NEVER change this: doing so
# renames every staging id and detaches all manual review decisions.
STAGING_NAMESPACE = uuid.UUID('6f2a1d4c-9b3e-5a77-8c14-2de0f7b6a913')


def normalize_date(date_raw):
    """Return ISO YYYY-MM-DD regardless of input format (M/D/YYYY, ISO, etc.).

    The source sheet mixes M/D/YYYY strings in with ISO timestamps. Both must
    reduce to the same value or the same airing would key differently depending
    on how the cell happened to be typed.
    """
    if not date_raw:
        return None
    s = str(date_raw).strip()
    # Already ISO, with or without a time component
    iso = re.match(r'(\d{4}-\d{2}-\d{2})', s)
    if iso:
        return iso.group(1)
    # M/D/YYYY or MM/DD/YYYY
    mdy = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if mdy:
        m, d, y = mdy.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return s  # return as-is if unrecognised


def episode_business_key(ep, date_raw, title):
    """Stable identity of a source row: episode number, air date, title."""
    return f"{str(ep).strip()}|{normalize_date(date_raw) or ''}|{str(title or '').strip()}"


def make_episode_id(ep, date_raw, title):
    """Deterministic staging_episode_id for a source row."""
    return str(uuid.uuid5(STAGING_NAMESPACE,
                          'episode:' + episode_business_key(ep, date_raw, title)))


def make_mention_id(ep, date_raw, title, mention_order=1):
    """Deterministic staging_mention_id for a mention within a source row."""
    return str(uuid.uuid5(
        STAGING_NAMESPACE,
        f"mention:{episode_business_key(ep, date_raw, title)}|{mention_order}"))


# ── Upcoming films ────────────────────────────────────────────────────────────
# The second source file, data/upcoming.csv, lists films expected in future
# episodes. Its rows are not airings -- there is no episode number and no date --
# so they need a key of their own.
#
# title + year, because that is all the source carries that identifies a film.
# The year is load-bearing rather than decorative: the list holds `Crash` (1996)
# and `Miami Vice` (2027) while the catalogue holds a different `Crash` (2005)
# and a different `Miami Vice` (2006), so a title-only key would merge two films
# that have nothing to do with each other.
#
# The year is kept as the source text, not parsed. Two rows are ranges
# ('1984-1990', '1997-2003') and one is blank; parsing them here would collapse
# all three onto the same key and lose rows. Identity does not need the year to
# be a number -- only to be the same string next time.


def upcoming_business_key(title, year):
    """Stable identity of a row in data/upcoming.csv: title and year as written."""
    return f"{str(title or '').strip()}|{str(year or '').strip()}"


def make_upcoming_id(title, year):
    """Deterministic upcoming_film_id for a source row.

    Shares STAGING_NAMESPACE with the episode ids; the 'upcoming:' prefix is
    what keeps the two spaces apart, exactly as 'episode:' and 'mention:' do.
    """
    return str(uuid.uuid5(STAGING_NAMESPACE,
                          'upcoming:' + upcoming_business_key(title, year)))
