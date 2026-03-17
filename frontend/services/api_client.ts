/**
 * Simple isomorphic fetch client to communicate with our FastAPI backend.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function fetchAssetHistory(symbol: string, days: number = 365, refresh: boolean = false) {
  try {
    const url = `${API_BASE_URL}/market/assets/${symbol}/history?days=${days}${refresh ? "&refresh=true" : ""}`;
    const response = await fetch(url, {
      next: { revalidate: refresh ? 0 : 60 }, // Disable Next.js cache if refreshing
      cache: refresh ? 'no-store' : 'default'
    });
    
    if (!response.ok) {
      console.error("Failed to fetch asset history from backend", response.statusText);
      return [];
    }

    const json = await response.json();
    if (json.status === "success") {
      return json;
    }
    return null;
  } catch (err) {
    console.error("Network error when fetching history:", err);
    return [];
  }
}
