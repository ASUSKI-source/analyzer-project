"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries } from "lightweight-charts";
import { fetchAssetHistory } from "@/services/api_client";
import { TrendingUp, RefreshCw } from "lucide-react";

export function ChartWidget({ symbol = "AAPL", realtimePrice, days = 365 }: { symbol?: string; realtimePrice?: number; days?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const lastUpdateRef = useRef<number | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Handle Real-time point updates
  useEffect(() => {
    if (seriesRef.current && realtimePrice && !loading) {
      const now = new Date();
      const timeStr = now.toISOString().split('T')[0];
      
      // Update the last candle
      // In a real app we'd fetch the exact candle, but for auto-refreshing 
      // the UX, we update the 'close' of the latest day.
      const lastBar = (seriesRef.current as any).data && (seriesRef.current as any).data.length > 0 
        ? (seriesRef.current as any).data[(seriesRef.current as any).data.length - 1] 
        : null;

      if (lastBar) {
        seriesRef.current.update({
          ...lastBar,
          close: realtimePrice,
          high: Math.max(lastBar.high, realtimePrice),
          low: Math.min(lastBar.low, realtimePrice),
        });
      }
    }
  }, [realtimePrice, loading]);

  useEffect(() => {
    // ... Initialize Chart code ...
    if (!chartContainerRef.current) return;
    
    // We want the chart to blend perfectly with our glassmorphism.
    // By using 'transparent' layout, it lets the background video bleed through the chart lines.
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
        mode: 0, // Normal crosshair
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
      autoSize: true, // Will inherit dimensions from flex parent
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "rgba(16, 185, 129, 0.8)", // success green
      downColor: "rgba(244, 63, 94, 0.8)", // danger red
      borderVisible: false,
      wickUpColor: "rgba(16, 185, 129, 1)",
      wickDownColor: "rgba(244, 63, 94, 1)",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(56, 189, 248, 0.2)",
      priceFormat: {
        type: "volume",
      },
      priceScaleId: "", // set as an overlay
    });
    
    // Position the volume chart at the bottom 20%
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchAssetHistory(symbol, days);
        if (data && data.length > 0) {
          // lightweight-charts requires data to be sorted strictly ascending by time
          const sorted = [...data].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
          
          candleSeries.setData(sorted as any);
          
          // Map volume data
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

    loadData();

    // Cleanup when component unmounts
    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
  }, [symbol, days]);

  return (
    <div className="relative flex-1 w-full h-full min-h-[250px]">
      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
          <p className="text-steel font-mono text-sm tracking-wider uppercase animate-pulse">Loading Market Data...</p>
        </div>
      )}

      {/* Error Overlay */}
      {error && !loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/60 rounded-xl px-6 text-center">
          <TrendingUp className="w-10 h-10 text-red-400 mb-4 opacity-70" />
          <p className="text-marble font-medium mb-2">Data Unavailable</p>
          <p className="text-steel text-sm max-w-sm">{error}</p>
        </div>
      )}

      {/* The actual chart container */}
      <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
    </div>
  );
}
