"use client";

import { AuthProvider } from "@/contexts/AuthContext";
import { WatchlistProvider } from "@/hooks/useWatchlist";

export function ClientProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <WatchlistProvider>
        {children}
      </WatchlistProvider>
    </AuthProvider>
  );
}
