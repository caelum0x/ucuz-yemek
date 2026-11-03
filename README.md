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

## Project layout

```
ucuz_yemek/
  trendyol_go.py   # real JSON API fetcher (api.tgoapis.com)
  yemeksepeti.py   # real but fragile HTML-scrape fetcher
  discovery.py     # finds a live restaurant for the same chain on both platforms
  matching.py      # blocking -> matching -> merge-policy same-item matcher
  jev.py           # thin client for the real TypeSafe System One (Jev) API
  cli.py           # argparse CLI: trendyol / yemeksepeti / compare / match
```

## Next steps (not done, scoped out of this prototype)

- `match` is chain-only (needs the same restaurant name reachable on both
  platforms). Real local restaurants (one meze shop, one kebap place) still
  have no shared catalog to join on — would need fuzzy restaurant-identity
  matching (name + address + cuisine), not just item matching, to extend
  `match` beyond chains.
- Decide if the Yemeksepeti ToS risk is acceptable for anything beyond a
  manual/dev-scale prototype before building a scheduled/production scraper.
- No persistence/scheduling yet — every run re-fetches both platforms live
  and re-runs matching from scratch; there's no database of known matches to
  reuse across runs yet.

## Owner-only steps

None currently — `gh` was authenticated and the repo was pushed in this
session. If `git push` ever fails with an auth error in a future session,
re-authenticating `gh` is an owner step.
