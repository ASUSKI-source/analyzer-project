"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { API_BASE_URL } from "@/services/api_client";

type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_premium: boolean;
};

type AuthContextType = {
  user: User | null;
  isGuest: boolean;
  loading: boolean;
  login: (token: string) => Promise<void>;
  loginAsGuest: () => void;
  logout: () => void;
  openAuthModal: (mode?: "login" | "register") => void;
  closeAuthModal: () => void;
  isAuthModalOpen: boolean;
  authMode: "login" | "register";
  updateUser: (updates: Partial<User>) => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isGuest, setIsGuest] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  useEffect(() => {
    // Check for existing session token on mount
    const checkSession = async () => {
      const token = localStorage.getItem("token");
      if (token) {
        await hydrateUser(token);
      } else {
        setLoading(false);
      }
    };
    checkSession();
  }, []);

  const hydrateUser = async (token: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("auth-hydrated"));
        }
      } else {
        localStorage.removeItem("token");
      }
    } catch (e) {
      console.error("Hydration failed", e);
    } finally {
      setLoading(false);
    }
  };

  const login = async (token: string) => {
    localStorage.setItem("token", token);
    await hydrateUser(token);
  };

  const loginAsGuest = () => {
    setIsGuest(true);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    setIsGuest(false);
  };

  const openAuthModal = (mode: "login" | "register" = "login") => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
  };

  const closeAuthModal = () => {
    setIsAuthModalOpen(false);
  };

  const updateUser = async (updates: Partial<User>): Promise<void> => {
    if (!user) return;
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE_URL}/users/me`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      }
    } catch (e) {
      console.error("Failed to update user", e);
    }
  };

  return (
    <AuthContext.Provider value={{
      user, isGuest, loading, login, loginAsGuest, logout, 
      openAuthModal, closeAuthModal, isAuthModalOpen, authMode,
      updateUser
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
