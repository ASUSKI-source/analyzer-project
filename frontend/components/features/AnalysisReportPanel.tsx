"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Gauge,
  Minus,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingDown,
  TrendingUp,
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
  };
  sentiment?: {
    sentiment_score?: number;
    trending_topics?: string[];
  };
  last_updated?: string;
}

interface Props {
  symbols: string[];
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

export function AnalysisReportPanel({ symbols, onSelectAsset }: Props) {
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

  const fetchAssetDeep = useCallback(
    async (symbol: string): Promise<void> => {
      if (!symbol || assetDeepData[symbol] || assetDeepLoading[symbol]) return;
      const token = localStorage.getItem("token");
      if (!token) return;

      setAssetDeepLoading((prev) => ({ ...prev, [symbol]: true }));
      try {
        const res = await fetch(`${API_BASE_URL}/market/assets/${symbol}/analysis`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data: AssetDeepAnalysis = await res.json();
        setAssetDeepData((prev) => ({ ...prev, [symbol]: data }));
      } catch {
        // best effort enrichment
      } finally {
        setAssetDeepLoading((prev) => ({ ...prev, [symbol]: false }));
      }
    },
    [assetDeepData, assetDeepLoading],
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

  const selectedAsset =
    displayedAssets.find((a) => a.symbol === selectedSymbol) || displayedAssets[0] || null;
  const selectedDeep = selectedAsset ? assetDeepData[selectedAsset.symbol] : undefined;

  useEffect(() => {
    if (!displayedAssets.length) {
      setSelectedSymbol(null);
      return;
    }
    if (!selectedSymbol || !displayedAssets.some((a) => a.symbol === selectedSymbol)) {
      setSelectedSymbol(displayedAssets[0].symbol);
    }
  }, [displayedAssets, selectedSymbol]);

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
      <div className="border-b border-white/10 bg-black/30 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm uppercase tracking-[0.16em] text-slate-300 font-semibold">Analysis Report</h3>
            <p className="mt-1 text-xs text-slate-400">Executive strip, signal matrix, focused drilldown</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {report.source_status && (
                <span
                  title="Current analysis response source"
                  className="rounded border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-300"
                >
                  {report.source_status}
                </span>
              )}
              {report.from_cache && (
                <span
                  title="Served from cached report"
                  className="rounded border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-300"
                >
                  Cached
                </span>
              )}
              {report._served_last_good && (
                <span
                  title="Fresh generation failed; showing last successful report"
                  className="rounded border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-200"
                >
                  Last Good
                </span>
              )}
              {report._mock && (
                <span
                  title="Simulated analysis fallback was used"
                  className="rounded border border-red-500/25 bg-red-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-red-200"
                >
                  Simulated
                </span>
              )}
            </div>
          </div>
          <button
            onClick={() => fetchReport(true)}
            className="inline-flex items-center gap-2 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshingDeep ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="border-b border-white/10 bg-black/15 p-4 sm:p-5">
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-2 text-[11px]">
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Health</p>
            <p className={`font-semibold ${HEALTH_COLORS[report.watchlist_health] || "text-slate-200"}`}>{report.watchlist_health}</p>
          </div>
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Risk</p>
            <p className={`font-semibold ${RISK_COLORS[report.risk_level] || "text-slate-200"}`}>
              <span className="inline-flex items-center gap-1"><Shield className="w-3 h-3" />{report.risk_level}</span>
            </p>
          </div>
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Coverage</p>
            <p className="font-semibold text-slate-200">{coverageEstimate}%</p>
          </div>
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Status</p>
            <p className="font-semibold text-slate-200">{report.source_status || "unknown"}</p>
          </div>
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Assets</p>
            <p className="font-semibold text-slate-200">{displayedAssets.length}</p>
          </div>
          <div className="rounded border border-white/10 bg-white/[0.03] p-2">
            <p className="uppercase tracking-wider text-slate-400">Updated</p>
            <p className="font-semibold text-slate-200">{report.generated_at ? new Date(report.generated_at).toLocaleTimeString() : "-"}</p>
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-300">{report.market_summary}</p>
      </div>

      <div className="p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-slate-400">Filter</span>
          {(["ALL", "BULLISH", "BEARISH", "NEUTRAL", "CAUTION"] as VerdictFilter[]).map((vf) => (
            <button
              key={vf}
              onClick={() => setVerdictFilter(vf)}
              className={`rounded-md border px-2.5 py-1 text-[11px] transition ${
                verdictFilter === vf
                  ? "border-blue-400/40 bg-blue-500/15 text-blue-200"
                  : "border-white/15 bg-white/[0.03] text-slate-300 hover:bg-white/[0.08]"
              }`}
            >
              {vf}
            </button>
          ))}
          <button
            onClick={resetView}
            className="ml-1 rounded-md border border-white/15 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-300 transition hover:bg-white/[0.08]"
            title="Reset filter and sorting"
          >
            Reset View
          </button>
          <span className="ml-1 text-[11px] text-slate-500">Use up/down keys to move rows</span>
        </div>

        <div
          className="overflow-x-auto rounded-lg border border-white/10"
          tabIndex={0}
          onKeyDown={handleMatrixKeyNav}
        >
          <table className="w-full min-w-[980px] text-xs">
            <thead className="text-slate-300">
              <tr className="border-b border-white/10">
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("symbol")} onClick={() => toggleSort("symbol")} title="Sort by symbol">
                    Symbol <span className="text-[10px]">{sortGlyph("symbol")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("verdict")} onClick={() => toggleSort("verdict")} title="Sort by verdict">
                    Verdict <span className="text-[10px]">{sortGlyph("verdict")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("h1")} onClick={() => toggleSort("h1")} title="Sort by 1h signal">
                    1h <span className="text-[10px]">{sortGlyph("h1")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("d1")} onClick={() => toggleSort("d1")} title="Sort by 1d signal">
                    1d <span className="text-[10px]">{sortGlyph("d1")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("w1")} onClick={() => toggleSort("w1")} title="Sort by 1w signal">
                    1w <span className="text-[10px]">{sortGlyph("w1")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("rsi")} onClick={() => toggleSort("rsi")} title="Sort by RSI">
                    RSI <span className="text-[10px]">{sortGlyph("rsi")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("macd")} onClick={() => toggleSort("macd")} title="Sort by MACD signal">
                    MACD <span className="text-[10px]">{sortGlyph("macd")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("ema")} onClick={() => toggleSort("ema")} title="Sort by EMA signal">
                    EMA <span className="text-[10px]">{sortGlyph("ema")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("pe")} onClick={() => toggleSort("pe")} title="Sort by P/E">
                    P/E <span className="text-[10px]">{sortGlyph("pe")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("beta")} onClick={() => toggleSort("beta")} title="Sort by beta">
                    Beta <span className="text-[10px]">{sortGlyph("beta")}</span>
                  </button>
                </th>
                <th className="sticky top-0 z-10 bg-black/75 backdrop-blur px-3 py-2 text-left font-semibold">
                  <button className={sortButtonClass("catalyst")} onClick={() => toggleSort("catalyst")} title="Sort by catalyst">
                    Catalyst <span className="text-[10px]">{sortGlyph("catalyst")}</span>
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {displayedAssets.map((asset) => {
                const style = VERDICT_STYLE[asset.verdict] || VERDICT_STYLE.NEUTRAL;
                const deep = assetDeepData[asset.symbol];
                return (
                  <tr
                    key={asset.symbol}
                    onClick={() => handleRowSelect(asset.symbol)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleRowSelect(asset.symbol);
                      }
                    }}
                    tabIndex={0}
                    className={`cursor-pointer border-b border-white/5 transition ${
                      selectedAsset?.symbol === asset.symbol ? "bg-white/[0.07]" : "hover:bg-white/[0.035]"
                    }`}
                  >
                    <td className="sticky left-0 z-[1] bg-black/70 px-3 py-2 font-mono font-semibold text-slate-100">
                      <div className="relative pl-2">
                        {selectedAsset?.symbol === asset.symbol && (
                          <span className="absolute left-0 top-0 bottom-0 w-0.5 rounded bg-blue-300" />
                        )}
                        {asset.symbol}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 ${style.bg} ${style.text}`}>
                        {style.icon}
                        {asset.verdict}
                      </span>
                    </td>
                    <td className={`px-3 py-2 ${signalClass(asset.timeframe_signals?.tactical_1h)}`}>{asset.timeframe_signals?.tactical_1h || "-"}</td>
                    <td className={`px-3 py-2 ${signalClass(asset.timeframe_signals?.trend_1d)}`}>{asset.timeframe_signals?.trend_1d || "-"}</td>
                    <td className={`px-3 py-2 ${signalClass(asset.timeframe_signals?.strategic_1w)}`}>{asset.timeframe_signals?.strategic_1w || "-"}</td>
                    <td className="px-3 py-2 text-slate-200">{fmt(asset.key_metrics?.rsi_daily, 1)}</td>
                    <td className="px-3 py-2 text-slate-200">{asset.key_metrics?.macd_signal || "-"}</td>
                    <td className="px-3 py-2 text-slate-200">{asset.key_metrics?.ema_signal || "-"}</td>
                    <td className="px-3 py-2 text-slate-200">{fmt(asset.key_metrics?.pe_ratio, 2)}</td>
                    <td className="px-3 py-2 text-slate-200">{fmt(deep?.fundamentals?.beta, 2)}</td>
                    <td className="max-w-[220px] truncate px-3 py-2 text-slate-400" title={asset.catalyst}>{asset.catalyst || "-"}</td>
                  </tr>
                );
              })}
              {displayedAssets.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-3 py-6 text-center text-slate-400">
                    No assets match the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selectedAsset && (
          <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
            <div className="rounded-lg border border-white/10 bg-black/20 p-3">
              <div className="mb-2 inline-flex items-center gap-2 text-[11px] uppercase tracking-wider text-blue-300 font-semibold">
                <Activity className="w-3.5 h-3.5" />
                Technical Stack
              </div>
              {assetDeepLoading[selectedAsset.symbol] ? (
                <p className="text-xs text-slate-400">Loading technical detail...</p>
              ) : (
                <div className="space-y-1 text-xs text-slate-300">
                  <p>Trend: <span className="text-slate-100">{selectedDeep?.technicals?.trend_signal || selectedAsset.timeframe_signals?.trend_1d || "-"}</span></p>
                  <p>RSI: <span className="text-slate-100">{fmt(selectedDeep?.technicals?.rsi, 1)}</span></p>
                  <p>MACD / Signal: <span className="text-slate-100">{fmt(selectedDeep?.technicals?.macd, 2)} / {fmt(selectedDeep?.technicals?.macd_signal, 2)}</span></p>
                  <p>EMA 9 / 21: <span className="text-slate-100">{fmt(selectedDeep?.technicals?.ema_9, 2)} / {fmt(selectedDeep?.technicals?.ema_21, 2)}</span></p>
                  <p>SMA 20 / 50 / 200: <span className="text-slate-100">{fmt(selectedDeep?.technicals?.sma_20, 2)} / {fmt(selectedDeep?.technicals?.sma_50, 2)} / {fmt(selectedDeep?.technicals?.sma_200, 2)}</span></p>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-white/10 bg-black/20 p-3">
              <div className="mb-2 inline-flex items-center gap-2 text-[11px] uppercase tracking-wider text-purple-300 font-semibold">
                <Gauge className="w-3.5 h-3.5" />
                Fundamental Stack
              </div>
              {assetDeepLoading[selectedAsset.symbol] ? (
                <p className="text-xs text-slate-400">Loading fundamentals...</p>
              ) : (
                <div className="space-y-1 text-xs text-slate-300">
                  <p>P/E: <span className="text-slate-100">{fmt(selectedDeep?.fundamentals?.pe_ratio ?? selectedAsset.key_metrics?.pe_ratio, 2)}</span></p>
                  <p>EPS: <span className="text-slate-100">{fmt(selectedDeep?.fundamentals?.eps, 2)}</span></p>
                  <p>Beta: <span className="text-slate-100">{fmt(selectedDeep?.fundamentals?.beta, 2)}</span></p>
                  <p>Dividend Yield: <span className="text-slate-100">{fmt(selectedDeep?.fundamentals?.dividend_yield, 2)}%</span></p>
                  <p>Market Cap: <span className="text-slate-100">{fmtCompact(selectedDeep?.fundamentals?.market_cap)}</span></p>
                  <p>52W H/L: <span className="text-slate-100">{fmt(selectedDeep?.fundamentals?.high_52week, 2)} / {fmt(selectedDeep?.fundamentals?.low_52week, 2)}</span></p>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-white/10 bg-black/20 p-3">
              <div className="mb-2 inline-flex items-center gap-2 text-[11px] uppercase tracking-wider text-amber-300 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5" />
                Event + AI Notes
              </div>
              {assetDeepLoading[selectedAsset.symbol] ? (
                <p className="text-xs text-slate-400">Loading event context...</p>
              ) : (
                <div className="space-y-2 text-xs text-slate-300">
                  <p>Sentiment: <span className="text-slate-100">{fmt(selectedDeep?.sentiment?.sentiment_score, 2)}</span></p>
                  <div className="flex flex-wrap gap-1">
                    {(selectedDeep?.sentiment?.trending_topics || []).slice(0, 4).map((topic, i) => (
                      <span key={`${selectedAsset.symbol}-topic-${i}`} className="rounded border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-200">
                        {topic}
                      </span>
                    ))}
                    {(selectedDeep?.sentiment?.trending_topics || []).length === 0 && (
                      <span className="text-slate-400">No event tags available</span>
                    )}
                  </div>
                  <p className="text-slate-200">{selectedAsset.action_note || "-"}</p>
                  {!!selectedAsset.catalyst && <p className="text-amber-200/90">Catalyst: {selectedAsset.catalyst}</p>}
                </div>
              )}
            </div>
          </div>
        )}

        {selectedAsset && (
          <div className="mt-3 rounded-lg border border-white/10 bg-black/15 p-3">
            <p className="mb-2 text-[11px] uppercase tracking-wider text-slate-400">AI Bullet Synthesis</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {(selectedAsset.analysis_bullets || []).map((bullet, idx) => (
                <p key={`${selectedAsset.symbol}-bullet-${idx}`} className="text-xs text-slate-300 leading-relaxed">
                  - {bullet}
                </p>
              ))}
              {(selectedAsset.analysis_bullets || []).length === 0 && (
                <p className="text-xs text-slate-400">No per-asset bullets returned.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {report.overall_insight && (
        <div className="border-t border-white/10 bg-gradient-to-r from-blue-500/10 to-transparent px-4 sm:px-5 py-3">
          <p className="text-sm text-slate-200 leading-relaxed">
            <span className="font-semibold text-blue-300">Portfolio Insight:</span> {report.overall_insight}
          </p>
        </div>
      )}
    </div>
  );
}
