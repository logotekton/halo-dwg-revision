import { ACadVersion } from "@node-projects/acad-ts";

const SUPPORTED: Record<string, ACadVersion> = {
  AC1009: ACadVersion.AC1009,
  AC1012: ACadVersion.AC1012,
  AC1014: ACadVersion.AC1014,
  AC1015: ACadVersion.AC1015,
  AC1018: ACadVersion.AC1018,
  AC1021: ACadVersion.AC1021,
  AC1024: ACadVersion.AC1024,
  AC1027: ACadVersion.AC1027,
  AC1032: ACadVersion.AC1032,
};

export const DEFAULT_DXF2DWG_VERSION = "AC1027";
export const DEFAULT_DWG2DXF_VERSION = "AC1032";

export function parseVersionName(name: string): ACadVersion {
  const key = name.trim().toUpperCase();
  const version = SUPPORTED[key];
  if (version === undefined) {
    throw new Error(
      `Unsupported ACadVersion "${name}". Supported: ${Object.keys(SUPPORTED).join(", ")}`
    );
  }
  return version;
}

/** Reverse lookup via the numeric enum's auto-generated reverse map. */
export function versionName(version: ACadVersion): string {
  const name = ACadVersion[version];
  return typeof name === "string" ? name : `Unknown(${String(version)})`;
}

/**
 * DXF R2007 (AC1021) and later write the ASCII DXF file itself as UTF-8:
 * non-ASCII text is real UTF-8 bytes, not `\U+XXXX` escapes in a legacy
 * single-byte code page. R2004 (AC1018) and earlier are legacy-codepage
 * versions. See packages/acad-bridge/README.md "DXF write path" for why this
 * matters for the string-sink implementation in acad/write.ts.
 */
export function isUtf8EraVersion(version: ACadVersion): boolean {
  return version >= ACadVersion.AC1021;
}
