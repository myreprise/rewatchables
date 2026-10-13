#!/usr/bin/env python3
"""
Step 16: load rewatchvault.com category entries into the raw zone, in batches.

Two sources, both raw (sql/schemas/raw_zone.sql, "Category entries"):

  --load-workbooks   the five scraper exports in data/raw/categories/, row by
                     row as they are. They are the index that plans the batches
                     and the cross-check the batches are held to. No network.
  --batch NAME       one batch of discussion pages, each page's <article> stored
                     compressed. NAME is "pilot" or 1-7 (report 021, batch plan).
                     One request a second; pages already stored are skipped, so
                     a batch that stopped can simply be run again.

  --plan             the batch table from today's sitemap (one request)
  --export NAME      write a batch's parsed entries to a workbook in
                     logs/categories/ for reading in Excel (no network)
  --check NAME       re-run a batch's checks against the pages its latest run
                     planned, from what is stored (no network)

Every batch ends with its checks, written to logs/categories/: whether every
page parsed, whether each page's bullets match its own "(N)", whether any
restored bullet still reads like a name was cut out of it, and every place the
page and its workbook row disagree. The next batch is run only after that
summary has been read -- this step is deliberately not in orchestrate.py's
STEPS, so no --all run starts a crawl.

The workbook load is idempotent: an unchanged row is recognised by its hash and
only its last_seen_* is touched.

Usage:
    python scripts/16_load_categories.py --load-workbooks
    python scripts/16_load_categories.py --plan
    python scripts/16_load_categories.py --batch pilot
    python scripts/16_load_categories.py --check pilot
"""

import argparse
import csv
import glob
import hashlib
import json
import logging
import re
import sqlite3
import sys
import time
import uuid
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from rewatchables import config, http
from rewatchables import rewatchvault as rv

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = config.DATA_DIR / "raw" / "categories"
CHECK_DIR = config.LOG_DIR / "categories"
USER_AGENT = ("rewatchables-category-archive/1.0 "
              "(+https://github.com/myreprise/rewatchables)")
DELAY = 1.0                # seconds between request starts
MAX_CONSECUTIVE_FAILURES = 5

# One episode per air year, chosen so ten episodes meet every variation the
# workbooks show before eleven thousand pages depend on the parser.
PILOT_EPISODES = {
    "friday":                       "2017; megaphone transcript; a prefix of friday-night-lights",
    "get-out":                      "2018; podscripts transcript; 1 page the workbooks missed",
    "the-godfather-part-ii":        "2019; TMDB poster; discussions up to 38 bullets",
    "rocky-iv":                     "2020; 2 pages missed",
    "heat":                         "2021; one of three Heat episodes (heat-2017, the-re-heat)",
    "boogie-nights-part-1":         "2022; a two-part episode; both its pages missed",
    "american-pie":                 "2023; 4 pages missed; a revisited film",
    "road-house":                   "2024; YouTube transcript",
    "f1":                           "2025; pod.wave.co transcript",
    "the-texas-chain-saw-massacre": "2026; megaphone transcript; report 021's example",
}
YEAR_BATCHES = {2017: "1", 2018: "1", 2019: "1", 2020: "2", 2021: "2",
                2022: "3", 2023: "4", 2024: "5", 2025: "6", 2026: "7"}
LAST_BATCH = "7"           # also takes any page no workbook episode claims
BATCHES = ["pilot", "1", "2", "3", "4", "5", "6", "7"]

# Workbook columns, by the scraper's names.
WB_DISCUSSION = re.compile(r"archive-discussion (\d+)$")
WB_MENTION = re.compile(r"archive-person-mention( \d+)?$")
# The <summary> of the hosts' picks block, which the scraper kept as a cell.
PICKS_HEADING = "Podcast choices"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def connect(db_path):
    conn = sqlite3.connect(db_path)
    # Entirely CREATE ... IF NOT EXISTS, so applying it to a database that
    # predates these tables adds them and touches nothing else (as step 11).
    conn.executescript((config.SCHEMA_DIR / "raw_zone.sql").read_text(encoding="utf-8"))
    return conn


