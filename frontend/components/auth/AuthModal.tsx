"use client";

import React, { useState } from "react";
import { X, Mail, Lock, User, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { API_BASE_URL } from "@/services/api_client";

export function AuthModal() {
  const { isAuthModalOpen, closeAuthModal, authMode, login, openAuthModal } = useAuth();
  
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isAuthModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (authMode === "register") {
        // Register flow
        const res = await fetch(`${API_BASE_URL}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });
        
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Registration failed");
        }
        // Auto-login after register by calling the token endpoint
      }

      // Login flow (runs immediately for login, or right after successful register)
      const formBody = new URLSearchParams();
      formBody.append("username", email);
      formBody.append("password", password);

      const loginRes = await fetch(`${API_BASE_URL}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formBody.toString(), // OAuth2PasswordRequestForm expects form data
      });

      if (!loginRes.ok) {
        const errData = await loginRes.json();
        throw new Error(errData.detail || "Login failed");
      }

      const { access_token } = await loginRes.json();
      await login(access_token);
      closeAuthModal();

    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-in fade-in duration-300">
      {/* Dark Blur Overlay */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm" 
        onClick={closeAuthModal}
      />
      
      {/* Modal Container */}
      <div className="relative w-full max-w-md p-8 rounded-2xl true-glass border border-white/10 shadow-2xl animate-in zoom-in-95 slide-in-from-bottom-10 duration-500 overflow-hidden">
        {/* Glow Effects */}
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-blue-500/50 to-transparent" />
        <div className="absolute -top-32 -right-32 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl rounded-full" />
        <div className="absolute -bottom-32 -left-32 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl rounded-full" />
        
        <button 
          onClick={closeAuthModal} 
          className="absolute top-4 right-4 p-2 text-steel hover:text-marble hover:bg-white/10 rounded-full transition-colors z-10"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-8 relative z-10">
          <h2 className="text-2xl font-bold text-marble tracking-tight">
            {authMode === "login" ? "Welcome Back" : "Create Account"}
          </h2>
          <p className="text-steel text-sm mt-2">
            {authMode === "login" 
              ? "Sign in to access your portfolio and custom watchlists." 
              : "Join our platform for advanced market tracking."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center animate-in fade-in zoom-in slide-in-from-top-2">
              {error}
            </div>
          )}

          {authMode === "register" && (
            <div className="relative group">
              <User className="absolute left-3 top-3 h-5 w-5 text-steel group-focus-within:text-blue-400 transition-colors" />
              <input
                type="text"
                placeholder="Full Name"
                required
                value={fullName}
                onChange={e => setFullName(e.target.value)}
                className="w-full bg-black/40 border border-white/5 rounded-xl py-2.5 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
              />
            </div>
          )}

          <div className="relative group">
            <Mail className="absolute left-3 top-3 h-5 w-5 text-steel group-focus-within:text-blue-400 transition-colors" />
            <input
              type="email"
              placeholder="Email Address"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-black/40 border border-white/5 rounded-xl py-2.5 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
            />
          </div>

          <div className="relative group">
            <Lock className="absolute left-3 top-3 h-5 w-5 text-steel group-focus-within:text-blue-400 transition-colors" />
            <input
              type="password"
              placeholder="Password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-black/40 border border-white/5 rounded-xl py-2.5 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="group relative w-full flex items-center justify-center py-3 px-4 border border-transparent text-sm font-semibold rounded-xl text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500/50 focus:ring-offset-black transition-all shadow-[0_0_15px_rgba(37,99,235,0.4)] hover:shadow-[0_0_25px_rgba(37,99,235,0.6)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              authMode === "login" ? "Sign In" : "Register Now"
            )}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-steel relative z-10">
          {authMode === "login" ? (
            <p>
              Don't have an account?{" "}
              <button onClick={() => openAuthModal("register")} className="text-blue-400 hover:text-blue-300 font-semibold transition-colors hover:underline">
                Sign up
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{" "}
              <button onClick={() => openAuthModal("login")} className="text-blue-400 hover:text-blue-300 font-semibold transition-colors hover:underline">
                Sign in
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
