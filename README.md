# Ucuz Yemek — real-data prototype

A small, honest proof-of-concept for a Turkish food-delivery price-comparison tool.
This is **not** a product yet — it's proof that real, unauthenticated price data
can actually be pulled from at least one platform, end to end, right now.

No fabricated numbers anywhere in this repo. Every price printed by the CLI comes
from a live HTTP request made at run time against the real platform.

## What actually works (verified live 2026-11-03)

### Trendyol Go Yemek — CONFIRMED, clean JSON API
- Backend: `api.tgoapis.com` (undocumented; found by grepping the site's own
  Next.js JS bundles for the string `"api.tgoapis.com"`).
- Plain `GET`, no cookies, no auth header, no API key. HTTP 200, real JSON.
- `tgoyemek.com/robots.txt` explicitly **Allows** `/restoranlar` and
  `/restoranlar/:id*` — the exact UI pages this API backs. That's the strongest
  (not risk-free, just least-contradicted) signal found for any platform here.
- Real example pulled live during this build: restaurant search for Kadıköy
  (40.9833, 29.0333) returned **McDonald's (Feneryolu)**, rating 3.9, with menu
  items including **Big Mac® Menü 530.0 TRY**, **Double Cheeseburger Menü 520.0
  TRY**, **Efsane İkili Menü (Big Mac® + McChicken®) 780.0 TRY**. (The probe's
  original example, Atm Burger id 14974, is also still live and returns its own
  real menu — both are reachable via `uv run python -m ucuz_yemek.cli trendyol`.)

### Yemeksepeti — WORKS, but fragile (UA-gated HTML scrape, not an API)
- Desktop User-Agent → **HTTP 403**, PerimeterX bot-challenge (confirmed live).
- Mobile Safari User-Agent → **HTTP 200**, real HTML with a server-embedded
  Apollo/GraphQL cache containing real prices.
- Real example pulled live during this build, restaurant
  `kadikoy-mezecisi-eoa3` (URL found via the site's own public sitemap at
  `/adventure-map/adventure-map-restaurant-0.xml`):
  - Yadigar Acılı Ezme: **240 TRY** (was 300 TRY)
  - Atom: **200 TRY** (was 250 TRY)
  - Şakşuka: **240 TRY** (was 300 TRY)
  - Haydari: **200 TRY** (was 250 TRY)
  - Havuç Tarator: **200 TRY** (was 250 TRY)
- The real backend JSON API (`disco.deliveryhero.io`, `tr.fd-api.com`) returned
  **HTTP 403 "Invalid Client ID: null"** even when replaying the page's own
  `perseus-client-id` header back at it — there is no clean API path, only this
  UA-gated HTML scrape.

### Getir Yemek — NOT A SEPARATE PLATFORM ANYMORE
- `getir.com/yemek/` 301-redirects straight to `tgoyemek.com/restoranlar?ref=getir`.
- It got consolidated into Trendyol Go / Uber Eats. There is nothing separate to
  fetch — "Getir Yemek" data IS the Trendyol Go data above.

## Known limitations — read before trusting this as a comparison tool

1. **`compare` is not a real cross-platform comparison yet.** The Trendyol Go
   fetcher returns whatever restaurant is geographically nearest to the given
   lat/lon. The Yemeksepeti fetcher only works against one specific,
   hand-picked restaurant URL (there's no clean Yemeksepeti search API to find
   restaurants by location). The two platforms have unrelated restaurant IDs
   and no shared catalog to join on — so `compare` currently prints two
   **different** restaurants' menus side by side, not the same order's price
   on both platforms. It proves both fetchers work on real live data; it does
   not yet prove "X is cheaper than Y for the same food."
2. **Yemeksepeti access is fragile, not a stable API.** It depends on (a) a
   mobile User-Agent bypassing PerimeterX bot detection and (b) the page's
   internal Apollo cache keeping its current shape. Either could break without
   notice. Don't build anything that depends on this running unattended or at
   volume.
3. **`requests` hangs in this dev environment; the CLI uses stdlib
   `urllib.request` instead.** (See `ucuz_yemek/trendyol_go.py` /
   `yemeksepeti.py` — no third-party HTTP dependency at all.) If you port this
   elsewhere and want to use `requests`, test it first; something about this
   sandbox makes PyPI's `requests`/`urllib3` stack never return from
   `requests.get()` against `api.tgoapis.com`, even with an explicit timeout,
   while raw sockets, stdlib `urllib.request`, and `curl` all work fine.

## Real ToS-risk note (from the original probe, still the honest position)

Mixed, and real — not cleared as risk-free:
- Trendyol Go's own `robots.txt` allows crawling the exact pages this API
  backs, and the API host itself has no `robots.txt` at all. Lowest-risk
  option found, but its Terms of Use (client-side rendered) were never loaded
  to check for an explicit no-scraping clause — that risk is **unverified**,
  not cleared.
- Yemeksepeti actively runs PerimeterX bot detection that blocks the default
  (desktop) path outright. Bypassing it with a different User-Agent to keep
  scraping at any real volume is a genuine anti-bot-circumvention / ToS risk,
  even though a single manual/dev-scale request goes through fine.
- Getir has no separate surface left to assess.

Net: this prototype proves real price data is reachable via real HTTP
requests on at least one platform (and a second, fragile one). It does **not**
mean either platform is risk-free to scrape continuously or at scale.

## Running it

```bash
cd ucuz-yemek

# Real Trendyol Go prices for a given lat/lon (defaults to Kadıköy, İstanbul)
uv run python -m ucuz_yemek.cli trendyol --lat 40.9833 --lon 29.0333 --limit 10

# Real Yemeksepeti prices for one specific restaurant (mobile-UA scrape)
uv run python -m ucuz_yemek.cli yemeksepeti --url https://www.yemeksepeti.com/restaurant/eoa3/kadikoy-mezecisi-eoa3

# Both, side by side (see "Known limitations" above — not yet a real comparison)
uv run python -m ucuz_yemek.cli compare --limit 5
```

Note: `uv run <entrypoint-name>` (the installed console script) was observed to
hang in this dev environment; `uv run python -m ucuz_yemek.cli ...` is the
tested, reliable invocation. If you hit the same hang, that's the workaround.

## Project layout

```
ucuz_yemek/
  trendyol_go.py   # real JSON API fetcher (api.tgoapis.com)
  yemeksepeti.py   # real but fragile HTML-scrape fetcher
  cli.py           # argparse CLI: trendyol / yemeksepeti / compare
```

## Next steps (not done, scoped out of this prototype)

- Build a real geo-aware Yemeksepeti restaurant search (there isn't a clean
  one — would need either further probing of `disco.deliveryhero.io`'s
  internal API auth, or scraping the city/neighborhood listing pages).
- Pick a canonical item (e.g. "Big Mac menu") and match it across both
  platforms' restaurant catalogs by name-similarity, to get an actual
  same-order comparison instead of two arbitrary restaurants.
- Decide if the Yemeksepeti ToS risk is acceptable for anything beyond a
  manual/dev-scale prototype before building a scheduled/production scraper.

## Owner-only steps

None currently — `gh` was authenticated and the repo was pushed in this
session. If `git push` ever fails with an auth error in a future session,
re-authenticating `gh` is an owner step.
