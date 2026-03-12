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
}

const LivePriceContext = createContext<LivePriceContextType | undefined>(undefined);

export function LivePriceProvider({ children }: { children: React.ReactNode }) {
  const [prices, setPrices] = useState<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const subsRef = useRef<Set<string>>(new Set());
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    console.log("[LivePriceProvider] Connecting to:", WS_BASE_URL);
    const ws = new WebSocket(WS_BASE_URL);

    ws.onopen = () => {
      console.log("[LivePriceProvider] Connected.");
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
          // Polygon aggregate second data has 'c' for close price
          const price = data.c || data.p; 
          if (price) {
            setPrices((prev) => ({ ...prev, [symbol]: price }));
          }
        }
      } catch (e) {
        console.error("[LivePriceProvider] Error parsing message:", e);
      }
    };

    ws.onclose = () => {
      console.warn("[LivePriceProvider] Disconnected. Reconnecting in 3s...");
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
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
    <LivePriceContext.Provider value={{ prices, subscribe, unsubscribe }}>
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
      context.subscribe(symbol);
      return () => context.unsubscribe(symbol);
    }
  }, [symbol, context]);

  return symbol ? context.prices[symbol.toUpperCase()] : undefined;
}
