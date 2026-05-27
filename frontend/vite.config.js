import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/tiles": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/tiles/, ""),
      },
    },
  },
  optimizeDeps: {
    include: ["apache-arrow", "maplibre-gl"],
  },
  build: {
    target: "esnext",
    rollupOptions: {
      output: {
        manualChunks: {
          "maplibre": ["maplibre-gl"],
          "deckgl": [
            "@deck.gl/core",
            "@deck.gl/layers",
            "@deck.gl/geo-layers",
            "@deck.gl/extensions",
            "@deck.gl/aggregation-layers",
          ],
          "react-vendor": ["react", "react-dom"],
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
});
