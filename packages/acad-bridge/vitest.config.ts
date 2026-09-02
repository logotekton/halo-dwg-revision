import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // Round-trip tests read fixtures/generated/*.dxf and write scratch DWG/DXF
    // output under the OS temp dir; entity trees for F06-sized fixtures are
    // small, but acad-ts's own module graph is large, so give it headroom.
    testTimeout: 20_000,
  },
});
