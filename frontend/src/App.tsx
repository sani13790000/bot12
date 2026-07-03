/**
 * frontend/src/App.tsx
 * ─────────────────────────────────────────────
 * Galaxy Vast AI Trading Platform — Router اصلی
 *
 * ساختار مسیرها:
 *   /                    → redirect به /dashboard
 *   /login               → Login (عمومی)
 *   /register            → Register (عمومی)
 *   /dashboard           → DashboardPage       [نیاز به ورود]
 *   /trades              → TradesPage          [نیاز به ورود]
 *   /trades/live         → LiveTradesPage      [نیاز به ورود]
 *   /signals             → SignalsPage         [نیاز به ورود]
 *   /analysis            → AnalysisPage        [نیاز به ورود]
 *   /ai-predictions      → AIPredictionsPage   [نیاز به ورود]
 *   /backtest            → BacktestPage        [نیاز به ورود]
 *   /portfolio           → PortfolioPage       [نیاز به ورود]
 *   /analytics           → AnalyticsPage       [نیاز به ورود]
 *   /equity              → EquityCurvePage     [نیاز به ورود]
 *   /risk                → RiskPage            [نیاز به ورود]
 *   /learning            → LearningPage        [نیاز به ورود]
 *   /reports             → ReportsPage         [نیاز به ورود]
 *   /model-performance   → ModelPerformancePage[نیاز به ورود]
 *   /history             → TradeHistoryPage    [نیاز به ورود]
 *   /settings            → SettingsPage        [نیاز به ورود]
 *   /overview            → CustomerOverviewPage[نیاز به ورود]
 *   /admin               → AdminDashboardPage  [فقط ADMIN]
 *   /admin/users         → AdminUsersPage      [فقط ADMIN]
 *   *                    → صفحه 404
 */

import React, { Suspense, lazy } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { WebSocketProvider } from "@/contexts/WebSocketContext";
import DashboardLayout from "@/layouts/DashboardLayout";

// ── بارگذاری تنبل صفحات ──────────────────────────────────────────────────────
const Login                = lazy(() => import("@/pages/Login"));
const Register             = lazy(() => import("@/pages/Register"));
const DashboardPage        = lazy(() => import("@/pages/DashboardPage"));
const TradesPage           = lazy(() => import("@/pages/TradesPage"));
const LiveTradesPage       = lazy(() => import("@/pages/LiveTradesPage"));
const SignalsPage          = lazy(() => import("@/pages/SignalsPage"));
const AnalysisPage         = lazy(() => import("@/pages/AnalysisPage"));
const AIPredictionsPage    = lazy(() => import("@/pages/AIPredictionsPage"));
const BacktestPage         = lazy(() => import("@/pages/BacktestPage"));
const PortfolioPage        = lazy(() => import("@/pages/PortfolioPage"));
const AnalyticsPage        = lazy(() => import("@/pages/AnalyticsPage"));
const EquityCurvePage      = lazy(() => import("@/pages/EquityCurvePage"));
const RiskPage             = lazy(() => import("@/pages/RiskPage"));
const LearningPage         = lazy(() => import("@/pages/LearningPage"));
const ReportsPage          = lazy(() => import("@/pages/ReportsPage"));
const ModelPerformancePage = lazy(() => import("@/pages/ModelPerformancePage"));
const TradeHistoryPage     = lazy(() => import("@/pages/TradeHistoryPage"));
const SettingsPage         = lazy(() => import("@/pages/SettingsPage"));
const CustomerOverviewPage = lazy(() => import("@/pages/CustomerOverviewPage"));
const AdminDashboardPage   = lazy(() => import("@/pages/AdminDashboardPage"));
const AdminUsersPage       = lazy(() => import("@/pages/AdminUsersPage"));

// ── صفحه بارگذاری ────────────────────────────────────────────────────────────
function PageLoader() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <svg
          className="animate-spin w-8 h-8 text-blue-500"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12" cy="12" r="10"
            stroke="currentColor" strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span className="text-gray-400 text-sm">در حال بارگذاری...</span>
      </div>
    </div>
  );
}

// ── صفحه 404 ─────────────────────────────────────────────────────────────────
function NotFound() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center space-y-4">
        <p className="text-7xl font-bold text-gray-700">404</p>
        <p className="text-xl text-gray-400">صفحه مورد نظر یافت نشد</p>
        <a
          href="/dashboard"
          className="inline-block mt-2 px-6 py-2 rounded-lg bg-blue-600
                     hover:bg-blue-500 text-white transition-colors"
        >
          بازگشت به داشبورد
        </a>
      </div>
    </div>
  );
}

// ── Guard: فقط کاربران لاگین‌شده ─────────────────────────────────────────────
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <PageLoader />;

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

// ── Guard: فقط ADMIN ─────────────────────────────────────────────────────────
function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <PageLoader />;

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (user.role !== "ADMIN") {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

// ── Guard: redirect کاربران لاگین‌شده از صفحات عمومی ─────────────────────────
function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return <PageLoader />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}

// ── مسیرهای داخل DashboardLayout ─────────────────────────────────────────────
function ProtectedRoutes() {
  return (
    <RequireAuth>
      <WebSocketProvider>
        <DashboardLayout>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="dashboard"        element={<DashboardPage />} />
              <Route path="trades"           element={<TradesPage />} />
              <Route path="trades/live"      element={<LiveTradesPage />} />
              <Route path="signals"          element={<SignalsPage />} />
              <Route path="analysis"         element={<AnalysisPage />} />
              <Route path="ai-predictions"   element={<AIPredictionsPage />} />
              <Route path="backtest"         element={<BacktestPage />} />
              <Route path="portfolio"        element={<PortfolioPage />} />
              <Route path="analytics"        element={<AnalyticsPage />} />
              <Route path="equity"           element={<EquityCurvePage />} />
              <Route path="risk"             element={<RiskPage />} />
              <Route path="learning"         element={<LearningPage />} />
              <Route path="reports"          element={<ReportsPage />} />
              <Route path="model-performance" element={<ModelPerformancePage />} />
              <Route path="history"          element={<TradeHistoryPage />} />
              <Route path="settings"         element={<SettingsPage />} />
              <Route path="overview"         element={<CustomerOverviewPage />} />

              {/* مسیرهای ADMIN */}
              <Route
                path="admin"
                element={
                  <RequireAdmin>
                    <AdminDashboardPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="admin/users"
                element={
                  <RequireAdmin>
                    <AdminUsersPage />
                  </RequireAdmin>
                }
              />

              {/* fallback داخل layout */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </DashboardLayout>
      </WebSocketProvider>
    </RequireAuth>
  );
}

// ── کامپوننت اصلی App ─────────────────────────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* redirect ریشه به داشبورد */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* صفحات عمومی */}
          <Route
            path="/login"
            element={
              <RedirectIfAuth>
                <Login />
              </RedirectIfAuth>
            }
          />
          <Route
            path="/register"
            element={
              <RedirectIfAuth>
                <Register />
              </RedirectIfAuth>
            }
          />

          {/* صفحات محافظت‌شده */}
          <Route path="/*" element={<ProtectedRoutes />} />

          {/* 404 */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </AuthProvider>
  );
}
