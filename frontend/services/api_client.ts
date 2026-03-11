/**
 * Simple isomorphic fetch client to communicate with our FastAPI backend.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function fetchAssetHistory(symbol: string, days: number = 365) {
  try {
    const response = await fetch(`${API_BASE_URL}/market/assets/${symbol}/history?days=${days}`, {
      next: { revalidate: 60 } // Next.js App Router cache: re-fetch only if older than 1 minute
    });
    
    if (!response.ok) {
      console.error("Failed to fetch asset history from backend", response.statusText);
      return [];
    }

    const json = await response.json();
    if (json.status === "success" && Array.isArray(json.data)) {
      return json.data;
    }
    return [];
  } catch (err) {
    console.error("Network error when fetching history:", err);
    return [];
  }
}
