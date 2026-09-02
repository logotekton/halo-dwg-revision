import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    // Examples are read relative to the package root; keep it pinned so the
    // suite behaves the same under `pnpm test` and `pnpm -r run test`.
    root: __dirname,
  },
});
