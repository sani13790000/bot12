import { Routes, Route, Navigate } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import DashboardPage from "./pages/DashboardPage";
import TradesPage from "./pages/TradesPage";
import SignalsPage from "./pages/SignalsPage";
import PortfolioPage from "./pages/PortfolioPage";
import LearningPage from "./pages/LearningPage";
import BacktestPage from "./pages/BacktestPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"  element={<DashboardPage />} />
        <Route path="trades"     element={<TradesPage />} />
        <Route path="signals"    element={<SignalsPage />} />
        <Route path="portfolio"  element={<PortfolioPage />} />
        <Route path="learning"   element={<LearningPage />} />
        <Route path="backtest"   element={<BacktestPage />} />
        <Route path="settings"   element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
