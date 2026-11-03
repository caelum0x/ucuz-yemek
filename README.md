# Ucuz Yemek — real Turkish food-delivery budget search + price comparison

A real, working web app, not just a dev tool: enter a budget in TRY and a
location, see real, live items you can actually afford right now on
Trendyol Go and Yemeksepeti, in one list. The core pain point (owner
clarification, 2026-11-03): "I have 300 lira, what can I actually eat"
instead of scrolling two apps by hand.

## Web app (primary interface)

```bash
cd ucuz-yemek
uv run uvicorn api.index:app --reload
# open http://127.0.0.1:8000/
```

- `web/index.html` — the real frontend: one budget input, one location
  picker, one results list (platform, restaurant, item, price). No
  frameworks, plain HTML/CSS/JS, served directly by FastAPI.
- `api/index.py` — FastAPI app: `GET /api/budget` (the real headline flow,
  cache-backed in production, wraps `ucuz_yemek/budget.py`), `GET /api/match`
  (chain-to-chain cross-platform same-item comparison, wraps
  `ucuz_yemek/service.py`), `GET /api/match-by-url` (same matching pipeline,
  but takes a caller-supplied Trendyol Go restaurant id/URL and a Yemeksepeti
  restaurant URL directly — not limited to the curated chain list, added
  2026-11-04), `GET /api/healthz`, `GET /robots.txt`.
- **Live in production** at `https://ucuz-yemek.ereboslab.com` (migrated off
  Vercel 2026-11-04 — the account is free/Hobby tier, not for real production
  traffic; see "Deploying" below for the real deploy shape). `/api/budget`
  reads from the real Postgres cache (`cache_backed: true`) first, falling
  back to a live fetch only on a genuine cache miss.

## What this was originally (still true, still real)

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

## Real cross-platform same-item matching (`match`, added 2026-11-03)

`compare` (above) only ever proved both fetchers work — it never matched
individual items, which was this README's own explicitly flagged gap. `match`
closes it for real:

```bash
uv run python -m ucuz_yemek.cli match --chain subway --lat 41.0422 --lon 29.0061
```

1. **Restaurant discovery, both platforms, for the same chain** (`discovery.py`):
   Trendyol Go via its own live search filtered by name; Yemeksepeti via its
   real public sitemap (`adventure-map-restaurant-{0,1,2}.xml`, ~37MB,
   cached 24h in `~/.cache/ucuz-yemek`) filtered by slug. No restaurant-search
   API exists on Yemeksepeti, so the sitemap is the only real path — see the
   original probe notes above.
2. **Entity-fusion matching pipeline** (`matching.py`, same blocking ->
   matching -> merge-policy architecture used for deduplicating entities
   across knowledge-graph sources): cheap token-Jaccard blocking first, then
   exact/near-exact normalized strings auto-match for free, and every
   genuinely ambiguous pair (shared words but possibly a different size or a
   combo-vs-standalone variant — Jaccard alone can't tell) goes to a real
   **Jev** (TypeSafe System One, `jev.py`) Noul judgment: "do these two
   listings refer to the exact same product, same size/variant?" Pairs Jev
   is unsure about are left `needs_review`, never silently force-matched.
3. **Verified live, real Subway branches, 2026-11-03**: Trendyol Go's Subway
   (Cihannüma, Beşiktaş) vs Yemeksepeti's Subway (Kozyatağı, Kadıköy) —
   179 Trendyol items, 198 Yemeksepeti items, 1047 candidate pairs from
   blocking, **172 real same-item matches** (168 exact-string, 4 Jev-resolved,
   e.g. correctly matching "İtalyan B.M.T. (15 cm)" to "İtalyan B.M.T.
   Sandviç (15 cm)" while correctly leaving "(30 cm.) Menü" vs "(30 cm)"
   combo-vs-standalone pairs as `needs_review` instead of merging them). A
   spot-check of every matched pair confirmed zero size-variant mismatches
   (e.g. no 15 cm item ever matched to a 30 cm one). Real finding from that
   run: Yemeksepeti was cheaper than Trendyol Go on essentially every matched
   item, by ~15-20 TRY per sandwich — a real, live, same-item price gap, not
   a fabricated example.
4. **Honest remaining limitation**: this proves the matching *engine* works
   end-to-end on live data for a chain that exists on both platforms. It does
   not yet have a UI, a scheduler, or a database — it's a CLI you run on
   demand. It's also chain-dependent: non-chain restaurants (a single meze
   shop, a single kebap place) usually don't exist under the same name on
   both platforms, so `match` will honestly report zero matches rather than
   invent a comparison — see the `compare` limitations below, which still
   apply to restaurants that aren't the same chain on both platforms.

## Known limitations — read before trusting this as a comparison tool

