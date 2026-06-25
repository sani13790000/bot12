/**
 * frontend/src/contexts/AuthContext.tsx
 *
 * FIX: localStorage key 'auth_token' -> 'gv_token'
 * FIX: localStorage key 'refresh_token' -> 'gv_refresh'
 * PROD-FIX-7: API_URL corrected — was 'http://localhost:8000/api' (extra /api suffix causing 404)
 * PROD-FIX-8: register() reads tokens directly from response (no redundant login() call)
 * PROD-FIX-9: All fetch paths updated to /api/v1/* prefix
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { User, UserSettings, ApiResponse } from '@/types';

interface AuthContextType {
  user: User | null;
  settings: UserSettings | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, full_name?: string) => Promise<void>;
  logout: () => void;
  updateSettings: (settings: Partial<UserSettings>) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// PROD-FIX-7: removed /api suffix — routes include /api/v1 prefix already
const API_URL = (import.meta.env?.VITE_API_URL as string | undefined) || 'http://localhost:8000';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]         = useState<User | null>(null);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [token, setToken]       = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('gv_token');
    if (storedToken) {
      setToken(storedToken);
      fetchCurrentUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchCurrentUser = async (authToken: string) => {
    try {
      // PROD-FIX-9: /api/v1/auth/me
      const response = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (response.ok) {
        const data: ApiResponse<User> = await response.json();
        if (data.success && data.data) {
          setUser(data.data);
          await fetchSettings(authToken);
        }
      } else {
        logout();
      }
    } catch {
      logout();
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSettings = async (authToken: string) => {
    try {
      // PROD-FIX-9: /api/v1/users/settings
      const response = await fetch(`${API_URL}/api/v1/users/settings`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (response.ok) {
        const data: ApiResponse<UserSettings> = await response.json();
        if (data.success && data.data) setSettings(data.data);
      }
    } catch {
      /* settings are optional */
    }
  };

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      // PROD-FIX-9: /api/v1/auth/login
      const response = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'خطا در ورود');
      }
      // PROD-FIX-4: backend now returns access_token + refresh_token + user in body
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem('gv_token', data.access_token);
      localStorage.setItem('gv_refresh', data.refresh_token);
      await fetchSettings(data.access_token);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    full_name?: string,
  ) => {
    setIsLoading(true);
    try {
      // PROD-FIX-8: read tokens from register response directly (was calling login() again)
      // PROD-FIX-9: /api/v1/auth/register
      const response = await fetch(`${API_URL}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, full_name: full_name || '' }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'خطا در ثبت‌نام');
      }
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem('gv_token', data.access_token);
      localStorage.setItem('gv_refresh', data.refresh_token);
      await fetchSettings(data.access_token);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setSettings(null);
    setToken(null);
    localStorage.removeItem('gv_token');
    localStorage.removeItem('gv_refresh');
  }, []);

  const updateSettings = useCallback(async (newSettings: Partial<UserSettings>) => {
    if (!token) return;
    try {
      const response = await fetch(`${API_URL}/api/v1/users/settings`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings),
      });
      const data: ApiResponse<UserSettings> = await response.json();
      if (data.success && data.data) setSettings(data.data);
    } catch (error) {
      console.error('updateSettings error:', error);
      throw error;
    }
  }, [token]);

  const refreshUser = useCallback(async () => {
    if (token) await fetchCurrentUser(token);
  }, [token]);

  return (
    <AuthContext.Provider value={{
      user, settings, token,
      isAuthenticated: !!user && !!token,
      isLoading,
      login, register, logout, updateSettings, refreshUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth باید داخل AuthProvider استفاده شود');
  return context;
}
