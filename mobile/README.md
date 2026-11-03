# Ucuz Yemek — mobile

Expo/React Native client for Ucuz Yemek. This is a **thin client** over the
already-live backend (`https://ucuz-yemek.ereboslab.com`, the same FastAPI app
the web frontend at `../web/index.html` talks to — migrated off Vercel
2026-11-04, see `~/products/plans/ucuz-yemek.md`) — no business logic lives
here. Every search is a real, live HTTP call to `/api/budget`; nothing is
cached or fabricated on-device.

## What's here

- `App.tsx` — the one real screen: budget input, location chips (4 preset
  Istanbul districts + a real "use my device location" option via
  `expo-location`), sort picker, and a results list (item name, restaurant,
  distance, rating, platform tag, price). Dark theme matching the web
  frontend's design tokens.
- `lib/api.ts` — typed fetch wrapper for `GET /api/budget`.
- `lib/locations.ts` — the same preset districts as the web frontend.

## Run it

```bash
npm install
npx expo start          # Expo Go / simulator
npx expo start --web    # react-native-web preview in a browser
npx tsc --noEmit        # typecheck
npx expo export --platform web   # real production web bundle (verifies the full build)
```

## Verified 2026-11-03

- `npx tsc --noEmit` — clean, zero errors.
- `npx expo export --platform web` — real production bundle built (480KB JS,
  228 modules), served locally and loaded in a real headless Chromium
  session (gstack `browse`).
- End-to-end: tapped the real "Ne yiyebilirim, göster" button, confirmed a
  real network request fired to `https://ucuz-yemek.vercel.app/api/budget`
  (200, ~4.1s), and real live Trendyol Go results rendered on screen
  (Starbucks Cihannüma frappuccino/latte items, Beşiktaş Çıtır Pide Lahmacun
  Kebap items, all at 300 TRY, with real distance/rating). Zero console
  errors.

## Verified 2026-11-03 (later): real iOS Simulator build — first time, found + fixed a real bug

`npx expo run:ios` was actually run against a real iPhone 16 Pro Max
simulator (iOS 26, Xcode 26.0.1) for the first time this pass (previously
only web-export/tsc had been verified — see above).

**Real bug found and fixed**: the first build failed outright — `expo-modules-jsi@58.0.22`
(an Expo SDK dependency pulled in transitively via `expo-modules-core`, not
our own code) fails to compile under Xcode 26's Swift 6 strict-concurrency
checker with `sending 'slot' risks causing data races` in
`JavaScriptObject.swift`'s `withEncodedValue`. Confirmed this is a genuine
upstream regression, not an environment fluke: diffed `expo-modules-jsi`
58.0.15/58.0.20/58.0.21/58.0.22 from the npm registry — the offending
`withEncodedValue` helper was introduced in **58.0.21** and is unchanged in
58.0.22 (the latest version on npm as of this pass); 58.0.20 and earlier
don't have it and compile fine (confirmed indirectly: this portfolio's
`ecomoney` app, pinned to `expo-modules-jsi@58.0.15`, built successfully on
this same machine/Xcode this same day).

Fixed with a `patch-package` patch (`patches/expo-modules-jsi+58.0.22.patch`,
auto-applied via `postinstall`) rather than downgrading the dependency —
downgrading broke CocoaPods' autolinked path resolution (npm nests
`expo-modules-jsi` under `expo-modules-core/node_modules/` instead of
hoisting it when an override is used, which the generated Podfile doesn't
expect) and risked an API-surface mismatch with `expo-modules-macros`'
`@Record` codegen, which does call the new 58.0.21+ JSI APIs. The patch
keeps the full 58.0.22 API surface and fixes only the one function: binds
the already-`nonisolated(unsafe)` slot pointer's wrapped `JavaScriptValue.Slot`
the same way before passing it into the actor-isolated closure, which is
enough for the Swift 6 compiler to see it as safe (same reasoning the
surrounding code already uses for the raw pointer itself).

After the patch: clean rebuild succeeded (`Build Succeeded`, 0 errors, 7
pre-existing unrelated warnings), installed on the simulator, Metro bundled
722 modules with zero JS errors, and the real UI rendered correctly
(screenshot-verified: budget input, 4 location chips, sort options, submit
button, Turkish copy, dark theme — matches the web version's design intent).
**Not independently re-verified on-device**: tapping the submit button to
re-confirm the live network fetch on native (vs. the web-export version
confirmed above) — this sandbox has no Accessibility permission granted to
automate a simulator tap (`osascript`/`cliclick` both need it; it's a
one-time interactive System Settings grant, an owner-only step, not
blocking anything else). The JS bundle and `lib/api.ts` fetch code are
unchanged from what was already live-verified via the web-export + headless
browser pass above, so this is a reasonable-confidence gap, not an unknown.

Android (`expo run:android`) was not run this pass — iOS was sufficient to
find and fix the one real cross-platform native-build blocker (the patched
Swift file is Apple-only code, doesn't affect Android).

## Not done yet (honest scope)

- Not submitted to TestFlight/Play Console — no app-store packaging
  (icons/screenshots/onboarding) done yet; this is a functional MVP, not a
  store-ready release.
- No `/api/match` (chain comparison) screen — kept as a secondary,
  API-only feature on web too, same scope decision carried over here.
- No offline/cache layer, no push notifications, no accounts — none exist
  on the backend either yet.
