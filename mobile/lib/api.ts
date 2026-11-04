// Thin client over the Ucuz Yemek backend (FastAPI, self-hosted on
// railyard-box). No business logic lives here -- this only calls the real
// JSON API (/api/budget, /api/cities, ...) and shapes the response for the
// native UI. See ../../README.md for the backend's real data sources
// (Trendyol Go live search, Yemeksepeti curated-chain sitemap lookup).
//
// STATUS (2026-11-04, see ~/products/plans/ucuz-yemek.md): this host is the
// public *web frontend* (web/index.html), which is currently DOWN (confirmed
// dead, HTTP 525) -- it was never meant to serve the mobile app's API calls
// in the first place, it just happened to also expose the backend's routes.
// A separate, dedicated public API host for this backend already exists and
// is live (https://ucuz-yemek-backend.ereboslab.com, verified via curl:
// /healthz -> 200, /api/budget -> real JSON, cache_backed:true) but pointing
// the app at it is an explicit decision left open for the owner -- see the
// plan file's open item -- so this constant intentionally still points at
// the dead host. Every call below fails loudly with a clear "service
// unavailable" ApiError instead of hanging or failing silently; nothing here
// assumes the host above is reachable.
export const API_BASE_URL = "https://ucuz-yemek.ereboslab.com";

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
  trendyol_restaurants_checked: number;
  yemeksepeti_chains_checked: number;
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
  trendyol_restaurants_checked: number;
  yemeksepeti_chains_checked: number;
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

export async function fetchCities(): Promise<City[]> {
  let response: Response;
  try {
    response = await fetch(new URL("/api/cities", API_BASE_URL).toString());
  } catch {
    throw new ApiError(NETWORK_UNREACHABLE_MESSAGE, null);
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  const body = (await response.json()) as { cities: City[] };
  return body.cities;
}

export async function searchCityBudget(params: {
  citySlug: string;
  budget: number;
  sort?: SortMode;
  limit?: number;
  q?: string;
}): Promise<CitySearchResponse> {
  const { citySlug, budget, sort = "best_value", limit = 30, q } = params;
  const url = new URL(`/api/cities/${encodeURIComponent(citySlug)}`, API_BASE_URL);
  url.searchParams.set("budget", String(budget));
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
  return (await response.json()) as CitySearchResponse;
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
