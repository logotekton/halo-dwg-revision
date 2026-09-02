import { readFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";

/**
 * Package root. Vitest is pinned to it by `vitest.config.ts`, so this holds
 * whether the suite runs through `pnpm test` in this package or through
 * `pnpm -r run test` from the workspace root.
 */
export const PACKAGE_ROOT = process.cwd();
export const EXAMPLES_DIR = path.join(PACKAGE_ROOT, "examples");

if (!existsSync(EXAMPLES_DIR)) {
  throw new Error(
    `examples directory not found at ${EXAMPLES_DIR}; run vitest from packages/schema`
  );
}

export function listExamples(): string[] {
  return readdirSync(EXAMPLES_DIR)
    .filter((name) => name.endsWith(".json"))
    .sort();
}

export function readExampleText(name: string): string {
  return readFileSync(path.join(EXAMPLES_DIR, name), "utf8");
}

export function loadExample(name: string): unknown {
  return JSON.parse(readExampleText(name));
}

/** Deep clone that keeps the value plain JSON, for building mutated fixtures. */
export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
