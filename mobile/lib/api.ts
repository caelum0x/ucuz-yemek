// Thin client over the Ucuz Yemek backend (FastAPI, self-hosted on
// railyard-box). No business logic lives here -- this only calls the real
// JSON API (/api/budget, /api/cities, ...) and shapes the response for the
// native UI. See ../../README.md for the backend's real data sources
// (Trendyol Go live search, Yemeksepeti curated-chain sitemap lookup).
//
// STATUS (2026-11-04, see ~/products/plans/ucuz-yemek.md): the old host
// (ucuz-yemek.ereboslab.com) was the public *web frontend*, taken down on
// purpose by the owner -- it was never meant to serve the mobile app's API
// calls, it just happened to also expose the backend's routes. The
// dedicated, API-only public host for this backend is live right now
// (verified via curl: /healthz -> 200, /api/budget -> real JSON,
// cache_backed:true) with zero new infra/deploy -- this is that host.
// NOTE: that host is still running the pre-JSON-API-expansion image (deploy
// to main's HEAD is pending separate owner approval, see plan), so
// /api/cities and /api/cities/{slug} 404 there for now; fetchCities() and
// searchCityBudget() below fall back to the real static city list
// (lib/locations.ts) and the already-live /api/budget endpoint so city
// search keeps working without depending on that pending redeploy. Every
// call still fails loudly with a clear "service unavailable" ApiError
// instead of hanging or failing silently.
import { FALLBACK_CITIES } from "./locations";

export const API_BASE_URL = "https://ucuz-yemek-backend.ereboslab.com";

export type SortMode =
  | "closest_to_budget"
  | "best_value"
  | "cheapest_first"
  | "priciest_first";

export type Platform = "trendyol_go" | "yemeksepeti";

export interface AffordableItem {
  platform: Platform;
  restaurant_name: string;
  item_name: string;
  price_try: number;
  distance_km: number | null;
  rating: number | null;
}

export interface BudgetSearchResponse {
  budget_try: number;
  latitude: number;
  longitude: number;
  sort: SortMode;
  trendyol_restaurants_checked: string[];
  yemeksepeti_chains_checked: string[];
  total_affordable_items_found: number;
  items: AffordableItem[];
  platform_errors: Record<string, string> | null;
  scope_note: string;
}

export class ApiError extends Error {
  /**
   * HTTP status of the failed response, or `null` when the request never
   * reached a server at all (DNS failure, TLS failure, offline device, etc).
   */
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * True when the failure means "the backend itself is down/misconfigured"
 * (5xx, or the request never reached any server) rather than a client-side
 * mistake (bad budget, unknown city, etc -- those come back as 4xx with a
 * real `detail` message from the API).
 */
export function isServiceUnavailable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.status === null || error.status >= 500;
}

const SERVICE_UNAVAILABLE_MESSAGE =
  "Ucuz Yemek is temporarily unavailable. We know, and we're on it -- try again in a few minutes.";
const NETWORK_UNREACHABLE_MESSAGE =
  "Could not reach Ucuz Yemek. Check your connection and try again.";

export interface City {
  slug: string;
  display_name: string;
  latitude: number;
  longitude: number;
  restaurant_count_seen: number;
}

export interface CitySearchResponse {
  city: City;
  budget_try: number;
  sort: SortMode;
  trendyol_restaurants_checked: string[];
  yemeksepeti_chains_checked: string[];
  total_affordable_items_found: number;
  items: AffordableItem[];
  platform_errors: Record<string, string> | null;
}

async function toApiError(response: Response): Promise<ApiError> {
  if (response.status >= 500) {
    // 5xx (or an edge/proxy error page like Cloudflare 521/525) means the
    // backend itself is broken, not something the user did -- never show a
    // raw status code for this, show a clear "we're down" state instead.
    return new ApiError(SERVICE_UNAVAILABLE_MESSAGE, response.status);
  }
  let detail = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (body?.detail) detail = String(body.detail);
  } catch {
    // response wasn't JSON -- keep the generic message above
  }
  return new ApiError(detail, response.status);
}