def _sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def store(conn, table, load_id, slug, source_hash, columns):
    """Insert one version of a row, or mark an identical one as seen again.

    Returns "new" or "unchanged". `columns` are the table's source columns.
    """
    found = conn.execute(f"SELECT raw_id FROM {table} "
                         f"WHERE discussion_slug = ? AND source_hash = ?",
                         (slug, source_hash)).fetchone()
    if found:
        conn.execute(f"UPDATE {table} SET last_seen_load_id = ?, "
                     f"last_seen_at = CURRENT_TIMESTAMP WHERE raw_id = ?",
                     (load_id, found[0]))
        return "unchanged"
    cols = {"load_id": load_id, "discussion_slug": slug, "source_hash": source_hash,
            "last_seen_load_id": load_id, **columns}
    conn.execute(f"INSERT INTO {table} ({', '.join(cols)}, last_seen_at) "
                 f"VALUES ({', '.join('?' * len(cols))}, CURRENT_TIMESTAMP)",
                 list(cols.values()))
    return "new"


def start_load(conn, source, batch, source_ref, source_sha256, planned, plan_slugs=None):
    load_id = str(uuid.uuid4())
    conn.execute("""INSERT INTO raw_category_loads
                    (load_id, source, batch, source_ref, source_sha256,
                     rows_planned, plan_json, load_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'running')""",
                 (load_id, source, batch, source_ref, source_sha256, planned,
                  json.dumps(plan_slugs) if plan_slugs is not None else None))
    conn.commit()
    return load_id


def finish_load(conn, load_id, counts, failures, status):
    conn.execute("""UPDATE raw_category_loads
                    SET finished_at = CURRENT_TIMESTAMP, rows_new = ?,
                        rows_unchanged = ?, rows_failed = ?, failures_json = ?,
                        load_status = ?
                    WHERE load_id = ?""",
                 (counts["new"], counts["unchanged"], len(failures),
                  json.dumps(failures) if failures else None, status, load_id))
    conn.commit()


# ---------------------------------------------------------------------------
# The workbooks
# ---------------------------------------------------------------------------

def workbook_row(pairs):
    """(discussion_slug, episode_slug, ISO air date) from a row's cells, or
    None for a row with no discussion URL."""
    cells = dict(pairs)
    url = cells.get("archive-answer-banner href") or cells.get("archive-answer-poster href")
    if not url or rv.DISCUSSION_PATH not in url:
        return None
    slug = url.split(rv.DISCUSSION_PATH, 1)[1]
    query = urlparse(cells.get("archive-answer-identity href") or "").query
    episode = (parse_qs(query).get("episode") or [None])[0]
    try:
        air_date = datetime.strptime(cells.get("archive-answer-date 2") or "",
                                     "%B %d, %Y").date().isoformat()
    except ValueError:
        air_date = None
    return slug, episode, air_date


