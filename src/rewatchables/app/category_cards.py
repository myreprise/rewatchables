"""One category entry, drawn: its card, its discussion, and the coverage note.

Shared by the Categories section and the film dossier's "In the categories"
block. It lives outside app/sections on purpose: the dossier importing a
section module would load the sections package, whose explorer imports the
dossier back.
"""

import html as htmlmod

import pandas as pd
import streamlit as st

from rewatchables.app.components import tape
from views import html, plain

FAMILY_LABEL = {"standing": "Standing", "segment": "Segment",
                "most_year": "The most…", "one_off": "One-off award"}
FAMILY_ORDER = ["standing", "segment", "most_year", "one_off"]
SOURCE_NOTE = ('From <a href="https://rewatchvault.com" target="_blank">rewatchvault.com</a>, '
               "an independent archive of The Rewatchables. Every entry links to its page there.")


# ── Formatting ────────────────────────────────────────────────────────────────

def minute(seconds):
    """1551 -> '25:51'; 3903 -> '1:05:03'; None -> None."""
    if seconds is None or pd.isna(seconds):
        return None
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _esc(text):
    return plain(htmlmod.escape(text or "", quote=False))


def prose_html(text, spans):
    """`text` escaped, with each linked name or title in it set in bold.

    `spans` are mention rows ({start, end, kind}); offsets are into `text`.
    """
    out, pos = [], 0
    for m in sorted(spans, key=lambda m: m["start"]):
        start, end = int(m["start"]), int(m["end"])
        if start < pos:          # overlapping spans: keep the first
            continue
        out.append(_esc(text[pos:start]))
        out.append(f'<b class="rw-cat-name is-{m["kind"]}">{_esc(text[start:end])}</b>')
        pos = end
    out.append(_esc(text[pos:]))
    return "".join(out)


def day_label(iso):
    if not iso or pd.isna(iso):
        return "date unknown"
    d = pd.Timestamp(iso)
    return f"{d.day} {d:%b %Y}"   # %-d is glibc-only


def episode_label(row):
    """'EP 068 · American Pie · 28 Nov 2023', or the film and date alone when
    the episode isn't linked to the episode list."""
    ep = f"EP {int(row['episode_number']):03d} · " if pd.notna(row["episode_number"]) else ""
    return f"{ep}{row['film_title']} · {day_label(row['air_date'])}"


def category_name(row):
    return row["display_name"] if isinstance(row.get("display_name"), str) else row["banner"]


# ── One entry ─────────────────────────────────────────────────────────────────

def entry_card(entry, mentions, show_film=False):
    """The card for one entry: category, answer, minute, and its links out."""
    spans = mentions[(mentions["location"] == "answer")].to_dict("records") if len(mentions) else []
    answer = entry["answer"]
    answer_html = (prose_html(answer, spans) if isinstance(answer, str)
                   else '<span class="rw-cat-noanswer">No single answer</span>')
    when = minute(entry["transcript_seconds"])
    links = [f'<a href="{entry["source_url"]}" target="_blank">rewatchvault</a>']
    if isinstance(entry["transcript_url"], str):
        links.append(f'<a href="{entry["transcript_url"]}" target="_blank">transcript</a>')
    family = FAMILY_LABEL.get(entry.get("family"), "Uncategorised")
    film = (f'<span class="rw-cat-film">{_esc(entry["film_title"])}</span>' if show_film else "")
    return html(f"""
    <div class="rw-cat-card">
      <div class="rw-cat-head">
        <span class="rw-cat-min">{when or "&mdash;"}</span>
        <span class="rw-cat-banner">{_esc(entry["banner"])}</span>
        <span class="badge">{family}</span>{film}
      </div>
      <div class="rw-cat-answer">{answer_html}</div>
      <div class="rw-cat-links">{' &middot; '.join(links)}</div>
    </div>""")


