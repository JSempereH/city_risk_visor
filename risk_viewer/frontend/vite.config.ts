import { defineConfig } from "vite";

// A port distinct from Vite's default 5173, which may already be in use by
// other projects on the same machine.
export default defineConfig({
  server: { port: 5183 },
  preview: { port: 5183 },
  // maplibre-gl spins up its own Web Worker (needed to decode vector
  // tiles off the main thread) via a `new Worker(new URL(...))` call
  // that Vite's dependency pre-bundler doesn't resolve correctly --
  // without this, the worker script 404s, tiles never decode, the map
  // never fires "load", and the app never gets past a blank screen.
  // Harmless with a purely raster basemap (no worker needed), so this
  // only became a hard blocker after switching to a vector basemap.
  optimizeDeps: { exclude: ["maplibre-gl"] },
});
