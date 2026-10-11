// Observable Framework configuration for the public Rewatchables site.
//
// The site's data is one SQLite database, src/data/site.db, built at build time
// by the data loader src/data/site.db.py from site.sql, the dump pipeline step
// 15 writes and the repository tracks. Every page queries it in the browser
// (src/components/db.js, src/queries/). See site/README.md.
//
// There is one page per section and one per kind of detail view: a film, a
// keyword, a person, a director, an actor and a requested film are each one
// page, which reads the thing it shows from its address (movie?id=heat-1995).
// Nothing is generated per film, so the build makes the same couple of dozen
// pages however large the catalogue grows.

export default {
  title: "Rewatchables Explorer",
  // Data loaders (src/data/site.db.py) run with Python. Windows installs it
  // as `python`; the CI runner, like most Unix systems, as `python3`.
  interpreters: {".py": [process.platform === "win32" ? "python" : "python3"]},
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
