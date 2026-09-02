import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

/**
 * acad-ts's package.json does not list a "./package.json" subpath in its
 * "exports" map, so it cannot be `require()`-d at runtime under Node's
 * strict ESM exports enforcement. Kept as a plain constant instead; it must
 * move in lockstep with the exact pin in package.json's "dependencies"
 * (Constraints: "@node-projects/acad-ts@3.1.0(정확 고정)").
 */
export const ACAD_TS_VERSION = "3.1.0";

export function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

/** Deterministic output: stable key order, 2-space indent, trailing newline, no timestamps (CLAUDE.md rule 7). */
export function writeJsonFile(path: string, data: unknown): void {
  writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}
