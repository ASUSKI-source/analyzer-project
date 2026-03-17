"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { API_BASE_URL } from "@/services/api_client";
import { useAuth } from "@/contexts/AuthContext";

export type WatchlistHeader = {
  id: string;
  name: string;
};

export type WatchlistSymbol = {
  symbol: string;
  name: string;
  asset_type: string;
};

type WatchlistContextType = {
  watchlists: WatchlistHeader[];
  activeId: string | null;
  symbols: WatchlistSymbol[];
  loading: boolean;
  addSymbol: (symbol: string) => Promise<boolean>;
  removeSymbol: (symbol: string) => Promise<boolean>;
  createWatchlist: (name: string) => Promise<string | null>;
  setActiveId: (id: string) => void;
  refresh: () => Promise<void>;
};

const WatchlistContext = createContext<WatchlistContextType | undefined>(undefined);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [watchlists, setWatchlists] = useState<WatchlistHeader[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [symbols, setSymbols] = useState<WatchlistSymbol[]>([]);
  const [loading, setLoading] = useState(true);

  const getToken = () => typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const fetchWatchlists = useCallback(async () => {
    if (authLoading) return;
    const token = getToken();
    if (!user || !token) {
      setWatchlists([{ id: "guest", name: "Guest Watchlist" }]);
      setActiveId("guest");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const lists = data.watchlists || [];
        setWatchlists(lists);
        if (lists.length > 0 && !activeId) {
          setActiveId(lists[0].id);
        }
      }
    } catch (e) {
      console.error("Failed to fetch watchlists:", e);
    }
  }, [user, authLoading, activeId]);

  const fetchSymbols = useCallback(async () => {
    if (!activeId) return;
    if (activeId === "guest") return; // Guest symbols in-memory/handled elsewhere or just empty

    const token = getToken();
    if (!token) return;

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/${activeId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSymbols(data.symbols || []);
      }
    } catch (e) {
      console.error("Failed to fetch symbols:", e);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    fetchWatchlists();
  }, [fetchWatchlists]);

  useEffect(() => {
    if (activeId) fetchSymbols();
  }, [activeId, fetchSymbols]);

  const createWatchlist = async (name: string): Promise<string | null> => {
    const token = getToken();
    if (!token || !user) return null;

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ name })
      });
      if (res.ok) {
        const data = await res.json();
        const newId = data.id;
        await fetchWatchlists();
        setActiveId(newId);
        return newId;
      }
    } catch (e) {
      console.error("Failed to create watchlist:", e);
    }
    return null;
  };

  const addSymbol = async (symbol: string): Promise<boolean> => {
    if (!activeId) return false;
    
    // Optimistic Update
    if (activeId === "guest") {
      setSymbols(prev => [...prev, { symbol, name: "", asset_type: "" }]);
      return true;
    }

    const token = getToken();
    if (!token || !user) return false;

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/${activeId}/symbols`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ symbol })
      });
      if (res.ok) {
        fetchSymbols();
        return true;
      }
    } catch (e) {
      console.error("Failed to add symbol:", e);
    }
    return false;
  };

  const removeSymbol = async (symbol: string): Promise<boolean> => {
    if (!activeId) return false;

    if (activeId === "guest") {
      setSymbols(prev => prev.filter(s => s.symbol !== symbol));
      return true;
    }

    const token = getToken();
    if (!token) return false;

    try {
      const res = await fetch(`${API_BASE_URL}/watchlist/${activeId}/symbols/${symbol}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setSymbols(prev => prev.filter(s => s.symbol !== symbol));
        return true;
      }
    } catch (e) {
      console.error("Failed to remove symbol:", e);
    }
    return false;
  };

  return (
    <WatchlistContext.Provider value={{ 
      watchlists, 
      activeId, 
      symbols, 
      loading, 
      addSymbol, 
      removeSymbol, 
      createWatchlist, 
      setActiveId,
      refresh: fetchWatchlists 
    }}>
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
