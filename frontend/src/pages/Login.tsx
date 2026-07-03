// frontend/src/pages/Login.tsx
import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Zap, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function Login() {
  const { login }  = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const from       = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/dashboard";
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow]         = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setLoading(true);
    try { await login({ email, password }); navigate(from, { replace: true }); }
    catch (err) { setError(err instanceof Error ? err.message : "خطا در ورود"); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-14 h-14 rounded-2xl bg-blue-600 flex items-center justify-center"><Zap size={28} /></div>
          <div className="text-center"><h1 className="text-xl font-bold text-white">Galaxy Vast</h1><p className="text-sm text-gray-400">پلتفرم معاملات هوشمند</p></div>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">ایمیل</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="example@mail.com" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">رمز عبور</label>
            <div className="relative">
              <input type={show ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} required
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 pr-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="••••••••" />
              <button type="button" onClick={() => setShow(p => !p)} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200">
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          {error && <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400">{error}</div>}
          <button type="submit" disabled={loading}
            className="w-full rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 py-2.5 text-sm font-medium text-white transition-colors flex items-center justify-center gap-2">
            {loading ? <><Loader2 size={16} className="animate-spin" /> در حال ورود...</> : "ورود"}
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-6">حساب ندارید؟{" "}<Link to="/register" className="text-blue-400 hover:text-blue-300">ثبت‌نام</Link></p>
      </div>
    </div>
  );
}
