"use client";

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { API_BASE_URL } from "@/services/api_client";

/**
 * WebSocket Base URL derived from the API URL.
 * If API is http://localhost:8000/api/v1, WS is ws://localhost:8000/api/v1/ws/ohlc
 */
const WS_BASE_URL = API_BASE_URL.replace("http", "ws") + "/ws/ohlc";

interface TickData {
  p: number; // Price
  s: number; // Size/Volume
  t: number; // Timestamp
  sym: string;
}

interface LivePriceContextType {
  prices: Record<string, number>;
  subscribe: (symbol: string) => void;
  unsubscribe: (symbol: string) => void;
  isConnected: boolean;
}

const LivePriceContext = createContext<LivePriceContextType | undefined>(undefined);

export function LivePriceProvider({ children }: { children: React.ReactNode }) {
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [isConnected, setIsConnected] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const subsRef = useRef<Set<string>>(new Set());
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // High-frequency price buffer to avoid React re-render thrashing
  const pendingPricesRef = useRef<Record<string, number>>({});
  const flushRequestRef = useRef<number | null>(null);

  const flushPrices = useCallback(() => {
    if (Object.keys(pendingPricesRef.current).length === 0) {
      flushRequestRef.current = null;
      return;
    }

    setPrices((prev) => ({
      ...prev,
      ...pendingPricesRef.current,
    }));
    
    pendingPricesRef.current = {};
    flushRequestRef.current = null;
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    console.log("[LivePriceProvider] Connecting to:", WS_BASE_URL);
    const ws = new WebSocket(WS_BASE_URL);

    ws.onopen = () => {
      console.log("[LivePriceProvider] Connected.");
      setIsConnected(true);
      // Restore previous subscriptions
      subsRef.current.forEach((symbol) => {
        ws.send(JSON.stringify({ type: "SUBSCRIBE", symbol }));
      });
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "TICK") {
          const { symbol, data } = msg;
          // Support multiple provider formats (Finnhub 'price', Polygon 'c', etc.)
          const price = data.price || data.c || data.p;
          
          if (price) {
            // Buffer the price update
            pendingPricesRef.current[symbol] = price;
            
            // Schedule a flush if one isn't already pending
            if (!flushRequestRef.current) {
                flushRequestRef.current = requestAnimationFrame(flushPrices);
            }
          }
        }
      } catch (e) {
        console.error("[LivePriceProvider] Error parsing message:", e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.warn("[LivePriceProvider] Disconnected. Reconnecting in 3s...");
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [connect, flushPrices]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (flushRequestRef.current) cancelAnimationFrame(flushRequestRef.current);
    };
  }, [connect]);

  const subscribe = useCallback((symbol: string) => {
    const sym = symbol.toUpperCase();
    if (subsRef.current.has(sym)) return;

    subsRef.current.add(sym);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "SUBSCRIBE", symbol: sym }));
    }
  }, []);

  const unsubscribe = useCallback((symbol: string) => {
    const sym = symbol.toUpperCase();
    if (!subsRef.current.has(sym)) return;

    subsRef.current.delete(sym);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "UNSUBSCRIBE", symbol: sym }));
    }
  }, []);

  return (
    <LivePriceContext.Provider value={{ prices, subscribe, unsubscribe, isConnected }}>
      {children}
    </LivePriceContext.Provider>
  );
}

export function useLivePrice(symbol?: string) {
  const context = useContext(LivePriceContext);
  if (!context) {
    throw new Error("useLivePrice must be used within a LivePriceProvider");
  }

  useEffect(() => {
    if (symbol) {
      const sym = symbol.toUpperCase();
      context.subscribe(sym);
      return () => context.unsubscribe(sym);
    }
  }, [symbol, context]);

  return symbol ? context.prices[symbol.toUpperCase()] : undefined;
}
