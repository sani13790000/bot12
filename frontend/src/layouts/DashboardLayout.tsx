/**
 * لی‌اوت داشبورد
 *
 * نویسنده: MT5 Trading Team
 */

import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  TrendingUp,
  Bell,
  FileText,
  Settings,
  LogOut,
  Menu,
  X,
  Activity
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface SidebarItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
}

function SidebarItem({ to, icon, label, active }: SidebarItemProps) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
        active
          ? 'bg-sky-500/20 text-sky-400'
          : 'text-slate-400 hover:bg-slate-800 hover:text-slate-300'
      }`}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
}

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  const navItems = [
    { to: '/', icon: <LayoutDashboard className="w-5 h-5" />, label: 'داشبورد' },
    { to: '/analysis', icon: <Activity className="w-5 h-5" />, label: 'تحلیل' },
    { to: '/trades', icon: <TrendingUp className="w-5 h-5" />, label: 'معاملات' },
    { to: '/signals', icon: <Bell className="w-5 h-5" />, label: 'سیگنال‌ها' },
    { to: '/reports', icon: <FileText className="w-5 h-5" />, label: 'گزارش‌ها' },
    { to: '/settings', icon: <Settings className="w-5 h-5" />, label: 'تنظیمات' }
  ];

  return (
    <div className="min-h-screen bg-slate-900 flex" dir="rtl">
      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex w-64 flex-col bg-slate-800/50 border-l border-slate-700/50">
        {/* Logo */}
        <div className="p-6 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-slate-100">MT5 Trading</h1>
              <p className="text-xs text-slate-500">Enterprise Edition</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <SidebarItem
              key={item.to}
              {...item}
              active={location.pathname === item.to}
            />
          ))}
        </nav>

        {/* User */}
        <div className="p-4 border-t border-slate-700/50">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center">
              <span className="text-slate-300 font-medium">
                {user?.first_name?.[0] || user?.email?.[0] || 'U'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-slate-200 font-medium truncate">
                {user?.first_name || 'کاربر'}
              </p>
              <p className="text-slate-500 text-sm truncate">
                {user?.email}
              </p>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full px-3 py-2 text-slate-400 hover:text-rose-400 hover:bg-slate-700/50 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="text-sm">خروج</span>
          </button>
        </div>
      </aside>

      {/* Mobile Sidebar */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50 bg-black/50" onClick={() => setSidebarOpen(false)}>
          <aside
            className="w-64 h-full bg-slate-800 border-l border-slate-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 flex justify-between items-center border-b border-slate-700">
              <h2 className="font-bold text-slate-100">منو</h2>
              <button onClick={() => setSidebarOpen(false)}>
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

            <nav className="p-4 space-y-1">
              {navItems.map((item) => (
                <SidebarItem
                  key={item.to}
                  {...item}
                  active={location.pathname === item.to}
                />
              ))}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-screen">
        {/* Header */}
        <header className="bg-slate-800/50 border-b border-slate-700/50 px-4 py-3 lg:px-6">
          <div className="flex items-center justify-between">
            {/* Mobile Menu */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 text-slate-400 hover:text-slate-200"
            >
              <Menu className="w-6 h-6" />
            </button>

            {/* Right side */}
            <div className="flex items-center gap-4">
              {/* Kill Zone indicator */}
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 rounded-lg">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                <span className="text-sm text-slate-300">Kill Zone: لندن</span>
              </div>

              {/* Notifications */}
              <button className="relative p-2 text-slate-400 hover:text-slate-200">
                <Bell className="w-5 h-5" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full"></span>
              </button>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto">
          {children}
        </main>

        {/* Footer */}
        <footer className="bg-slate-800/30 border-t border-slate-700/50 px-4 py-3 text-center">
          <p className="text-slate-600 text-sm">
            MT5 Trading System v1.0.0 • Enterprise Edition
          </p>
        </footer>
      </div>
    </div>
  );
}
