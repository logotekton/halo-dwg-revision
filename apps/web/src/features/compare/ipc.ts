/**
 * Thin wrappers around `window.halocad.dialog/clipboard/shell`
 * (docs/contracts/r1.md §8, this task's own `apps/desktop/src/main/ipc.ts`
 * additions). `window.halocad`'s ambient type comes from
 * `apps/web/src/api/halocad.d.ts` (picked up automatically via tsconfig's
 * "include": ["src"]) -- same pattern as `features/xref/api.ts`'s
 * `pickOneFile`.
 */

/** Screen A's "폴더 선택…" buttons. `null` when the user cancels the native
 * dialog (brief "Defaults for ambiguity": "취소(null)하면 아무 변화 없음"). */
export function pickFolder(title?: string): Promise<string | null> {
  return window.halocad.dialog.pickFolder(title)
}

export function copyToClipboard(text: string): Promise<void> {
  return window.halocad.clipboard.writeText(text)
}

/** Screen B's "도곽 열기" / a produced output path. */
export function openInOS(path: string): Promise<void> {
  return window.halocad.shell.openPath(path)
}
