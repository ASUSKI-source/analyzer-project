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
  ticks: Record<string, TickData>;
  subscribe: (symbol: string) => void;
  unsubscribe: (symbol: string) => void;
  isConnected: boolean;
}

const LivePriceContext = createContext<LivePriceContextType | undefined>(undefined);

export function LivePriceProvider({ children }: { children: React.ReactNode }) {
  const [ticks, setTicks] = useState<Record<string, TickData>>({});
  const [isConnected, setIsConnected] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const subsRef = useRef<Set<string>>(new Set());
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // High-frequency tick buffer to avoid React re-render thrashing
  const pendingTicksRef = useRef<Record<string, TickData>>({});
  const flushRequestRef = useRef<number | null>(null);

  const flushTicks = useCallback((): void => {
    if (Object.keys(pendingTicksRef.current).length === 0) {
      flushRequestRef.current = null;
      return;
    }

    setTicks((prev) => ({
      ...prev,
      ...pendingTicksRef.current,
    }));
    
    pendingTicksRef.current = {};
    flushRequestRef.current = null;
  }, []);

  const connect = useCallback((): void => {
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
          const volume = data.volume || data.v || data.s || 0;
          const timestamp = data.timestamp || data.t || Date.now();
          
          if (price) {
            // Buffer the tick update
            pendingTicksRef.current[symbol] = {
              p: price,
              s: volume,
              t: timestamp,
              sym: symbol
            };
            
            // Schedule a flush if one isn't already pending
            if (!flushRequestRef.current) {
                flushRequestRef.current = requestAnimationFrame(flushTicks);
            }
          }
        }
      } catch (e) {
        console.error("[LivePriceProvider] Error parsing message:", e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.warn("[LivePriceProvider] Disconnected.");
      // Reconnection can be handled by the caller or a future enhancement.
      // For now, avoid self-recursive reconnect logic to keep typing simple.
    };

    wsRef.current = ws;
  }, [flushTicks]);

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
    <LivePriceContext.Provider value={{ ticks, subscribe, unsubscribe, isConnected }}>
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

  return symbol ? context.ticks[symbol.toUpperCase()]?.p : undefined;
}

export function useLiveTick(symbol?: string) {
  const context = useContext(LivePriceContext);
  if (!context) {
    throw new Error("useLiveTick must be used within a LivePriceProvider");
  }

  useEffect(() => {
    if (symbol) {
      const sym = symbol.toUpperCase();
      context.subscribe(sym);
      return () => context.unsubscribe(sym);
    }
  }, [symbol, context]);

  return symbol ? context.ticks[symbol.toUpperCase()] : undefined;
}
