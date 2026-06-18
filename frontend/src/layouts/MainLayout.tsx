import { useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, TrendingUp, Zap, Shield,
  Brain, FlaskConical, Settings, ChevronLeft,
  Activity, Bell, Moon,
} from "lucide-react";

// ── Nav items ────────────────────────────────────────────────
const NAV_ITEMS = [
  { to: "/dashboard", icon: LayoutDashboard, label: "داشبورد" },
  { to: "/trades",    icon: TrendingUp,       label: "معاملات" },
  { to: "/signals",   icon: Zap,              label: "سیگنال‌ها" },
  { to: "/portfolio", icon: Shield,            label: "ریسک پرتفولیو" },
  { to: "/learning",  icon: Brain,             label: "یادگیری ML" },
  { to: "/backtest",  icon: FlaskConical,      label: "بک‌تست" },
  { to: "/settings",  icon: Settings,          label: "تنظیمات" },
] as const;

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  // ── Current page title ──────────────────────────────────
  const currentItem = NAV_ITEMS.find((n) => location.pathname.startsWith(n.to));
  const pageTitle = currentItem?.label ?? "Galaxy Vast";

  return (
    <div className="flex min-h-screen" style={{ background: "var(--gv-bg-primary)" }}>

      {/* ── Sidebar ─────────────────────────────────────── */}
      <aside
        className="flex flex-col transition-all duration-300 shrink-0"
        style={{
          width: collapsed ? 64 : 240,
          background: "var(--gv-bg-secondary)",
          borderLeft: "1px solid var(--gv-border)",
        }}
      >
        {/* Logo */}
        <div
          className="flex items-center gap-3 px-4 py-5"
          style={{ borderBottom: "1px solid var(--gv-border)" }}
        >
          <div
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 36, height: 36,
              background: "linear-gradient(135deg, #00d4ff22, #0ea5e922)",
              border: "1px solid rgba(0,212,255,0.3)",
            }}
          >
            <Activity size={18} style={{ color: "var(--gv-accent)" }} />
          </div>
          {!collapsed && (
            <div>
              <div
                className="font-bold text-sm leading-tight"
                style={{ color: "var(--gv-accent)" }}
              >
                Galaxy Vast
              </div>
              <div className="text-xs" style={{ color: "var(--gv-text-muted)" }}>
                AI Trading
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 transition-all duration-150 cursor-pointer
                 text-sm font-medium ${isActive ? "nav-item-active" : ""}`
              }
              style={({ isActive }) => ({
                color: isActive ? "var(--gv-accent)" : "var(--gv-text-secondary)",
              })}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle */}
        <div style={{ borderTop: "1px solid var(--gv-border)" }} className="p-3">
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="w-full flex items-center justify-center rounded-lg py-2 transition-colors"
            style={{
              color: "var(--gv-text-muted)",
              background: "transparent",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.background = "var(--gv-bg-card)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.background = "transparent")
            }
          >
            <ChevronLeft
              size={16}
              style={{
                transform: collapsed ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 0.3s",
              }}
            />
          </button>
        </div>
      </aside>

      {/* ── Main content ────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Topbar */}
        <header
          className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{
            background: "var(--gv-bg-secondary)",
            borderBottom: "1px solid var(--gv-border)",
          }}
        >
          <h1
            className="text-lg font-bold"
            style={{ color: "var(--gv-text-primary)" }}
          >
            {pageTitle}
          </h1>

          <div className="flex items-center gap-3">
            {/* Live indicator */}
            <div className="flex items-center gap-2">
              <span
                className="pulse-dot rounded-full"
                style={{ width: 8, height: 8, background: "var(--gv-green)" }}
              />
              <span className="text-xs" style={{ color: "var(--gv-text-muted)" }}>
                Live
              </span>
            </div>

            <button
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--gv-text-muted)" }}
            >
              <Bell size={16} />
            </button>
            <button
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--gv-text-muted)" }}
            >
              <Moon size={16} />
            </button>

            {/* User badge */}
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
              style={{
                background: "var(--gv-bg-card)",
                border: "1px solid var(--gv-border)",
              }}
            >
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: "rgba(0,212,255,0.15)", color: "var(--gv-accent)" }}
              >
                A
              </div>
              <span className="text-xs" style={{ color: "var(--gv-text-secondary)" }}>
                Admin
              </span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>

        {/* Footer */}
        <footer
          className="px-6 py-2 text-center text-xs shrink-0"
          style={{
            color: "var(--gv-text-muted)",
            borderTop: "1px solid var(--gv-border)",
          }}
        >
          Galaxy Vast AI Trading Platform v2.0 — Institutional Grade
        </footer>
      </div>
    </div>
  );
}
