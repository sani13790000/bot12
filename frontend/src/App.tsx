// frontend/src/App.tsx
// FIX-FE8: /login route وجود نداشت → redirect loop
// FIX-FE8: lazy loading اضافه شد — کاهش bundle size
// FIX-FE8: ErrorBoundary per-page

import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { WebSocketProvider } from "./contexts/WebSocketContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import MainLayout from "./layouts/MainLayout";

const Login               = lazy(() => import("./pages/Login"));
const DashboardPage       = lazy(() => import("./pages/DashboardPage"));
const LiveTradesPage      = lazy(() => import("./pages/LiveTradesPage"));
const TradeHistoryPage    = lazy(() => import("./pages/TradeHistoryPage"));
const SignalsPage         = lazy(() => import("./pages/SignalsPage"));
const AIPredictionsPage   = lazy(() => import("./pages/AIPredictionsPage"));
const RiskPage            = lazy(() => import("./pages/RiskPage"));
const AnalyticsPage       = lazy(() => import("./pages/AnalyticsPage"));
const EquityCurvePage     = lazy(() => import("./pages/EquityCurvePage"));
const ModelPerformancePage = lazy(() => import("./pages/ModelPerformancePage"));
const SettingsPage        = lazy(() => import("./pages/SettingsPage"));

const PageLoader = () => (
  <div className="flex items-center justify-center min-h-[300px]">
    <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <WebSocketProvider>
      <Routes>
        <Route path="/login" element={<LazyPage><Login /></LazyPage>} />
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"         element={<LazyPage><DashboardPage /></LazyPage>} />
          <Route path="live-trades"       element={<LazyPage><LiveTradesPage /></LazyPage>} />
          <Route path="trade-history"     element={<LazyPage><TradeHistoryPage /></LazyPage>} />
          <Route path="signals"           element={<LazyPage><SignalsPage /></LazyPage>} />
          <Route path="ai-predictions"    element={<LazyPage><AIPredictionsPage /></LazyPage>} />
          <Route path="risk"              element={<LazyPage><RiskPage /></LazyPage>} />
          <Route path="analytics"         element={<LazyPage><AnalyticsPage /></LazyPage>} />
          <Route path="equity-curve"      element={<LazyPage><EquityCurvePage /></LazyPage>} />
          <Route path="model-performance" element={<LazyPage><ModelPerformancePage /></LazyPage>} />
          <Route path="settings"          element={<LazyPage><SettingsPage /></LazyPage>} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </WebSocketProvider>
  );
}
