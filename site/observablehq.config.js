// Observable Framework configuration for the public Rewatchables site.
//
// Everything under src/data/ is written by pipeline step 15
// (src/rewatchables/pipeline/s15_export_site.py) and committed, so a build needs
// neither Python nor the database. See site/README.md.

import {readFileSync} from "node:fs";

// One page per film, at /movie/<movie_id>. The ids come from the exported index,
// so a film added to the catalogue gets a page on the next build.
const films = JSON.parse(
  readFileSync(new URL("./src/data/films.json", import.meta.url), "utf-8")
);

export default {
  title: "Rewatchables Explorer",
  root: "src",
  style: "site.css",
  pages: [
    {name: "Overview", path: "/"},
    {name: "All films", path: "/films"}
  ],
  dynamicPaths: films.map((f) => `/movie/${f.id}`),
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
