/* Urja - app-shell cache. Cache-first so the installed app works fully
 * offline (data.js is embedded model data, not a live API). Bump VERSION
 * whenever any shell file or the data snapshot changes.
 *
 * MERGED when the redesigned app landed. The redesign shipped its
 * own simpler service worker; this file deliberately keeps the two protections
 * that one dropped, and adopts the two improvements it added. Do not replace
 * this wholesale on the next design import - re-merge.
 */

/* KEPT FROM THE OLD WORKER (1/2) - VERSION CONTRACT.
 * The `-dataYYYYMMDD` suffix is NOT decoration: it must be set to the date
 * stamped inside data.js by scripts/app_data_extract.py - not to today's date,
 * and not to the date of the code change. Bump the semver part for shell/code
 * changes, the data suffix for a re-pin, and both when both moved.
 *
 * WHY THIS EXISTS. Three sources once disagreed and nothing looked broken:
 * sw.js advertised the pin, data.js had moved to the
 * regen, and app.js carried a hardcoded "-56% CO2" against a real -60.8%.
 * A cache-first PWA hides exactly this.
 *
 * NOTE, AND IT IS A REGRESSION TO CLOSE: the OLD app.js read this suffix back
 * at runtime and showed the user "STALE" when it disagreed with data.js's
 * meta.generated. The redesigned app.js does not do that check. The naming
 * contract is therefore currently a convention enforced by hand rather than by
 * code. The Hot water screen does surface `meta.generated`, which is a partial
 * substitute. Re-adding the check is tracked as an open item.
 *
 * v3.0.0: the redesigned app (new index.html, app.js, styles.css). data.js is
 * UNCHANGED from the second extract, so the suffix does not move. */
/* v3.0.1: hot-water arithmetic fixed in app.js (per-household divisor, plus
 * the three district.st read errors). data.js unchanged, so only the semver
 * moves. This bump is what actually ships the fix - during testing the old
 * app.js was served from cache after the file on disk had changed, which is
 * the very failure the `cache: "reload"` note below exists for. */
const VERSION = "urja-v3.7.0-data20260821"; // data.js meta.generated 2026-08-21 (DENS batch: area-budget PV caps, density multipliers 1.00 flat, roof-competition pair, farm density 0.08022 kWp/m2 = GCR 0.382). Town 1,733,362,452.99 / BAU 3,643,546,228.06, vs-BAU 52.4265% / 62.0169%. Farm 241,462.2 kWp FLAT across all three periods - built entirely in 2030, land-bound thereafter; rooftop 116,886.3 kWp; collector 63,226.0 m2.

/* No "./" here: on some hosts the bare directory 404s. */
const SHELL = [
  "index.html", "styles.css", "app.js", "data.js",
  "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  /* KEPT FROM THE OLD WORKER (2/2) - `cache: "reload"`. BUGFIX.
   * `cache.addAll(SHELL)` was silently shipping stale code: addAll issues its
   * requests with the DEFAULT cache mode, so each one may be satisfied from the
   * browser's own HTTP cache. Bumping VERSION therefore created a brand-new,
   * correctly-named cache and filled it with the OLD files. Caught live on
   * - cache "urja-v2.9.0-data20260816" held a 67,977-byte app.js
   * while the server was serving 74,356 bytes. That is not cosmetic: a re-pin
   * can be published, VERSION dutifully bumped, and residents still shown the
   * previous run's numbers with no symptom.
   *
   * ADOPTED FROM THE REDESIGN: each entry is added on its own with a catch, so
   * one missing file logs a warning instead of rejecting install and leaving
   * the app with no offline cache at all. The old worker used a single addAll,
   * which was atomic in the wrong direction. */
  e.waitUntil(
    caches.open(VERSION).then((c) => Promise.all(
      SHELL.map((u) => c.add(new Request(u, { cache: "reload" }))
        .catch((err) => {
          console.warn("[urja sw] not cached:", u, err && err.message);
          return null;
        }))
    )).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const FONTS = /fonts\.(googleapis|gstatic)\.com/;

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      if (hit) {
        /* ADOPTED FROM THE REDESIGN: the new shell loads Instrument Sans from
         * Google Fonts, so the font must be cached or the installed app loses
         * its typeface offline. Served from cache, refreshed in the background. */
        if (FONTS.test(req.url)) {
          fetch(req).then((r) => {
            if (r && r.ok) caches.open(VERSION).then((c) => c.put(req, r.clone()));
          }).catch(() => {});
        }
        return hit;
      }
      return fetch(req).then((res) => {
        if (res && res.ok && (req.url.startsWith(self.registration.scope) || FONTS.test(req.url))) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match("index.html"));   // navigation fallback
    })
  );
});
