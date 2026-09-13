import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api (REST + WebSocket) to the FastAPI backend on :8000,
// so the dashboard in the browser talks to one origin (no CORS, no polling).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});