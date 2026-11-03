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

export async function searchBudget(params: {
  budget: number;
  lat: number;
  lon: number;
  sort?: SortMode;
  limit?: number;
}): Promise<BudgetSearchResponse> {
  const { budget, lat, lon, sort = "closest_to_budget", limit = 30 } = params;
  const url = new URL("/api/budget", API_BASE_URL);
  url.searchParams.set("budget", String(budget));
  url.searchParams.set("lat", String(lat));
  url.searchParams.set("lon", String(lon));
  url.searchParams.set("sort", sort);
  url.searchParams.set("limit", String(limit));

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
