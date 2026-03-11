"use client";

import { Search, User, Bell, LogIn, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { SymbolSearch } from "@/components/features/SymbolSearch";
import { useWatchlist } from "@/hooks/useWatchlist";

export function TopNav() {
  const { user, isGuest, openAuthModal, logout } = useAuth();
  const { addSymbol } = useWatchlist();

  return (
    <header className="sticky top-0 z-40 w-full true-glass !border-t-0 !border-l-0 !border-r-0 !rounded-none">
      <div className="flex h-16 items-center justify-between px-6 xl:px-8 max-w-[1600px] mx-auto">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl overflow-hidden bg-white/5 border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)] flex items-center justify-center relative group cursor-pointer">
            <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <span className="font-bold text-marble text-sm tracking-wider">AI</span>
          </div>
          <span className="font-semibold text-lg text-marble tracking-tight">Analyzer Pro</span>
        </div>
        
        {/* Live Symbol Search */}
        <SymbolSearch onAddSymbol={addSymbol} />
        
        {/* User Actions */}
        <div className="flex items-center gap-5">
          <button className="text-steel hover:text-marble transition-colors relative group">
            <Bell className="h-5 w-5 group-hover:animate-bounce" />
            <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-blue-500 animate-pulse shadow-[0_0_10px_rgba(59,130,246,0.8)]"></span>
          </button>
          
          {user ? (
            <div className="flex items-center gap-3 border-l border-white/10 pl-4 ml-1">
              <span className="text-sm font-semibold text-marble hidden sm:block tracking-wide">
                {user.full_name || user.email.split('@')[0]}
              </span>
              <button 
                onClick={logout}
                className="h-9 w-9 rounded-full bg-black/30 border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] flex items-center justify-center cursor-pointer hover:border-red-500/50 hover:text-red-400 hover:bg-red-500/10 transition-all group"
                title="Log out"
              >
                <LogOut className="h-4 w-4 text-steel group-hover:text-red-400" />
              </button>
            </div>
          ) : isGuest ? (
            <div className="flex items-center gap-3 border-l border-white/10 pl-4 ml-1">
              <span className="text-xs text-steel/50 hidden sm:block">Guest</span>
              <button 
                onClick={() => openAuthModal("register")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 text-steel hover:text-marble hover:border-white/20 transition-all text-xs font-semibold"
              >
                <LogIn className="w-3.5 h-3.5" />
                Create Account
              </button>
              <button 
                onClick={logout}
                className="h-8 w-8 rounded-full bg-black/30 border border-white/10 flex items-center justify-center cursor-pointer hover:border-red-500/50 hover:bg-red-500/10 transition-all group"
                title="Exit guest mode"
              >
                <LogOut className="h-3.5 w-3.5 text-steel group-hover:text-red-400" />
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
