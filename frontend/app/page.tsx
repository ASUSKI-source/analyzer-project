"use client";

import React, { useState, useEffect, useCallback } from "react";
import { ArrowUpRight, ArrowDownRight, Clock, RefreshCw, X, Trash2 } from "lucide-react";
import { ChartWidget } from "@/components/features/ChartWidget";
import { SparklineWidget } from "@/components/features/SparklineWidget";
import { useDashboardPulse, MarketQuote } from "@/hooks/useDashboardPulse";
import { useAuth } from "@/contexts/AuthContext";
import { LandingAuth } from "@/components/auth/LandingAuth";
import { API_BASE_URL } from "@/services/api_client";
import { useWatchlist } from "@/hooks/useWatchlist";

export default function Home() {
  const { data, loading, refreshing, lastUpdated, error } = useDashboardPulse();
  const { user, isGuest, loading: authLoading, updateUser } = useAuth();
  const { symbols: userSymbols, addSymbol, removeSymbol } = useWatchlist();
  const [customPrices, setCustomPrices] = useState<MarketQuote[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<string>("BTC");
  const [chartDays, setChartDays] = useState<number>(365);

  const ytdDays = React.useMemo(() => {
    const now = new Date();
    const startOfYear = new Date(now.getFullYear(), 0, 1);
    return Math.max(1, Math.floor((now.getTime() - startOfYear.getTime()) / (1000 * 60 * 60 * 24)));
  }, []);

  // Fetch real prices for user's custom watchlist symbols
  const fetchCustomPrices = useCallback(async () => {
    if (userSymbols.length === 0) {
      setCustomPrices([]);
      return;
    }
    try {
      const symbolStr = userSymbols.map(s => s.symbol).join(",");
      const res = await fetch(`${API_BASE_URL}/market/prices?symbols=${symbolStr}`);
      if (res.ok) {
        const prices: MarketQuote[] = await res.json();
        setCustomPrices(prices);
      }
    } catch (e) {
      console.error("Failed to fetch custom watchlist prices", e);
    }
  }, [userSymbols]);

  // Initial fetch + poll every 8s (aligned with pulse)
  useEffect(() => {
    fetchCustomPrices();
    const interval = setInterval(fetchCustomPrices, 10000); // 10s interval
    return () => clearInterval(interval);
  }, [fetchCustomPrices]);

  // Build the final watchlist from strictly user-added symbols
  const watchlistItems = React.useMemo(() => {
    if (userSymbols.length === 0) return [];

    // Create a price lookup from custom prices
    const customPriceMap = new Map(customPrices.map(p => [p.symbol, p]));
    
    // User's symbols with real prices
    return userSymbols.map(s => 
      customPriceMap.get(s.symbol) || { symbol: s.symbol, price: 0, changePercent: 0 }
    );
  }, [userSymbols, customPrices]);
  
  if (authLoading) {
     return <div className="min-h-[70vh] flex items-center justify-center">
       <RefreshCw className="w-8 h-8 animate-spin text-blue-500/50" />
     </div>;
  }
  
  if (!user && !isGuest) {
     return <LandingAuth />;
  }

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-1000">
      
      {/* Page Header */}
      <div className="flex flex-col gap-2 relative">
        <h1 className="text-3xl font-bold tracking-tight text-marble">Market Overview</h1>
        <p className="text-steel flex items-center gap-2 text-sm">
          <Clock className="w-4 h-4" /> Market Open • 
          <span className="flex items-center gap-1.5 ml-1">
            <span className="relative flex h-2 w-2">
              <span className={`absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75 ${refreshing ? 'animate-ping' : ''}`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${refreshing ? 'bg-blue-500' : 'bg-blue-500/50'}`}></span>
            </span>
            Live Data Sync {lastUpdated && <span className="text-[10px] opacity-50 ml-1">at {lastUpdated.toLocaleTimeString()}</span>}
          </span>
          {(loading || refreshing) && <RefreshCw className="w-3 h-3 animate-spin text-blue-400 ml-2" />}
        </p>
      </div>

      {error ? (
        <div className="w-full p-4 rounded-xl truly-glass border border-red-500/30 bg-red-500/10 text-red-400">
          Failed to load live market data: {error}. Are your backend and Redis servers running?
        </div>
      ) : null}

      {/* Main Grid View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Market Overview Hero (Wider Column) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Stats Row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {data?.market_overview ? (
              data.market_overview.map((item) => (
                  <StatCard 
                    key={item.symbol} 
                    title={item.symbol} 
                    rawPrice={item.price}
                    value={item.price > 1000 ? `$${item.price.toLocaleString(undefined, {minimumFractionDigits: 2})}` : `$${item.price.toFixed(item.price < 5 ? 4 : 2)}`}
                    change={item.price > 0 ? `${item.changePercent > 0 ? '+' : ''}${item.changePercent.toFixed(2)}%` : '—'}
                    isPositive={item.changePercent >= 0}
                    onClick={() => setSelectedAsset(item.symbol)}
                    isSelected={selectedAsset === item.symbol}
                  />
                ))
            ) : (
              // Loading placeholders
              Array.from({length: 4}).map((_, i) => (
                <div key={i} className="true-glass rounded-xl p-4 h-24 animate-pulse bg-white/5" />
              ))
            )}
          </div>

          {/* Main Chart Widget */}
          <div className="true-glass rounded-2xl p-6 min-h-[500px] flex flex-col relative overflow-hidden group/chart">
            <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover/chart:opacity-100 transition-opacity duration-1000" />
            
            <div className="flex items-center justify-between mb-6 relative">
              <h2 className="text-lg font-semibold text-marble flex items-center gap-3">
                Market Momentum: {selectedAsset}
                <div className="flex items-center gap-2">
                  <PriceBubble 
                    symbol={selectedAsset} 
                    price={
                      data?.market_overview?.find(m => m.symbol === selectedAsset)?.price || 
                      customPrices.find(p => p.symbol === selectedAsset)?.price || 
                      0
                    } 
                  />
                  {selectedAsset === 'BTC' && data?.sentiment && (
                    <span className={`whitespace-nowrap flex-shrink-0 text-[10px] px-2 py-0.5 rounded-full border font-bold ${data.sentiment.sentiment_score >= 0 ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                       AI: {data.sentiment.sentiment_score > 0 ? 'BULLISH' : 'BEARISH'}
                    </span>

                  )}
                </div>
              </h2>
              <div className="flex gap-2 p-1 bg-black/40 rounded-xl border border-white/5 shadow-inner overflow-x-auto no-scrollbar">
                <FilterButton active={chartDays === 1} onClick={() => setChartDays(1)}>1D</FilterButton>
                <FilterButton active={chartDays === 7} onClick={() => setChartDays(7)}>1W</FilterButton>
                <FilterButton active={chartDays === 30} onClick={() => setChartDays(30)}>1M</FilterButton>
                <FilterButton active={chartDays === 180} onClick={() => setChartDays(180)}>6M</FilterButton>
                <FilterButton active={chartDays === ytdDays} onClick={() => setChartDays(ytdDays)}>YTD</FilterButton>
                <FilterButton active={chartDays === 365} onClick={() => setChartDays(365)}>1Y</FilterButton>
                <FilterButton active={chartDays === 1825} onClick={() => setChartDays(1825)}>5Y</FilterButton>
              </div>
            </div>
            {/* Live Chart Canvas */}
            <div className="flex-1 rounded-xl bg-black/20 border border-white/5 flex items-center justify-center shadow-inner relative overflow-hidden group-hover/chart:border-white/10 transition-colors p-2">
               <ChartWidget 
                 symbol={selectedAsset} 
                 days={chartDays}
                 realtimePrice={
                   data?.market_overview?.find(m => m.symbol === selectedAsset)?.price || 
                   customPrices.find(p => p.symbol === selectedAsset)?.price
                 } 
               />
            </div>
          </div>
        </div>

        {/* Watchlist Sidebar (Narrow Column) */}
        <div className="space-y-6">
          <div className="true-glass rounded-2xl p-6 min-h-[500px] relative overflow-hidden group/watchlist">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-50" />
            
            <div className="flex items-center justify-between mb-6 relative">
              <h2 className="text-lg font-semibold text-marble flex items-center gap-2">
                Watchlist
                <span className={`flex h-2 w-2 rounded-full ${loading ? 'bg-steel animate-pulse' : 'bg-blue-500 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.8)]'}`}></span>
              </h2>
              <button className="text-xs tracking-wider uppercase font-semibold text-blue-400 hover:text-blue-300 hover:tracking-widest transition-all">
                View All
              </button>
            </div>
            
            <div className="space-y-2.5 relative">
              {watchlistItems.length > 0 ? (
                watchlistItems.map(item => (
                  <WatchlistItem 
                    key={item.symbol}
                    symbol={item.symbol} 
                    name=""
                    rawPrice={item.price}
                    price={
                      item.price === 0 ? '—' :
                      item.price > 1000 ? `$${item.price.toLocaleString(undefined, {minimumFractionDigits: 2})}` : 
                      item.price < 5 ? `$${item.price.toFixed(4)}` :
                      `$${item.price.toFixed(2)}`
                    } 
                    change={item.price > 0 ? `${item.changePercent > 0 ? '+' : ''}${item.changePercent.toFixed(2)}%` : '—'} 
                    isPositive={item.changePercent >= 0} 
                    onClick={() => setSelectedAsset(item.symbol)}
                    isSelected={selectedAsset === item.symbol}
                    onRemove={() => removeSymbol(item.symbol)}
                  />
                ))
              ) : loading ? (
                Array.from({length: 5}).map((_, i) => (
                  <div key={i} className="h-16 rounded-xl bg-black/20 animate-pulse border border-white/5" />
                ))
              ) : (
                <p className="text-sm text-steel text-center py-8">Search and add symbols above</p>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

function StatCard({ title, value, change, isPositive, rawPrice, onClick, isSelected }: { title: string, value: string, change: string, isPositive: boolean, rawPrice: number, onClick?: () => void, isSelected?: boolean }) {
  const [isFlashActive, setIsFlashActive] = useState(false);
  // Initialize to null so the first real data arrival triggers a pulse
  const prevValue = React.useRef<number | null>(null);

  useEffect(() => {
    if (rawPrice > 0 && prevValue.current !== rawPrice) {
      setIsFlashActive(true);
      const timer = setTimeout(() => setIsFlashActive(false), 800);
      prevValue.current = rawPrice;
      return () => clearTimeout(timer);
    }
  }, [rawPrice]);

  return (
    <div 
      onClick={onClick}
      className={`true-glass rounded-xl p-4 transition-all hover:-translate-y-0.5 cursor-pointer relative overflow-hidden group 
        ${isFlashActive ? 'ring-1 ring-blue-500/30' : ''} 
        ${isSelected ? 'bg-white/10 ring-1 ring-white/20' : 'hover:bg-white/5'}
      `}
    >
      <div className="absolute inset-0 bg-gradient-to-tr from-white/0 via-white/5 to-white/0 opacity-0 group-hover:opacity-100 transition-opacity -translate-x-full group-hover:translate-x-full duration-1000 ease-in-out z-0" />
      
      {/* Dynamic Mini-Chart Sparkline */}
      <div className="absolute inset-x-0 bottom-0 top-6 opacity-30 group-hover:opacity-60 transition-opacity z-0 pointer-events-none px-2 pb-2">
        <SparklineWidget symbol={title} isPositive={isPositive} />
      </div>

      <div className="relative z-10 pointer-events-none">
        <p className="text-xs text-steel tracking-wider mb-2 font-mono uppercase">{title}</p>
        <p className={`text-xl font-bold mb-1 transition-all duration-300 ${isFlashActive ? 'text-blue-400 scale-[1.02]' : 'text-marble'}`}>
          {value}
        </p>
        <div className={`flex items-center gap-1 text-sm font-medium ${isPositive ? "text-positive" : "text-negative"}`}>
          {isPositive ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
          {change}
        </div>
      </div>
    </div>
  )
}

function WatchlistItem({ symbol, name, price, change, isPositive, rawPrice, onClick, isSelected, onRemove }: { symbol: string, name: string, price: string, change: string, isPositive: boolean, rawPrice: number, onClick?: () => void, isSelected?: boolean, onRemove?: () => void }) {
  const [sentiment, setSentiment] = React.useState<{ score: number; topics: string[] } | null>(null);
  const [isFlashActive, setIsFlashActive] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  // Initialize to null so the first real data arrival triggers a pulse
  const prevPrice = React.useRef<number | null>(null);
  
  React.useEffect(() => {
    if (rawPrice > 0 && prevPrice.current !== rawPrice) {
      setIsFlashActive(true);
      const timer = setTimeout(() => setIsFlashActive(false), 800);
      prevPrice.current = rawPrice;
      return () => clearTimeout(timer);
    }
  }, [rawPrice]);

  React.useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/market/assets/${symbol}/sentiment`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && !cancelled) {
          setSentiment({ score: data.sentiment_score, topics: data.trending_topics });
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [symbol]);

  if (isRemoving) return null;

  return (
    <div 
      onClick={onClick}
      className={`flex items-center justify-between p-3 rounded-xl hover:bg-white/10 transition-all cursor-pointer group border shadow-[inset_0_1px_1px_rgba(0,0,0,0.5)] hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] relative overflow-hidden
        ${isSelected ? 'bg-white/10 border-white/20 ring-1 ring-white/10' : 'bg-black/20 border-white/5'}
      `}
    >
      {onRemove && (
        <button 
          onClick={(e) => {
            e.stopPropagation();
            setIsRemoving(true);
            onRemove();
          }}
          className="absolute right-2 top-2 z-20 p-1.5 rounded-lg bg-red-500/10 text-red-500 opacity-0 group-hover:opacity-100 transition-all hover:bg-red-500 hover:text-white border border-red-500/20 shadow-lg"
          title="Remove from watchlist"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-transparent group-hover:bg-blue-500/50 transition-colors z-10" />
      
      <div className="flex flex-col gap-1.5 pl-2 z-10 w-2/5">
        <div className="flex flex-col items-start xl:flex-row xl:items-center gap-2">
          <span className="font-bold text-marble group-hover:text-blue-400 transition-colors font-mono tracking-tight">{symbol}</span>
          {sentiment && (
            <span className={`whitespace-nowrap flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${sentiment.score >= 0 ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}
              title={`AI Sentiment: ${sentiment.score > 0 ? '+' : ''}${sentiment.score.toFixed(2)} | Topics: ${sentiment.topics.join(', ')}`}
            >
              {sentiment.score >= 0 ? '↑' : '↓'} {sentiment.score >= 0 ? 'Bullish' : 'Bearish'}
            </span>
          )}
        </div>
        {name && <span className="text-xs text-steel truncate max-w-[120px]">{name}</span>}
      </div>

      {/* Dynamic Mini-Chart Sparkline */}
      <div className="absolute top-1 bottom-1 left-[40%] right-1/4 opacity-40 group-hover:opacity-100 px-2 pointer-events-none">
         <SparklineWidget symbol={symbol} isPositive={isPositive} />
      </div>

      <div className="flex flex-col items-end gap-1 z-10 w-1/4 text-right">
        <span className={`font-mono font-bold transition-all duration-300 ${isFlashActive ? 'text-blue-400 scale-105' : 'text-marble'}`}>
          {price}
        </span>
        <span className={`text-xs font-medium ${isPositive ? "text-positive" : "text-negative"}`}>
          {change}
        </span>
      </div>
    </div>
  )
}

function PriceBubble({ symbol, price }: { symbol: string, price: number }) {
  const [isFlashActive, setIsFlashActive] = useState(false);
  const prevPrice = React.useRef<number | null>(null);

  useEffect(() => {
    if (price > 0 && prevPrice.current !== price) {
      setIsFlashActive(true);
      const timer = setTimeout(() => setIsFlashActive(false), 800);
      prevPrice.current = price;
      return () => clearTimeout(timer);
    }
  }, [price]);

  return (
    <div className={`px-3 py-1 rounded-full border transition-all duration-300 font-mono text-xs font-bold ${isFlashActive ? 'bg-blue-500/20 border-blue-400/50 text-blue-400 scale-110' : 'bg-white/5 border-white/10 text-marble'}`}>
      ${price > 0 ? price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
    </div>
  );
}

function FilterButton({ children, active, onClick }: { children: React.ReactNode, active?: boolean, onClick?: () => void }) {
  return (
    <button onClick={onClick} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${active ? "bg-white/15 text-marble shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)] border border-white/10" : "text-steel hover:text-marble hover:bg-white/5 border border-transparent"}`}>
      {children}
    </button>
  )
}
