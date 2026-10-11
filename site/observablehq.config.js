// Observable Framework configuration for the public Rewatchables site.
//
// Everything under src/data/ is written by pipeline step 15
// (src/rewatchables/pipeline/s15_export_site.py) and committed, so a build needs
// neither Python nor the database. See site/README.md.

import {readFileSync} from "node:fs";

// One page per film, at /movie/<slug> -- heat-1995 -- made by step 15 from the
// title and year so an address never changes between publishes. The slugs come
// from the exported index,
// so a film added to the catalogue gets a page on the next build.
const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf-8"));
const films = read("./src/data/films.json");

// Likewise one page per keyword on two or more films, at /keyword/<slug>, and
// one per person in the room, at /person/<slug>. A keyword on a single film
// has no page; its chip is drawn as plain text, as in the app.
const keywords = read("./src/data/keywords.json").vocabulary.filter((k) => k.id);
const people = read("./src/data/people.json");

// And one spotlight per director and actor in the app's pickers.
const spotlights = (section) => read(`./src/data/sections/${section}.json`).spotlight;

// And one page per requested film on the Upcoming list.
const requests = read("./src/data/upcoming.json").requests ?? [];

export default {
  title: "Rewatchables Explorer",
  root: "src",
  style: "site.css",
  // Grouped as the app's sidebar is (state.NAV).
  pages: [
    {name: "Overview", path: "/"},
    {name: "Movie Explorer", path: "/films"},
    {name: "The films", open: true, pages: [
      {name: "Genres", path: "/genres"},
      {name: "Directors", path: "/directors"},
      {name: "Actors", path: "/actors"},
      {name: "Keywords", path: "/keywords"},
      {name: "Ratings", path: "/ratings"},
      {name: "Box Office", path: "/boxoffice"}
    ]},
    {name: "The show", open: true, pages: [
      {name: "Hosts & Guests", path: "/hosts"},
      {name: "Timeline & Revisits", path: "/timeline"}
    ]},
    {name: "The bits", open: true, pages: [
      {name: "Cruise vs. Hanks", path: "/verdicts"}
    ]},
    {name: "On deck", open: true, pages: [
      {name: "Upcoming Films", path: "/upcoming"}
    ]}
  ],
  dynamicPaths: [
    ...films.map((f) => `/movie/${f.id}`),
    ...keywords.map((k) => `/keyword/${k.id}`),
    ...people.map((p) => `/person/${p.id}`),
    ...spotlights("directors").map((d) => `/director/${d.id}`),
    ...spotlights("actors").map((a) => `/actor/${a.id}`),
    ...requests.map((r) => `/upcoming/${r.id}`)
  ],
  toc: false,
  pager: false,
  search: false,
  head: `<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cg fill='none' stroke='%232BE8A0' stroke-width='6'%3E%3Ccircle cx='50' cy='50' r='16'/%3E%3Ccircle cx='50' cy='50' r='30'/%3E%3Ccircle cx='50' cy='50' r='44'/%3E%3C/g%3E%3C/svg%3E">`,
  footer: `Unofficial fan project, not affiliated with The Ringer or Spotify.
    Film data and posters from <a href="https://www.themoviedb.org/" target="_blank">TMDB</a>.
    This product uses the TMDB API but is not endorsed or certified by TMDB.
    Plot synopses from Wikipedia (<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank">CC BY-SA 4.0</a>)
    and the <a href="https://www.cs.cmu.edu/~ark/personas/" target="_blank">CMU Movie Summary Corpus</a>.`
};
