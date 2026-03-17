"use client";

import { useState, useEffect, useRef } from "react";
import { AlertCircle, Bitcoin, Check, Plus, Search, TrendingUp, X } from "lucide-react";
import { API_BASE_URL } from "@/services/api_client";

type SearchResult = {
  symbol: string;
  type?: string;
};

type Props = {
  onAddSymbol?: (symbol: string) => Promise<boolean>;
  watchlistSymbols?: string[];
};

export function SymbolSearch({ onAddSymbol, watchlistSymbols = [] }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [addingSymbol, setAddingSymbol] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [justAdded, setJustAdded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const cleaned = query.trim();
    if (cleaned.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/watchlist/search?q=${encodeURIComponent(cleaned)}`, {
          signal: controller.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setResults(
            (data.results || []).map((r: any) => ({
              symbol: String(r.symbol || "").toUpperCase(),
              type: String(r.type || "").toLowerCase(),
            }))
          );
          setIsOpen(true);
        } else {
          setResults([]);
          setIsOpen(true);
        }
      } catch (e: any) {
        if (e?.name === "AbortError") return;
        console.error("Search failed:", e);
      }
    }, 250);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleAdd = async (symbol: string) => {
    if (!onAddSymbol) {
      return;
    }

    setError(null);

    setAddingSymbol(symbol);
    const success = await onAddSymbol(symbol);
    setAddingSymbol(null);
    
    if (success) {
      setJustAdded(prev => new Set(prev).add(symbol));
      setTimeout(() => setJustAdded(prev => {
        const next = new Set(prev);
        next.delete(symbol);
        return next;
      }), 1400);
    } else {
      setError("Could not add symbol. Check that you are logged in and have an active watchlist.");
    }
  };

  const [isMobileSearchOpen, setIsMobileSearchOpen] = useState(false);

  return (
    <div ref={containerRef} className="relative flex items-center justify-center flex-1 md:flex-none">
      {/* Mobile Toggle Button */}
      {!isMobileSearchOpen && (
        <button 
          onClick={() => setIsMobileSearchOpen(true)}
          className="md:hidden p-2 text-steel hover:text-marble transition-colors"
        >
          <Search className="h-5 w-5" />
        </button>
      )}

      {/* Search Input Container */}
      <div className={`
        ${isMobileSearchOpen ? 'absolute inset-0 z-50 flex' : 'hidden md:flex'}
        relative w-full md:w-[320px] lg:w-[400px] items-center
      `}>
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-steel z-10" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => query.length > 0 && setIsOpen(true)}
          placeholder="Search symbols..."
          className="w-full bg-black/40 md:bg-black/20 border border-white/5 shadow-inner rounded-xl md:rounded-full py-2 pl-10 pr-10 text-sm text-marble focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-steel/50 hover:bg-black/40"
        />
        {(query || isMobileSearchOpen) && (
          <button
            onClick={() => { 
              if (query) {
                setQuery(""); 
                setResults([]); 
                setIsOpen(false);
              } else {
                setIsMobileSearchOpen(false);
              }
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-steel hover:text-marble transition-colors z-10"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Dropdown Results */}
      {isOpen && (results.length > 0 || error || query.length > 0) && (
        <div
          className={`
            absolute top-full mt-2 rounded-lg border border-white/10 bg-slate-900/95
            backdrop-blur-xl shadow-2xl overflow-hidden z-50 animate-in fade-in
            slide-in-from-top-2 duration-150 max-h-64 overflow-y-auto
            ${isMobileSearchOpen ? 'left-1/2 -translate-x-1/2 w-[calc(100vw-3rem)]' : 'left-0 w-full max-w-xs'}
          `}
        >
          {results.map((r) => (
            <div
              key={r.symbol}
              className="flex items-center justify-between px-3 py-1.5 hover:bg-white/5 transition-colors cursor-default"
            >
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className={`h-6 w-6 rounded-md flex items-center justify-center text-[11px] ${
                    r.type === "crypto"
                      ? "bg-amber-500/10 text-amber-300"
                      : "bg-blue-500/10 text-blue-300"
                  }`}
                >
                  {r.type === "crypto" ? (
                    <Bitcoin className="w-3.5 h-3.5" />
                  ) : (
                    <TrendingUp className="w-3.5 h-3.5" />
                  )}
                </div>
                <span className="text-sm font-semibold text-marble font-mono tracking-wide truncate">
                  {r.symbol}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleAdd(r.symbol);
                }}
                disabled={addingSymbol === r.symbol || watchlistSymbols.includes(r.symbol)}
                className={`h-6 w-6 rounded-md border flex items-center justify-center transition-all ${
                  watchlistSymbols.includes(r.symbol) || justAdded.has(r.symbol)
                    ? "border-green-400/40 bg-green-500/10 text-green-300"
                    : "border-white/15 bg-white/[0.03] text-slate-300 hover:bg-white/[0.08] hover:text-marble"
                }`}
                title={watchlistSymbols.includes(r.symbol) ? "Already in watchlist" : `Add ${r.symbol}`}
              >
                {watchlistSymbols.includes(r.symbol) || justAdded.has(r.symbol)
                  ? <Check className="w-3.5 h-3.5" />
                  : addingSymbol === r.symbol
                    ? <span className="text-[10px]">..</span>
                    : <Plus className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}

          {results.length === 0 && query.length > 0 && !error && (
            <div className="px-3 py-2 text-center text-steel text-xs">
              No results for &ldquo;{query}&rdquo;
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 px-3 py-2 border-t border-red-500/30 bg-red-500/5">
              <AlertCircle className="w-3.5 h-3.5 text-red-400 mt-0.5" />
              <p className="text-[11px] text-red-300 leading-snug">{error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
