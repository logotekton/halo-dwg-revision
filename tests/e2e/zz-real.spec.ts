import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { REPO_ROOT } from '../../packages/testing/src/electron'
import { createViewerSession, openFixture, viewerStatus } from '../../packages/testing/src/viewer'

/**
 * Opt-in run over the real facility drawings (`docs/contracts/r1.md` §12).
 *
 * It is **off unless `HALO_E2E_REAL=1`**: `samples/` is gitignored, absent from
 * every worktree and from CI, so `tools/verify.sh --e2e` must stay green
 * without it (brief R1-00a, Constraints). Nothing here asserts a pass/fail
 * threshold — the six 설비 drawings of `docs/contracts/wave-3.md` are opened one
 * per Electron process and the render load, heap and RSS are printed for the
 * report. The named file is the measurement; a failure to open is logged, not
 * thrown, so one bad drawing does not hide the numbers of the other five.
 *
 * ```bash
 * HALO_E2E_REAL=1 HALO_E2E_REAL_DIR=/path/to/samples/2026-09-02-실시도서 \
 *   pnpm --filter @halo-cad/testing e2e zz-real
 * ```
 */

/** Default location, relative to the repo: the set the ledger names. */
const DEFAULT_SET_DIR = join(REPO_ROOT, 'samples', '2026-09-02-실시도서')
const SET_DIR = process.env.HALO_E2E_REAL_DIR ?? DEFAULT_SET_DIR
/** The drawings live one level below, under the delivery folder. */
const DELIVERY_DIR = '##실시도서(시공도면 수정)'

const ALL: [string, string][] = [
  ['02_기계', '02_기계/01_기계도면(김화공고 모듈러 생활관 증축공사)_수정.DWG'],
  ['03_전기', '03_전기/김화공업고등학교 모듈러 생활관 제작·설치 구매_전기도서 (1).dwg'],
  ['04_통신', '04_통신/김화공업고등학교 모듈러 생활관 제작·설치 구매_통신도서.dwg'],
  ['05_소방기계-1', '05_소방_기계/01_기계소방도면(김화공고 모듈러 생활관 증축공사).dwg'],
  ['05_소방기계-2', '05_소방_기계/02_기계소방내진도면(김화공고 모듈러 생활관 증축공사).dwg'],
  ['06_소방전기', '06_소방_전기/김화공업고등학교 모듈러 생활관 제작·설치 구매_전기소방도서 (3).dwg'],
]

const ONLY = process.env.HALO_REAL_ONLY?.split(',')
const FILES = ALL.filter(([label]) => !ONLY || ONLY.includes(label))
const ENABLED = process.env.HALO_E2E_REAL === '1'

interface ProcessRow {
  pid: number
  ppid: number
  rssBytes: number
}

/** Summed RSS of the whole Electron process tree, in bytes. */
function treeRss(rootPid: number): number {
  const out = execFileSync('ps', ['-eo', 'pid=,ppid=,rss='], { encoding: 'utf8' })
  const rows: ProcessRow[] = []
  for (const line of out.trim().split('\n')) {
    const [pid, ppid, rss] = line.trim().split(/\s+/).map(Number)
    if (pid === undefined || ppid === undefined || rss === undefined) continue
    rows.push({ pid, ppid, rssBytes: rss * 1024 })
  }
  const children = new Map<number, number[]>()
  for (const row of rows) {
    const siblings = children.get(row.ppid) ?? []
    siblings.push(row.pid)
    children.set(row.ppid, siblings)
  }
  let total = 0
  const stack = [rootPid]
  const seen = new Set<number>()
  while (stack.length > 0) {
    const pid = stack.pop()
    if (pid === undefined || seen.has(pid)) continue
    seen.add(pid)
    total += rows.find((row) => row.pid === pid)?.rssBytes ?? 0
    for (const child of children.get(pid) ?? []) stack.push(child)
  }
  return total
}

for (const [label, relative] of FILES) {
  test(`facility drawing ${label}`, async () => {
    test.skip(!ENABLED, 'HALO_E2E_REAL=1일 때만 실행합니다 (samples/는 저장소에 없습니다)')
    const file = join(SET_DIR, DELIVERY_DIR, relative)
    test.skip(!existsSync(file), `실도면이 없습니다: ${file}`)
    test.setTimeout(420_000)

    const session = createViewerSession()
    await session.start([file])
    const pid = session.pid()
    const rssBefore = treeRss(pid)
    const started = Date.now()
    try {
      const result = await openFixture(session.page, file)
      await expect.poll(() => viewerStatus(session.page), { timeout: 240_000 }).toBe('ready')
      const measured = await session.page.evaluate(() => {
        const hooks = window.__haloViewer
        return hooks ? { heap: hooks.heapUsedBytes() ?? 0, load: hooks.renderLoad() } : null
      })
      // eslint-disable-next-line no-console -- the numbers are the deliverable
      console.log(
        `FACILITY ${JSON.stringify({
          label,
          ok: true,
          converter: result.converter,
          entities: result.entityCount,
          load: measured?.load ?? null,
          ms: Date.now() - started,
          heapMb: Math.round((measured?.heap ?? 0) / 1e6),
          rssMb: Math.round(treeRss(pid) / 1e6),
          rssBeforeMb: Math.round(rssBefore / 1e6),
        })}`,
      )
      await session.page.screenshot({
        path: join(REPO_ROOT, `test-results/viewer/facility-${label}.png`),
      })
    } catch (error) {
      // eslint-disable-next-line no-console -- a failure is also a measurement
      console.log(
        `FACILITY ${JSON.stringify({
          label,
          ok: false,
          ms: Date.now() - started,
          error: String(error).slice(0, 400),
        })}`,
      )
    } finally {
      await session.stop()
    }
  })
}
