/**
 * frontend/src/layouts/MainLayout.tsx
 * FIX-E3: Missing layout — App.tsx imported MainLayout from layouts/ -> build fail
 */
import { useEffect, useState } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useWebSocket } from "../contexts/WebSocketContext";
import {
  LayoutDashboard, TrendingUp, History, Brain,
  Shield, BarChart2, LineChart, Activity,
  Settings, LogOut, Menu, X, Wifi, WifiOff,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/dashboard",         label: "داشبورد",        icon: LayoutDashboard },
  { to: "/live-trades",       label: "معاملات زنده",   icon: TrendingUp },
  { to: "/trade-history",     label: "تاریخچه",        icon: History },
  { to: "/ai-predictions",    label: "پیش‌بینی AI",    icon: Brain },
  { to: "/risk",              label: "مدیریت ریسک",    icon: Shield },
  { to: "/analytics",         label: "آنالیتیکس",      icon: BarChart2 },
  { to: "/equity-curve",      label: "منحنی سرمایه",   icon: LineChart },
  { to: "/model-performance", label: "عملکرد مدل",     icon: Activity },
  { to: "/settings",          label: "تنظیمات",        icon: Settings },
];

export default function MainLayout() {
  const navigate        = useNavigate();
  const location        = useLocation();
  const { isConnected } = useWebSocket();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("gv_token")) navigate("/login", { replace: true });
  }, [navigate]);

  useEffect(() => { setOpen(false); }, [location.pathname]);

  const logout = () => {
    localStorage.removeItem("gv_token");
    localStorage.removeItem("gv_refresh");
    navigate("/login", { replace: true });
  };

  const SidebarContent = () => (
    <aside className="flex flex-col h-full bg-gray-900 border-r border-gray-800 w-64">
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-800">
        <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
          <TrendingUp className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-none">Galaxy Vast</p>
          <p className="text-gray-500 text-xs mt-0.5">AI Trading</p>
        </div>
      </div>
      <div className="px-6 py-3 border-b border-gray-800">
        <div className={`flex items-center gap-2 text-xs ${isConnected ? "text-green-400" : "text-gray-500"}`}>
          {isConnected
            ? <><Wifi className="w-3.5 h-3.5" /> اتصال زنده</>
            : <><WifiOff className="w-3.5 h-3.5" /> در حال اتصال...</>}
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`
            }>
            <Icon className="w-4 h-4 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="px-3 py-4 border-t border-gray-800">
        <button onClick={logout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:bg-red-900/30 hover:text-red-300 transition-colors">
          <LogOut className="w-4 h-4 shrink-0" />
          <span>خروج</span>
        </button>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      <div className="hidden lg:flex flex-col shrink-0"><SidebarContent /></div>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />
      )}
      <div className={`fixed inset-y-0 left-0 z-50 flex flex-col lg:hidden transition-transform duration-300 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <SidebarContent />
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="lg:hidden flex items-center gap-4 px-4 py-3 border-b border-gray-800 bg-gray-900">
          <button onClick={() => setOpen(v => !v)} className="text-gray-400 hover:text-white">
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <span className="text-white font-semibold text-sm">Galaxy Vast AI</span>
        </header>
        <main className="flex-1 overflow-y-auto"><Outlet /></main>
      </div>
    </div>
  );
}
