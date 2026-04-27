import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxia chamadas /tiles para o Martin (evita CORS em dev)
      "/tiles": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/tiles/, ""),
      },
    },
  },
  // Necessário para apache-arrow (módulos ESM com top-level await)
  optimizeDeps: {
    include: ["apache-arrow", "maplibre-gl"],
  },
});
