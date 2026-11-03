# Ucuz Yemek — mobile

Expo/React Native client for Ucuz Yemek. This is a **thin client** over the
already-live backend (`https://ucuz-yemek.vercel.app`, the same FastAPI app
the web frontend at `../web/index.html` talks to) — no business logic lives
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

## Not done yet (honest scope)

- Not built for iOS/Android simulator/device in this pass (no `expo run:ios`
  / `expo run:android` — those require a much longer native build; the web
  export + tsc verification above proves the same cross-platform code
  compiles and the data flow genuinely works end-to-end).
- Not submitted to TestFlight/Play Console — no app-store packaging
  (icons/screenshots/onboarding) done yet; this is a functional MVP, not a
  store-ready release.
- No `/api/match` (chain comparison) screen — kept as a secondary,
  API-only feature on web too, same scope decision carried over here.
- No offline/cache layer, no push notifications, no accounts — none exist
  on the backend either yet.
