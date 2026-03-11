"use client";

import React, { useState, useCallback } from "react";
import { Sparkles, ChevronDown, ChevronUp, AlertTriangle, TrendingUp, TrendingDown, Minus, RefreshCw, Shield } from "lucide-react";
import { API_BASE_URL } from "@/services/api_client";

interface AssetAnalysis {
  symbol: string;
  verdict: string;
  key_metrics: {
    rsi?: number;
    pe_ratio?: number;
    macd_signal?: string;
    trend_50d?: string;
  };
  technical_bullets: string[];
  fundamental_bullets: string[];
  catalyst: string;
  action_note: string;
}

interface AIReport {
  market_summary: string;
  watchlist_health: string;
  risk_level: string;
  sector_exposure: string;
  assets: AssetAnalysis[];
  overall_insight: string;
  generated_at?: string;
  from_cache?: boolean;
  _mock?: boolean;
  cooldown_remaining?: number;
  error?: string;
}

interface Props {
  symbols: string[];
  onSelectAsset?: (symbol: string) => void;
}

export function AnalysisReportPanel({ symbols, onSelectAsset }: Props) {
  const [report, setReport] = useState<AIReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedAssets, setExpandedAssets] = useState<Set<string>>(new Set());

  const fetchReport = useCallback(async (forceRefresh = false) => {
    if (symbols.length === 0) return;
    setLoading(true);
    setError(null);

    try {
      const symbolStr = symbols.join(",");
      const token = localStorage.getItem("token");
      const url = `${API_BASE_URL}/ai/watchlist-analysis?symbols=${symbolStr}${forceRefresh ? "&refresh=true" : ""}`;
      
      const res = await fetch(url, {
        headers: token ? { "Authorization": `Bearer ${token}` } : {}
      });
      const data: AIReport = await res.json();
      
      if (data.error && !data.assets?.length) {
        setError(data.error);
      } else {
        setReport(data);
        // Auto-expand all assets on first load
        setExpandedAssets(new Set(data.assets?.map(a => a.symbol) || []));
      }
    } catch (e: any) {
      setError(e?.message || "Failed to generate analysis");
    } finally {
      setLoading(false);
    }
  }, [symbols]);

  const toggleAsset = (symbol: string) => {
    setExpandedAssets(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  };

  const verdictConfig: Record<string, { color: string; icon: React.ReactNode; bg: string }> = {
    BULLISH:  { color: "text-green-400", icon: <TrendingUp className="w-4 h-4" />, bg: "bg-green-500/10 border-green-500/20" },
    BEARISH:  { color: "text-red-400",   icon: <TrendingDown className="w-4 h-4" />, bg: "bg-red-500/10 border-red-500/20" },
    NEUTRAL:  { color: "text-steel",     icon: <Minus className="w-4 h-4" />, bg: "bg-white/5 border-white/10" },
    CAUTION:  { color: "text-amber-400", icon: <AlertTriangle className="w-4 h-4" />, bg: "bg-amber-500/10 border-amber-500/20" },
  };

  const healthColors: Record<string, string> = {
    STRONG: "text-green-400",
    MODERATE: "text-amber-400",
    WEAK: "text-red-400",
    MIXED: "text-blue-400",
  };

  const riskColors: Record<string, string> = {
    LOW: "text-green-400",
    MODERATE: "text-amber-400",
    HIGH: "text-red-400",
  };

  // ─── Empty State: Show Generate Button ────────────────────────────────────
  if (!report && !loading) {
    return (
      <div className="true-glass rounded-2xl p-6 sm:p-8 relative overflow-hidden group/ai">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-500/30 to-transparent" />
        
        <div className="flex flex-col items-center text-center py-8 gap-5">
          <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/20 flex items-center justify-center shadow-[0_0_30px_rgba(59,130,246,0.2)]">
            <Sparkles className="w-7 h-7 text-blue-400" />
          </div>

          <div>
            <h3 className="text-lg font-bold text-marble mb-2">AI Watchlist Analysis</h3>
            <p className="text-sm text-steel max-w-md">
              Get a comprehensive technical, fundamental, and risk analysis of your entire watchlist powered by AI.
              {symbols.length > 0 
                ? ` Analyzing ${symbols.length} asset${symbols.length > 1 ? 's' : ''}.`
                : " Add symbols to your watchlist to get started."
              }
            </p>
          </div>

          {error && (
            <div className="w-full max-w-md p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 text-sm">
              {error}
            </div>
          )}

          <button
            onClick={() => fetchReport(false)}
            disabled={symbols.length === 0}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-blue-500/20 to-blue-600/20 border border-blue-500/30 text-blue-400 font-semibold text-sm hover:from-blue-500/30 hover:to-blue-600/30 hover:border-blue-400/50 hover:-translate-y-0.5 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(59,130,246,0.15)]"
          >
            <Sparkles className="w-4 h-4" />
            Generate Analysis
          </button>
        </div>
      </div>
    );
  }

  // ─── Loading State ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="true-glass rounded-2xl p-6 sm:p-8 relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-500/50 to-transparent animate-pulse" />
        
        <div className="flex flex-col items-center text-center py-12 gap-4">
          <div className="relative">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/30 flex items-center justify-center animate-pulse">
              <Sparkles className="w-7 h-7 text-blue-400 animate-spin" />
            </div>
            <div className="absolute -inset-4 bg-blue-500/10 rounded-full blur-xl animate-pulse" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-marble mb-1">Analyzing Your Watchlist...</h3>
            <p className="text-sm text-steel">Gathering technicals, fundamentals, and market context</p>
          </div>
          <div className="flex gap-1.5 mt-2">
            <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        </div>
      </div>
    );
  }

  // ─── Report Rendered ──────────────────────────────────────────────────────
  if (!report) return null;

  return (
    <div className="true-glass rounded-2xl relative overflow-hidden" id="ai-analysis-panel">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-500/30 to-transparent" />

      {/* Header */}
      <div className="p-5 sm:p-6 border-b border-white/5 bg-black/10">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20">
              <Sparkles className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="font-bold text-marble text-lg">AI Watchlist Analysis</h3>
              <p className="text-xs text-steel flex items-center gap-2 mt-0.5">
                {report.from_cache && <span className="text-blue-400/60">Cached</span>}
                {report.generated_at && <span>{new Date(report.generated_at).toLocaleString()}</span>}
                {report._mock && <span className="text-amber-400">(Simulated)</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Health Badge */}
            <div className={`px-3 py-1 rounded-full border text-xs font-bold ${healthColors[report.watchlist_health] || "text-steel"} border-white/10 bg-white/5`}>
              Health: {report.watchlist_health}
            </div>
            {/* Risk Badge */}
            <div className={`px-3 py-1 rounded-full border text-xs font-bold flex items-center gap-1.5 ${riskColors[report.risk_level] || "text-steel"} border-white/10 bg-white/5`}>
              <Shield className="w-3 h-3" />
              Risk: {report.risk_level}
            </div>
            {/* Refresh */}
            <button
              onClick={() => fetchReport(true)}
              className="p-2 rounded-lg bg-white/5 border border-white/10 text-steel hover:text-marble hover:bg-white/10 transition-all"
              title="Regenerate analysis (Force Refresh)"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Market Summary */}
      <div className="px-5 sm:px-6 py-4 border-b border-white/5 bg-black/5">
        <p className="text-sm text-marble/90 leading-relaxed">{report.market_summary}</p>
        {report.sector_exposure && (
          <p className="text-xs text-steel mt-2">📊 {report.sector_exposure}</p>
        )}
      </div>

      {/* Per-Asset Analysis */}
      <div className="divide-y divide-white/5">
        {report.assets?.map((asset) => {
          const vc = verdictConfig[asset.verdict] || verdictConfig.NEUTRAL;
          const isExpanded = expandedAssets.has(asset.symbol);

          return (
            <div key={asset.symbol} className="group/asset">
              {/* Collapsed Header (Full Row Clickable) */}
              <div 
                onClick={() => toggleAsset(asset.symbol)}
                className="w-full flex items-center justify-between px-5 sm:px-6 py-4 hover:bg-white/5 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-4 flex-wrap">
                  <span
                    className="font-mono font-bold text-marble hover:text-blue-400 transition-colors text-base z-10"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectAsset?.(asset.symbol);
                    }}
                  >
                    {asset.symbol}
                  </span>
                  
                  {/* Verdict Badge */}
                  <span className={`px-2.5 py-0.5 rounded-full border text-[10px] font-bold flex items-center gap-1 ${vc.bg} ${vc.color}`}>
                    {vc.icon}
                    {asset.verdict}
                  </span>

                  {/* Key Metric Badges */}
                  <div className="flex items-center gap-2">
                    {asset.key_metrics?.rsi !== undefined && (
                      <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[10px]" title="RSI (14)">
                        <span className="text-steel">RSI</span>
                        <span className={asset.key_metrics.rsi > 70 ? "text-red-400" : asset.key_metrics.rsi < 30 ? "text-green-400" : "text-blue-300"}>
                          {asset.key_metrics.rsi}
                        </span>
                      </div>
                    )}
                    {asset.key_metrics?.pe_ratio !== undefined && (
                      <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[10px]" title="P/E Ratio">
                        <span className="text-steel">P/E</span>
                        <span className="text-purple-300">{asset.key_metrics.pe_ratio}</span>
                      </div>
                    )}
                    {asset.key_metrics?.macd_signal && (
                      <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[10px]" title="MACD Signal">
                        <span className="text-steel text-[9px] uppercase">MACD</span>
                        <span className={asset.key_metrics.macd_signal === 'Bullish' ? "text-green-400" : asset.key_metrics.macd_signal === 'Bearish' ? "text-red-400" : "text-steel"}>
                          {asset.key_metrics.macd_signal}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="p-1.5 rounded-lg text-steel">
                  {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </div>
              </div>

              {/* Expanded Detail */}
              {isExpanded && (
                <div className="px-5 sm:px-6 pb-6 space-y-4 animate-in slide-in-from-top-2 duration-200">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Technical Strategy */}
                    <div className="bg-black/20 rounded-2xl p-4 border border-white/5 relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-3 opacity-10">
                        <TrendingUp className="w-8 h-8 text-blue-400" />
                      </div>
                      <h4 className="text-[10px] uppercase tracking-[0.2em] text-blue-400 mb-3 font-bold">Technical Outlook</h4>
                      <ul className="space-y-2">
                        {Array.isArray(asset.technical_bullets) ? asset.technical_bullets.map((bullet, idx) => (
                          <li key={idx} className="flex gap-2 text-sm text-marble/90 leading-relaxed">
                            <span className="text-blue-500/50 mt-1">•</span>
                            {bullet}
                          </li>
                        )) : <li className="text-sm text-steel">No technical data available.</li>}
                      </ul>
                    </div>

                    {/* Fundamental Core */}
                    <div className="bg-black/20 rounded-2xl p-4 border border-white/5 relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-3 opacity-10">
                        <Sparkles className="w-8 h-8 text-purple-400" />
                      </div>
                      <h4 className="text-[10px] uppercase tracking-[0.2em] text-purple-400 mb-3 font-bold">Fundamental Health</h4>
                      <ul className="space-y-2">
                        {Array.isArray(asset.fundamental_bullets) ? asset.fundamental_bullets.map((bullet, idx) => (
                          <li key={idx} className="flex gap-2 text-sm text-marble/90 leading-relaxed">
                            <span className="text-purple-500/50 mt-1">•</span>
                            {bullet}
                          </li>
                        )) : <li className="text-sm text-steel">No fundamental data available.</li>}
                      </ul>
                    </div>
                  </div>

                  {/* Footer Row: Catalyst & Action */}
                  <div className="flex flex-col sm:flex-row gap-3">
                    {asset.catalyst && (
                      <div className="flex-1 bg-amber-500/5 rounded-xl px-4 py-3 border border-amber-500/10 flex items-start gap-3">
                        <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-amber-200/80 leading-relaxed">
                          <span className="font-bold text-amber-400 mr-1">WATCH CATALYST:</span>
                          {asset.catalyst}
                        </p>
                      </div>
                    )}
                    {asset.action_note && (
                      <div className="flex-1 bg-blue-500/5 rounded-xl px-4 py-3 border border-blue-500/10 flex items-start gap-3">
                        <Sparkles className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
                        <p className="text-xs text-blue-200/80 leading-relaxed italic">
                          {asset.action_note}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Overall Insight Footer */}
      {report.overall_insight && (
        <div className="px-5 sm:px-6 py-4 border-t border-white/5 bg-gradient-to-r from-blue-500/5 to-transparent">
          <p className="text-sm text-marble/80 leading-relaxed">
            <span className="font-bold text-blue-400">Summary:</span> {report.overall_insight}
          </p>
        </div>
      )}
    </div>
  );
}
