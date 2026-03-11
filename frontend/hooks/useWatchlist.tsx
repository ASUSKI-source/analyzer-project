"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { API_BASE_URL } from "@/services/api_client";
import { useAuth } from "@/contexts/AuthContext";

export type WatchlistSymbol = {
  symbol: string;
  name: string;
  asset_type: string;
};

type WatchlistContextType = {
  symbols: WatchlistSymbol[];
  loading: boolean;
  addSymbol: (symbol: string) => Promise<boolean>;
  removeSymbol: (symbol: string) => Promise<boolean>;
  refresh: () => Promise<void>;
};

const WatchlistContext = createContext<WatchlistContextType | undefined>(undefined);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [symbols, setSymbols] = useState<WatchlistSymbol[]>([]);
  const [loading, setLoading] = useState(true);

  const getToken = () => typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const loadLocalWatchlist = (): WatchlistSymbol[] => {
    // Guest watchlist is completely in-memory now
    return [];
  };

  const saveLocalWatchlist = (newSymbols: WatchlistSymbol[]) => {
    // We only hold state in memory for guests, no local storage.
  };

  const syncLocalToApi = async (localSymbols: WatchlistSymbol[]) => {
    const token = getToken();
    if (!token) return;
    for (const s of localSymbols) {
      try {
        await fetch(`${API_BASE_URL}/watchlist/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({ symbol: s.symbol })
        });
      } catch (e) {
        console.error("Failed to sync symbol to API", e);
      }
    }
  };

  const fetchWatchlist = useCallback(async () => {
    if (authLoading) return;

    const localSymbols = loadLocalWatchlist();
    const token = getToken();

    if (!user || !token) {
      // Guest: use local storage
      setSymbols(localSymbols);
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const apiSymbols: WatchlistSymbol[] = data.symbols || [];
        
        // Merge missing local symbols into API
        const apiSymbolSet = new Set(apiSymbols.map(s => s.symbol));
        const missingLocals = localSymbols.filter(s => !apiSymbolSet.has(s.symbol));
        
        if (missingLocals.length > 0) {
          await syncLocalToApi(missingLocals);
          // Refetch after sync
          const res2 = await fetch(`${API_BASE_URL}/watchlist/`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          if (res2.ok) {
             const data2 = await res2.json();
             setSymbols(data2.symbols || []);
             saveLocalWatchlist(data2.symbols || []);
          }
        } else {
          setSymbols(apiSymbols);
          saveLocalWatchlist(apiSymbols);
        }
      }
    } catch (e) {
      console.error("Failed to fetch watchlist:", e);
      setSymbols(localSymbols);
    } finally {
      setLoading(false);
    }
  }, [user, authLoading]);

  useEffect(() => {
    fetchWatchlist();
    
    // Fallback sync listener for manual triggers
    const handleUpdate = () => fetchWatchlist();
    window.addEventListener("watchlist-updated", handleUpdate);
    return () => window.removeEventListener("watchlist-updated", handleUpdate);
  }, [fetchWatchlist]);

  const addSymbol = async (symbol: string): Promise<boolean> => {
    // Optimistic UI Update
    const newSymbolObj = { symbol, name: "", asset_type: "" }; 
    setSymbols(prev => {
      if (prev.some(s => s.symbol === symbol)) return prev;
      const next = [...prev, newSymbolObj];
      saveLocalWatchlist(next);
      return next;
    });

    const token = getToken();
    if (user && token) {
      try {
        const res = await fetch(`${API_BASE_URL}/watchlist/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({ symbol })
        });
        if (res.ok) {
          await fetchWatchlist(); 
          return true;
        }
      } catch (e) {
        console.error("Failed to add to watchlist API:", e);
      }
    } else {
        return true; 
    }
    return false;
  };

  const removeSymbol = async (symbol: string): Promise<boolean> => {
    // Optimistic UI Update
    setSymbols(prev => {
      const next = prev.filter(s => s.symbol !== symbol);
      saveLocalWatchlist(next);
      return next;
    });

    const token = getToken();
    if (user && token) {
      try {
        const res = await fetch(`${API_BASE_URL}/watchlist/${symbol}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          return true;
        }
      } catch (e) {
        console.error("Failed to remove from watchlist API:", e);
      }
    } else {
        return true;
    }
    return false;
  };

  return (
    <WatchlistContext.Provider value={{ symbols, loading, addSymbol, removeSymbol, refresh: fetchWatchlist }}>
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist() {
  const context = useContext(WatchlistContext);
  if (context === undefined) {
    throw new Error("useWatchlist must be used within a WatchlistProvider");
  }
  return context;
}
