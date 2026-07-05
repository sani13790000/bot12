/**
 * frontend/vite.config.ts
 * FIX-E16: @ alias وجود داشت — بررسی شد درست است
 * FIX-E17: sourcemap فقط در dev — بررسی شد درست است
 * FIX-E18: proxy /api و /ws برای dev — بررسی شد درست است
 * FIX-E19: manualChunks برای bundle splitting — بررسی شد درست است
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws":  { target: "ws://localhost:8000",   ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: process.env.NODE_ENV !== "production",
    rollupOptions: {
      output: {
        manualChunks: {
          vendor:  ["react", "react-dom", "react-router-dom"],
          charts:  ["recharts"],
          icons:   ["lucide-react"],
          datefns: ["date-fns"],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
});