def discussion_html(bullets, mentions, picks):
    """One entry's discussion: bullets with names in bold and their speaker,
    then the hosts' picks when the page has them."""
    parts = []
    if len(bullets):
        items = []
        for b in bullets.itertuples():
            spans = mentions[(mentions["location"] == "bullet")
                             & (mentions["position"] == b.position)].to_dict("records")
            who = (f' <span class="rw-cat-who">&mdash; {_esc(b.speaker_names)}</span>'
                   if isinstance(b.speaker_names, str) else "")
            items.append(f"<li>{prose_html(b.text, spans)}{who}</li>")
        parts.append(f'<ul class="rw-cat-disc">{"".join(items)}</ul>')
    if len(picks):
        rows = []
        for p in picks.itertuples():
            spans = mentions[(mentions["location"] == "pick")
                             & (mentions["position"] == p.position)].to_dict("records")
            rows.append(f"<div><dt>{_esc(p.speaker_name)}</dt>"
                        f"<dd>{prose_html(p.text, spans)}</dd></div>")
        parts.append('<div class="rw-cat-picks"><span class="lbl">The hosts\' picks</span>'
                     f'<dl>{"".join(rows)}</dl></div>')
    return html("".join(parts)) or '<p class="rw-cat-noanswer">No discussion recorded.</p>'


def render_entries(cats, entries, show_film=False):
    """Cards, each with its discussion in an expander, in the order given."""
    slugs = set(entries["discussion_slug"])
    bullets = cats.bullets[cats.bullets["discussion_slug"].isin(slugs)]
    mentions = cats.mentions[cats.mentions["discussion_slug"].isin(slugs)]
    picks = cats.picks[cats.picks["discussion_slug"].isin(slugs)]
    by = lambda df: dict(tuple(df.groupby("discussion_slug"))) if len(df) else {}  # noqa: E731
    b_of, m_of, p_of = by(bullets), by(mentions), by(picks)
    none = pd.DataFrame(columns=["location", "position", "start", "end", "kind"])
    for _, e in entries.iterrows():
        slug = e["discussion_slug"]
        m = m_of.get(slug, none)
        st.markdown(entry_card(e, m, show_film), unsafe_allow_html=True)
        # bullet_count is blank (NaN here) for an entry with no discussion.
        n = 0 if pd.isna(e["bullet_count"]) else int(e["bullet_count"])
        picks_n = 0 if pd.isna(e["pick_count"]) else int(e["pick_count"])
        if not n and not picks_n:
            continue
        label = f"Discussion — {n} point{'s' if n != 1 else ''}"
        if picks_n:
            label += f", {picks_n} pick{'s' if picks_n != 1 else ''}"
        with st.expander(label):
            st.markdown(discussion_html(b_of.get(slug, pd.DataFrame()), m,
                                        p_of.get(slug, pd.DataFrame())),
                        unsafe_allow_html=True)


def coverage_note(coverage):
    """The caveat every count on these pages carries until all batches are in."""
    if coverage["complete"]:
        return ""
    # One string, not a wrapped block: html() joins lines with no space between.
    text = (f"<b>Partial data.</b> {coverage['episodes_covered']} of "
            f"{coverage['episodes_known']} episodes, {coverage['entries']:,} entries so far. "
            "Counts here cover only these episodes; more arrive batch by batch.")
    return f'<div class="rw-cat-coverage">{text}</div>'


# ── The film dossier's block ──────────────────────────────────────────────────

def render_film_block(ctx, movie_id):
    """'In the categories' on a film's dossier: its entries, airing by airing.
    Draws nothing for a film with none."""
    cats = ctx.categories
    if cats.entries.empty:
        return
    entries = cats.entries[cats.entries["movie_id"] == movie_id]
    if entries.empty:
        return
    tape(f"In the categories &mdash; {len(entries)} entr{'ies' if len(entries) != 1 else 'y'}")
    note = coverage_note(cats.coverage)
    if note:
        st.markdown(note, unsafe_allow_html=True)
    for _, airing in entries.groupby(["air_date", "rv_episode_slug"], sort=True):
        first = airing.iloc[0]
        st.markdown(
            f'<div class="rw-kw-gridnote"><span>{episode_label(first)} · '
            f'{len(airing)} entries</span></div>', unsafe_allow_html=True)
        render_entries(cats, airing.sort_values("transcript_seconds", na_position="last"))
    st.markdown(f'<p class="rw-cat-source">{SOURCE_NOTE}</p>', unsafe_allow_html=True)
