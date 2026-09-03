import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { promisify } from 'node:util'
import type { StyleInfo, XrefInfo } from './protocol'

const execFileAsync = promisify(execFile)

/** A second full parse of the DWG; 2.6 MB takes a few seconds. */
const INFO_TIMEOUT_MS = 10 * 60 * 1000

/**
 * Reads the two things `dxfOut()` does not preserve, straight from the DWG.
 *
 * W3-09 measured both losses over the real drawing set: **XREF paths** survive
 * 0 of 133 conversions and **TrueType typefaces** 0 of 838 styles, while
 * acad-ts reads both correctly from the same files. The engine needs them to
 * re-attach external references (W3-06) and to map Korean TTF names onto the
 * font pool (W3-05), so the converter reports them next to the converted file
 * (`docs/contracts/wave-3.md`, `POST /files/{id}/converted`).
 *
 * This is a second parse of the same DWG by a second library, and it is worth
 * it: it is also the only cross-check that the conversion saw the same drawing
 * at all (the two entity counts are compared by the engine).
 *
 * Never fatal: a conversion that produced a good DXF is still a good
 * conversion, so a failure here comes back as empty lists plus a warning.
 */
export async function readDwgMetadata(
  acadBridgeEntry: string | null,
  dwgPath: string,
): Promise<{ xrefs: XrefInfo[]; styles: StyleInfo[]; warnings: string[] }> {
  if (!acadBridgeEntry || !existsSync(acadBridgeEntry)) {
    return {
      xrefs: [],
      styles: [],
      warnings: ['XREF paths and text styles were not read: acad-bridge is not built'],
    }
  }
  try {
    const { stdout } = await execFileAsync(process.execPath, [acadBridgeEntry, 'info', dwgPath], {
      timeout: INFO_TIMEOUT_MS,
      maxBuffer: 64 * 1024 * 1024,
      // process.execPath is the Electron binary; without this it would boot a
      // second Electron app instead of running the script.
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    })
    const parsed: unknown = JSON.parse(stdout)
    const info = parsed as { xrefs?: XrefInfo[]; styles?: StyleInfo[] }
    return { xrefs: info.xrefs ?? [], styles: info.styles ?? [], warnings: [] }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return {
      xrefs: [],
      styles: [],
      warnings: [`XREF paths and text styles could not be read from the DWG: ${message}`],
    }
  }
}
