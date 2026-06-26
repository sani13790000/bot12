/**
 * frontend/src/App.tsx
 * P9-FIX-6: /overview route added (CustomerOverviewPage)
 * P9-FIX-7: /admin route added (AdminUsersPage — role-gated inside component)
 * P9-FIX-8: /admin/devices → AdminUsersPage with tab param
 * P9-FIX-9: DashboardLayout wraps all private routes (not just MainLayout)
 */
import { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { WebSocketProvider }     from "./contexts/WebSocketContext";
import { DashboardLayout }       from "./layouts/DashboardLayout";
import { ErrorBoundary }         from "./components/common/ErrorBoundary";

// └ page imports └-----------------------------------------------------------------
const Login                = lazy(() => import("./pages/Login"));
const Register             = lazy(() => import("./pages/Register"));
const CustomerOverviewPage = lazy(() => import("./pages/CustomerOverviewPage"));
const DashboardPage        = lazy(() => import("./pages/DashboardPage"));
const LiveTradesPage       = lazy(() => import("./pages/LiveTradesPage"));
const TradeHistoryPage     = lazy(() => import("./pages/TradeHistoryPage"));
const AIPredictionsPage    = lazy(() => import("./pages/AIPredictionsPage"));
const RiskPage             = lazy(() => import("./pages/RiskPage"));
const AnalyticsPage        = lazy(() => import("./pages/AnalyticsPage"));
const EquityCurvePage      = lazy(() => import("./pages/EquityCurvePage"));
const ModelPerformancePage = lazy(() => import("./pages/ModelPerformancePage"));
const SettingsPage         = lazy(() => import("./pages/SettingsPage"));
const SignalsPage           = lazy(() => import("./pages/SignalsPage"));
const TradesPage           = lazy(() => import("./pages/TradesPage"));
const BacktestPage         = lazy(() => import("./pages/BacktestPage"));
const AnalysisPage         = lazy(() => import("./pages/AnalysisPage"));
const ReportsPage          = lazy(() => import("./pages/ReportsPage"));
const PortfolioPage        = lazy(() => import("./pages/PortfolioPage"));
const LearningPage         = lazy(() => import("./pages/LearningPage"));
const AdminUsersPage       = lazy(() => import("./pages/AdminUsersPage"));  // P9-FIX-7

function PageLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-slate-900">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
    </div>
  );
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <PageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <PageLoader />;
  if (isAuthenticated) return <Navigate to="/overview" replace />;
  return <>{children}</>;
}

function PrivatePage({ children }: { children: React.ReactNode }) {
  return (
    <PrivateRoute>
      <DashboardLayout>
        <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>{children}</Suspense>
        </ErrorBoundary>
      </DashboardLayout>
    </PrivateRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {* Public *}
              <Route path="/login"    element={<PublicRoute><Login /></PublicRoute>} />
              <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />

              {* Customer pages *}
              <Route path="/overview"         element={<PrivatePage><CustomerOverviewPage /></PrivatePage>} />
              <Route path="/dashboard"        element={<PrivatePage><DashboardPage /></PrivatePage>} />
              <Route path="/live-trades"      element={<PrivatePage><LiveTradesPage /></PrivatePage>} />
              <Route path="/trade-history"    element={<PrivatePage><TradeHistoryPage /></PrivatePage>} />
              <Route path="/trades"           element={<PrivatePage><TradesPage /></PrivatePage>} />
              <Route path="/signals"          element={<PrivatePage><SignalsPage /></PrivatePage>} />
              <Route path="/ai-predictions"   element={<PrivatePage><AIPredictionsPage /></PrivatePage>} />
              <Route path="/risk"             element={<PrivatePage><RiskPage /></PrivatePage>} />
              <Route path="/analytics"        element={<PrivatePage><AnalyticsPage /></PrivatePage>} />
              <Route path="/equity-curve"     element={<PrivatePage><EquityCurvePage /></PrivatePage>} />
              <Route path="/model-performance" element={<PrivatePage><ModelPerformancePage /></PrivatePage>} />
              <Route path="/backtest"         element={<PrivatePage><BacktestPage /></PrivatePage>} />
              <Route path="/analysis"         element={<PrivatePage><AnalysisPage /></PrivatePage>} />
              <Route path="/reports"          element={<PrivatePage><ReportsPage /></PrivatePage>} />
              <Route path="/portfolio"        element={<PrivatePage><PortfolioPage /></PrivatePage>} />
              <Route path="/learning"         element={<PrivatePage><LearningPage /></PrivatePage>} />
              <Route path="/settings"         element={<PrivatePage><SettingsPage /></PrivatePage>} />

              {* Admin pages — role check inside AdminUsersPage *}
              <Route path="/admin"            element={<PrivatePage><AdminUsersPage /></PrivatePage>} />
              <Route path="/admin/devices"    element={<PrivatePage><AdminUsersPage /></PrivatePage>} />

              {* Root & 404 *}
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </WebSocketProvider>
    </AuthProvider>
  );
}
