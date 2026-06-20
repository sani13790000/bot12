/**
 * frontend/src/contexts/AuthContext.tsx
 *
 * FIX: localStorage key 'auth_token' -> 'gv_token' (inconsistency with api.ts)
 * FIX: localStorage key 'refresh_token' -> 'gv_refresh' (same)
 * This was causing logout in api.ts to not clear AuthContext state.
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
  register: (email: string, password: string, firstName?: string, lastName?: string) => Promise<void>;
  logout: () => void;
  updateSettings: (settings: Partial<UserSettings>) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const API_URL = (import.meta.env?.VITE_API_URL as string | undefined) || 'http://localhost:8000/api';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]         = useState<User | null>(null);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [token, setToken]       = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // FIX: was 'auth_token' - inconsistent with api.ts which uses 'gv_token'
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
      const response = await fetch(`${API_URL}/auth/me`, {
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
      const response = await fetch(`${API_URL}/users/settings`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (response.ok) {
        const data: ApiResponse<UserSettings> = await response.json();
        if (data.success && data.data) setSettings(data.data);
      }
    } catch {
      /* settings are optional, ignore errors */
    }
  };

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data: ApiResponse<{ access_token: string; refresh_token: string; user: User }> =
        await response.json();

      if (data.success && data.data) {
        setToken(data.data.access_token);
        setUser(data.data.user);
        // FIX: was 'auth_token' and 'refresh_token' - now matches api.ts keys
        localStorage.setItem('gv_token', data.data.access_token);
        localStorage.setItem('gv_refresh', data.data.refresh_token);
        await fetchSettings(data.data.access_token);
      } else {
        throw new Error(data.error || '\u062e\u0637\u0627 \u062f\u0631 \u0648\u0631\u0648\u062f');
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    firstName?: string,
    lastName?: string,
  ) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, first_name: firstName, last_name: lastName }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || '\u062e\u0637\u0627 \u062f\u0631 \u062b\u0628\u062a\u200c\u0646\u0627\u0645');
      await login(email, password);
    } finally {
      setIsLoading(false);
    }
  }, [login]);

  const logout = useCallback(() => {
    setUser(null);
    setSettings(null);
    setToken(null);
    // FIX: was 'auth_token' and 'refresh_token'
    localStorage.removeItem('gv_token');
    localStorage.removeItem('gv_refresh');
  }, []);

  const updateSettings = useCallback(async (newSettings: Partial<UserSettings>) => {
    if (!token) return;
    try {
      const response = await fetch(`${API_URL}/users/settings`, {
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
  if (!context) throw new Error('useAuth \u0628\u0627\u06cc\u062f \u062f\u0627\u062e\u0644 AuthProvider \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u0634\u0648\u062f');
  return context;
}
