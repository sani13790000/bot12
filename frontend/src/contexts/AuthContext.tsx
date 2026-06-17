/**
 * کانتکست احراز هویت
 *
 * نویسنده: MT5 Trading Team
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
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // بررسی توکن در localStorage
  useEffect(() => {
    const storedToken = localStorage.getItem('auth_token');
    if (storedToken) {
      setToken(storedToken);
      fetchCurrentUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  // دریافت کاربر جاری
  const fetchCurrentUser = async (authToken: string) => {
    try {
      const response = await fetch(`${API_URL}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
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
    } catch (error) {
      console.error('خطا در دریافت کاربر:', error);
      logout();
    } finally {
      setIsLoading(false);
    }
  };

  // دریافت تنظیمات
  const fetchSettings = async (authToken: string) => {
    try {
      const response = await fetch(`${API_URL}/users/settings`, {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      });

      if (response.ok) {
        const data: ApiResponse<UserSettings> = await response.json();
        if (data.success && data.data) {
          setSettings(data.data);
        }
      }
    } catch (error) {
      console.error('خطا در دریافت تنظیمات:', error);
    }
  };

  // ورود
  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, password })
      });

      const data: ApiResponse<{
        access_token: string;
        refresh_token: string;
        user: User;
      }> = await response.json();

      if (data.success && data.data) {
        setToken(data.data.access_token);
        setUser(data.data.user);
        localStorage.setItem('auth_token', data.data.access_token);
        localStorage.setItem('refresh_token', data.data.refresh_token);
        await fetchSettings(data.data.access_token);
      } else {
        throw new Error(data.error || 'خطا در ورود');
      }
    } catch (error) {
      console.error('خطا در ورود:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ثبت‌نام
  const register = useCallback(async (
    email: string,
    password: string,
    firstName?: string,
    lastName?: string
  ) => {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email,
          password,
          first_name: firstName,
          last_name: lastName
        })
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'خطا در ثبت‌نام');
      }

      // پس از ثبت‌نام موفق، ورود خودکار
      await login(email, password);
    } catch (error) {
      console.error('خطا در ثبت‌نام:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [login]);

  // خروج
  const logout = useCallback(() => {
    setUser(null);
    setSettings(null);
    setToken(null);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('refresh_token');
  }, []);

  // به‌روزرسانی تنظیمات
  const updateSettings = useCallback(async (newSettings: Partial<UserSettings>) => {
    if (!token) return;

    try {
      const response = await fetch(`${API_URL}/users/settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newSettings)
      });

      const data: ApiResponse<UserSettings> = await response.json();

      if (data.success && data.data) {
        setSettings(data.data);
      }
    } catch (error) {
      console.error('خطا در به‌روزرسانی تنظیمات:', error);
      throw error;
    }
  }, [token]);

  // رفرش کاربر
  const refreshUser = useCallback(async () => {
    if (token) {
      await fetchCurrentUser(token);
    }
  }, [token]);

  const value: AuthContextType = {
    user,
    settings,
    token,
    isAuthenticated: !!user && !!token,
    isLoading,
    login,
    register,
    logout,
    updateSettings,
    refreshUser
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth باید داخل AuthProvider استفاده شود');
  }
  return context;
}
