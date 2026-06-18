/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "gv-bg-primary":    "#070b12",
        "gv-bg-secondary":  "#0d1420",
        "gv-bg-card":       "#111827",
        "gv-border":        "#1e2d40",
        "gv-accent":        "#00d4ff",
        "gv-gold":          "#f59e0b",
        "gv-green":         "#10b981",
        "gv-red":           "#ef4444",
        "gv-purple":        "#8b5cf6",
      },
      fontFamily: {
        fa:   ["Vazirmatn", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
      },
    },
  },
  plugins: [],
};
