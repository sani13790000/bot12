// frontend/src/pages/CustomerOverviewPage.tsx
import React from "react";
import { User, Mail, Shield } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import Badge from "@/components/Badge";

export default function CustomerOverviewPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><User size={20} className="text-blue-400" /> پروفایل</h1></div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-blue-600 flex items-center justify-center text-2xl font-bold">{user.full_name?.[0]?.toUpperCase()??"U"}</div>
          <div><p className="text-xl font-bold text-white">{user.full_name}</p><p className="text-sm text-gray-400 mt-1">{user.email}</p></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[{icon:User,label:"نام کامل",value:user.full_name},{icon:Mail,label:"ایمیل",value:user.email},{icon:Shield,label:"نقش",value:user.role}]
            .map(({icon:Icon,label,value}) => (
              <div key={label} className="rounded-lg bg-gray-800 p-4">
                <div className="flex items-center gap-2 mb-2"><Icon size={16} className="text-gray-400" /><p className="text-xs text-gray-400">{label}</p></div>
                <p className="text-sm font-medium text-white">{value}</p>
              </div>
            ))}
        </div>
        <div className="mt-4">
          <p className="text-xs text-gray-400 mb-1">وضعیت حساب</p>
          <Badge label={user.is_active?"فعال":"غیرفعال"} color={user.is_active?"green":"red"} />
        </div>
      </div>
    </div>
  );
}
