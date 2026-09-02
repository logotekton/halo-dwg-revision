import { readFileSync } from "node:fs";

import {
  DwgReader,
  DwgReaderConfiguration,
  DxfReader,
  DxfReaderConfiguration,
  NotificationType,
  type CadDocument,
  type NotificationEventArgs,
} from "@node-projects/acad-ts";

import type { DropEntry } from "../drops";

export interface ReadResult {
  doc: CadDocument;
  /** Notifications raised while reading (NotSupported/Warning/Error/NotImplemented). */
  drops: DropEntry[];
}

function notificationDrop(e: NotificationEventArgs): DropEntry {
  const label = NotificationType[e.notificationType] ?? String(e.notificationType);
  const exceptionSuffix = e.exception ? `: ${e.exception.message}` : "";
  return { reason: "read-notification", message: `[${label}] ${e.message}${exceptionSuffix}` };
}

/**
 * `keepUnknownEntities: true` is the whole point of reading through this
 * wrapper instead of the bare `DwgReader.readFromStream` shown in the
 * acad-ts README: the default (`false`) silently drops any entity acad-ts
 * cannot resolve to a real class, which is exactly the signal the drops
 * report (ADR-0002) needs. Kept `UnknownEntity`/`ProxyEntity` instances are
 * found later by walking the document (see acad/entity-types.ts callers).
 */
export function readDwgFile(path: string): ReadResult {
  const buffer = readFileSync(path);
  const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  const drops: DropEntry[] = [];
  const configuration = new DwgReaderConfiguration();
  configuration.keepUnknownEntities = true;
  const doc = DwgReader.readFromStreamWithConfig(arrayBuffer, configuration, (_sender, e) => {
    if (e.notificationType !== NotificationType.None) drops.push(notificationDrop(e));
  });
  return { doc, drops };
}

/**
 * Reads raw file bytes, not a decoded string: acad-ts follows `$DWGCODEPAGE`
 * itself for both ASCII and binary DXF (README "Reading a DXF file"). If the
 * bytes were decoded to a JS string first, the original code page
 * information needed for legacy (pre-UTF8-era, e.g. cp949) DXF would already
 * be lost.
 */
export function readDxfFile(path: string): ReadResult {
  const buffer = readFileSync(path);
  const bytes = new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  const drops: DropEntry[] = [];
  const configuration = new DxfReaderConfiguration();
  configuration.keepUnknownEntities = true;
  const doc = DxfReader.readFromStreamWithConfig(bytes, configuration, (_sender, e) => {
    if (e.notificationType !== NotificationType.None) drops.push(notificationDrop(e));
  });
  return { doc, drops };
}

export type CadFormat = "dwg" | "dxf";

export function detectFormat(path: string): CadFormat {
  const lower = path.toLowerCase();
  if (lower.endsWith(".dwg")) return "dwg";
  if (lower.endsWith(".dxf")) return "dxf";
  throw new Error(`Cannot tell DWG from DXF by extension: ${path} (rename with .dwg or .dxf)`);
}

export function readCadFile(path: string): ReadResult {
  return detectFormat(path) === "dwg" ? readDwgFile(path) : readDxfFile(path);
}
