// frontend/src/layouts/DashboardLayout.tsx
// FIX-FE10: Link → NavLink (active state fix)
// FIX-FE10: close sidebar on navigate
// FIX-FE10: @ alias works now

import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, TrendingUp, Bell, FileText, Settings, LogOut, Menu, X, Activity, Zap } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const NAV = [
  { to: "/dashboard",   icon: LayoutDashboard, label: "داشبورد"   },
  { to: "/live-trades", icon: TrendingUp,      label: "معاملات"   },
  { to: "/signals",     icon: Zap,             label: "سیگنال‌ها"  },
  { to: "/analytics",   icon: Activity,        label: "تحلیل"      },
  { to: "/reports",     icon: FileText,        label: "گزارش‌ها"  },
  { to: "/settings",    icon: Settings,        label: "تنظیمات"   },
];

interface DashboardLayoutProps { children: React.ReactNode }

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const handleLogout = () => { logout(); navigate("/login", { replace: true }); };
  const NavItems = () => (
    <>
      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink key={to} to={to} onClick={() => setSidebarOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
              isActive ? "bg-sky-500/20 text-sky-400" : "text-slate-400 hover:bg-slate-800 hover:text-slate-300"
            }`
          }>
          <Icon className="w-5 h-5" />
          <span className="font-medium">{label}</span>
        </NavLink>
      ))}
    </>
  );
  return (
    <div className="min-h-screen bg-slate-900 flex" dir="rtl">
      <aside className="hidden lg:flex w-64 flex-col bg-slate-800/50 border-l border-slate-700/50">
        <div className="p-6 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div><h1 className="font-bold text-slate-100">Galaxy Vast</h1><p className="text-xs text-slate-500">AI Trading</p></div>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-1"><NavItems /></nav>
        <div className="p-4 border-t border-slate-700/50">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center">
              <span className="text-slate-300 font-medium">{user?.first_name?.[0] || user?.email?.[0] || "U"}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-slate-200 font-medium truncate">{user?.first_name || "کاربر"}</p>
              <p className="text-slate-500 text-sm truncate">{user?.email}</p>
            </div>
          </div>
          <button onClick={handleLogout} className="flex items-center gap-2 w-full px-3 py-2 text-slate-400 hover:text-rose-400 hover:bg-slate-700/50 rounded-lg transition-colors">
            <LogOut className="w-4 h-4" /><span className="text-sm">خروج</span>
          </button>
        </div>
      </aside>
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50 bg-black/50" onClick={() => setSidebarOpen(false)}>
          <aside className="w-64 h-full bg-slate-800 border-l border-slate-700" onClick={e => e.stopPropagation()}>
            <div className="p-4 flex justify-between items-center border-b border-slate-700">
              <h2 className="font-bold text-slate-100">منو</h2>
              <button onClick={() => setSidebarOpen(false)}><X className="w-5 h-5 text-slate-400" /></button>
            </div>
            <nav className="p-4 space-y-1"><NavItems /></nav>
          </aside>
        </div>
      )}
      <div className="flex-1 flex flex-col min-h-screen">
        <header className="bg-slate-800/50 border-b border-slate-700/50 px-4 py-3 lg:px-6">
          <div className="flex items-center justify-between">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden p-2 text-slate-400 hover:text-slate-200"><Menu className="w-6 h-6" /></button>
            <div className="flex items-center gap-4">
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 rounded-lg">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm text-slate-300">Kill Zone: لندن</span>
              </div>
              <button className="relative p-2 text-slate-400 hover:text-slate-200">
                <Bell className="w-5 h-5" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full" />
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-auto">{children}</main>
        <footer className="bg-slate-800/30 border-t border-slate-700/50 px-4 py-3 text-center">
          <p className="text-slate-600 text-sm">Galaxy Vast AI v2.0 • Enterprise Edition</p>
        </footer>
      </div>
    </div>
  );
}
