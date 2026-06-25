/**
 * frontend/src/pages/Register.tsx
 * PROD-FIX-6: Register page — previously /register routed to Login component
 */
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface RegisterForm {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
}

interface FormErrors {
  full_name?: string;
  email?: string;
  password?: string;
  confirm_password?: string;
  general?: string;
}

export default function Register() {
  const navigate = useNavigate();
  const { register, isLoading } = useAuth();

  const [form, setForm] = useState<RegisterForm>({
    full_name: "", email: "", password: "", confirm_password: "",
  });
  const [errors, setErrors]         = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const validate = (): boolean => {
    const errs: FormErrors = {};
    if (!form.full_name.trim()) errs.full_name = "نام الزامی است";
    if (!form.email.trim()) errs.email = "ایمیل الزامی است";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "فرمت ایمیل نامعتبر است";
    if (!form.password) errs.password = "رمز عبور الزامی است";
    else if (form.password.length < 8) errs.password = "رمز عبور باید حداقل ۸ کاراکتر باشد";
    if (form.password !== form.confirm_password) errs.confirm_password = "رمز عبور تکرار نمی‌شود";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
    if (errors[name as keyof FormErrors]) setErrors(prev => ({ ...prev, [name]: undefined }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    if (!validate()) return;
    setSubmitting(true);
    try {
      await register(form.email, form.password, form.full_name);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "خطا در ثبت‌نام — دوباره تلاش کنید";
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
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white">ثبت‌نام</h1>
          <p className="text-gray-400 mt-2">Galaxy Vast AI Trading Platform</p>
        </div>

        <div className="bg-gray-900 rounded-2xl shadow-2xl p-8 border border-gray-800">
          {errors.general && (
            <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm">
              {errors.general}
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {(["full_name", "email", "password", "confirm_password"] as const).map((field) => (
              <div key={field}>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  {field === "full_name" ? "نام کامل" : field === "email" ? "ایمیل" :
                   field === "password" ? "رمز عبور" : "تکرار رمز عبور"}
                </label>
                <input
                  type={field.includes("password") ? "password" : field === "email" ? "email" : "text"}
                  name={field} value={form[field]} onChange={handleChange}
                  disabled={isBusy}
                  className={`w-full px-4 py-3 rounded-lg bg-gray-800 border text-white
                    placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500
                    transition-colors ${
                      errors[field] ? "border-red-500" : "border-gray-700"
                    }`}
                />
                {errors[field] && <p className="mt-1 text-sm text-red-400">{errors[field]}</p>}
              </div>
            ))}
            <button type="submit" disabled={isBusy}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800
                disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                focus:ring-offset-gray-900 mt-2">
              {isBusy ? "در حال ثبت‌نام..." : "ثبت‌نام"}
            </button>
          </form>
          <div className="mt-6 text-center text-sm text-gray-400">
            حساب دارید؟{" "}
            <Link to="/login" className="text-blue-400 hover:text-blue-300 transition-colors font-medium">
              وارد شوید
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
