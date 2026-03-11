import React, { useState } from "react";
import { Mail, Lock, User, Loader2, Eye } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { API_BASE_URL } from "@/services/api_client";

export function LandingAuth() {
  const { login, loginAsGuest } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (mode === "register") {
        const res = await fetch(`${API_BASE_URL}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Registration failed");
        }
      }

      const formBody = new URLSearchParams();
      formBody.append("username", email);
      formBody.append("password", password);

      const loginRes = await fetch(`${API_BASE_URL}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formBody.toString(),
      });

      if (!loginRes.ok) {
        const errData = await loginRes.json();
        throw new Error(errData.detail || "Login failed");
      }

      const { access_token } = await loginRes.json();
      await login(access_token);

    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full flex items-center justify-center min-h-[70vh] animate-in fade-in duration-1000">
      <div className="relative w-full max-w-lg p-10 rounded-3xl border border-white/15 overflow-hidden backdrop-blur-sm bg-white/[0.08]"
        style={{ boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.12), 0 10px 25px -8px rgba(0,0,0,0.15)' }}
      >
        {/* Platinum frosted glass — metallic, see-through */}
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-b from-white/[0.06] via-transparent to-white/[0.02] pointer-events-none" />

        <div className="text-center mb-10 relative z-10">
          <div className="h-12 w-12 mx-auto mb-4 rounded-xl overflow-hidden bg-white/5 border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)] flex items-center justify-center relative group">
            <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/40 to-transparent opacity-100" />
            <span className="font-bold text-marble text-lg tracking-wider">AI</span>
          </div>
          <h2 className="text-3xl font-bold text-marble tracking-tight">
            {mode === "login" ? "Welcome Back" : "Start Tracking Market Alpha"}
          </h2>
          <p className="text-steel text-sm mt-3">
            {mode === "login"
              ? "Sign in to access your portfolio and custom watchlists."
              : "Create an account to unlock institutional-grade sentiment analysis."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center animate-in fade-in zoom-in slide-in-from-top-2">
              {error}
            </div>
          )}

          {mode === "register" && (
            <div className="relative group/input">
              <User className="absolute left-3 top-3.5 h-5 w-5 text-steel group-focus-within/input:text-blue-400 transition-colors" />
              <input
                type="text"
                name="fullName"
                autoComplete="name"
                placeholder="Full Name"
                required
                value={fullName}
                onChange={e => setFullName(e.target.value)}
                className="w-full bg-black/40 border border-white/5 rounded-xl py-3 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
              />
            </div>
          )}

          <div className="relative group/input">
            <Mail className="absolute left-3 top-3.5 h-5 w-5 text-steel group-focus-within/input:text-blue-400 transition-colors" />
            <input
              type="email"
              name="email"
              autoComplete="email"
              placeholder="Email Address"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-black/40 border border-white/5 rounded-xl py-3 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
            />
          </div>

          <div className="relative group/input">
            <Lock className="absolute left-3 top-3.5 h-5 w-5 text-steel group-focus-within/input:text-blue-400 transition-colors" />
            <input
              type="password"
              name="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder="Password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-black/40 border border-white/5 rounded-xl py-3 pl-10 pr-4 text-marble placeholder-steel/50 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="group relative w-full flex items-center justify-center py-3.5 px-4 border border-transparent text-sm font-bold tracking-wide rounded-xl text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500/50 focus:ring-offset-black transition-all shadow-[0_0_15px_rgba(37,99,235,0.4)] hover:shadow-[0_0_25px_rgba(37,99,235,0.6)] disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              mode === "login" ? "Sign In" : "Create Account"
            )}
          </button>
        </form>

        <div className="mt-8 text-center text-sm text-steel relative z-10 w-full flex flex-col items-center gap-3">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/5">
            <span>{mode === "login" ? "Don't have an account?" : "Already have an account?"}</span>
            <button
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="text-blue-400 hover:text-blue-300 font-bold transition-colors hover:underline"
            >
              {mode === "login" ? "Sign up" : "Sign in"}
            </button>
          </div>
          <button
            onClick={loginAsGuest}
            className="inline-flex items-center gap-1.5 text-xs text-steel/60 hover:text-steel transition-colors"
          >
            <Eye className="w-3.5 h-3.5" />
            Continue as Guest
          </button>
        </div>
      </div>
    </div>
  );
}
