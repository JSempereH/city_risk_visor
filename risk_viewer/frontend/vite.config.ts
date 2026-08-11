import { defineConfig } from "vite";

// A port distinct from Vite's default 5173, which may already be in use by
// other projects on the same machine.
export default defineConfig({
  server: { port: 5183 },
  preview: { port: 5183 },
});
