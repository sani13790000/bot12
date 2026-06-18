import { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Activity, History, Brain, ShieldAlert,
  BarChart2, TrendingUp, Cpu, Settings, ChevronRight,
  ChevronLeft, Menu, X, LogOut, Zap
} from "lucide-react";
import { WSIndicator } from "../components/common/WSIndicator";

const NAV_ITEMS = [
  { path: "dashboard",      label: "داشبورد",         icon: LayoutDashboard },
  { path: "live-trades",    label: "معاملات زنده",     icon: Activity        },
  { path: "trade-history",  label: "تاریخچه",          icon: History         },
  { path: "ai-predictions", label: "پیش‌بینی هوش مصنوعی", icon: Brain       },
  { path: "risk",           label: "مدیریت ریسک",      icon: ShieldAlert     },
  { path: "analytics",      label: "آنالیتیکس",        icon: BarChart2       },
  { path: "equity-curve",   label: "منحنی سرمایه",     icon: TrendingUp      },
  { path: "model-performance", label: "عملکرد مدل",    icon: Cpu             },
  { path: "settings",       label: "تنظیمات",          icon: Settings        },
];

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem("gv_token");
    navigate("/login");
  };

  const Sidebar = () => (
    <aside className={`
      flex flex-col h-full bg-[#0d1420] border-l border-[#1e2d40]
      transition-all duration-300 ease-in-out
      ${collapsed ? "w-[64px]" : "w-[240px]"}
    `}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-[#1e2d40] min-h-[68px]">
        <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#0ea5e9] flex items-center justify-center shadow-lg">
          <Zap size={18} className="text-[#070b12]" strokeWidth={2.5} />
        </div>
        {!collapsed && (
          <div>
            <div className="text-[#f0f6ff] font-bold text-sm leading-tight">Galaxy Vast</div>
            <div className="text-[#00d4ff] text-[10px] font-mono">AI TRADING</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) => `
              flex items-center gap-3 px-4 py-3 my-0.5 mx-2 rounded-xl
              transition-all duration-200 cursor-pointer group
              ${isActive ? "nav-item-active" : "text-[#94a3b8] hover:text-[#f0f6ff] hover:bg-[#111827]"}
              ${collapsed ? "justify-center" : ""}
            `}
            title={collapsed ? label : undefined}
          >
            <Icon size={18} className="flex-shrink-0" />
            {!collapsed && <span className="text-sm">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse + Logout */}
      <div className="border-t border-[#1e2d40] p-3 space-y-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center p-2.5 rounded-xl text-[#475569] hover:text-[#00d4ff] hover:bg-[#111827] transition-all"
          title={collapsed ? "باز کردن" : "جمع کردن"}
        >
          {collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
        <button
          onClick={handleLogout}
          className="w-full flex items-center justify-center gap-2 p-2.5 rounded-xl text-[#475569] hover:text-[#ef4444] hover:bg-[#ef444410] transition-all"
          title="خروج"
        >
          <LogOut size={16} />
          {!collapsed && <span className="text-xs">خروج</span>}
        </button>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-[#070b12]">
      {/* Desktop Sidebar */}
      <div className="hidden md:flex flex-shrink-0">
        <Sidebar />
      </div>

      {/* Mobile Sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setMobileOpen(false)} />
          <div className="absolute right-0 top-0 bottom-0 w-[240px]">
            <Sidebar />
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center justify-between px-4 py-3 bg-[#0d1420] border-b border-[#1e2d40] min-h-[60px]">
          <button
            className="md:hidden text-[#94a3b8] hover:text-[#00d4ff] transition-colors"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="flex items-center gap-3 mr-auto">
            <WSIndicator />
            <div className="text-[#475569] text-xs font-mono hidden sm:block">
              {new Date().toLocaleDateString("fa-IR")}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
