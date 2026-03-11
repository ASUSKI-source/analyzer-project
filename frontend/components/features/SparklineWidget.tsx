"use client";

import { useEffect, useState } from "react";
import { fetchAssetHistory } from "@/services/api_client";

export function SparklineWidget({ symbol, isPositive }: { symbol: string; isPositive: boolean }) {
  const [data, setData] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      setLoading(true);
      try {
        const historyData = await fetchAssetHistory(symbol, 1);
        if (historyData && historyData.length > 0) {
          const sorted = [...historyData].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
          const prices = sorted.map(d => d.close);
          if (mounted) setData(prices);
        }
      } catch (e) {
        // Silently fail if history unavailable
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadData();

    return () => { mounted = false; };
  }, [symbol]);

  if (loading) {
    return (
      <div className="w-full h-full min-h-[30px] flex items-center justify-center opacity-70">
        <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden animate-pulse" />
      </div>
    );
  }

  if (data.length < 2) {
    return <div className="w-full h-full min-h-[30px]" />;
  }

  // Calculate SVG ViewBox and Path
  const width = 100;
  const height = 30;
  const padding = 2; // Keep line from touching edges

  const minPrice = Math.min(...data);
  const maxPrice = Math.max(...data);
  const range = maxPrice - minPrice || 1; // avoid div by zero

  const points = data.map((price, i) => {
    const x = (i / (data.length - 1)) * width;
    
    // Y is inverted in SVG (0 is top)
    const normalizedY = (price - minPrice) / range;
    const y = padding + ((1 - normalizedY) * (height - (padding * 2)));
    
    return `${i === 0 ? 'M' : 'L'} ${x},${y}`;
  }).join(' ');

  const strokeColor = isPositive ? "rgba(16, 185, 129, 0.8)" : "rgba(244, 63, 94, 0.8)";
  const fillColor = isPositive ? "rgba(16, 185, 129, 0.1)" : "rgba(244, 63, 94, 0.1)";

  // Create absolute bottom corners for the gradient fill path
  const fillPath = `${points} L ${width},${height} L 0,${height} Z`;

  return (
    <div className="relative w-full h-full min-h-[30px] opacity-70 group-hover:opacity-100 transition-opacity flex items-center">
      <svg 
        viewBox={`0 0 ${width} ${height}`} 
        className="w-full h-full overflow-visible"
        preserveAspectRatio="none"
      >
        <path
          d={fillPath}
          fill={fillColor}
          stroke="none"
        />
        <path
          d={points}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="drop-shadow-sm"
        />
      </svg>
    </div>
  );
}