def load_workbooks(conn, source=DEFAULT_SOURCE):
    import openpyxl  # only this sub-command needs it

    files = sorted(glob.glob(str(Path(source) / "*.xlsx")))
    if not files:
        raise SystemExit(f"No .xlsx files in {source}")
    digest = hashlib.sha256()
    for f in files:
        digest.update(Path(f).read_bytes())
    load_id = start_load(conn, "workbook", None,
                         "; ".join(Path(f).name for f in files), digest.hexdigest(), None)

    counts, failures, planned = Counter(new=0, unchanged=0), [], 0
    for f in files:
        name = Path(f).name
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except PermissionError:
            finish_load(conn, load_id, counts, [[name, "unreadable"]], "failed")
            raise SystemExit(f"{name} is open in another program. Close it and run again.")
        rows = wb.worksheets[0].iter_rows(values_only=True)
        header = [str(h) if h is not None else "" for h in next(rows)]
        for number, row in enumerate(rows, start=2):
            pairs = [[h, v] for h, v in zip(header, row) if v not in (None, "")]
            if not pairs:
                continue
            planned += 1
            keys = workbook_row(pairs)
            if keys is None:
                failures.append([f"{name}:{number}", "no discussion URL"])
                continue
            slug, episode, air_date = keys
            text = json.dumps(pairs, ensure_ascii=False, default=str)
            counts[store(conn, "raw_category_workbook_rows", load_id, slug, _sha(text), {
                "source_file": name, "source_row_number": number,
                "episode_slug": episode, "air_date": air_date,
                "payload": zlib.compress(text.encode("utf-8")),
            })] += 1
        wb.close()
        logger.info(f"{name}: read")
    conn.execute("UPDATE raw_category_loads SET rows_planned = ? WHERE load_id = ?",
                 (planned, load_id))
    finish_load(conn, load_id, counts, failures, "partial" if failures else "success")
    logger.info(f"Workbooks: {planned} rows, {counts['new']} new, "
                f"{counts['unchanged']} unchanged, {len(failures)} without a URL")
    return counts, failures


def workbook_index(conn):
    """{discussion_slug: (episode_slug, air_date, raw_id)} as of the latest
    successful workbook load."""
    latest = conn.execute("""SELECT load_id FROM raw_category_loads
                             WHERE source = 'workbook' AND load_status = 'success'
                             ORDER BY started_at DESC, rowid DESC LIMIT 1""").fetchone()
    if latest is None:
        raise SystemExit("No workbook load yet. Run with --load-workbooks first.")
    return {slug: (ep, date, raw_id) for slug, ep, date, raw_id in conn.execute(
        """SELECT discussion_slug, episode_slug, air_date, raw_id
           FROM raw_category_workbook_rows WHERE last_seen_load_id = ?""", latest)}


def workbook_pairs(conn, raw_id):
    blob = conn.execute("SELECT payload FROM raw_category_workbook_rows WHERE raw_id = ?",
                        (raw_id,)).fetchone()[0]
    return json.loads(zlib.decompress(blob).decode("utf-8"))


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def episode_owners(slugs, index):
    """{slug: episode slug or None}. A page the workbooks list belongs to the
    episode its row names; any other page to the longest episode slug it
    starts with. The workbook comes first because 56 of its pages have opaque
    slugs (c2, c54, ...) that name no episode at all."""
    by_prefix = rv.owners([s for s in slugs if s not in index],
                          {ep for ep, _, _ in index.values() if ep})
    return {s: index[s][0] if s in index else by_prefix[s] for s in slugs}


def plan(sitemap_slugs, index):
    """{batch: [slug, ...]} and {slug: owning episode or None}.

    A page belongs to the batch of its episode's air year, by the workbook
    rows' dates. A page no workbook episode claims goes in the last batch. The
    pilot is a subset: its pages also sit in their year's batch, where being
    already stored means they are skipped.
    """
    years = {}
    for ep, date, _ in index.values():
        if ep and date:
            years.setdefault(ep, int(date[:4]))
    owner = episode_owners(sitemap_slugs, index)
    batches = defaultdict(list)
    for slug in sitemap_slugs:
        ep = owner[slug]
        batches[YEAR_BATCHES.get(years.get(ep), LAST_BATCH)].append(slug)
        if ep in PILOT_EPISODES:
            batches["pilot"].append(slug)
    return batches, owner


