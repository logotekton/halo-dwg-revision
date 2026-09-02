// Local flat config for @halo-cad/schema. The workspace-wide config lands with
// W1-01; until then this package lints itself so `pnpm -r run lint` is green.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "gen/**", "node_modules/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: {
      parserOptions: { projectService: false },
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "separate-type-imports" },
      ],
      "@typescript-eslint/no-non-null-assertion": "off",
      eqeqeq: ["error", "always"],
      "no-console": "error",
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: { process: "readonly", console: "readonly" },
    },
    rules: {
      "no-console": "off",
    },
  }
);
