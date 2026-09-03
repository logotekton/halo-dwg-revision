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

/** What `halocad:convert:dwg-to-dxf` resolves to (`docs/contracts/wave-3.md`). */
export interface ConvertResult {
  dxf_path: string
  entity_count: number
  converter: 'mlightcad-dxfout' | 'acad-ts'
  warnings: string[]
}