def fetch_sitemap(session):
    r = http.get(rv.SITEMAP_URL, session=session, timeout=60, what="sitemap")
    if r.status_code != 200:
        raise SystemExit(f"Sitemap: HTTP {r.status_code}")
    return rv.sitemap_discussion_slugs(r.text), _sha(r.content)


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def show_plan(conn):
    index = workbook_index(conn)
    slugs, _ = fetch_sitemap(_session())
    batches, owner = plan(slugs, index)
    stored = {r[0] for r in conn.execute("SELECT DISTINCT discussion_slug FROM raw_category_pages")}
    print(f"Sitemap: {len(slugs)} discussion pages; workbooks: {len(index)} rows; "
          f"in the workbooks but not the sitemap: {len(set(index) - set(slugs))}")
    print(f"{'batch':>6} {'episodes':>9} {'pages':>6} {'not in workbooks':>17} "
          f"{'stored':>7} {'minutes':>8}")
    for b in BATCHES:
        pages = batches.get(b, [])
        todo = [s for s in pages if s not in stored]
        print(f"{b:>6} {len({owner[s] for s in pages}):>9} {len(pages):>6} "
              f"{sum(s not in index for s in pages):>17} {len(pages) - len(todo):>7} "
              f"{len(todo) * DELAY / 60:>8.0f}")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def run_batch(conn, batch, delay=DELAY, refetch=False, limit=None):
    index = workbook_index(conn)
    session = _session()
    slugs, sitemap_sha = fetch_sitemap(session)
    batches, _ = plan(slugs, index)
    pages = batches.get(batch, [])
    stored = {r[0] for r in conn.execute("SELECT DISTINCT discussion_slug FROM raw_category_pages")}
    wanted = [s for s in pages if refetch or s not in stored]
    todo = wanted[:limit]
    load_id = start_load(conn, "web", batch, rv.SITEMAP_URL, sitemap_sha, len(pages), pages)
    logger.info(f"Batch {batch}: {len(pages)} pages, {len(pages) - len(todo)} already "
                f"stored, {len(todo)} to fetch (about {len(todo) * delay / 60:.0f} min)")

    counts, failures, streak, status = Counter(new=0, unchanged=0), [], 0, "success"
    next_start = 0.0
    try:
        for n, slug in enumerate(todo, 1):
            time.sleep(max(0.0, next_start - time.monotonic()))
            next_start = time.monotonic() + delay
            url = rv.discussion_url(slug)
            try:
                r = http.get(url, session=session, timeout=30, what=slug)
            except requests.RequestException as e:
                failures.append([slug, type(e).__name__])
                streak += 1
                if streak >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(f"{streak} failures in a row; stopping the batch.")
                    status = "failed"
                    break
                continue
            streak = 0
            if r.status_code != 200:
                failures.append([slug, f"HTTP {r.status_code}"])
                continue
            try:
                article = rv.article_html(r.text)
            except rv.ParseError as e:
                failures.append([slug, str(e)])
                continue
            counts[store(conn, "raw_category_pages", load_id, slug, _sha(article), {
                "url": url, "http_status": r.status_code,
                "article_html": zlib.compress(article.encode("utf-8")),
            })] += 1
            if n % 25 == 0 or n == len(todo):
                conn.commit()
                logger.info(f"  {n}/{len(todo)} fetched, {len(failures)} failed")
    except KeyboardInterrupt:
        status = "partial"
        logger.warning("Interrupted. Pages stored so far are kept; run the batch again to resume.")
    if status == "success" and (failures or len(todo) < len(wanted)):
        status = "partial"
    finish_load(conn, load_id, counts, failures, status)
    logger.info(f"Batch {batch}: {counts['new']} new, {counts['unchanged']} unchanged, "
                f"{len(failures)} failed; load {load_id[:8]} {status}")
    return check_batch(conn, batch, pages, index), status


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

def latest_pages(conn, slugs):
    """{slug: article html} for the newest stored version of each slug."""
    wanted = set(slugs)
    out = {}
    for slug, blob in conn.execute(
            """SELECT discussion_slug, article_html FROM raw_category_pages p
               WHERE raw_id = (SELECT MAX(raw_id) FROM raw_category_pages q
                               WHERE q.discussion_slug = p.discussion_slug)"""):
        if slug in wanted:
            out[slug] = zlib.decompress(blob).decode("utf-8")
    return out


