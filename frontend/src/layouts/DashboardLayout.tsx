// frontend/src/layouts/DashboardLayout.tsx
import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, TrendingUp, Zap, BarChart2, Brain,
  FlaskConical, Briefcase, LineChart, Activity, Shield,
  BookOpen, FileText, Cpu, History, Settings,
  Users, User, ChevronLeft, ChevronRight, LogOut, Wifi, WifiOff, AlertTriangle,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useWebSocket } from "@/contexts/WebSocketContext";

const NAV_ITEMS = [
  { to: "/dashboard",         icon: LayoutDashboard, label: "داشبورد" },
  { to: "/trades",            icon: TrendingUp,      label: "معاملات" },
  { to: "/trades/live",       icon: Activity,        label: "معاملات زنده" },
  { to: "/signals",           icon: Zap,             label: "سیگنال‌ها" },
  { to: "/analysis",          icon: BarChart2,        label: "تحلیل" },
  { to: "/ai-predictions",    icon: Brain,           label: "پیش‌بینی AI" },
  { to: "/backtest",          icon: FlaskConical,    label: "بک‌تست" },
  { to: "/portfolio",         icon: Briefcase,       label: "پورتفولیو" },
  { to: "/analytics",         icon: LineChart,       label: "آنالیتیکس" },
  { to: "/equity",            icon: TrendingUp,      label: "منحنی سرمایه" },
  { to: "/risk",              icon: Shield,          label: "مدیریت ریسک" },
  { to: "/learning",          icon: BookOpen,        label: "یادگیری" },
  { to: "/reports",           icon: FileText,        label: "گزارش‌ها" },
  { to: "/model-performance", icon: Cpu,             label: "عملکرد مدل" },
  { to: "/history",           icon: History,         label: "تاریخچه" },
  { to: "/settings",          icon: Settings,        label: "تنظیمات" },
  { to: "/overview",          icon: User,            label: "پروفایل" },
  { to: "/admin",             icon: Users,           label: "پنل ادمین", adminOnly: true },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout }   = useAuth();
  const { isConnected }    = useWebSocket();
  const navigate           = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = () => { logout(); navigate("/login"); };
  const visible = NAV_ITEMS.filter(i => !i.adminOnly || user?.role === "ADMIN");

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      <aside className={`flex flex-col border-r border-gray-800 bg-gray-900 transition-all duration-300 ${collapsed ? "w-16" : "w-60"}`}>
        <div className={`flex items-center gap-3 px-4 py-5 border-b border-gray-800 ${collapsed ? "justify-center" : ""}`}>
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shrink-0"><Zap size={16} /></div>
          {!collapsed && (<div><p className="text-sm font-bold text-white leading-none">Galaxy Vast</p><p className="text-xs text-gray-400 mt-0.5">AI Trading</p></div>)}
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {visible.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} title={collapsed ? label : undefined}
              className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"} ${collapsed ? "justify-center" : ""}`}>
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-gray-800 p-3 space-y-2">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs ${isConnected ? "text-green-400" : "text-red-400"} ${collapsed ? "justify-center" : ""}`}>
            {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
            {!collapsed && <span>{isConnected ? "متصل" : "قطع"}</span>}
          </div>
          {!collapsed && user && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800">
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold shrink-0">{user.full_name?.[0]?.toUpperCase() ?? "U"}</div>
              <div className="flex-1 min-w-0"><p className="text-xs font-medium text-white truncate">{user.full_name}</p><p className="text-xs text-gray-400">{user.role}</p></div>
            </div>
          )}
          <button onClick={handleLogout} className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs text-gray-400 hover:bg-red-500/10 hover:text-red-400 transition-colors ${collapsed ? "justify-center" : ""}`}>
            <LogOut size={14} />{!collapsed && <span>خروج</span>}
          </button>
          <button onClick={() => setCollapsed(p => !p)} className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors ${collapsed ? "justify-center" : ""}`}>
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            {!collapsed && <span>جمع کردن</span>}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-gray-950">
        <KillSwitchBanner />
        {children}
      </main>
    </div>
  );
}

function KillSwitchBanner() {
  const { subscribe } = useWebSocket();
  const [active, setActive] = React.useState(false);
  React.useEffect(() => subscribe("kill_switch", (d: unknown) => setActive(!!(d as { active: boolean }).active)), [subscribe]);
  if (!active) return null;
  return (
    <div className="flex items-center gap-2 bg-red-600 px-4 py-2 text-sm font-medium text-white">
      <AlertTriangle size={16} />
      <span>Kill Switch فعال است — همه معاملات متوقف شده‌اند</span>
    </div>
  );
}
