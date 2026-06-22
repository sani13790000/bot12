import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider }        from "./contexts/AuthContext";
import { WebSocketProvider }   from "./contexts/WebSocketContext";
import MainLayout              from "./layouts/MainLayout";
import Login                   from "./pages/Login";
import DashboardPage           from "./pages/DashboardPage";
import LiveTradesPage          from "./pages/LiveTradesPage";
import TradeHistoryPage        from "./pages/TradeHistoryPage";
import AIPredictionsPage       from "./pages/AIPredictionsPage";
import RiskPage                from "./pages/RiskPage";
import AnalyticsPage           from "./pages/AnalyticsPage";
import EquityCurvePage         from "./pages/EquityCurvePage";
import ModelPerformancePage    from "./pages/ModelPerformancePage";
import SettingsPage            from "./pages/SettingsPage";

export default function App() {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<MainLayout />}>
            <Route index                  element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard"         element={<DashboardPage />} />
            <Route path="live-trades"       element={<LiveTradesPage />} />
            <Route path="trade-history"     element={<TradeHistoryPage />} />
            <Route path="ai-predictions"    element={<AIPredictionsPage />} />
            <Route path="risk"              element={<RiskPage />} />
            <Route path="analytics"         element={<AnalyticsPage />} />
            <Route path="equity-curve"      element={<EquityCurvePage />} />
            <Route path="model-performance" element={<ModelPerformancePage />} />
            <Route path="settings"          element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </WebSocketProvider>
    </AuthProvider>
  );
}
