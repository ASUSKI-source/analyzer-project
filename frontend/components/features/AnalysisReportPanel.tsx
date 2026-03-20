"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Gauge,
  Globe,
  Info,
  Layers,
  Minus,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import { API_BASE_URL } from "@/services/api_client";

interface AssetAnalysis {
  symbol: string;
  verdict: string;
  timeframe_signals: {
    tactical_1h: string;
    trend_1d: string;
    strategic_1w: string;
  };
  key_metrics: {
    rsi_daily?: number;
    pe_ratio?: number;
    eps?: number;
    macd_signal?: string;
    ema_signal?: string;
  };
  analysis_bullets: string[];
  catalyst: string;
  action_note: string;
}

interface AIReport {
  market_summary: string;
  watchlist_health: string;
  risk_level: string;
  tactical_outlook: string;
  strategic_horizon: string;
  assets: AssetAnalysis[];
  overall_insight: string;
  generated_at?: string;
  from_cache?: boolean;
  source_status?: string;
  _mock?: boolean;
  _served_last_good?: boolean;
  _fallback_reason?: string;
  cooldown_remaining?: number;
  error?: string;
}

interface AssetDeepAnalysis {
  symbol: string;
  technicals?: {
    rsi?: number;
    macd?: number;
    macd_signal?: number;
    sma_20?: number;
    sma_50?: number;
    sma_200?: number;
    ema_9?: number;
    ema_21?: number;
    vwap?: number;
    obv?: number;
    adx?: number;
    trend_signal?: string;
  };
  fundamentals?: {
    pe_ratio?: number;
    eps?: number;
    beta?: number;
    dividend_yield?: number;
    market_cap?: number;
    high_52week?: number;
    low_52week?: number;
    short_interest?: number;
    short_ratio?: number;
    shares_float?: number;
    free_float?: number;
  };
  sentiment?: {
    sentiment_score?: number;
    trending_topics?: string[];
  };
  institutional?: {
    shares_held?: number;
    institution_count?: number;
    top_holder?: string;
  };
  on_chain?: {
    fear_and_greed?: {
      value: string;
      value_classification: string;
    };
    futures_sentiment?: {
      long_short_ratio: number;
      open_interest: number;
      funding_rate?: number;
    };
  };
  last_updated?: string;
}

interface Props {
  symbols: string[];
  selectedSymbol?: string | null;
  onSelectAsset?: (symbol: string) => void;
}

type VerdictFilter = "ALL" | "BULLISH" | "BEARISH" | "NEUTRAL" | "CAUTION";
type SortKey = "symbol" | "verdict" | "h1" | "d1" | "w1" | "rsi" | "macd" | "ema" | "pe" | "beta" | "catalyst";

const HEALTH_COLORS: Record<string, string> = {
  STRONG: "text-green-300",
  MODERATE: "text-amber-300",
  WEAK: "text-red-300",
  MIXED: "text-blue-300",
};

const RISK_COLORS: Record<string, string> = {
  LOW: "text-green-300",
  MODERATE: "text-amber-300",
  HIGH: "text-red-300",
};

const VERDICT_STYLE: Record<string, { text: string; bg: string; icon: React.ReactNode }> = {
  BULLISH: {
    text: "text-green-300",
    bg: "bg-green-500/10 border-green-500/25",
    icon: <TrendingUp className="w-3.5 h-3.5" />,
  },
  BEARISH: {
    text: "text-red-300",
    bg: "bg-red-500/10 border-red-500/25",
    icon: <TrendingDown className="w-3.5 h-3.5" />,
  },
  NEUTRAL: {
    text: "text-slate-300",
    bg: "bg-white/5 border-white/15",
    icon: <Minus className="w-3.5 h-3.5" />,
  },
  CAUTION: {
    text: "text-amber-300",
    bg: "bg-amber-500/10 border-amber-500/25",
    icon: <AlertTriangle className="w-3.5 h-3.5" />,
  },
};

function fmt(v?: number, d = 2): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "-";
  return Number(v).toFixed(d);
}

function fmtCompact(v?: number): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "-";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(v);
}

function signalClass(signal?: string): string {
  if (!signal) return "text-slate-400";
  const normalized = signal.toLowerCase();
  if (normalized.startsWith("bull")) return "text-green-300";
  if (normalized.startsWith("bear")) return "text-red-300";
  return "text-slate-300";
}

