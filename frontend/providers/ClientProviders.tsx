"use client";

import { AuthProvider } from "@/contexts/AuthContext";
import { WatchlistProvider } from "@/hooks/useWatchlist";
import { LivePriceProvider } from "@/components/features/LivePriceProvider";

export function ClientProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <WatchlistProvider>
        <LivePriceProvider>
          {children}
        </LivePriceProvider>
      </WatchlistProvider>
    </AuthProvider>
  );
}