def compare(page, pairs):
    """[(field, workbook value, page value)] wherever a workbook row and the
    parsed page disagree, plus the bullet and mention tallies.

    The workbook's discussion cells are bullets with the names cut out, so
    each is compared with the page bullet put through the same cut.
    """
    cells = dict(pairs)
    diffs = []

    def same(field, wb, pg, norm=rv.clean):
        if (norm(wb) if wb is not None else None) != (norm(pg) if pg is not None else None):
            diffs.append((field, wb, pg))

    query = urlparse(cells.get("archive-answer-identity href") or "").query
    same("episode_slug", (parse_qs(query).get("episode") or [None])[0], page["episode_slug"])
    same("film_title", cells.get("archive-answer-identity"), page["film_title"])
    same("banner", cells.get("archive-answer-banner"), page["banner"])
    # The workbook's answer had its links cut out like its bullets did.
    page_answer = rv.without_mentions({"text": page["answer"] or "",
                                       "mentions": page["answer_mentions"]})
    same("answer", cells.get("archive-answer"), page_answer or None)
    same("transcript_url", cells.get("archive-transcript-reference href"), page["transcript_url"])
    same("icon_family", rv.icon_family(cells.get("archive-icon src")), page["icon_family"])
    wb_secs = rv.transcript_seconds(cells.get("archive-transcript-time"))
    if wb_secs != page["transcript_seconds"]:
        diffs.append(("transcript_seconds", wb_secs, page["transcript_seconds"]))
    if rv.count_label(cells.get("archive-discussion 2")) != page["bullet_count"]:
        diffs.append(("bullet_count", cells.get("archive-discussion 2"), page["bullet_count"]))
    keys = workbook_row(pairs)
    wb_date = keys[2] if keys else None
    if wb_date != page["air_date"]:
        diffs.append(("air_date", wb_date, page["air_date"]))

    # "archive-discussion 2" is the "(N)" label; the bullets start at 3.
    slots = sorted((int(m.group(1)), v) for h, v in pairs
                   if (m := WB_DISCUSSION.match(h)) and int(m.group(1)) >= 3)
    wb_bullets = [v for _, v in slots]
    # The scraper's discussion columns also caught the hosts' picks block:
    # its heading, speaker labels and picks, cut the same way (batch 2).
    page_cut = ({rv.without_mentions(b) for b in page["bullets"]}
                | {rv.without_mentions(c) for c in page["choices"]}
                | {c["speaker"]["name"] for c in page["choices"]}
                | ({PICKS_HEADING} if page["choices"] else set()))
    unmatched = [v for v in wb_bullets if rv.clean(str(v)) not in page_cut]
    for v in unmatched:
        diffs.append(("bullet", v, None))
    wb_names = {rv.clean(str(v)) for h, v in pairs if WB_MENTION.match(h)}
    page_names = [m["name"] for b in page["bullets"] for m in b["mentions"]
                  if m["kind"] == "person"]
    tallies = {
        "wb_bullets": len(wb_bullets),
        "wb_bullets_matched": len(wb_bullets) - len(unmatched),
        "page_mentions": len(page_names),
        "page_mentions_not_in_wb": sum(n not in wb_names for n in page_names),
    }
    return diffs, tallies


