/**
 * Search bar component with live symbol search and "Add to Watchlist" action.
 * Uses the backend /watchlist/search endpoint (local dictionary, no rate limits).
 * Guests can search but adding triggers auth prompt.
 */
"use client";

import { useState, useEffect, useRef } from "react";
import { Search, Plus, X, TrendingUp, Bitcoin } from "lucide-react";
import { API_BASE_URL } from "@/services/api_client";
import { useAuth } from "@/contexts/AuthContext";

type SearchResult = {
  symbol: string;
  name: string;
  type: string;
};

type Props = {
  onAddSymbol?: (symbol: string) => Promise<boolean>;
};

export function SymbolSearch({ onAddSymbol }: Props) {
  const { user, openAuthModal } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [addingSymbol, setAddingSymbol] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced search
  useEffect(() => {
    if (query.length < 1) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/watchlist/search?q=${encodeURIComponent(query)}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data.results || []);
          setIsOpen(true);
        }
      } catch (e) {
        console.error("Search failed:", e);
      }
    }, 200); // 200ms debounce

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside to close
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const [addedSymbols, setAddedSymbols] = useState<Set<string>>(new Set());

  const handleAdd = async (symbol: string) => {
    if (!onAddSymbol) return;

    setAddingSymbol(symbol);
    const success = await onAddSymbol(symbol);
    setAddingSymbol(null);
    
    if (success) {
      setAddedSymbols(prev => new Set(prev).add(symbol));
      setTimeout(() => setAddedSymbols(prev => {
        const next = new Set(prev);
        next.delete(symbol);
        return next;
      }), 1500);
    }
  };

  return (
    <div ref={containerRef} className="hidden md:flex relative w-[400px]">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-steel z-10" />
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => query.length > 0 && setIsOpen(true)}
        placeholder="Search symbols, e.g. AAPL, BTC..."
        className="w-full bg-black/20 border border-white/5 shadow-inner rounded-full py-2 pl-10 pr-10 text-sm text-marble focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-all placeholder:text-steel/50 hover:bg-black/40"
      />
      {query && (
        <button
          onClick={() => { setQuery(""); setResults([]); setIsOpen(false); }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-steel hover:text-marble transition-colors z-10"
        >
          <X className="h-4 w-4" />
        </button>
      )}

      {/* Dropdown Results */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-xl shadow-2xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          {results.map((r) => (
            <div
              key={r.symbol}
              className="flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors group cursor-default"
            >
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${r.type === "crypto" ? "bg-amber-500/10 text-amber-400" : "bg-blue-500/10 text-blue-400"}`}>
                  {r.type === "crypto" ? <Bitcoin className="w-4 h-4" /> : <TrendingUp className="w-4 h-4" />}
                </div>
                <div>
                  <span className="text-sm font-bold text-marble font-mono">{r.symbol}</span>
                  <p className="text-xs text-steel">{r.name}</p>
                </div>
              </div>
              <button
                onClick={() => handleAdd(r.symbol)}
                disabled={addingSymbol === r.symbol || addedSymbols.has(r.symbol)}
                className={`opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all disabled:opacity-100 ${addedSymbols.has(r.symbol) ? 'bg-green-500/10 text-green-400' : 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20'}`}
              >
                {addedSymbols.has(r.symbol) ? '✓ Added' : addingSymbol === r.symbol ? 'Adding...' : <><Plus className="w-3 h-3" /> Add</>}
              </button>
            </div>
          ))}
        </div>
      )}

      {isOpen && query.length > 0 && results.length === 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-xl shadow-2xl p-4 text-center text-steel text-sm z-50">
          No results for &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  );
}
