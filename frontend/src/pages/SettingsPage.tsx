/**
 * صفحه تنظیمات
 *
 * نویسنده: MT5 Trading Team
 */

import { useState } from 'react';
import {
  User,
  Bell,
  DollarSign,
  Save,
  RefreshCw
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { TIMEFRAMES, DEFAULT_SYMBOLS } from '@/utils/config';

export function SettingsPage() {
  const { user, settings, updateSettings } = useAuth();

  // Local state
  const [formData, setFormData] = useState({
    default_symbol: settings?.default_symbol || 'EURUSD',
    default_lot: settings?.default_lot || 0.1,
    risk_per_trade: settings?.risk_per_trade || 1,
    max_daily_trades: settings?.max_daily_trades || 5,
    min_entry_score: settings?.min_entry_score || 65,
    telegram_notifications: settings?.telegram_notifications ?? true,
    default_timeframe: settings?.default_timeframe || 'H1'
  });

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Save handler
  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings(formData);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (error) {
      console.error('خطا در ذخیره:', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">تنظیمات</h1>
          <p className="text-slate-500 mt-1">پیکربندی سیستم معاملاتی</p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-sky-500/20 text-sky-400 rounded-lg hover:bg-sky-500/30 transition-colors disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          <span>{saving ? 'در حال ذخیره...' : 'ذخیره تغییرات'}</span>
        </button>
      </div>

      {/* Saved notification */}
      {saved && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 flex items-center gap-2">
          <div className="w-2 h-2 bg-emerald-500 rounded-full"></div>
          <span className="text-emerald-400">تنظیمات با موفقیت ذخیره شد</span>
        </div>
      )}

      {/* Profile Section */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
        <div className="flex items-center gap-3 mb-6">
          <User className="w-5 h-5 text-sky-500" />
          <h2 className="text-lg font-semibold text-slate-100">پروفایل</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-slate-400 text-sm mb-2">نام</label>
            <input
              type="text"
              value={user?.first_name || ''}
              disabled
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-300 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">ایمیل</label>
            <input
              type="email"
              value={user?.email || ''}
              disabled
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-300 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">نقش</label>
            <input
              type="text"
              value={user?.role === 'admin' ? 'مدیر' : user?.role === 'trader' ? 'تریدر' : 'کاربر'}
              disabled
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-300 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">وضعیت</label>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                user?.status === 'active' ? 'bg-emerald-500' : 'bg-slate-500'
              }`}></div>
              <span className={user?.status === 'active' ? 'text-emerald-400' : 'text-slate-400'}>
                {user?.status === 'active' ? 'فعال' : 'غیرفعال'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Trading Settings */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
        <div className="flex items-center gap-3 mb-6">
          <DollarSign className="w-5 h-5 text-emerald-500" />
          <h2 className="text-lg font-semibold text-slate-100">تنظیمات معاملات</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-slate-400 text-sm mb-2">نماد پیش‌فرض</label>
            <select
              value={formData.default_symbol}
              onChange={(e) => setFormData({ ...formData, default_symbol: e.target.value })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            >
              {DEFAULT_SYMBOLS.map((symbol) => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">تایم‌فریم پیش‌فرض</label>
            <select
              value={formData.default_timeframe}
              onChange={(e) => setFormData({ ...formData, default_timeframe: e.target.value })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf.value} value={tf.value}>{tf.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">لات پیش‌فرض</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              max="10"
              value={formData.default_lot}
              onChange={(e) => setFormData({ ...formData, default_lot: parseFloat(e.target.value) || 0.01 })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">ریسک هر معامله (%)</label>
            <input
              type="number"
              step="0.5"
              min="0.5"
              max="10"
              value={formData.risk_per_trade}
              onChange={(e) => setFormData({ ...formData, risk_per_trade: parseFloat(e.target.value) || 1 })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">حداکثر معاملات روزانه</label>
            <input
              type="number"
              min="1"
              max="20"
              value={formData.max_daily_trades}
              onChange={(e) => setFormData({ ...formData, max_daily_trades: parseInt(e.target.value) || 5 })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-sm mb-2">حداقل امتیاز ورود</label>
            <input
              type="number"
              min="50"
              max="90"
              value={formData.min_entry_score}
              onChange={(e) => setFormData({ ...formData, min_entry_score: parseInt(e.target.value) || 65 })}
              className="w-full bg-slate-700/50 border border-slate-600/50 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            />
          </div>
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
        <div className="flex items-center gap-3 mb-6">
          <Bell className="w-5 h-5 text-amber-500" />
          <h2 className="text-lg font-semibold text-slate-100">اعلان‌ها</h2>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-slate-700/30 rounded-lg">
            <div>
              <p className="text-slate-200 font-medium">اعلان‌های تلگرام</p>
              <p className="text-slate-500 text-sm">دریافت سیگنال‌ها و گزارش‌ها از طریق تلگرام</p>
            </div>

            <button
              onClick={() => setFormData({ ...formData, telegram_notifications: !formData.telegram_notifications })}
              className={`relative w-12 h-6 rounded-full transition-colors ${
                formData.telegram_notifications ? 'bg-sky-500' : 'bg-slate-600'
              }`}
            >
              <div
                className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                  formData.telegram_notifications ? 'right-1' : 'left-1'
                }`}
              />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
