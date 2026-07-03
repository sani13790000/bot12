// frontend/src/pages/Register.tsx
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Zap, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate     = useNavigate();
  const [form, setForm]     = useState({ email: "", password: "", full_name: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(p => ({ ...p, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 8) { setError("رمز عبور باید حداقل ۸ کاراکتر باشد"); return; }
    setError(""); setLoading(true);
    try { await register(form); navigate("/dashboard", { replace: true }); }
    catch (err) { setError(err instanceof Error ? err.message : "خطا در ثبت‌نام"); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-14 h-14 rounded-2xl bg-blue-600 flex items-center justify-center"><Zap size={28} /></div>
          <h1 className="text-xl font-bold text-white">ایجاد حساب</h1>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { key: "full_name", label: "نام کامل", type: "text",     placeholder: "Ali Ahmadi" },
            { key: "email",     label: "ایمیل",      type: "email",    placeholder: "ali@example.com" },
            { key: "password",  label: "رمز عبور",   type: "password", placeholder: "حداقل ۸ کاراکتر" },
          ].map(({ key, label, type, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">{label}</label>
              <input type={type} value={form[key as keyof typeof form]} onChange={set(key as keyof typeof form)}
                required placeholder={placeholder}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors" />
            </div>
          ))}
          {error && <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400">{error}</div>}
          <button type="submit" disabled={loading}
            className="w-full rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 py-2.5 text-sm font-medium text-white transition-colors flex items-center justify-center gap-2">
            {loading ? <><Loader2 size={16} className="animate-spin" /> در حال ثبت‌نام...</> : "ثبت‌نام"}
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-6">حساب دارید؟{" "}<Link to="/login" className="text-blue-400 hover:text-blue-300">ورود</Link></p>
      </div>
    </div>
  );
}
