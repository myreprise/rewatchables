"""
Read rewatchvault.com discussion pages: one category entry per page.

rewatchvault.com is an independent archive of the show's categories. Every
entry has its own page, /archive/discussions/<slug>, and everything about the
entry is inside that page's one <article class="archive-answer-card">:

    the film and episode   a.archive-answer-identity  /archive/movies/<film>?episode=<episode>
    the air date           <time datetime="2026-10-06">
    the category           img.archive-icon (the family) and the banner's <h1> (as aired)
    the answer             p.archive-answer, absent for categories that have none
    the discussion         details.archive-discussion: a "(N)" count, the transcript
                           time and link, then a <ul> of bullets

    the hosts' picks       on some pages, a second details.archive-podcast-choices:
                           a <dl> of speaker (dt) and pick (dd)

Bullets, answers and picks are prose with people (a.archive-person-mention) and
films (a.archive-movie-mention) linked inline; a bullet may end in a
span.archive-speaker naming who said it. The workbooks in data/raw/categories/
were scraped from these same pages by a tool that pulled every link out of the
prose and into columns of their own; parse_article puts them back where they
were, with their character offsets.

Nothing here touches the network or the database. Report 021 has the profile
this is built against.
"""

import re
import unicodedata
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

BASE_URL = "https://rewatchvault.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
DISCUSSION_PATH = "/archive/discussions/"

_ICON = re.compile(r"/category-awards/(.+?)-[0-9a-f]{8}\.\w+$")
_COUNT = re.compile(r"\((\d+)\)")
_HMS = re.compile(r"(\d+):(\d{2}):(\d{2})")
_WS = re.compile(r"\s+")
# A space before punctuation, or punctuation opening a bullet, is what a name
# cut out of the prose leaves behind ("makeup,  would" / ", who played").
# Punctuation followed by a digit is a number, not a gap: "hit .406 with a
# .553 on-base" (batch 1). A dot followed by a dot is an ellipsis: "a game ...
# of focus", "...And Justice for All" (batch 2).
_EXCISION = re.compile(r"^[,.;:](?![\d.])|\s[,.;:](?![\d.])")


class ParseError(ValueError):
    """The page is not a discussion page this parser understands."""


def discussion_url(slug):
    return f"{BASE_URL}{DISCUSSION_PATH}{slug}"


def sitemap_discussion_slugs(xml):
    """The discussion slugs a sitemap lists, in sitemap order, without repeats."""
    pattern = re.escape(BASE_URL + DISCUSSION_PATH) + r"([^<\s]+)</loc>"
    return list(dict.fromkeys(re.findall(pattern, xml)))


def episode_owner(slug, episode_slugs):
    """The episode a discussion slug belongs to, or None.

    A slug is "<episode>-<category>-<n>". The longest matching episode wins:
    "friday-night-lights-apex-12" belongs to friday-night-lights, not friday.
    `episode_slugs` should be sorted longest first; see owners().
    """
    for ep in episode_slugs:
        if slug.startswith(ep + "-"):
            return ep
    return None


def owners(slugs, episode_slugs):
    """{discussion slug: episode slug or None} for every slug."""
    ranked = sorted(set(episode_slugs), key=len, reverse=True)
    return {s: episode_owner(s, ranked) for s in slugs}


def category_slug(slug, episode_slug):
    """The site's category id, from "<episode>-<category>-<n>", or None."""
    if not episode_slug or not slug.startswith(episode_slug + "-"):
        return None
    rest = re.sub(r"-\d+$", "", slug[len(episode_slug) + 1:])
    return rest or None


def transcript_seconds(text):
    """'Approx. transcript time · 00:25:51' -> 1551, else None."""
    m = _HMS.search(text or "")
    if not m:
        return None
    h, mnt, s = (int(x) for x in m.groups())
    return h * 3600 + mnt * 60 + s


def icon_family(src):
    """'/assets/category-awards/great-shot-b52bbece.svg' -> 'great-shot', else None."""
    m = _ICON.search(src or "")
    return m.group(1) if m else None


def count_label(text):
    """'(4)' or 'In the discussion (4)' -> 4, else None."""
    m = _COUNT.search(text or "")
    return int(m.group(1)) if m else None


def clean(text):
    """NFC, every whitespace run one space, trimmed. For comparing, not storing."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def looks_excised(text):
    """True when `text` reads like prose with a name cut out of it."""
    return bool(_EXCISION.search(text or ""))


def article_html(page_html):
    """The page's <article> as a string: all the raw zone keeps of a page."""
    soup = BeautifulSoup(page_html, "html.parser")
    art = soup.find("article", class_="archive-answer-card")
    if art is None:
        raise ParseError("no article.archive-answer-card on the page")
    return str(art)


class _Text:
    """Accumulates a bullet's text with whitespace collapsed as it goes, so the
    offsets recorded for a mention are offsets into the final text."""

    def __init__(self):
        self.buf = ""

    def add(self, s):
        s = _WS.sub(" ", unicodedata.normalize("NFC", s))
        if not self.buf or self.buf.endswith(" "):
            s = s.lstrip(" ")
        self.buf += s


# Inline link classes and the path each one's slug sits under.
MENTION_KINDS = {"archive-person-mention": ("person", "/archive/people/"),
                 "archive-movie-mention": ("movie", "/archive/movies/")}


