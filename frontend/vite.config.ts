import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Build and development configuration for the frontend.
 *
 * The build writes into the Python package, at `corpus_query/api/static`,
 * because that directory is what FastAPI serves and what is committed. The
 * usual `dist/` would be both gitignored and somewhere the API has no reason
 * to know about.
 *
 * Relative asset URLs (`base: "./"`) keep the bundle independent of where it
 * is mounted, so the same build works whether it is served at `/` or behind a
 * prefix.
 *
 * In development, Vite serves the app itself with hot module replacement and
 * proxies the API paths through to a `scripts/serve.py` on the usual port.
 * That is what lets the frontend be worked on against a live corpus without a
 * rebuild per change, and it keeps requests same-origin so there is no CORS
 * configuration to carry in the API for the sake of development alone.
 */
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../corpus_query/api/static",
    emptyOutDir: true,
  },
  server: {
    proxy: Object.fromEntries(
      ["/search", "/answer", "/chunks", "/health", "/openapi.json", "/docs"].map((path) => [
        path,
        { target: "http://127.0.0.1:8000", changeOrigin: true },
      ]),
    ),
  },
});
