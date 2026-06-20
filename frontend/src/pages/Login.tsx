/**
 * frontend/src/pages/Login.tsx
 *
 * FIX: form field changed from telegram_id to email (was causing 422 on every login)
 * FIX: client-side validation with clear error messages
 * FIX: error messages from backend are shown to user
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface LoginForm {
  email: string;
  password: string;
}

interface FormErrors {
  email?: string;
  password?: string;
  general?: string;
}

export default function Login() {
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();

  const [form, setForm]         = useState<LoginForm>({ email: "", password: "" });
  const [errors, setErrors]     = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const validate = (): boolean => {
    const errs: FormErrors = {};
    if (!form.email.trim()) {
      errs.email = "\u0627\u06CC\u0645\u06CC\u0644 \u0627\u0644\u0632\u0627\u0645\u06CC \u0627\u0633\u062A";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      errs.email = "\u0641\u0631\u0645\u062A \u0627\u06CC\u0645\u06CC\u0644 \u0646\u0627\u0645\u0639\u062A\u0628\u0631 \u0627\u0633\u062A";
    }
    if (!form.password) {
      errs.password = "\u0631\u0645\u0632 \u0639\u0628\u0648\u0631 \u0627\u0644\u0632\u0627\u0645\u06CC \u0627\u0633\u062A";
    } else if (form.password.length < 8) {
      errs.password = "\u0631\u0645\u0632 \u0639\u0628\u0648\u0631 \u0628\u0627\u06CC\u062F \u062D\u062F\u0627\u0642\u0644 \u0668 \u06A9\u0627\u0631\u0627\u06A9\u062A\u0631 \u0628\u0627\u0634\u062F";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
    if (errors[name as keyof FormErrors]) {
      setErrors(prev => ({ ...prev, [name]: undefined }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    if (!validate()) return;
    setSubmitting(true);
    try {
      await login(form.email, form.password);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "\u062E\u0637\u0627 \u062F\u0631 \u0648\u0631\u0648\u062F \u2014 \u062F\u0648\u0628\u0627\u0631\u0647 \u062A\u0644\u0627\u0634 \u06A9\u0646\u06CC\u062F";
      setErrors({ general: message });
    } finally {
      setSubmitting(false);
    }
  };

  const isBusy = isLoading || submitting;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-600 mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">Galaxy Vast AI</h1>
          <p className="text-gray-400 mt-1">\u067E\u0644\u062A\u0641\u0631\u0645 \u0645\u0639\u0627\u0645\u0644\u0627\u062A\u06CC \u0647\u0648\u0634\u0645\u0646\u062F</p>
        </div>
        <div className="bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-800">
          <h2 className="text-xl font-semibold text-white mb-6 text-center">\u0648\u0631\u0648\u062F \u0628\u0647 \u062D\u0633\u0627\u0628</h2>
          {errors.general && (
            <div className="mb-4 p-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
              {errors.general}
            </div>
          )}
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-1">
                \u0627\u06CC\u0645\u06CC\u0644
              </label>
              <input
                id="email" name="email" type="email" autoComplete="email" required
                value={form.email} onChange={handleChange} disabled={isBusy}
                placeholder="example@domain.com"
                className={`w-full px-4 py-2.5 rounded-lg bg-gray-800 border text-white placeholder-gray-500 focus:outline-none focus:ring-2 transition ${
                  errors.email ? "border-red-500 focus:ring-red-500/40" : "border-gray-700 focus:ring-blue-500/40 focus:border-blue-500"
                }`}
              />
              {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email}</p>}
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-1">
                \u0631\u0645\u0632 \u0639\u0628\u0648\u0631
              </label>
              <input
                id="password" name="password" type="password" autoComplete="current-password" required
                value={form.password} onChange={handleChange} disabled={isBusy}
                placeholder="\u062D\u062F\u0627\u0642\u0644 \u0668 \u06A9\u0627\u0631\u0627\u06A9\u062A\u0631"
                className={`w-full px-4 py-2.5 rounded-lg bg-gray-800 border text-white placeholder-gray-500 focus:outline-none focus:ring-2 transition ${
                  errors.password ? "border-red-500 focus:ring-red-500/40" : "border-gray-700 focus:ring-blue-500/40 focus:border-blue-500"
                }`}
              />
              {errors.password && <p className="mt-1 text-xs text-red-400">{errors.password}</p>}
            </div>
            <button
              type="submit" disabled={isBusy}
              className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              {isBusy ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  \u062F\u0631 \u062D\u0627\u0644 \u0648\u0631\u0648\u062F...
                </span>
              ) : "\u0648\u0631\u0648\u062F"}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-gray-500">
            \u062D\u0633\u0627\u0628 \u0646\u062F\u0627\u0631\u06CC\u062F\u061F{" "}
            <a href="/register" className="text-blue-400 hover:text-blue-300 transition-colors">
              \u062B\u0628\u062A\u200C\u0646\u0627\u0645 \u06A9\u0646\u06CC\u062F
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
