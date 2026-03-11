import { useState, useEffect } from "react";
import { API_BASE_URL } from "@/services/api_client";

export type MarketQuote = {
  symbol: string;
  price: number;
  changePercent: number;
};

export type NewsSentiment = {
  symbol: string;
  sentiment_score: number;
  trending_topics: string[];
};

export type DashboardPulse = {
  market_overview: MarketQuote[];
  sentiment: NewsSentiment;
};

export function useDashboardPulse() {
  const [data, setData] = useState<DashboardPulse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function fetchData() {
      // Small pulse in header can start immediately/silently if needed
      // But for the Card Shimmer, we wait until data is READY
      try {
        const timestamp = new Date().getTime();
        const response = await fetch(`${API_BASE_URL}/market/dashboard-pulse?t=${timestamp}`);
        if (!response.ok) {
          throw new Error("Failed to fetch dashboard pulse");
        }
        const json: DashboardPulse = await response.json();

        if (mounted) {
          // 1. Commit Data AND Start Visual Pulse simultaneously
          setData(json);
          setRefreshing(true);
          setLoading(false);
          setLastUpdated(new Date());
          setError(null);

          // 2. Hold pulse for 800ms so it's a visible, timed 'heartbeat'
          setTimeout(() => {
            if (mounted) setRefreshing(false);
          }, 800);
        }
      } catch (err: any) {
        if (mounted) {
          setError(err.message || "Network error");
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    // Initial fetch
    fetchData();

    // Poll every 10 seconds (aligned with Backend Redis cache TTL)
    const intervalId = setInterval(fetchData, 10000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  return { data, loading, refreshing, lastUpdated, error };
}
