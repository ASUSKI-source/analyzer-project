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
      visible: false,
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

          // Helper to get numeric timestamp for sorting
          const getTs = (t: string | number) => typeof t === 'number' ? t : Math.floor(new Date(t).getTime() / 1000);

          const sorted = [...data].sort((a, b) => getTs(a.time) - getTs(b.time));
          
          candleSeries.setData(sorted as any);
          
          // Store the last bar for live updates
          lastBarRef.current = sorted[sorted.length - 1];
          
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
      {/* Live Indicator Overlay */}
      {!loading && !error && (
        <div className="absolute top-4 right-4 z-20 flex flex-col items-end gap-2">
          {/* Socket Status */}
          <div className="flex items-center gap-2 px-3 py-1 bg-black/40 backdrop-blur-md rounded-full border border-white/5 ring-1 ring-white/5 shadow-xl transition-all duration-300">
            <div className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isSocketConnected ? 'bg-blue-400' : 'bg-amber-400'} opacity-75`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isSocketConnected ? 'bg-blue-500' : 'bg-amber-500'}`}></span>
            </div>
            <span className="text-[10px] font-bold tracking-widest uppercase text-marble/60">
              {isSocketConnected ? 'Socket: Connected' : 'Socket: Connecting...'}
            </span>
          </div>

          {/* Data Stream Status */}
          <div className="flex items-center gap-2 px-3 py-1 bg-black/40 backdrop-blur-md rounded-full border border-white/5 ring-1 ring-white/5 shadow-xl transition-all duration-300">
            <div className="relative flex h-2 w-2">
              {liveTick && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              )}
              <span className={`relative inline-flex rounded-full h-2 w-2 ${liveTick ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
            </div>
            <span className="text-[10px] font-bold tracking-widest uppercase text-marble/60">
              {liveTick ? 'Stream: Live' : 'Stream: Waiting'}
            </span>
          </div>
        </div>
      )}

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