def _slug(href, prefix):
    path = urlparse(href or "").path
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def parse_inline(node):
    """{text, mentions, speakers} for prose with links inline: a bullet, an
    answer, or a host's pick.

    text      the prose with every linked name and title in place, speaker excluded
    mentions  [{kind, slug, name, start, end}], kind "person" or "movie",
              text[start:end] == name
    speakers  [{person_slug, name}] from span.archive-speaker, in order
    """
    out, mentions, speakers = _Text(), [], []

    def walk(node):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                out.add(str(child))
            elif isinstance(child, Tag):
                classes = child.get("class") or []
                kind = next((MENTION_KINDS[c] for c in classes if c in MENTION_KINDS), None)
                if "archive-speaker" in classes:
                    for a in child.find_all("a"):
                        speakers.append({"person_slug": _slug(a.get("href"), "/archive/people/"),
                                         "name": clean(a.get_text())})
                elif child.name == "a" and kind:
                    # The space before a name is in the text node before it,
                    # already added; the name itself is added trimmed.
                    name = clean(child.get_text())
                    start = len(out.buf)
                    out.add(name)
                    mentions.append({"kind": kind[0], "slug": _slug(child.get("href"), kind[1]),
                                     "name": name, "start": start, "end": len(out.buf)})
                else:
                    walk(child)

    walk(node)
    return {"text": out.buf.rstrip(" "), "mentions": mentions, "speakers": speakers}


def source_bullet_texts(html):
    """Each bullet's text as the page itself has it, speaker removed, cleaned.

    The yardstick for the parser: when parse_article's bullet equals this, the
    parser dropped nothing, and a gap that reads like a cut-out name is in the
    site's own prose ("through the 1960s ." -- batch 3).
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("details.archive-discussion")
    details = next((d for d in blocks if "archive-podcast-choices" not in d.get("class", [])), None)
    ul = details.find("ul") if details is not None else None
    texts = []
    for li in (ul.find_all("li", recursive=False) if ul else []):
        for span in li.select(".archive-speaker"):
            span.decompose()
        texts.append(clean(li.get_text()))
    return texts


def without_mentions(inline):
    """Prose as the workbook scraper saw it: every linked name and title cut
    out (it took both kinds), then cleaned."""
    text, parts, pos = inline["text"], [], 0
    for m in inline["mentions"]:
        parts.append(text[pos:m["start"]])
        pos = m["end"]
    parts.append(text[pos:])
    return clean("".join(parts))


def _text(node):
    return clean(node.get_text()) if node is not None else None


def parse_choices(details):
    """[{speaker, text, mentions}] from a details.archive-podcast-choices block:
    each host's own pick. A speaker the site couldn't identify is kept by its
    label ("Speaker not identified") with person_slug None."""
    picks = []
    for div in details.select("dl > div") if details is not None else []:
        dt, dd = div.find("dt"), div.find("dd")
        link = dt.find("a") if dt is not None else None
        pick = parse_inline(dd) if dd is not None else {"text": "", "mentions": []}
        picks.append({
            "speaker": {"person_slug": _slug(link.get("href"), "/archive/people/") if link else None,
                        "name": _text(dt)},
            "text": pick["text"], "mentions": pick["mentions"],
        })
    return picks


def parse_article(html):
    """Everything a discussion page says about its entry, as a dict.

    Raises ParseError when the page has no article or no identity link: the
    loader treats that as a failure. A page with no discussion block is a real
    entry with none (batch 1: The Natural's "Casting What-Ifs", answered "None
    found"): its bullets are empty and its bullet_count None, matching the "(N)"
    label it doesn't have. Step 16's checks count such pages, so a layout change
    that drops the block everywhere still shows.
    """
    soup = BeautifulSoup(html, "html.parser")
    art = soup.find("article", class_="archive-answer-card")
    if art is None:
        raise ParseError("no article.archive-answer-card")
    slug = (art.get("id") or "").removeprefix("answer-") or None

    identity = art.select_one("a.archive-answer-identity")
    if identity is None:
        raise ParseError("no a.archive-answer-identity")
    href = urlparse(identity.get("href") or "")
    film_slug = href.path.removeprefix("/archive/movies/") or None
    episode_slug = (parse_qs(href.query).get("episode") or [None])[0]
    strong = identity.find("strong")

    time = art.select_one(".archive-answer-date time")
    icon = art.select_one("img.archive-icon")
    banner = art.select_one(".archive-answer-banner h1")
    answer_node = art.select_one("p.archive-answer")
    answer = parse_inline(answer_node) if answer_node is not None else None

    # Two blocks share the class: the discussion itself, and on some pages a
    # second one listing each host's pick ("Podcast choices").
    blocks = art.select("details.archive-discussion")
    details = next((d for d in blocks if "archive-podcast-choices" not in d.get("class", [])), None)
    choices = art.select_one("details.archive-podcast-choices")
    summary = details.find("summary") if details is not None else None
    # Inside the discussion block when there is one, loose in the card when not.
    ref = (details if details is not None else art).select_one(".archive-transcript-reference")
    ref_link = ref.find("a") if ref is not None else None
    ul = details.find("ul") if details is not None else None
    bullets = [parse_inline(li) for li in (ul.find_all("li", recursive=False) if ul else [])]

    return {
        "discussion_slug": slug,
        "film_slug": film_slug,
        "film_title": _text(strong),
        "episode_slug": episode_slug,
        "air_date": time.get("datetime") if time is not None else None,
        "icon_family": icon_family(icon.get("src") if icon is not None else None),
        "category_slug": category_slug(slug or "", episode_slug),
        "banner": _text(banner),
        "answer": (answer["text"] or None) if answer else None,
        "answer_mentions": answer["mentions"] if answer else [],
        "bullet_count": count_label(summary.get_text() if summary is not None else None),
        "transcript_seconds": transcript_seconds(_text(ref)),
        "transcript_url": ref_link.get("href") if ref_link is not None else None,
        "bullets": bullets,
        "has_discussion": details is not None,
        "choices": parse_choices(choices),
    }
