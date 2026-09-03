import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { readDwgMetadata } from './metadata'
import type { ConvertResult } from './protocol'

const execFileAsync = promisify(execFile)

/** acad-ts writes ~200k entities in 15.7 s (`docs/spikes/large-file.md` §5.1). */
const FALLBACK_TIMEOUT_MS = 15 * 60 * 1000

export interface FallbackJob {
  /** Absolute path of `packages/acad-bridge/bin/acad-bridge.mjs`, or null. */
  entry: string | null
  dwgPath: string
  outPath: string
}

/**
 * Second converter: `acad-bridge dwg2dxf` (ADR-0002 개정 §1, "acad-ts는 보조").
 *
 * Deliberately **does not repair** the output. W2-06 measured that acad-ts
 * drops ATTRIB tags and duplicates handles, which makes ezdxf's auditor delete
 * entities — the engine's crosscheck is the blocking gate that catches this
 * (ADR-0002 개정 §4), and W3-08 owns the writer defects themselves. This layer's
 * only job is to produce *something* and to say honestly which converter made
 * it, so the user can be told when the crosscheck rejects it.
 */
export async function runAcadTsFallback(job: FallbackJob): Promise<ConvertResult> {
  if (!job.entry || !existsSync(job.entry)) {
    throw new Error(
      'DWG 변환에 실패했고 acad-ts 폴백도 사용할 수 없습니다 (acad-bridge 빌드 없음).',
    )
  }
  const { stdout, stderr } = await execFileAsync(
    process.execPath,
    [job.entry, 'dwg2dxf', job.dwgPath, job.outPath, '--version', 'AC1032'],
    {
      timeout: FALLBACK_TIMEOUT_MS,
      maxBuffer: 8 * 1024 * 1024,
      // ELECTRON_RUN_AS_NODE: process.execPath is the Electron binary; without
      // this it would boot a second Electron app instead of running the script.
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    },
  )
  const size = await stat(job.outPath).catch(() => null)
  if (!size || size.size === 0) {
    throw new Error(`acad-ts 폴백이 빈 결과를 만들었습니다: ${stderr || stdout}`)
  }
  const metadata = await readDwgMetadata(job.entry, job.dwgPath)
  return {
    dxf_path: job.outPath,
    entity_count: await countEntities(job),
    converter: 'acad-ts',
    warnings: [
      'converted with the acad-ts fallback; the engine crosscheck decides whether it is usable',
      ...metadata.warnings,
    ],
    xrefs: metadata.xrefs,
    styles: metadata.styles,
  }
}

/**
 * The converter's own entity count, which ADR-0002 개정 §4 compares against the
 * engine's `stats.totals.entity_count` with a ±0.5% band. It has to be a real
 * count from the same parser — a size estimate would fail the gate for every
 * file — so `acad-bridge stats` runs over the DXF that was just written.
 * Returning 0 when that second pass fails makes the gate reject the conversion,
 * which is the safe direction.
 */
async function countEntities(job: FallbackJob): Promise<number> {
  if (!job.entry) return 0
  const out = join(tmpdir(), `halo-acadts-stats-${String(process.pid)}-${String(Date.now())}.json`)
  try {
    await execFileAsync(process.execPath, [job.entry, 'stats', job.outPath, '--out', out], {
      timeout: FALLBACK_TIMEOUT_MS,
      maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    })
    const parsed: unknown = JSON.parse(await readFile(out, 'utf8'))
    const totals = (parsed as { totals?: { entity_count?: unknown } }).totals
    return typeof totals?.entity_count === 'number' ? totals.entity_count : 0
  } catch {
    return 0
  }
}
