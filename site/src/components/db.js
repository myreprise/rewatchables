// The site's one data source: site.db, queried in the browser.
//
// Pipeline step 15 writes site.sql; the data loader src/data/site.db.py builds
// site.db from it at build time. Every page reads through here: query() runs a
// named query from src/queries/ (bundled into queries.json by its loader), so
// the SQL a page runs is the SQL tests/test_site_db.py checks against the app.
//
// The database and the queries are fetched once per page and cached by the
// browser across pages: their file names carry a hash of their contents, so a
// publish is picked up on the next visit and nothing else is refetched.

import {FileAttachment} from "observablehq:stdlib";

const database = FileAttachment("../data/site.db").sqlite();
const sql = FileAttachment("../data/queries.json").json();

// The rows of a named query, as objects.
export async function query(name, ...params) {
  const [db, queries] = await Promise.all([database, sql]);
  if (!(name in queries)) throw new Error(`no query named ${name}`);
  return db.query(queries[name], params);
}

// The first row of a named query, or null.
export async function row(name, ...params) {
  return (await query(name, ...params))[0] ?? null;
}

// A section's precomputed numbers and lists (section_data) and its charts
// (figures), as one object: {key: value, ..., figures: {name: spec}}. The
// shape is the section builder's own, from src/rewatchables/pipeline/site_export.
export async function section(name) {
  const [data, figures] = await Promise.all([query("section_data", name), query("figures", name)]);
  return {
    ...Object.fromEntries(data.map((d) => [d.key, JSON.parse(d.value)])),
    figures: Object.fromEntries(figures.map((f) => [f.name, JSON.parse(f.spec)]))
  };
}

// One value from a section's precomputed data, without its charts.
export async function sectionValue(name, key) {
  const value = (await query("section_data", name)).find((d) => d.key === key)?.value;
  return value === undefined ? undefined : JSON.parse(value);
}

// The full Wikipedia synopses, fetched only when a reader opens one.
let synopses;
export function synopsis(slug) {
  synopses ??= FileAttachment("../data/synopses.json").json();
  return synopses.then((all) => all[slug] ?? null);
}

// A film row from the database as the components draw it: they read `id`.
export function asFilm(row) {
  return row && {...row, id: row.slug};
}

// Round half to even, as Python's round() and the app's tables do: a mean of
// four runtimes that lands on 96.5 shows as 96, where Math.round gives 97.
export function roundEven(x) {
  if (x == null) return null;
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

// views.blurb: a summary cut at a word boundary, as the overview spotlight cuts it.
function blurb(text, limit = 320) {
  text = text ?? "";
  return text.length <= limit ? text : text.slice(0, limit).replace(/\s+\S*$/, "") + "…";
}

// Every film, as the Explorer, the Genres shelf and the Overview's random
// film read them: the explorer query, in the shape their pages use.
export async function films() {
  return (await query("explorer")).map((f) => ({
    id: f.slug, title: f.title, year: f.year, poster: f.poster, sort: f.sort_title,
    decade: f.decade, genres: list(f.genres), director: f.director_primary,
    directors: f.director_primary ? [f.director_primary] : [], runtime: f.runtime,
    tmdb: f.tmdb, rt: f.rt, ebert: f.ebert, episodes: f.episodes,
    first: f.first_episode, last: f.last_episode, blurb: blurb(f.plot)
  }));
}

// A pipe-joined list column (group_concat) as an array.
export function list(value) {
  return value ? value.split("|") : [];
}

// The page's ?id= value.
export function pageId() {
  return new URLSearchParams(location.search).get("id");
}
