// Thin client over the ALREADY LIVE Ucuz Yemek backend (FastAPI, self-hosted
// on railyard-box -- migrated off Vercel 2026-11-04, see
// ~/products/plans/ucuz-yemek.md: Vercel account is free/Hobby tier, not for
// real production traffic). No business logic lives here -- this only calls
// the same real /api/budget endpoint the web frontend (web/index.html)
// calls, and shapes the response for the native UI. See ../../README.md for
// the backend's real data sources (Trendyol Go live search, Yemeksepeti
// curated-chain sitemap lookup).

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

export class ApiError extends Error {}

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

async function parseErrorDetail(response: Response): Promise<string> {
  let detail = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (body?.detail) detail = String(body.detail);
  } catch {
    // response wasn't JSON -- keep the generic message above
  }
  return detail;
}

export async function fetchCities(): Promise<City[]> {
  let response: Response;
  try {
    response = await fetch(new URL("/api/cities", API_BASE_URL).toString());
  } catch {
    throw new ApiError(
      "Could not reach the live server. Check your connection and try again."
    );
  }
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
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
    throw new ApiError(
      "Could not reach the live server. Check your connection and try again."
    );
  }
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
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
  } catch (networkErr) {
    throw new ApiError(
      "Could not reach the live server. Check your connection and try again."
    );
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // response wasn't JSON -- keep the generic message above
    }
    throw new ApiError(detail);
  }

  return (await response.json()) as BudgetSearchResponse;
}

export function platformLabel(platform: Platform): string {
  return platform === "trendyol_go" ? "Trendyol Go" : "Yemeksepeti";
}
