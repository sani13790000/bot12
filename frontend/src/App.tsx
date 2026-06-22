/**
 * frontend/src/App.tsx
 *
 * FIX-1: AuthProvider اضافه شد — useAuth در Login و سایر pages crash می‌کرد
 * FIX-2: /login route اضافه شد — redirect loop بی‌نهایت
 * FIX-3: React.lazy + Suspense — code splitting برای همه صفحات
 * FIX-4: ErrorBoundary per-route — یک crash نباید کل app را خراب کند
 * FIX-5: WebSocketProvider داخل AuthProvider — WS به token نیاز دارد
 * FIX-6: /register route اضافه شد — Login.tsx لینک register دارد
 */
import { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider }       from "./contexts/AuthContext";
import { WebSocketProvider }  from "./contexts/WebSocketContext";
import MainLayout             from "./layouts/MainLayout";
import { ErrorBoundary }      from "./components/common/ErrorBoundary";

/* FIX-3: lazy loading */
const Login               = lazy(() => import("./pages/Login"));
const DashboardPage       = lazy(() => import("./pages/DashboardPage"));
const LiveTradesPage      = lazy(() => import("./pages/LiveTradesPage"));
const TradeHistoryPage    = lazy(() => import("./pages/TradeHistoryPage"));
const AIPredictionsPage   = lazy(() => import("./pages/AIPredictionsPage"));
const RiskPage            = lazy(() => import("./pages/RiskPage"));
const AnalyticsPage       = lazy(() => import("./pages/AnalyticsPage"));
const EquityCurvePage     = lazy(() => import("./pages/EquityCurvePage"));
const ModelPerformancePage= lazy(() => import("./pages/ModelPerformancePage"));
const SettingsPage        = lazy(() => import("./pages/SettingsPage"));
const SignalsPage         = lazy(() => import("./pages/SignalsPage"));
const TradesPage          = lazy(() => import("./pages/TradesPage"));
const BacktestPage        = lazy(() => import("./pages/BacktestPage"));
const AnalysisPage        = lazy(() => import("./pages/AnalysisPage"));
const ReportsPage         = lazy(() => import("./pages/ReportsPage"));
const PortfolioPage       = lazy(() => import("./pages/PortfolioPage"));
const LearningPage        = lazy(() => import("./pages/LearningPage"));

function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center py-20">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login"    element={<Login />} />
              <Route path="/register" element={<Login />} />
              <Route path="/" element={<MainLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard"         element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                <Route path="live-trades"       element={<ErrorBoundary><LiveTradesPage /></ErrorBoundary>} />
                <Route path="trade-history"     element={<ErrorBoundary><TradeHistoryPage /></ErrorBoundary>} />
                <Route path="trades"            element={<ErrorBoundary><TradesPage /></ErrorBoundary>} />
                <Route path="signals"           element={<ErrorBoundary><SignalsPage /></ErrorBoundary>} />
                <Route path="ai-predictions"    element={<ErrorBoundary><AIPredictionsPage /></ErrorBoundary>} />
                <Route path="risk"              element={<ErrorBoundary><RiskPage /></ErrorBoundary>} />
                <Route path="analytics"         element={<ErrorBoundary><AnalyticsPage /></ErrorBoundary>} />
                <Route path="equity-curve"      element={<ErrorBoundary><EquityCurvePage /></ErrorBoundary>} />
                <Route path="model-performance" element={<ErrorBoundary><ModelPerformancePage /></ErrorBoundary>} />
                <Route path="backtest"          element={<ErrorBoundary><BacktestPage /></ErrorBoundary>} />
                <Route path="analysis"          element={<ErrorBoundary><AnalysisPage /></ErrorBoundary>} />
                <Route path="reports"           element={<ErrorBoundary><ReportsPage /></ErrorBoundary>} />
                <Route path="portfolio"         element={<ErrorBoundary><PortfolioPage /></ErrorBoundary>} />
                <Route path="learning"          element={<ErrorBoundary><LearningPage /></ErrorBoundary>} />
                <Route path="settings"          element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </WebSocketProvider>
    </AuthProvider>
  );
}
