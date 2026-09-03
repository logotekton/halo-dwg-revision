/**
 * The IPC contract between the main process and the hidden converter window.
 *
 * Both sides are separate electron-vite entries (main / preload / renderer), so
 * this file is duplicated by value, not by import: `apps/web` deliberately does
 * not depend on `apps/desktop` (see `apps/desktop/scripts/dev.mjs`). Keep the
 * three copies — here, `src/preload/convert.ts` and
 * `apps/web/src/features/viewer/convert-entry.ts` — in step by hand.
 */

/** main → hidden window. */
export const CONVERT_REQUEST_CHANNEL = 'halocad:convert:request'
/** hidden window → main. */
export const CONVERT_RESULT_CHANNEL = 'halocad:convert:result'
/** hidden window → main, once the converter page has registered its handler. */
export const CONVERT_READY_CHANNEL = 'halocad:convert:ready'
/** renderer/main → main (`docs/contracts/wave-3.md` "IPC 채널"). */
export const CONVERT_INVOKE_CHANNEL = 'halocad:convert:dwg-to-dxf'
/** renderer → main: where the viewer assets are served from. */
export const VIEWER_ASSETS_BASE_CHANNEL = 'halocad:viewer:assets-base'

export interface ConvertRequest {
  requestId: string
  /** DWG bytes; transferred as a Uint8Array over the structured clone. */
  bytes: Uint8Array
  /** Original file name, used only for messages. */
  name: string
}

export interface ConvertReply {
  requestId: string
  ok: boolean
  /** Post-processed DXF text (ADR-0002 개정 §3), present when `ok`. */
  dxf?: string
  /** Top-level entity count per `docs/contracts/stats-definition.md`. */
  entityCount?: number
  warnings: string[]
  error?: string
}

/**
 * One external reference as the DWG stores it. `dxfOut()` drops these
 * (W3-09: 0 of 133 preserved), so they travel beside the converted file for the
 * engine to re-attach (`POST /files/{id}/converted`, W3-06 consumes them).
 */
export interface XrefInfo {
  block_name: string
  path: string
  is_overlay: boolean
}

/**
 * One text style. `typeface` is the TrueType name, which lives only in XDATA
 * and is likewise lost by `dxfOut()` (W3-09: 0 of 838 styles) — the font panel
 * (W3-05) needs it to map Korean TTF names.
 */
export interface StyleInfo {
  name: string
  font: string
  bigfont: string
  typeface?: string
}

/** What `halocad:convert:dwg-to-dxf` resolves to (`docs/contracts/wave-3.md`). */
export interface ConvertResult {
  dxf_path: string
  entity_count: number
  converter: 'mlightcad-dxfout' | 'acad-ts'
  warnings: string[]
  /** Read from the DWG by acad-ts, because the conversion loses them. */
  xrefs: XrefInfo[]
  styles: StyleInfo[]
}
