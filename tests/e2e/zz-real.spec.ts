import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { REPO_ROOT } from '../../packages/testing/src/electron'
import { createViewerSession, openFixture, viewerStatus } from '../../packages/testing/src/viewer'

const S = '/Users/ythong/Desktop/대명건설/Free CAD for Mac OS/samples/2026-09-02-실시도서/##실시도서(시공도면 수정)'
const ALL = [
  ['02_기계', '02_기계/01_기계도면(김화공고 모듈러 생활관 증축공사)_수정.DWG'],
  ['03_전기', '03_전기/김화공업고등학교 모듈러 생활관 제작·설치 구매_전기도서 (1).dwg'],
  ['04_통신', '04_통신/김화공업고등학교 모듈러 생활관 제작·설치 구매_통신도서.dwg'],
  ['05_소방기계-1', '05_소방_기계/01_기계소방도면(김화공고 모듈러 생활관 증축공사).dwg'],
  ['05_소방기계-2', '05_소방_기계/02_기계소방내진도면(김화공고 모듈러 생활관 증축공사).dwg'],
  ['06_소방전기', '06_소방_전기/김화공업고등학교 모듈러 생활관 제작·설치 구매_전기소방도서 (3).dwg'],
]
const ONLY = process.env.HALO_REAL_ONLY ? process.env.HALO_REAL_ONLY.split(',') : null
const FILES = ALL.filter(([label]) => !ONLY || ONLY.includes(label))

/** Summed RSS of the whole Electron process tree, in bytes. */
function treeRss(rootPid) {
  const out = execFileSync('ps', ['-eo', 'pid=,ppid=,rss='], { encoding: 'utf8' })
  const rows = out
    .trim()
    .split('\n')
    .map((line) => line.trim().split(/\s+/).map(Number))
  const children = new Map()
  for (const [pid, ppid, rss] of rows) {
    if (!children.has(ppid)) children.set(ppid, [])
    children.get(ppid).push({ pid, rss })
  }
  let total = 0
  const stack = [rootPid]
  const seen = new Set()
  while (stack.length > 0) {
    const pid = stack.pop()
    if (seen.has(pid)) continue
    seen.add(pid)
    const self = rows.find((row) => row[0] === pid)
    if (self) total += self[2] * 1024
    for (const child of children.get(pid) ?? []) stack.push(child.pid)
  }
  return total
}

for (const [label, relative] of FILES) {
  test(`facility drawing ${label}`, async () => {
    test.setTimeout(420_000)
    const file = join(S, relative)
    const session = createViewerSession()
    await session.start([file])
    const pid = session.pid()
    const rssBefore = treeRss(pid)
    const started = Date.now()
    let result
    try {
      result = await openFixture(session.page, file)
      await expect.poll(() => viewerStatus(session.page), { timeout: 240_000 }).toBe('ready')
    } catch (error) {
      console.log('FACILITY ' + JSON.stringify({ label, ok: false, ms: Date.now() - started, error: String(error).slice(0, 400) }))
      await session.stop()
      return
    }
    const ms = Date.now() - started
    const measured = await session.page.evaluate(() => {
      const hooks = window.__haloViewer
      return hooks ? { heap: hooks.heapUsedBytes(), load: hooks.renderLoad() } : null
    })
    const rss = treeRss(pid)
    console.log('FACILITY ' + JSON.stringify({
      label,
      ok: true,
      converter: result.converter,
      entities: result.entityCount,
      load: measured?.load ?? null,
      ms,
      heapMb: Math.round((measured?.heap ?? 0) / 1e6),
      rssMb: Math.round(rss / 1e6),
      rssBeforeMb: Math.round(rssBefore / 1e6),
    }))
    await session.page.screenshot({ path: join(REPO_ROOT, `test-results/viewer/facility-${label}.png`) })
    await session.stop()
  })
}
