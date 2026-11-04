// The real city picker now comes from GET /api/cities (the live backend's
// 20 real, coverage-verified cities -- see ucuz_yemek/cities.py). This is
// only the fallback used if that fetch fails before the user picks a city.
export const FALLBACK_CITY_SLUG = "istanbul";