def check_batch(conn, batch, slugs, index=None, out_dir=CHECK_DIR):
    """Parse a batch's stored pages, hold them to the gate, and write the
    summary (markdown) and the disagreements (CSV) to `out_dir`."""
    index = index if index is not None else workbook_index(conn)
    pages = latest_pages(conn, slugs)
    owner = episode_owners(slugs, index)
    t = Counter()
    problems, diff_rows = [], []
    per_episode = defaultdict(Counter)
    source_texts = {}
    for slug in slugs:
        ep = owner.get(slug) or "(unclaimed)"
        per_episode[ep]["pages"] += 1
        if slug not in pages:
            problems.append((slug, "not stored", ""))
            continue
        try:
            page = rv.parse_article(pages[slug])
        except rv.ParseError as e:
            problems.append((slug, "parse failure", str(e)))
            continue
        t["parsed"] += 1
        bullets = page["bullets"]
        t["bullets"] += len(bullets)
        per_episode[ep]["bullets"] += len(bullets)
        if not page["has_discussion"]:
            problems.append((slug, "no discussion block", page["banner"] or ""))
        elif page["bullet_count"] != len(bullets):
            problems.append((slug, "bullet count", f"(N)={page['bullet_count']} parsed={len(bullets)}"))
        if page["category_slug"] is None:
            problems.append((slug, "no category slug", f"{page['episode_slug']}: {page['banner']}"))
        if owner.get(slug) and page["episode_slug"] != owner[slug]:
            problems.append((slug, "episode prefix", f"page says {page['episode_slug']}"))
        for i, b in enumerate(bullets):
            if not b["text"]:
                problems.append((slug, "empty bullet", str(i)))
            if rv.looks_excised(b["text"]):
                # Is the gap the parser's, or already in the page's own text?
                source = source_texts.get(slug) or rv.source_bullet_texts(pages[slug])
                source_texts[slug] = source
                kind = ("source quirk" if i < len(source) and source[i] == rv.clean(b["text"])
                        else "reads excised")
                problems.append((slug, kind, f"{i}: {b['text'][:100]}"))
            t["speakers"] += bool(b["speakers"])
        answer = {"text": page["answer"] or "", "mentions": page["answer_mentions"]}
        if rv.looks_excised(answer["text"]):
            problems.append((slug, "reads excised", f"answer: {answer['text'][:100]}"))
        for c in page["choices"]:
            if rv.looks_excised(c["text"]):
                problems.append((slug, "reads excised", f"pick: {c['text'][:100]}"))
        inlines = ([("answer", answer)] + [(str(i), b) for i, b in enumerate(bullets)]
                   + [("pick", c) for c in page["choices"]])
        for where, inline in inlines:
            for m in inline["mentions"]:
                if inline["text"][m["start"]:m["end"]] != m["name"]:
                    problems.append((slug, "mention offset", f"{where}: {m['name']}"))
                t[f"mentions:{m['kind']}"] += 1
        t["answers_with_links"] += bool(page["answer_mentions"])
        t["pages_with_picks"] += bool(page["choices"])
        t["picks"] += len(page["choices"])
        if slug in index:
            t["in_workbook"] += 1
            per_episode[ep]["in_workbook"] += 1
            diffs, tallies = compare(page, workbook_pairs(conn, index[slug][2]))
            for k, v in tallies.items():
                t[k] += v
                per_episode[ep][k] += v
            for field, wb, pg in diffs:
                t[f"diff:{field}"] += 1
                diff_rows.append((slug, field, wb, pg))
        else:
            t["not_in_workbook"] += 1
            per_episode[ep]["not_in_workbook"] += 1

    gate_kinds = {"not stored", "parse failure", "bullet count", "reads excised",
                  "mention offset", "empty bullet", "episode prefix"}
    kinds = Counter(k for _, k, _ in problems)
    passed = not any(kinds[k] for k in gate_kinds)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = out_dir / f"batch-{batch}-{stamp}.md"
    csv_path = out_dir / f"batch-{batch}-{stamp}-disagreements.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["discussion_slug", "field", "workbook", "page"])
        w.writerows(diff_rows)
        w.writerows((s, f"PROBLEM: {k}", "", d) for s, k, d in problems)
    md_path.write_text(_summary_md(batch, slugs, t, kinds, passed, per_episode,
                                   problems, csv_path.name), encoding="utf-8")
    logger.info(f"Batch {batch} checks: {'PASS' if passed else 'FAIL'}; "
                f"{t['parsed']}/{len(slugs)} parsed; summary {md_path}")
    return {"passed": passed, "tallies": t, "problems": kinds,
            "summary": md_path, "disagreements": csv_path}


