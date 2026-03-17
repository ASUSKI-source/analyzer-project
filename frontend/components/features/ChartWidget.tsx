"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, UTCTimestamp } from "lightweight-charts";
import { fetchAssetHistory } from "@/services/api_client";
import { TrendingUp, RefreshCw } from "lucide-react";
import { useLiveTick } from "./LivePriceProvider";

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
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const intervalSecondsRef = useRef<number>(86400);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Handle Real-time point updates
  useEffect(() => {
    if (seriesRef.current && liveTick && !loading) {
      const isDaily = intervalSecondsRef.current >= 86400;
      const interval = intervalSecondsRef.current;
      
      // Get the last data point from the series
      // Note: we can't easily get 'data' from seriesRef.current in standard types,
      // but 'update' handled it. However, to roll, we need to KNOW the last bar's time.
      // We'll track the last bar time in a ref to be safe.
      
      const lastBar = (seriesRef.current as any)._lastBar; 
      // Note: Hacky, but lightweight-charts doesn't expose public 'data' getter on series.
      // Better way: Track lastBar in a Ref.

      if (!lastBar) return;

      const tickTime = Math.floor(liveTick.t / 1000);
      const lastTime = typeof lastBar.time === 'number' ? lastBar.time : new Date(lastBar.time).getTime() / 1000;
      
      const isNewBar = tickTime >= lastTime + interval;

      if (isNewBar) {
        // Roll to a new bar
        const newTime = isDaily 
          ? new Date(tickTime * 1000).toISOString().split('T')[0]
          : Math.floor(tickTime / interval) * interval;
          
        const newBar = {
          time: newTime as Time,
          open: liveTick.p,
          high: liveTick.p,
          low: liveTick.p,
          close: liveTick.p,
        };
        seriesRef.current.update(newBar);
        (seriesRef.current as any)._lastBar = newBar;

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
        (seriesRef.current as any)._lastBar = updatedBar;

        if (volumeSeriesRef.current) {
          volumeSeriesRef.current.update({
            ...lastBar,
            time: lastBar.time as Time,
            value: (lastBar.value || 0) + liveTick.s,
          });
        }
      }
    }
  }, [liveTick, loading]);

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
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      crosshair: {
        mode: 0,
        vertLine: {
            color: 'rgba(56, 189, 248, 0.5)',
            width: 1,
            style: 3,
        },
        horzLine: {
            color: 'rgba(56, 189, 248, 0.5)',
            width: 1,
            style: 3,
        },
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
      priceFormat: {
        type: "volume",
      },
      priceScaleId: "",
    });
    
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const loadData = async (isRefreshed: boolean = false) => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchAssetHistory(symbol, days, isRefreshed);
        if (response && response.data && response.data.length > 0) {
          const data = response.data;
          intervalSecondsRef.current = response.interval_seconds || 86400;

          const sorted = [...data].sort((a, b) => {
            const timeA = typeof a.time === 'number' ? a.time : new Date(a.time).getTime();
            const timeB = typeof b.time === 'number' ? b.time : new Date(b.time).getTime();
            return timeA - timeB;
          });
          
          candleSeries.setData(sorted as any);
          
          // Store the last bar for live updates
          (candleSeries as any)._lastBar = sorted[sorted.length - 1];
          
          const volData = sorted.map(d => ({
            time: d.time as Time,
            value: d.value,
            color: d.close >= d.open ? "rgba(16, 185, 129, 0.2)" : "rgba(244, 63, 94, 0.2)"
          }));
          volumeSeries.setData(volData);
          
          chart.timeScale().fitContent();
        } else {
            setError(`No data found for ${symbol}. (Did you run the backend sync?)`);
        }
      } catch (e: any) {
        setError(e.message || "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };

    loadData(refreshKey > 0);

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
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
