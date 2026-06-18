import { useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Activity, History, Brain, ShieldCheck,
  BarChart3, TrendingUp, Cpu, Settings, Menu, X, Zap
} from "lucide-react";
import { WSIndicator } from "../components/common/WSIndicator";

const NAV = [
  { to: "/dashboard",       icon: LayoutDashboard, label: "داشبورد"         },
  { to: "/live-trades",     icon: Activity,        label: "معاملات زنده"    },
  { to: "/trade-history",   icon: History,         label: "تاریخچه"         },
  { to: "/ai-predictions",  icon: Brain,           label: "پیش‌بینی AI"     },
  { to: "/risk",            icon: ShieldCheck,     label: "مدیریت ریسک"     },
  { to: "/analytics",       icon: BarChart3,       label: "آنالیتیکس"       },
  { to: "/equity-curve",    icon: TrendingUp,      label: "منحنی Equity"    },
  { to: "/model-performance",icon: Cpu,            label: "عملکرد مدل"      },
  { to: "/settings",        icon: Settings,        label: "تنظیمات"         },
];

export default function MainLayout() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();

  return (
    <div className="min-h-screen bg-[#070b12] flex" dir="rtl">
      {/* Mobile overlay */}
      {open && (
        <div className="fixed inset-0 bg-black/60 z-20 md:hidden" onClick={() => setOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed md:sticky top-0 right-0 h-screen w-64 bg-[#0d1420] border-l border-[#1e2d40]
        flex flex-col z-30 transition-transform duration-300
        ${open ? "translate-x-0" : "translate-x-full md:translate-x-0"}
      `}>
        {/* Logo */}
        <div className="p-5 border-b border-[#1e2d40] flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#00d4ff]/15 border border-[#00d4ff]/30 flex items-center justify-center">
            <Zap size={18} className="text-[#00d4ff]" />
          </div>
          <div>
            <div className="text-[#f0f6ff] font-bold text-sm leading-tight">Galaxy Vast</div>
            <div className="text-[#475569] text-xs">AI Trading v3</div>
          </div>
          <button onClick={() => setOpen(false)} className="mr-auto md:hidden text-[#475569] hover:text-[#f0f6ff]">
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} onClick={() => setOpen(false)}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                ${isActive
                  ? "bg-[#00d4ff]/10 text-[#00d4ff] border border-[#00d4ff]/20"
                  : "text-[#475569] hover:text-[#f0f6ff] hover:bg-[#111827]"}
              `}>
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-[#1e2d40]">
          <WSIndicator />
          <div className="mt-2 text-[10px] text-[#2d3f55]">Galaxy Vast AI © 2025</div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-10 h-14 bg-[#0d1420]/90 backdrop-blur border-b border-[#1e2d40] flex items-center px-4 gap-3">
          <button onClick={() => setOpen(true)} className="md:hidden text-[#475569] hover:text-[#f0f6ff]">
            <Menu size={20} />
          </button>
          <span className="text-[#f0f6ff] font-semibold text-sm">
            {NAV.find(n => loc.pathname.startsWith(n.to))?.label ?? "Galaxy Vast"}
          </span>
          <div className="mr-auto hidden md:flex"><WSIndicator /></div>
        </header>

        {/* Page */}
        <main className="flex-1 p-4 md:p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
