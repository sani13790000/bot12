// frontend/src/main.tsx
// FIX-FE1: AuthProvider MISSING → useAuth() crash در Login + DashboardLayout
// FIX-FE2: @/ path alias → vite.config.ts resolve.alias اضافه شد

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