def _summary_md(batch, slugs, t, kinds, passed, per_episode, problems, csv_name):
    pct = lambda a, b: f"{a / b:.1%}" if b else "n/a"  # noqa: E731
    lines = [
        f"# Category batch {batch}: checks",
        "",
        f"Written {datetime.now():%Y-%m-%d %H:%M}. Gate: **{'PASS' if passed else 'FAIL'}**.",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Pages in the batch | {len(slugs)} |",
        f"| Stored and parsed | {t['parsed']} |",
        f"| Not stored | {kinds['not stored']} |",
        f"| Parse failures | {kinds['parse failure']} |",
        f"| Entries with no discussion block (reported, not a failure) | "
        f"{kinds['no discussion block']} |",
        f"| Bullets parsed | {t['bullets']} |",
        f"| Pages whose bullets differ from their own (N) | {kinds['bullet count']} |",
        f"| Bullets that still read as if a name was cut out | {kinds['reads excised']} |",
        f"| ...of which the gap is in the site's own text (reported, not a failure) | "
        f"{kinds['source quirk']} |",
        f"| Mention offsets that don't point at the name | {kinds['mention offset']} |",
        f"| Pages whose slug prefix names a different episode | {kinds['episode prefix']} |",
        f"| Pages with no derivable category slug | {kinds['no category slug']} |",
        f"| Links restored, people / films (answers, bullets, picks) | "
        f"{t['mentions:person']} / {t['mentions:movie']} |",
        f"| Answers with links in them | {t['answers_with_links']} |",
        f"| Pages with a hosts' picks block / picks | {t['pages_with_picks']} / {t['picks']} |",
        f"| Bullets with a speaker | {t['speakers']} |",
        f"| Pages in the workbooks / not | {t['in_workbook']} / {t['not_in_workbook']} |",
        f"| Workbook bullets found on the page | {t['wb_bullets_matched']} of {t['wb_bullets']} "
        f"({pct(t['wb_bullets_matched'], t['wb_bullets'])}) |",
        f"| Page mentions the workbook row lacked | {t['page_mentions_not_in_wb']} of {t['page_mentions']} |",
        "",
        "## Workbook vs page, by field",
        "",
        "| Field | Disagreements |",
        "| --- | ---: |",
    ]
    fields = sorted(k.removeprefix("diff:") for k in t if k.startswith("diff:"))
    lines += [f"| {f} | {t['diff:' + f]} |" for f in fields] or ["| (none) | 0 |"]
    lines += ["", f"Every disagreement and problem is in `{csv_name}`.", "",
              "## By episode", "",
              "| Episode | Pages | Not in workbooks | Bullets | Workbook bullets matched | Mentions not in workbook |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for ep in sorted(per_episode):
        c = per_episode[ep]
        lines.append(f"| {ep} | {c['pages']} | {c['not_in_workbook']} | {c['bullets']} | "
                     f"{c['wb_bullets_matched']} of {c['wb_bullets']} | {c['page_mentions_not_in_wb']} |")
    if problems:
        lines += ["", "## Problems (first 40)", "", "| Page | Problem | Detail |", "| --- | --- | --- |"]
        lines += [f"| {s} | {k} | {d.replace('|', '/')} |" for s, k, d in problems[:40]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reading a batch
# ---------------------------------------------------------------------------

def _hms(seconds):
    if seconds is None:
        return None
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def batch_slugs(conn, batch):
    """The slugs a batch's latest run planned."""
    row = conn.execute("""SELECT plan_json FROM raw_category_loads
                          WHERE source = 'web' AND batch = ?
                          ORDER BY started_at DESC, rowid DESC LIMIT 1""",
                       (batch,)).fetchone()
    if row is None:
        raise SystemExit(f"Batch {batch} has not been run.")
    return json.loads(row[0])


def export_batch(conn, batch, out_dir=CHECK_DIR):
    """Write a batch's stored pages, parsed, to a workbook: one sheet of
    entries, one of discussion bullets, one of the hosts' picks. A reading
    copy for review, rebuilt on every call; nothing reads it back."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    index = workbook_index(conn)
    slugs = batch_slugs(conn, batch)
    pages = latest_pages(conn, slugs)
    entries, bullets, picks = [], [], []
    for slug in slugs:
        if slug not in pages:
            continue
        e = rv.parse_article(pages[slug])
        names = lambda inline, kind: "; ".join(  # noqa: E731
            m["name"] for m in inline["mentions"] if m["kind"] == kind)
        entries.append([e["air_date"], e["episode_slug"], e["film_title"], e["banner"],
                         e["category_slug"], e["icon_family"], e["answer"], len(e["bullets"]),
                         len(e["choices"]), _hms(e["transcript_seconds"]),
                         "yes" if slug in index else "no", rv.discussion_url(slug),
                         e["transcript_url"]])
        for i, b in enumerate(e["bullets"], 1):
            bullets.append([e["air_date"], e["episode_slug"], e["banner"], i, b["text"],
                            "; ".join(sp["name"] for sp in b["speakers"]),
                            names(b, "person"), names(b, "movie"), slug])
        for c in e["choices"]:
            picks.append([e["air_date"], e["episode_slug"], e["banner"],
                          c["speaker"]["name"], c["text"], slug])

    wb = Workbook()
    sheets = [
        ("Entries", ["Air date", "Episode", "Film", "Category (as aired)", "Category slug",
                     "Family", "Answer", "Bullets", "Picks", "Transcript time",
                     "In workbooks", "rewatchvault page", "Transcript"], entries,
         {4: 45, 7: 60, 12: 40}),
        ("Discussion", ["Air date", "Episode", "Category (as aired)", "#", "Text", "Speaker",
                        "People", "Films", "Page slug"], bullets, {3: 40, 5: 100, 7: 30}),
        ("Hosts' picks", ["Air date", "Episode", "Category (as aired)", "Speaker", "Pick",
                          "Page slug"], picks, {3: 40, 5: 50}),
    ]
    for n, (title, header, rows, widths) in enumerate(sheets):
        ws = wb.active if n == 0 else wb.create_sheet()
        ws.title = title
        ws.append(header)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        # Air date, episode, category, then position: discussion order.
        for row in sorted(rows, key=lambda r: tuple(str(x) for x in r[:4])):
            ws.append(row)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in range(1, len(header) + 1):
            letter = ws.cell(row=1, column=col).column_letter
            ws.column_dimensions[letter].width = widths.get(col, 16)
        for col in widths:
            for (cell,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"batch-{batch}-entries.xlsx"
    wb.save(path)
    logger.info(f"Batch {batch}: {len(entries)} entries, {len(bullets)} bullets, "
                f"{len(picks)} picks -> {path}")
    return path, len(entries), len(bullets), len(picks)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--load-workbooks", action="store_true")
    what.add_argument("--plan", action="store_true")
    what.add_argument("--batch", choices=BATCHES)
    what.add_argument("--check", choices=BATCHES, metavar="BATCH")
    what.add_argument("--export", choices=BATCHES, metavar="BATCH")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--db", default=str(config.db_path()))
    ap.add_argument("--delay", type=float, default=DELAY,
                    help="seconds between requests (default 1; not below 1)")
    ap.add_argument("--refetch", action="store_true",
                    help="fetch pages already stored too")
    ap.add_argument("--limit", type=int, help="fetch at most this many pages")
    args = ap.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"{args.db} not found.")
    conn = connect(args.db)
    try:
        if args.load_workbooks:
            load_workbooks(conn, args.source)
        elif args.plan:
            show_plan(conn)
        elif args.batch:
            result, status = run_batch(conn, args.batch, max(args.delay, DELAY),
                                       args.refetch, args.limit)
            sys.exit(0 if result["passed"] and status == "success" else 1)
        elif args.export:
            export_batch(conn, args.export)
        else:
            result = check_batch(conn, args.check, batch_slugs(conn, args.check))
            sys.exit(0 if result["passed"] else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    config.setup_logging()
    main()
