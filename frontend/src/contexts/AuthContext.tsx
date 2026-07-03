// frontend/src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import { authApi, tokenStorage } from "@/utils/api";
import type { User, LoginPayload, RegisterPayload } from "@/types";

interface AuthContextValue {
  user: User | null;
  role: "USER" | "ADMIN" | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  error: string | null;
  login: (p: LoginPayload) => Promise<void>;
  register: (p: RegisterPayload) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,      setUser]      = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  const loadUser = useCallback(async () => {
    const token = tokenStorage.getAccess();
    if (!token) { setIsLoading(false); return; }
    try { const me = await authApi.me(); setUser(me); }
    catch { tokenStorage.clearTokens(); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { loadUser(); }, [loadUser]);

  const login = useCallback(async (p: LoginPayload) => {
    setError(null);
    try {
      const tokens = await authApi.login(p);
      tokenStorage.setTokens(tokens);
      setUser(await authApi.me());
    } catch (e: any) {
      const msg = e?.message ?? "خطا در ورود";
      setError(msg); throw new Error(msg);
    }
  }, []);

  const register = useCallback(async (p: RegisterPayload) => {
    setError(null);
    try { await authApi.register(p); await login({ email: p.email, password: p.password }); }
    catch (e: any) { const msg = e?.message ?? "خطا در ثبت‌نام"; setError(msg); throw new Error(msg); }
  }, [login]);

  const logout = useCallback(() => {
    authApi.logout().catch(() => {});
    tokenStorage.clearTokens(); setUser(null); setError(null);
  }, []);

  const clearError  = useCallback(() => setError(null), []);
  const refreshUser = useCallback(async () => {
    try { setUser(await authApi.me()); } catch { logout(); }
  }, [logout]);

  const value = useMemo<AuthContextValue>(() => ({
    user, role: (user as any)?.role ?? null,
    isAuthenticated: !!user, isAdmin: (user as any)?.role === "ADMIN",
    isLoading, error, login, register, logout, clearError, refreshUser,
  }), [user, isLoading, error, login, register, logout, clearError, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth باید داخل AuthProvider استفاده شود");
  return ctx;
}