1. **`compare` is not a real cross-platform comparison yet.** The Trendyol Go
   fetcher returns whatever restaurant is geographically nearest to the given
   lat/lon. The Yemeksepeti fetcher only works against one specific,
   hand-picked restaurant URL (there's no clean Yemeksepeti search API to find
   restaurants by location). The two platforms have unrelated restaurant IDs
   and no shared catalog to join on — so `compare` currently prints two
   **different** restaurants' menus side by side, not the same order's price
   on both platforms. `match` (above) is the real fix for chain restaurants;
   `compare` is unchanged for the general non-chain case.
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

# Real cross-platform SAME-ITEM matching for one chain (needs a TypeSafe API
# key, see "Jev API key" below)
uv run python -m ucuz_yemek.cli match --chain subway --lat 41.0422 --lon 29.0061
```

Note: `uv run <entrypoint-name>` (the installed console script) was observed to
hang in this dev environment; `uv run python -m ucuz_yemek.cli ...` is the
tested, reliable invocation. If you hit the same hang, that's the workaround.

### Jev API key (required for `match` only)

`match` calls the real TypeSafe System One API (Jev) to adjudicate ambiguous
item pairs. Set `TYPESAFE_API_KEY` in the environment, or add
`typesafe_api_key=...` to `~/products/.env` (this portfolio's existing
convention — `jev.py` reads that file automatically if the env var isn't
set). `trendyol`, `yemeksepeti`, and `compare` need no key at all.

## Real budget-first search (`budget`, the headline feature, added 2026-11-03)

```bash
uv run python -m ucuz_yemek.cli budget --budget 300 --lat 41.0422 --lon 29.0061
```

`ucuz_yemek/budget.py` answers "I have N TRY, what can I actually eat right
now" directly, across both platforms:

- **Trendyol Go**: real location-based nearby-restaurant search (no chain
  filter needed) — `trendyol_go.search_restaurants` already returns the real
  nearest restaurants to a lat/lon. Capped to the nearest 6 restaurants per
  request (each is its own live menu-fetch HTTP call).
- **Yemeksepeti**: no real location-search API exists yet (same finding as
  `discovery.py`), so v1 checks a curated set of popular chains independently
  confirmed live on the sitemap this session: Subway, Burger King,
  McDonald's, KFC, Domino's. This is a real, honestly-scoped v1 limitation,
  not a silent narrowing — the API response labels it explicitly via
  `scope_note`.
- Ranking (v1, deliberately simple): closest to the budget first (most food
  for the money), since no real per-item nutrition/portion data exists to
  rank on anything richer yet.

**Verified live, real data, this session**: a 300 TRY search near Beşiktaş
(41.0422, 29.0061) checked 6 real Trendyol Go restaurants + 5 curated
Yemeksepeti chains in ~9 seconds wall time and returned **636 real affordable
items**, e.g. real Subway/Burger King/McDonald's/Domino's combo items at or
just under 300 TRY on both platforms, sorted closest-to-budget first. Also
driven end-to-end through the real browser UI (not just the API) — see
`plans/ucuz-yemek.md` for the full verification notes and screenshot.

## Project layout

```
ucuz_yemek/
  trendyol_go.py     # real JSON API fetcher (api.tgoapis.com)
  yemeksepeti.py      # real but fragile HTML-scrape fetcher
  discovery.py        # finds a live restaurant for the same chain on both platforms
  matching.py         # blocking -> matching -> merge-policy same-item matcher
  jev.py              # thin client for the real TypeSafe System One (Jev) API
  budget.py           # real budget-first affordable-item search (the headline feature)
  cache_db.py         # real Postgres connection + schema for the cache layer (added 2026-11-03)
  cached_fetchers.py  # read-through/write-back cache around trendyol_go/yemeksepeti (added 2026-11-03)
  refresh_job.py      # real scheduled cache-warming job, 20 cities + 9 chains (expanded 2026-11-04)
  service.py          # shared match pipeline (run_match chain-to-chain, run_match_by_urls by
                      # caller-supplied identity, added 2026-11-04), used by cli.py and api/index.py
  cli.py              # argparse CLI: trendyol / yemeksepeti / compare / match / budget
api/
  index.py         # FastAPI app, self-hosted on railyard-box (migrated off Vercel 2026-11-04):
                   # /api/budget (proxies to backend/'s cache, same box, container DNS),
                   # /api/match, /api/match-by-url, /api/healthz, /robots.txt
  Dockerfile       # runs this app via uvicorn (added 2026-11-04, replaces Vercel's Python builder)
backend/
  server.py          # real standalone FastAPI backend: cache-first /api/budget, in-process scheduled
                      # refresh loop, /admin/refresh (added 2026-11-03)
  Dockerfile, docker-compose.yml  # real deploy shape, LIVE on railyard-box (deployed 2026-11-03)
web/
  index.html        # the real frontend (plain HTML/CSS/JS, no framework)
  templates/        # server-rendered SEO pages: city.html, chain_compare.html, about/privacy/faq,
                     # sitemap.xml -- cross-linked, robots.txt-covered (audited+fixed 2026-11-04)