export function AnalysisReportPanel({ symbols, selectedSymbol: externalSymbol, onSelectAsset }: Props) {
  const [report, setReport] = useState<AIReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshingDeep, setRefreshingDeep] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [assetDeepData, setAssetDeepData] = useState<Record<string, AssetDeepAnalysis>>({});
  const [assetDeepLoading, setAssetDeepLoading] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState<"signals" | "technicals" | "fundamentals" | "squeeze" | "macro">("signals");
  const loadedSymbolsRef = React.useRef<Set<string>>(new Set());
  const currentlyLoadingRef = React.useRef<Set<string>>(new Set());

  const fetchAssetDeep = useCallback(
    async (symbol: string): Promise<void> => {
      if (!symbol || loadedSymbolsRef.current.has(symbol) || currentlyLoadingRef.current.has(symbol)) return;
      
      const token = localStorage.getItem("token");
      if (!token) return;

      currentlyLoadingRef.current.add(symbol);
      setAssetDeepLoading((prev) => ({ ...prev, [symbol]: true }));
      try {
        const encodedSymbol = encodeURIComponent(symbol);
        const res = await fetch(`${API_BASE_URL}/market/assets/${encodedSymbol}/analysis`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
           console.error(`Deep analysis error for ${symbol}: ${res.status}`);
           return;
        }
        const data: AssetDeepAnalysis = await res.json();
        console.log(`Deep analysis data for ${symbol}:`, data);
        setAssetDeepData((prev) => ({ ...prev, [symbol]: data }));
        loadedSymbolsRef.current.add(symbol);
      } catch (err) {
        console.error(`Deep analysis fetch failed for ${symbol}:`, err);
        loadedSymbolsRef.current.delete(symbol); // Allow retry
      } finally {
        currentlyLoadingRef.current.delete(symbol);
        setAssetDeepLoading((prev) => ({ ...prev, [symbol]: false }));
      }
    },
    [], 
  );

  const pollJobUntilDone = useCallback(async (jobId: string): Promise<AIReport | null> => {
    const token = localStorage.getItem("token");
    for (let i = 0; i < 30; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const statusRes = await fetch(`${API_BASE_URL}/ai/watchlist-analysis/jobs/${jobId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const statusPayload = await statusRes.json();
      if (statusPayload?.status === "succeeded" && statusPayload?.result) {
        return statusPayload.result as AIReport;
      }
      if (statusPayload?.status === "failed") {
        throw new Error(statusPayload?.error || "Background analysis failed");
      }
    }
    throw new Error("Background analysis timed out");
  }, []);

  const requestDeepRefresh = useCallback(async (): Promise<void> => {
    const token = localStorage.getItem("token");
    if (!token || symbols.length === 0) return;

    setRefreshingDeep(true);
    try {
      const createRes = await fetch(`${API_BASE_URL}/ai/watchlist-analysis/jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ symbols, refresh: true, reason: "user_refresh" }),
      });

      const createPayload = await createRes.json();
      const jobId = createPayload?.job_id;
      if (!jobId) return;

      const finalReport = await pollJobUntilDone(jobId);
      if (finalReport) {
        setReport(finalReport);
        setSelectedSymbol(finalReport.assets?.[0]?.symbol || null);
      }
    } catch (e: any) {
      setError(e?.message || "Failed background refresh");
    } finally {
      setRefreshingDeep(false);
    }
  }, [pollJobUntilDone, symbols]);

  const fetchReport = useCallback(
    async (forceRefresh = false) => {
      if (symbols.length === 0) return;
      setLoading(true);
      setError(null);

      try {
        const symbolStr = symbols.join(",");
        const token = localStorage.getItem("token");
        const url = `${API_BASE_URL}/ai/watchlist-analysis?symbols=${symbolStr}`;
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const data: AIReport = await res.json();

        if (data.error && !data.assets?.length) {
          setError(data.error);
        } else {
          setReport(data);
          setSelectedSymbol(data.assets?.[0]?.symbol || null);
        }

        if (forceRefresh || data?._served_last_good || data?.source_status === "cache_hit") {
          await requestDeepRefresh();
        }
      } catch (e: any) {
        setError(e?.message || "Failed to generate analysis");
      } finally {
        setLoading(false);
      }
    },
    [requestDeepRefresh, symbols],
  );

  useEffect(() => {
    if (!selectedSymbol) return;
    fetchAssetDeep(selectedSymbol);
  }, [fetchAssetDeep, selectedSymbol]);

  const assets = report?.assets || [];

  const displayedAssets = useMemo(() => {
    const filtered = assets.filter((asset) => verdictFilter === "ALL" || asset.verdict === verdictFilter);
    const ranked = [...filtered].sort((a, b) => {
      const betaA = assetDeepData[a.symbol]?.fundamentals?.beta;
      const betaB = assetDeepData[b.symbol]?.fundamentals?.beta;
      const getSignal = (v?: string): number => {
        const s = (v || "").toLowerCase();
        if (s.startsWith("bull")) return 1;
        if (s.startsWith("bear")) return -1;
        return 0;
      };
      const scoreSignal = (x: AssetAnalysis, k: SortKey): number => {
        if (k === "h1") return getSignal(x.timeframe_signals?.tactical_1h);
        if (k === "d1") return getSignal(x.timeframe_signals?.trend_1d);
        return getSignal(x.timeframe_signals?.strategic_1w);
      };

      let cmp = 0;
      switch (sortKey) {
        case "symbol":
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case "verdict":
          cmp = a.verdict.localeCompare(b.verdict);
          break;
        case "h1":
        case "d1":
        case "w1":
          cmp = scoreSignal(a, sortKey) - scoreSignal(b, sortKey);
          break;
        case "rsi":
          cmp = (a.key_metrics?.rsi_daily ?? -999) - (b.key_metrics?.rsi_daily ?? -999);
          break;
        case "macd":
          cmp = (a.key_metrics?.macd_signal || "").localeCompare(b.key_metrics?.macd_signal || "");
          break;
        case "ema":
          cmp = (a.key_metrics?.ema_signal || "").localeCompare(b.key_metrics?.ema_signal || "");
          break;
        case "pe":
          cmp = (a.key_metrics?.pe_ratio ?? -999) - (b.key_metrics?.pe_ratio ?? -999);
          break;
        case "beta":
          cmp = (betaA ?? -999) - (betaB ?? -999);
          break;
        case "catalyst":
          cmp = (a.catalyst || "").localeCompare(b.catalyst || "");
          break;
        default:
          cmp = 0;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return ranked;
  }, [assetDeepData, assets, sortDir, sortKey, verdictFilter]);

  const selectedAsset = useMemo(() => {
    if (!selectedSymbol || !displayedAssets.length) return displayedAssets[0] || null;
    return displayedAssets.find((a) => a.symbol.toUpperCase() === selectedSymbol.toUpperCase()) || displayedAssets[0] || null;
  }, [displayedAssets, selectedSymbol]);

  const selectedDeep = assetDeepData[selectedSymbol?.toUpperCase() || selectedAsset?.symbol?.toUpperCase() || ""];
  const isDeepLoading = selectedSymbol ? assetDeepLoading[selectedSymbol.toUpperCase()] : false;

  // Sync internal selection with external prop
  useEffect(() => {
    if (externalSymbol && externalSymbol !== selectedSymbol) {
      if (displayedAssets.some(a => a.symbol === externalSymbol)) {
        setSelectedSymbol(externalSymbol);
        fetchAssetDeep(externalSymbol);
      }
    }
  }, [externalSymbol, displayedAssets, fetchAssetDeep, selectedSymbol]);

  useEffect(() => {
    if (!displayedAssets.length) {
      setSelectedSymbol(null);
      return;
    }
    if (!selectedSymbol || !displayedAssets.some((a) => a.symbol === selectedSymbol)) {
      const firstSym = displayedAssets[0].symbol;
      
      // If we have an external symbol from the dashboard (Stats/Watchlist), use that!
      if (externalSymbol && displayedAssets.some(a => a.symbol === externalSymbol)) {
        setSelectedSymbol(externalSymbol);
        fetchAssetDeep(externalSymbol);
      } else {
        // Otherwise, fallback to first in list
        setSelectedSymbol(firstSym);
        fetchAssetDeep(firstSym);
        // Only notify parent if we are truly forcing a new selection
        if (externalSymbol !== firstSym) {
          onSelectAsset?.(firstSym);
        }
      }
    }
  }, [displayedAssets, selectedSymbol, externalSymbol, onSelectAsset]);

  const coverageEstimate = useMemo(() => {
    if (!displayedAssets.length) return 0;
    let expected = 0;
    let available = 0;

    for (const asset of displayedAssets) {
      expected += 8;
      if (asset.timeframe_signals?.tactical_1h) available += 1;
      if (asset.timeframe_signals?.trend_1d) available += 1;
      if (asset.timeframe_signals?.strategic_1w) available += 1;
      if (asset.key_metrics?.rsi_daily !== undefined && asset.key_metrics?.rsi_daily !== null) available += 1;
      if (asset.key_metrics?.macd_signal) available += 1;
      if (asset.key_metrics?.pe_ratio !== undefined && asset.key_metrics?.pe_ratio !== null) available += 1;
      if (asset.analysis_bullets?.length) available += 1;
      if (asset.action_note) available += 1;
    }

    return Math.round((available / Math.max(expected, 1)) * 100);
  }, [displayedAssets]);

  // Pre-fetch top 3 symbols for speed
  useEffect(() => {
    if (symbols.length > 0) {
      symbols.slice(0, 3).forEach(sym => {
        fetchAssetDeep(sym);
      });
    }
  }, [fetchAssetDeep, symbols]);

  const toggleSort = (key: SortKey): void => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "symbol" ? "asc" : "desc");
  };

  const handleRowSelect = (symbol: string): void => {
    setSelectedSymbol(symbol);
    fetchAssetDeep(symbol);
    onSelectAsset?.(symbol);
  };

  const handleMatrixKeyNav = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (!displayedAssets.length || !selectedAsset) return;
    const idx = displayedAssets.findIndex((a) => a.symbol === selectedAsset.symbol);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = displayedAssets[Math.min(displayedAssets.length - 1, idx + 1)];
      if (next) handleRowSelect(next.symbol);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      const prev = displayedAssets[Math.max(0, idx - 1)];
      if (prev) handleRowSelect(prev.symbol);
    }
  };

  const sortGlyph = (key: SortKey): string => {
    if (sortKey !== key) return "↕";
    return sortDir === "asc" ? "↑" : "↓";
  };

  const sortButtonClass = (key: SortKey): string => {
    const isActive = sortKey === key;
    return isActive
      ? "inline-flex items-center gap-1 text-slate-100 hover:text-white transition"
      : "inline-flex items-center gap-1 text-slate-400 hover:text-white transition";
  };

  const resetView = (): void => {
    setVerdictFilter("ALL");
    setSortKey("symbol");
    setSortDir("asc");
  };

  if (!report && !loading) {
    return (
      <div className="true-glass rounded-2xl p-6 relative overflow-hidden">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm uppercase tracking-[0.15em] text-slate-300 font-semibold">Analysis Report</h3>
          <span className="text-[11px] text-slate-400">{symbols.length} assets</span>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">{error}</div>
        )}

        <div className="rounded-xl border border-white/10 bg-black/25 p-4">
          <p className="text-sm text-slate-200 mb-4">
            Build a concise institutional brief with multi-horizon technical and fundamental context.
          </p>
          <button
            onClick={() => fetchReport(false)}
            disabled={symbols.length === 0}
            className="inline-flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-2 text-xs font-semibold text-blue-300 transition hover:bg-blue-500/20 disabled:opacity-40"
          >
            <Sparkles className="w-4 h-4" />
            Run Analysis
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="true-glass rounded-2xl p-6 relative overflow-hidden">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm uppercase tracking-[0.15em] text-slate-300 font-semibold">Analysis Report</h3>
          <RefreshCw className="w-4 h-4 animate-spin text-blue-300" />
        </div>
        <div className="space-y-2">
          <div className="h-8 rounded bg-white/5 animate-pulse" />
          <div className="h-8 rounded bg-white/5 animate-pulse" />
          <div className="h-8 rounded bg-white/5 animate-pulse" />
          <div className="h-8 rounded bg-white/5 animate-pulse" />
        </div>
      </div>
    );
  }

  if (!report) return null;

  return (
    <div className="true-glass rounded-2xl overflow-hidden" id="ai-analysis-panel">
      {/* 1. Header & Executive Summary */}
      <div className="border-b border-white/10 bg-black/40 p-4 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-blue-400" />
              <h3 className="text-sm uppercase tracking-[0.2em] text-slate-100 font-bold">AI Analysis Brief</h3>
            </div>
            <p className="mt-1 text-[11px] text-slate-400 font-medium">Institutional-grade multi-layer intelligence</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex flex-col items-end">
              <span className="text-[10px] uppercase tracking-wider text-slate-500">Portfolio Health</span>
              <span className={`text-sm font-bold ${HEALTH_COLORS[report.watchlist_health] || "text-slate-200"}`}>
                {report.watchlist_health}
              </span>
            </div>
            <div className="h-8 w-px bg-white/10 mx-1" />
            <button
              onClick={() => fetchReport(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-white/10 transition active:scale-95"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshingDeep ? "animate-spin" : ""}`} />
              Re-run
            </button>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3">
            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Risk Profile</span>
            <div className={`flex items-center gap-1.5 font-bold ${RISK_COLORS[report.risk_level] || "text-slate-200"}`}>
              <Shield className="w-3.5 h-3.5" />
              {report.risk_level}
            </div>
          </div>
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3">
            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Coverage</span>
            <div className="text-slate-100 font-bold">{coverageEstimate}%</div>
          </div>
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3 hidden md:block">
            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Assets</span>
            <div className="text-slate-100 font-bold">{displayedAssets.length} <span className="text-slate-500 text-[10px] font-normal">Tracked</span></div>
          </div>
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3 hidden md:block">
            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Freshness</span>
            <div className="text-slate-100 font-bold">{report.generated_at ? new Date(report.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit'}) : "-"}</div>
          </div>
        </div>

        <div className="mt-4 p-4 rounded-xl border border-blue-500/10 bg-blue-500/5">
          <div className="flex gap-3">
            <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <p className="text-xs leading-relaxed text-slate-300 italic">"{report.market_summary}"</p>
          </div>
        </div>
      </div>

      {/* 2. Asset Selection Grid */}
      <div className="p-4 sm:p-6 bg-black/10">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4 overflow-x-auto no-scrollbar pb-1">
            {(["ALL", "BULLISH", "BEARISH", "NEUTRAL", "CAUTION"] as VerdictFilter[]).map((vf) => (
              <button
                key={vf}
                onClick={() => setVerdictFilter(vf)}
                className={`text-[10px] font-bold uppercase tracking-wider transition-all px-1 py-1 border-b-2 whitespace-nowrap ${
                  verdictFilter === vf
                    ? "text-blue-400 border-blue-400"
                    : "text-slate-500 border-transparent hover:text-slate-300"
                }`}
              >
                {vf}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 hidden sm:block">Sort by:</span>
            <select 
              className="bg-white/5 border border-white/10 rounded px-2 py-1 text-[10px] text-slate-300 outline-none"
              value={sortKey}
              onChange={(e) => toggleSort(e.target.value as SortKey)}
            >
              <option value="symbol">Symbol</option>
              <option value="verdict">Verdict</option>
              <option value="rsi">RSI</option>
              <option value="beta">Volatility</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {displayedAssets.map((asset) => {
            const style = VERDICT_STYLE[asset.verdict] || VERDICT_STYLE.NEUTRAL;
            const isSelected = selectedAsset?.symbol === asset.symbol;
            
            return (
              <button
                key={asset.symbol}
                onClick={() => handleRowSelect(asset.symbol)}
                className={`relative group text-left p-3 rounded-xl border transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl hover:shadow-blue-500/10 active:scale-[0.98] ${
                  isSelected 
                    ? "bg-white/10 border-blue-500/50 ring-1 ring-blue-500/20" 
                    : "bg-white/[0.03] border-white/10 hover:border-white/20 hover:bg-white/[0.05]"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-slate-100">{asset.symbol}</span>
                  <div className={`px-1.5 py-0.5 rounded text-[9px] font-bold flex items-center gap-1 ${style.bg} ${style.text}`}>
                    {style.icon}
                    {asset.verdict}
                  </div>
                </div>

                <div className="flex gap-1.5 mb-2">
                  {Object.entries(asset.timeframe_signals || {}).map(([tf, signal]) => (
                    <div 
                      key={tf} 
                      className={`h-1.5 flex-1 rounded-full ${
                        signal.toLowerCase().includes("bull") ? "bg-green-500/50" : 
                        signal.toLowerCase().includes("bear") ? "bg-red-500/50" : "bg-white/20"
                      }`}
                      title={`${tf.replace('strategic_','').replace('trend_','').replace('tactical_','')}: ${signal}`}
                    />
                  ))}
                </div>

                <div className="flex items-center justify-between items-end mt-3">
                  <div className="flex flex-col">
                    <span className="text-[9px] text-slate-500 uppercase font-bold">RSI</span>
                    <span className={`text-[11px] font-bold ${
                      (asset.key_metrics?.rsi_daily ?? 50) > 70 ? "text-red-400" :
                      (asset.key_metrics?.rsi_daily ?? 50) < 30 ? "text-green-400" : "text-slate-300"
                    }`}>
                      {fmt(asset.key_metrics?.rsi_daily, 0)}
                    </span>
                  </div>

                  <div className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <span className="text-[9px] text-slate-500 uppercase font-bold">P/E</span>
                      <span className="text-[11px] font-bold text-slate-300">
                        {fmt(asset.key_metrics?.pe_ratio, 1)}
                      </span>
                    </div>
                    <div className="flex flex-col items-center">
                      <span className="text-[9px] text-slate-500 uppercase font-bold">EPS</span>
                      <span className="text-[11px] font-bold text-slate-300">
                        {fmt(asset.key_metrics?.eps, 2)}
                      </span>
                    </div>
                  </div>

                  <ArrowRight className={`w-3.5 h-3.5 text-slate-600 transition-transform group-hover:translate-x-0.5 ${isSelected ? "text-blue-400" : ""}`} />
                </div>

                {isSelected && (
                  <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-8 h-1 bg-blue-500 rounded-full" />
                )}
              </button>
            );
          })}
        </div>
      </div>

        {/* 3. Detail Drawer (Multi-tab) */}
        {selectedAsset && (
          <div className="mt-8 border-t border-white/10 pt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex flex-col lg:flex-row gap-8">
              {/* Left: Summary & Tab Bar */}
              <div className="lg:w-1/3 space-y-6">
                <div>
                  <h4 className="text-2xl font-mono font-bold text-slate-100 mb-1">{selectedAsset.symbol}</h4>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 capitalize">Daily Momentum:</span>
                    <span className={`text-xs font-bold ${signalClass(selectedAsset.timeframe_signals?.trend_1d)}`}>
                      {selectedAsset.timeframe_signals?.trend_1d}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  {(["signals", "technicals", "fundamentals", "squeeze", "macro"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setActiveTab(t)}
                      className={`flex items-center justify-between p-3 rounded-xl transition-all ${
                        activeTab === t 
                          ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" 
                          : "text-slate-500 hover:bg-white/5 border border-transparent"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        {t === "signals" && <Sparkles className="w-4 h-4" />}
                        {t === "technicals" && <Activity className="w-4 h-4" />}
                        {t === "fundamentals" && <BarChart3 className="w-4 h-4" />}
                        {t === "squeeze" && <Zap className="w-4 h-4" />}
                        {t === "macro" && <Globe className="w-4 h-4" />}
                        <span className="text-xs font-bold uppercase tracking-wider">{t}</span>
                      </div>
                      <ArrowRight className={`w-3.5 h-3.5 opacity-0 -translate-x-2 transition-all ${activeTab === t ? "opacity-100 translate-x-0" : ""}`} />
                    </button>
                  ))}
                </div>

                <div className="p-4 rounded-xl bg-amber-500/[0.03] border border-amber-500/10">
                  <span className="text-[10px] uppercase text-amber-500 font-bold block mb-2">Tactical Action Note</span>
                  <p className="text-xs text-slate-300 leading-relaxed italic">
                    "{selectedAsset?.action_note || "No specific tactical action required at current levels."}"
                  </p>
                </div>
              </div>

              {/* Right: Tab Content */}
              <div className="lg:w-2/3 min-h-[300px] rounded-2xl bg-white/[0.02] border border-white/5 p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 blur-[100px] rounded-full -translate-y-1/2 translate-x-1/2" />
                
                {isDeepLoading && (
                  <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-300">
                    <div className="w-12 h-12 rounded-full border-2 border-blue-500/20 border-t-blue-500 animate-spin mb-4" />
                    <span className="text-[10px] uppercase tracking-[0.2em] text-blue-400 font-bold animate-pulse">
                      Assembling intelligence...
                    </span>
                  </div>
                )}

                {activeTab === "signals" && (
                  <div className="space-y-6 animate-in fade-in duration-300">
                    <div className="grid grid-cols-3 gap-4">
                      {Object.entries(selectedAsset?.timeframe_signals || {}).map(([tf, signal]) => (
                        <div key={tf} className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                          <span className="text-[9px] uppercase text-slate-500 font-bold block mb-1">
                            {tf.replace('strategic_','sm:').replace('trend_','dly:').replace('tactical_','hly:')}
                          </span>
                          <span className={`text-xs font-bold ${signalClass(signal)}`}>{signal}</span>
                        </div>
                      ))}
                    </div>
                    <div>
                      <h5 className="text-[10px] uppercase text-slate-500 font-bold mb-3 tracking-widest">AI Synthesis</h5>
                      <div className="space-y-2">
                        {(selectedAsset.analysis_bullets || []).map((b, i) => (
                          <div key={i} className="flex gap-3 text-xs text-slate-300 leading-relaxed">
                            <span className="text-blue-500 font-bold mt-1">/</span>
                            <span>{b}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "technicals" && (
                  <div className="space-y-6 animate-in fade-in duration-300">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-4">
                        <section>
                          <span className="text-[10px] uppercase text-slate-500 font-bold block mb-2">Relative Strength</span>
                          <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden flex">
                             <div 
                               className={`h-full transition-all duration-1000 ${
                                 (selectedDeep?.technicals?.rsi || 50) < 30 ? "bg-green-500" : 
                                 (selectedDeep?.technicals?.rsi || 50) > 70 ? "bg-red-500" : "bg-blue-500"
                               }`}
                               style={{ width: `${selectedDeep?.technicals?.rsi || 50}%` }}
                             />
                          </div>
                          <div className="flex justify-between mt-1 text-[10px] font-mono text-slate-500">
                            <span>0</span>
                            <span className="text-slate-300 font-bold">RSI: {fmt(selectedDeep?.technicals?.rsi, 1)}</span>
                            <span>100</span>
                          </div>
                        </section>
                        <section>
                          <span className="text-[10px] uppercase text-slate-500 font-bold block mb-2">MACD / EMA Context</span>
                          <div className="flex gap-2 text-[10px] font-mono">
                             <div className="flex-1 p-2 rounded-lg bg-white/5 border border-white/10 text-center">
                                <span className="text-slate-500 block">MACD</span>
                                <span className={signalClass(selectedDeep?.technicals?.trend_signal)}>
                                  {selectedDeep?.technicals?.macd || "-"}
                                </span>
                             </div>
                             <div className="flex-1 p-2 rounded-lg bg-white/5 border border-white/10 text-center">
                                <span className="text-slate-500 block">EMA</span>
                                <span className={signalClass(selectedDeep?.technicals?.trend_signal)}>
                                  {selectedDeep?.technicals?.ema_9 || "-"}
                                </span>
                             </div>
                          </div>
                        </section>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2 text-[10px]">
                         <div className="p-2 rounded-lg bg-white/5 flex justify-between">
                            <span className="text-slate-500">VWAP</span>
                            <span className="font-mono text-slate-200">{fmt(selectedDeep?.technicals?.vwap || selectedDeep?.technicals?.sma_20, 2)}</span>
                         </div>
                         <div className="p-2 rounded-lg bg-white/5 flex justify-between">
                            <span className="text-slate-500">OBV</span>
                            <span className="font-mono text-slate-200">{fmtCompact(selectedDeep?.technicals?.obv)}</span>
                         </div>
                         <div className="p-2 rounded-lg bg-white/5 flex justify-between">
                            <span className="text-slate-500">EMA 9/21</span>
                            <span className="font-mono text-slate-200">{fmt(selectedDeep?.technicals?.ema_9, 1)} / {fmt(selectedDeep?.technicals?.ema_21, 1)}</span>
                         </div>
                         <div className="p-2 rounded-lg bg-white/5 flex justify-between">
                            <span className="text-slate-500">SMA 50/200</span>
                            <span className="font-mono text-slate-200">{fmt(selectedDeep?.technicals?.sma_50, 0)} / {fmt(selectedDeep?.technicals?.sma_200, 0)}</span>
                         </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "fundamentals" && (
                  <div className="space-y-6 animate-in fade-in duration-300">
                     <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {[
                          { l: "Market Cap", v: fmtCompact(selectedDeep?.fundamentals?.market_cap) },
                          { l: "P/E Ratio", v: fmt(selectedDeep?.fundamentals?.pe_ratio, 2) },
                          { l: "EPS", v: fmt(selectedDeep?.fundamentals?.eps, 2) },
                          { l: "Beta", v: fmt(selectedDeep?.fundamentals?.beta, 2) },
                          { l: "Div Yield", v: `${fmt(selectedDeep?.fundamentals?.dividend_yield, 2)}%` },
                          { l: "52W Range", v: `${fmt(selectedDeep?.fundamentals?.low_52week, 0)} - ${fmt(selectedDeep?.fundamentals?.high_52week, 0)}` }
                        ].map((m, i) => (
                          <div key={i} className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">{m.l}</span>
                            <span className="text-xs font-mono text-slate-200">{m.v || "N/A"}</span>
                          </div>
                        ))}
                     </div>
                  </div>
                )}

                {activeTab === "squeeze" && (
                  <div className="space-y-6 animate-in fade-in duration-300">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {(selectedDeep?.on_chain) ? (
                        /* Crypto Derivatives View */
                        <>
                          <div className="p-4 rounded-xl bg-white/[0.03] border border-white/5">
                            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Long / Short Ratio</span>
                            <span className="text-xl font-mono text-slate-100">{fmt(selectedDeep.on_chain.futures_sentiment?.long_short_ratio, 2)}</span>
                            <p className="text-[10px] text-slate-500 mt-1">High ratio suggests overextended bullish positioning</p>
                          </div>
                          <div className="p-4 rounded-xl bg-white/[0.03] border border-white/5">
                            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Open Interest</span>
                            <span className="text-xl font-mono text-slate-100">{fmtCompact(selectedDeep.on_chain.futures_sentiment?.open_interest)}</span>
                            <p className="text-[10px] text-slate-500 mt-1">Net positions in perpetual contracts</p>
                          </div>
                        </>
                      ) : (
                        /* Stock Short Squeeze View */
                        <>
                          <div className="p-4 rounded-xl bg-white/[0.03] border border-white/5">
                            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Short Interest %</span>
                            <span className={`text-xl font-mono ${(selectedDeep?.fundamentals?.short_interest || 0) > 10 ? "text-amber-400" : "text-slate-100"}`}>
                              {fmt(selectedDeep?.fundamentals?.short_interest, 2)}%
                            </span>
                            <p className="text-[10px] text-slate-500 mt-1">Percentage of float sold short</p>
                          </div>
                          <div className="p-4 rounded-xl bg-white/[0.03] border border-white/5">
                            <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Short Ratio</span>
                            <span className={`text-xl font-mono ${(selectedDeep?.fundamentals?.short_ratio || 0) > 5 ? "text-amber-400" : "text-slate-100"}`}>
                              {fmt(selectedDeep?.fundamentals?.short_ratio, 1)}
                            </span>
                            <p className="text-[10px] text-slate-500 mt-1">Days to cover based on avg volume</p>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === "macro" && (
                  <div className="space-y-6 animate-in fade-in duration-300">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                       {selectedDeep?.on_chain?.fear_and_greed && (
                          <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
                             <div className="flex items-center gap-2 mb-2">
                                <Users className="w-4 h-4 text-indigo-400" />
                                <span className="text-[10px] uppercase text-indigo-400 font-bold tracking-widest">Fear & Greed Index</span>
                             </div>
                             <span className="text-xl font-bold text-slate-100">{selectedDeep.on_chain.fear_and_greed.value}</span>
                             <span className="ml-2 text-xs uppercase text-indigo-300 font-bold">/ {selectedDeep.on_chain.fear_and_greed.value_classification}</span>
                          </div>
                       )}
                       {selectedDeep?.institutional && (
                          <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                             <div className="flex items-center gap-2 mb-2">
                                <Search className="w-4 h-4 text-blue-400" />
                                <span className="text-[10px] uppercase text-blue-400 font-bold tracking-widest">Institutional Held</span>
                             </div>
                             <span className="text-xl font-bold text-slate-100">{fmt(selectedDeep.institutional.shares_held, 1)}%</span>
                             <p className="text-[10px] text-slate-400 mt-1">Verified holdings across {selectedDeep.institutional.institution_count} entities</p>
                          </div>
                       )}
                       <div className="p-4 rounded-xl bg-slate-500/5 border border-white/5 md:col-span-2">
                         <span className="text-[10px] uppercase text-slate-500 font-bold block mb-3">Breaking Context</span>
                         <div className="flex flex-wrap gap-2">
                            {(selectedDeep?.sentiment?.trending_topics || []).map((t, i) => (
                              <span key={i} className="px-2 py-1 rounded-lg bg-white/5 border border-white/10 text-[10px] text-slate-300">#{t}</span>
                            ))}
                         </div>
                       </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      {report.overall_insight && (
        <div className="border-t border-white/10 bg-gradient-to-r from-blue-500/[0.08] to-transparent p-6">
          <div className="flex gap-4">
            <div className="h-10 w-1 bg-blue-500 rounded-full" />
            <div>
              <span className="text-[10px] uppercase text-blue-400 font-bold tracking-[0.2em] mb-1 block">Institutional Takeaway</span>
              <p className="text-sm text-slate-200 leading-relaxed font-medium">
                {report.overall_insight}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
