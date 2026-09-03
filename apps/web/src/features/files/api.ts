import type { HaloCadApi } from '../../api/halocad'

/**
 * `window.halocad.files.pickDrawings()` (docs/contracts/wave-3.md "IPC
 * 채널": `halocad:files:pick-drawings`). Its type isn't merged into
 * `apps/web/src/api/halocad.d.ts`'s `HaloCadApi` here because
 * `apps/web/src/api/**` isn't in this task's "Files you own" glob (see the
 * task report's "Shared-file patch" proposing `files` be added there
 * officially -- W3-02 will hit the identical situation for
 * `viewer.assetsBase`). Declared as a local intersection type instead of
 * widening the global `Window` interface from a file outside this task's
 * ownership.
 */
type HaloCadApiWithFiles = HaloCadApi & {
  files: {
    pickDrawings: () => Promise<string[]>
  }
}

export function pickDrawings(): Promise<string[]> {
  return (window.halocad as HaloCadApiWithFiles).files.pickDrawings()
}
