import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** packages/acad-bridge/src/acad/ -> repo root, independent of the test runner's cwd. */
const REPO_ROOT = fileURLToPath(new URL("../../../..", import.meta.url));

export const FIXTURES_DIR = path.join(REPO_ROOT, "fixtures", "generated");

export function fixturePath(name: string): string {
  return path.join(FIXTURES_DIR, name);
}

export function makeScratchDir(prefix: string): string {
  return mkdtempSync(path.join(tmpdir(), `acad-bridge-${prefix}-`));
}
