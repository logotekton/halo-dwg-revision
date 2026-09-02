import { defineConfig } from "tsup";

// Bundles the CLI into one self-contained ESM file. acad-ts (~7MB unpacked,
// zero deps of its own) and @halo-cad/schema stay external: they are real
// node_modules packages at runtime (pnpm workspace symlink for the latter),
// so there is no reason to inline them into the bin file.
export default defineConfig({
  entry: { "acad-bridge": "src/cli.ts" },
  outDir: "bin",
  format: ["esm"],
  target: "node24",
  platform: "node",
  splitting: false,
  sourcemap: true,
  clean: true,
  dts: false,
  minify: false,
  external: ["@node-projects/acad-ts", "@halo-cad/schema"],
  // package.json has "type": "module", so plain ".js" is already ESM, but the
  // brief names the entry point "bin/acad-bridge.mjs" explicitly -- force the
  // extension so the built file matches that literally regardless of type.
  outExtension: () => ({ js: ".mjs" }),
  banner: { js: "#!/usr/bin/env node" },
});
