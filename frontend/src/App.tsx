/**
 * اپلیکیشن اصلی React
 *
 * نویسنده: MT5 Trading Team
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { TradesPage } from '@/pages/TradesPage';
import { SignalsPage } from '@/pages/SignalsPage';
import { ReportsPage } from '@/pages/ReportsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { AnalysisPage } from '@/pages/AnalysisPage';

// صفحه ورود
function LoginPage() {
  const { login, isLoading } = useAuth();
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      await login(email, password);
    } catch (err) {
      setError('ایمیل یا رمز عبور اشتباه است');
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" dir="rtl">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl text-white font-bold">M</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">MT5 Trading</h1>
          <p className="text-slate-500 mt-2">Enterprise Edition</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
          <h2 className="text-lg font-semibold text-slate-100 mb-6 text-center">ورود به سیستم</h2>

          {error && (
            <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400 text-sm text-center">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-slate-400 text-sm mb-2">ایمیل</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
                placeholder="email@example.com"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-sm mb-2">رمز عبور</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
                placeholder="********"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-sky-500/20 text-sky-400 py-3 rounded-lg font-medium hover:bg-sky-500/30 transition-colors disabled:opacity-50"
            >
              {isLoading ? 'در حال ورود...' : 'ورود'}
            </button>
          </div>
        </form>

        <p className="text-slate-600 text-center text-sm mt-6">
          نسخه 1.0.0 • MT5 Trading Team
        </p>
      </div>
    </div>
  );
}

// کامپوننت محافظت شده
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-slate-400">در حال بارگذاری...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

// روتینگ اصلی
function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DashboardPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/trades"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <TradesPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/signals"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <SignalsPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ReportsPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <SettingsPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/analysis"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <AnalysisPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

// اپلیکیشن اصلی
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
