"use client";

import { MessageSquare, X, Send } from "lucide-react";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export function AIPanel() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      {/* Floating Toggle Button (visible when closed) */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            className="fixed bottom-8 right-8 z-40"
          >
            <button
              onClick={() => setIsOpen(true)}
              className="h-16 w-16 rounded-2xl true-glass flex items-center justify-center hover:bg-white/10 transition-all hover:-translate-y-1 hover:shadow-[0_0_30px_rgba(59,130,246,0.5)] text-marble group relative overflow-hidden"
            >
              <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <MessageSquare className="h-7 w-7 group-hover:text-blue-400 transition-colors relative z-10" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* The Slide-out Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed top-0 right-0 h-screen w-full sm:w-[420px] true-glass !rounded-none !border-t-0 !border-r-0 !border-b-0 shadow-[0_0_60px_rgba(0,0,0,0.8)] z-50 flex flex-col"
          >
            {/* Panel Header */}
            <div className="flex items-center justify-between p-5 border-b border-glass-border bg-black/20">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)]">
                  <MessageSquare className="h-4 w-4" />
                </div>
                <h3 className="font-bold text-marble tracking-wide">AI Copilot</h3>
              </div>
              <button 
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg bg-black/20 border border-white/5 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] hover:border-white/10 hover:bg-white/5 text-steel hover:text-marble transition-all"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Chat Area */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              <div className="bg-white/5 backdrop-blur-md shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] rounded-xl p-4 border border-white/10 text-sm leading-relaxed text-marble/90 inline-block max-w-[90%] font-medium">
                Hello! I'm your AI Analyzer. I'm currently monitoring global markets. How can I assist with your portfolio today?
              </div>
            </div>

            {/* Input Area */}
            <div className="p-5 border-t border-glass-border bg-black/20 relative">
              <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
              <div className="relative">
                <input 
                  type="text" 
                  placeholder="Ask about AAPL or your portfolio..." 
                  className="w-full bg-black/40 border border-white/5 rounded-xl py-3.5 pl-4 pr-12 text-sm text-marble focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 shadow-inner placeholder:text-steel/40 transition-all font-mono"
                />
                <button className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg hover:bg-blue-500/10 true-glass !border-none text-marble transition-colors flex items-center justify-center group pointer-events-auto">
                  <Send className="h-4 w-4 text-steel group-hover:text-blue-400" />
                </button>
              </div>
              <p className="text-xs text-steel/40 text-center mt-3 font-mono">
                AI can make mistakes. Consider verifying options.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
