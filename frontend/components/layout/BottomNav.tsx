"use client";

import { Home, List, MessageSquare } from "lucide-react";

export function BottomNav() {
  const openAIPanel = () => {
    window.dispatchEvent(new CustomEvent("open-ai-panel"));
  };

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      // Offset by roughly TopNav height + mobile padding
      const y = element.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top: y, behavior: "smooth" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 sm:hidden">
      {/* Seamless glass matching the background */}
      <div className="absolute inset-0 true-glass !border-none !rounded-none" />
      <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      
      <div className="relative flex justify-around items-center px-4 pb-safe pt-2 h-16">
        <button 
          onClick={() => scrollToSection("market-overview")}
          className="flex flex-col items-center justify-center p-2 text-steel hover:text-marble transition-colors w-16"
        >
          <Home className="h-5 w-5 mb-1" />
          <span className="text-[10px] font-medium">Feed</span>
        </button>

        <button 
          onClick={() => scrollToSection("watchlist-section")}
          className="flex flex-col items-center justify-center p-2 text-steel hover:text-marble transition-colors w-16"
        >
          <List className="h-5 w-5 mb-1" />
          <span className="text-[10px] font-medium">Watchlist</span>
        </button>

        <button 
          onClick={openAIPanel}
          className="relative flex flex-col items-center justify-center p-2 text-steel transition-all group w-16 -mt-3"
        >
          <div className="absolute -inset-1 bg-gradient-to-tr from-blue-500/20 to-blue-300/10 rounded-full blur-sm opacity-0 group-hover:opacity-100 transition-opacity" />
          <div className="h-12 w-12 rounded-full true-glass border border-blue-500/30 flex items-center justify-center relative z-10 shadow-[0_0_15px_rgba(59,130,246,0.3)] group-hover:bg-blue-500/10 group-active:scale-95 transition-all text-blue-400">
            <MessageSquare className="h-5 w-5" />
          </div>
          <span className="text-[10px] font-medium text-blue-400 mt-1">AI Copilot</span>
        </button>
      </div>
    </div>
  );
}