mobile/
  App.tsx            # real Expo/React Native client, thin wrapper over the live /api/budget
                      # (added 2026-11-03; iOS verified 2026-11-03, Android verified 2026-11-04)
```

## Deploying (live — see plans/ucuz-yemek.md for full history)

Both halves run as their own Docker service on railyard-box (one of this
portfolio's own Oracle boxes — never Vercel for real production traffic,
owner constraint 2026-11-04), on the same `products-net` so the web app
reaches the backend by container DNS instead of a public URL:

- `backend/` → `infra-box/stacks/ucuz-yemek-backend` →
  `ucuz-yemek-backend.ereboslab.com` (internal-only, grey-cloud DNS).
- `api/` (this app) → `infra-box/stacks/ucuz-yemek-web` →
  **`https://ucuz-yemek.ereboslab.com`** (the real public one).

Redeploy either with `sudo ./install.sh ucuz-yemek-backend` /
`sudo ./install.sh ucuz-yemek-web` from `infra-box/` on that box after a
`git pull` of this repo into `/srv/src/ucuz-yemek`.

No environment variables are required for `/api/budget` (Trendyol Go and
Yemeksepeti need no auth). `/api/match`/`/api/match-by-url` additionally need
`TYPESAFE_API_KEY` set wherever this app runs if those endpoints adjudicate
ambiguous matches via Jev.

## Real backend service (caching + scheduled job, added 2026-11-03)

Originally the only "backend" was `api/index.py` — a stateless serverless
function that live-called Trendyol Go/Yemeksepeti on *every* request, with
no database, no cache, no scheduled job. `backend/` is a real, separate,
persistent service that fixes that (and, once both were moved onto the same
box 2026-11-04, is what `api/index.py` now proxies to for every request):

- `ucuz_yemek/cache_db.py` — real Postgres schema (`trendyol_restaurant_search_cache`,
  `trendyol_menu_cache`, `yemeksepeti_chain_cache`).
- `ucuz_yemek/cached_fetchers.py` — read-through/write-back cache around the
  existing live fetchers; a cache miss/stale entry falls through to the exact
  same live call `api/index.py` already makes, then writes the real result
  back for next time.
- `ucuz_yemek/refresh_job.py` — a real scheduled job that live-fetches every
  supported city (`cities.py`, 20 cities) and curated chain
  (`budget.CURATED_YEMEKSEPETI_CHAINS`, 9 chains as of 2026-11-04) and warms
  the cache.
- `backend/server.py` — a standalone FastAPI process that runs that job
  in-process on a timer (default every 6h) and serves `/api/budget` from the
  cache first (`use_cache=True`), plus `/admin/refresh` for an on-demand
  manual warm.
- `budget.find_affordable_items(..., use_cache=True)` is purely additive —
  the default (`use_cache=False`) is byte-for-byte the original behavior, so
  the existing CLI is unaffected either way.

Run it locally:

```bash
docker run -d -p 15544:5432 -e POSTGRES_DB=ucuz_yemek -e POSTGRES_USER=ucuz_yemek \
    -e POSTGRES_PASSWORD=ucuz_yemek postgres:16-alpine
DATABASE_URL=postgresql://ucuz_yemek:ucuz_yemek@localhost:15544/ucuz_yemek \
    uv run python -m ucuz_yemek.refresh_job      # one real warm-up pass
DATABASE_URL=postgresql://ucuz_yemek:ucuz_yemek@localhost:15544/ucuz_yemek \
    uv run uvicorn backend.server:app --port 8811
curl "http://127.0.0.1:8811/api/budget?budget=300&lat=41.0082&lon=28.9784"
```

**Why this also matters for the known `/api/budget` 502/403 history**: the
original bug was Yemeksepeti's anti-bot layer 403ing Vercel's hosting IP on a
live call. The real fix (2026-11-04) wasn't just caching — it was moving the
whole app off Vercel onto the same box as this backend, so `/api/budget`
reaches it over the box's internal `products-net` instead of any public
egress. See plans/ucuz-yemek.md for the full verification history (live psql
counts, curl timings, refresh-job runs with zero failures, and the final
live `cache_backed:true` proof in production).

## Next steps (not done)

- `/api/match-by-url` (added 2026-11-04) covers the "I already know both
  restaurants' identity" case. True fuzzy restaurant-identity matching (find
  the SAME local restaurant across both platforms from name+address+cuisine
  alone, with no identity given) is still not built — still needed to extend
  matching to arbitrary local restaurants a user hasn't already identified.
- Decide if the Yemeksepeti ToS risk is acceptable for anything beyond this
  curated-chain/cache-backed scale before scraping more broadly.
- No real custom domain yet (`ucuz-yemek.ereboslab.com` is a subdomain of a
  shared box's zone) — owner has said a real domain purchase is a future
  step, not blocking anything today.

## Owner-only steps

None currently — `gh` was authenticated and the repo was pushed in this
session. If `git push` ever fails with an auth error in a future session,
re-authenticating `gh` is an owner step.