/**
 * Fetches the live city list from GET /api/cities. If that route isn't
 * deployed yet on the current host (404 -- see API_BASE_URL comment above)
 * this falls back to the real static list in lib/locations.ts instead of
 * leaving the city picker empty; a real network/5xx failure still throws so
 * the caller can show the honest "service unavailable" state.
 */
export async function fetchCities(): Promise<City[]> {
  let response: Response;
  try {
    response = await fetch(new URL("/api/cities", API_BASE_URL).toString());
  } catch {
    throw new ApiError(NETWORK_UNREACHABLE_MESSAGE, null);
  }
  if (response.status === 404) {
    return FALLBACK_CITIES;
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  const body = (await response.json()) as { cities: City[] };
  return body.cities;
}

/**
 * City-scoped budget search. The dedicated GET /api/cities/{slug} route
 * isn't deployed on the current host yet (see API_BASE_URL comment above),
 * so this reuses the already-live GET /api/budget with the selected city's
 * real coordinates (from the live list when available, otherwise the same
 * static real coordinates in lib/locations.ts) rather than depending on
 * that pending redeploy.
 */
export async function searchCityBudget(params: {
  citySlug: string;
  budget: number;
  sort?: SortMode;
  limit?: number;
  q?: string;
  knownCities?: readonly City[];
}): Promise<CitySearchResponse> {
  const { citySlug, budget, sort = "best_value", limit = 30, q, knownCities } = params;
  const city = (knownCities ?? FALLBACK_CITIES).find((c) => c.slug === citySlug);
  if (!city) {
    throw new ApiError(`Unknown city: ${citySlug}`, 404);
  }

  const budgetResult = await searchBudget({
    budget,
    lat: city.latitude,
    lon: city.longitude,
    sort,
    limit,
    q,
  });

  return {
    city,
    budget_try: budgetResult.budget_try,
    sort: budgetResult.sort,
    trendyol_restaurants_checked: budgetResult.trendyol_restaurants_checked,
    yemeksepeti_chains_checked: budgetResult.yemeksepeti_chains_checked,
    total_affordable_items_found: budgetResult.total_affordable_items_found,
    items: budgetResult.items,
    platform_errors: budgetResult.platform_errors,
  };
}

function haversineKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371;
  const dLat = ((bLat - aLat) * Math.PI) / 180;
  const dLon = ((bLon - aLon) * Math.PI) / 180;
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const h =
    sinLat * sinLat +
    Math.cos((aLat * Math.PI) / 180) * Math.cos((bLat * Math.PI) / 180) * sinLon * sinLon;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function nearestCity(lat: number, lon: number, cities: readonly City[]): City | null {
  if (cities.length === 0) return null;
  return cities.reduce((closest, city) =>
    haversineKm(lat, lon, city.latitude, city.longitude) <
    haversineKm(lat, lon, closest.latitude, closest.longitude)
      ? city
      : closest
  );
}

export async function searchBudget(params: {
  budget: number;
  lat: number;
  lon: number;
  sort?: SortMode;
  limit?: number;
  q?: string;
}): Promise<BudgetSearchResponse> {
  const { budget, lat, lon, sort = "best_value", limit = 30, q } = params;
  const url = new URL("/api/budget", API_BASE_URL);
  url.searchParams.set("budget", String(budget));
  url.searchParams.set("lat", String(lat));
  url.searchParams.set("lon", String(lon));
  url.searchParams.set("sort", sort);
  url.searchParams.set("limit", String(limit));
  if (q) url.searchParams.set("q", q);

  let response: Response;
  try {
    response = await fetch(url.toString());
  } catch {
    throw new ApiError(NETWORK_UNREACHABLE_MESSAGE, null);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as BudgetSearchResponse;
}

export function platformLabel(platform: Platform): string {
  return platform === "trendyol_go" ? "Trendyol Go" : "Yemeksepeti";
}
