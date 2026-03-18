"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, UTCTimestamp } from "lightweight-charts";
import { fetchAssetHistory } from "@/services/api_client";
import { TrendingUp, RefreshCw, Radio } from "lucide-react";
import { useLiveTick, useLiveConnection } from "./LivePriceProvider";

export function ChartWidget({ 
  symbol = "AAPL", 
  days = 365,
  refreshKey = 0 
}: { 
  symbol?: string; 
  days?: number;
  refreshKey?: number;
}) {
  const liveTick = useLiveTick(symbol);
  const isSocketConnected = useLiveConnection();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const intervalSecondsRef = useRef<number>(86400);
  const lastBarRef = useRef<any>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Handle Real-time point updates
  useEffect(() => {
    if (seriesRef.current && liveTick && !loading) {
      const isDaily = intervalSecondsRef.current >= 86400;
      const interval = intervalSecondsRef.current;
      
      const lastBar = lastBarRef.current;
      if (!lastBar) return;

      // Normalize tick and last bar times to seconds
      const tickTime = Math.floor(liveTick.t / 1000);
      let lastTime: number;
      
      if (typeof lastBar.time === 'number') {
        lastTime = lastBar.time;
      } else {
        // Handle ISO string or YYYY-MM-DD
        const date = new Date(lastBar.time);
        lastTime = Math.floor(date.getTime() / 1000);
      }
      
      const isNewBar = tickTime >= lastTime + interval;

      if (isNewBar) {
        // Roll to a new bar
        const normalizedTickTime = Math.floor(tickTime / interval) * interval;
        const newTime = isDaily 
          ? new Date(normalizedTickTime * 1000).toISOString().split('T')[0]
          : (normalizedTickTime as UTCTimestamp);
          
        const newBar = {
          time: newTime as Time,
          open: liveTick.p,
          high: liveTick.p,
          low: liveTick.p,
          close: liveTick.p,
        };
        seriesRef.current.update(newBar);
        lastBarRef.current = newBar;

        if (volumeSeriesRef.current) {
          volumeSeriesRef.current.update({
            time: newTime as Time,
            value: liveTick.s,
            color: "rgba(16, 185, 129, 0.2)"
          });
        }
      } else {
        // Update existing bar
        const updatedBar = {
          ...lastBar,
          close: liveTick.p,
          high: Math.max(lastBar.high, liveTick.p),
          low: Math.min(lastBar.low, liveTick.p),
        };
        seriesRef.current.update(updatedBar);
        lastBarRef.current = updatedBar;

        if (volumeSeriesRef.current) {
          volumeSeriesRef.current.update({
            time: lastBar.time as Time,
            value: (lastBar.value || 0) + liveTick.s,
            color: updatedBar.close >= updatedBar.open ? "rgba(16, 185, 129, 0.2)" : "rgba(244, 63, 94, 0.2)"
          });
        }
      }
    }
  }, [liveTick, loading]);

  // 1. Chart Instance Initialization (Once)
  useEffect(() => {
    if (!chartContainerRef.current) return;
    
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.6)",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      crosshair: {
        mode: 0,
        vertLine: { color: 'rgba(56, 189, 248, 0.5)', width: 1, style: 3 },
        horzLine: { color: 'rgba(56, 189, 248, 0.5)', width: 1, style: 3 },
      },
      autoSize: true,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "rgba(16, 185, 129, 0.8)",
      downColor: "rgba(244, 63, 94, 0.8)",
      borderVisible: false,
      wickUpColor: "rgba(16, 185, 129, 1)",
      wickDownColor: "rgba(244, 63, 94, 1)",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(56, 189, 248, 0.2)",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    
    volumeSeries.priceScale().applyOptions({
      visible: false,
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // 2. Data Fetching (On symbol/days/refreshKey change)
  useEffect(() => {
    if (!seriesRef.current || !volumeSeriesRef.current || !chartRef.current) return;

    // Clear stale ref immediately when symbol/days changes (prevents ghost live-tick updates)
    lastBarRef.current = null;
    intervalSecondsRef.current = days <= 1 ? 60 : 86400;

    const loadData = async (isRefreshed: boolean = false) => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchAssetHistory(symbol, days, isRefreshed);
        if (response && response.data && response.data.length > 0) {
          const data = response.data;
          // For 1-day view, ALWAYS treat as 1-minute regardless of what backend says
          // This prevents DB daily-candle fallback from corrupting the live-tick update logic
          const backendInterval = response.interval_seconds || 86400;
          intervalSecondsRef.current = days <= 1 ? 60 : backendInterval;

          const getTs = (t: string | number) => typeof t === 'number' ? t : Math.floor(new Date(t).getTime() / 1000);
          const sorted = [...data].sort((a, b) => getTs(a.time) - getTs(b.time));
          
          seriesRef.current?.setData(sorted as any);
          lastBarRef.current = sorted[sorted.length - 1];
          
          const volData = sorted.map(d => ({
            time: d.time as Time,
            value: d.value,
            color: d.close >= d.open ? "rgba(16, 185, 129, 0.2)" : "rgba(244, 63, 94, 0.2)"
          }));
          volumeSeriesRef.current?.setData(volData);
          chartRef.current?.timeScale().fitContent();

          // Force immediate sync with live tick if available (Prevents stale history vs StatCard mismatch)
          if (liveTick && seriesRef.current && lastBarRef.current) {
            const isDaily = intervalSecondsRef.current >= 86400;
            const normalizedTickTime = Math.floor(Math.floor(liveTick.t / 1000) / intervalSecondsRef.current) * intervalSecondsRef.current;
            const tickDate = isDaily ? new Date(normalizedTickTime * 1000).toISOString().split('T')[0] : (normalizedTickTime as UTCTimestamp);
            
            seriesRef.current.update({
              time: tickDate as Time,
              open: lastBarRef.current.open,
              high: Math.max(lastBarRef.current.high, liveTick.p),
              low: Math.min(lastBarRef.current.low, liveTick.p),
              close: liveTick.p
            });
          }
        } else {
          setError(`No history for ${symbol}`);
        }
      } catch (e: any) {
        setError(e.message || "History error");
      } finally {
        setLoading(false);
      }
    };

    loadData(refreshKey > 0);
  }, [symbol, days, refreshKey]);

  return (
    <div className="relative flex-1 w-full h-full min-h-[250px]">

      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
          <p className="text-steel font-mono text-sm tracking-wider uppercase animate-pulse">Loading Market Data...</p>
        </div>
      )}

      {error && !loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/60 rounded-xl px-6 text-center">
          <TrendingUp className="w-10 h-10 text-red-400 mb-4 opacity-70" />
          <p className="text-marble font-medium mb-2">Data Unavailable</p>
          <p className="text-steel text-sm max-w-sm">{error}</p>
        </div>
      )}

      <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
    </div>
  );
}
