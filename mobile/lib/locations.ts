import type { City } from "./api";

// The real city picker normally comes from GET /api/cities (the live
// backend's 20 real, coverage-verified cities -- see ucuz_yemek/cities.py
// in the main repo, the single source of truth this list mirrors exactly,
// same slugs/names/coordinates, no invented data). This file is only the
// bootstrap fallback used when that live fetch fails -- e.g. the currently
// deployed host (ucuz-yemek-backend.ereboslab.com) doesn't have the
// /api/cities route live yet (pending redeploy, see plans/ucuz-yemek.md),
// so without this fallback the city chip row would render empty.
// `restaurant_count_seen` here matches the real verified count from the
// Python source as of 2026-11-03; a live /api/cities fetch always wins when
// it succeeds.
export const FALLBACK_CITY_SLUG = "istanbul";

export const FALLBACK_CITIES: City[] = [
  { slug: "istanbul", display_name: "İstanbul", latitude: 41.0082, longitude: 28.9784, restaurant_count_seen: 10 },
  { slug: "ankara", display_name: "Ankara", latitude: 39.9334, longitude: 32.8597, restaurant_count_seen: 10 },
  { slug: "izmir", display_name: "İzmir", latitude: 38.4237, longitude: 27.1428, restaurant_count_seen: 10 },
  { slug: "bursa", display_name: "Bursa", latitude: 40.1826, longitude: 29.0665, restaurant_count_seen: 10 },
  { slug: "antalya", display_name: "Antalya", latitude: 36.8969, longitude: 30.7133, restaurant_count_seen: 10 },
  { slug: "adana", display_name: "Adana", latitude: 37.0, longitude: 35.3213, restaurant_count_seen: 10 },
  { slug: "konya", display_name: "Konya", latitude: 37.8746, longitude: 32.4932, restaurant_count_seen: 10 },
  { slug: "gaziantep", display_name: "Gaziantep", latitude: 37.0662, longitude: 37.3833, restaurant_count_seen: 10 },
  { slug: "mersin", display_name: "Mersin", latitude: 36.8, longitude: 34.6333, restaurant_count_seen: 10 },
  { slug: "kayseri", display_name: "Kayseri", latitude: 38.7312, longitude: 35.4787, restaurant_count_seen: 10 },
  { slug: "eskisehir", display_name: "Eskişehir", latitude: 39.7767, longitude: 30.5206, restaurant_count_seen: 10 },
  { slug: "diyarbakir", display_name: "Diyarbakır", latitude: 37.9144, longitude: 40.2306, restaurant_count_seen: 10 },
  { slug: "samsun", display_name: "Samsun", latitude: 41.2867, longitude: 36.33, restaurant_count_seen: 10 },
  { slug: "denizli", display_name: "Denizli", latitude: 37.7765, longitude: 29.0864, restaurant_count_seen: 10 },
  { slug: "sanliurfa", display_name: "Şanlıurfa", latitude: 37.1591, longitude: 38.7969, restaurant_count_seen: 10 },
  { slug: "malatya", display_name: "Malatya", latitude: 38.3552, longitude: 38.3095, restaurant_count_seen: 10 },
  { slug: "kocaeli", display_name: "Kocaeli (İzmit)", latitude: 40.7654, longitude: 29.9408, restaurant_count_seen: 10 },
  { slug: "trabzon", display_name: "Trabzon", latitude: 41.0027, longitude: 39.7168, restaurant_count_seen: 10 },
  { slug: "erzurum", display_name: "Erzurum", latitude: 39.9, longitude: 41.27, restaurant_count_seen: 10 },
  { slug: "van", display_name: "Van", latitude: 38.4891, longitude: 43.4089, restaurant_count_seen: 10 },
];
