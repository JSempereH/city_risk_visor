import { defineConfig } from "vite";

// A port distinct from Vite's default 5173, which may already be in use by
// other projects on the same machine.
export default defineConfig({
  server: { port: 5183 },
  preview: { port: 5183 },
  // maplibre-gl loads its worker via a dynamic `new URL(...)` at runtime,
  // which Vite's dependency pre-bundler doesn't follow correctly, leaving
  // a dangling reference to a worker chunk that was never emitted into
  // .vite/deps. Excluding it from optimization sidesteps that entirely.
  optimizeDeps: { exclude: ["maplibre-gl"] },
});
