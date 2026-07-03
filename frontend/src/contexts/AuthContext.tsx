// frontend/src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authApi, tokenStorage } from "@/utils/api";
import type { User, LoginPayload, RegisterPayload } from "@/types";

interface AuthContextValue {
  user:            User | null;
  isAuthenticated: boolean;
  isLoading:       boolean;
  login:           (p: LoginPayload)    => Promise<void>;
  register:        (p: RegisterPayload) => Promise<void>;
  logout:          () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,      setUser]      = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = tokenStorage.getAccess();
    if (!token) { setIsLoading(false); return; }
    authApi.me()
      .then(setUser)
      .catch(() => tokenStorage.clearTokens())
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (p: LoginPayload) => {
    const tokens = await authApi.login(p);
    tokenStorage.setTokens(tokens);
    const me = await authApi.me();
    setUser(me);
  }, []);

  const register = useCallback(async (p: RegisterPayload) => {
    await authApi.register(p);
    await login({ email: p.email, password: p.password });
  }, [login]);

  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth باید داخل AuthProvider استفاده شود");
  return ctx;
}
