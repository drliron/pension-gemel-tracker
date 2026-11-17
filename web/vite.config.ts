import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// פיתוח: הדפדפן מדבר עם /api, וה-proxy מעביר לשרת המקומי על localhost בלבד.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: { outDir: "dist" },
});
