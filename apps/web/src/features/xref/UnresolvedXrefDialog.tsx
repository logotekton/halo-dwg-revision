import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { pickOneFile, resolveFileXref, updateSearchPaths, waitForJob, type XrefLink } from './api'

interface UnresolvedXrefDialogProps {
  projectId: string
  fileId: string
  unresolved: XrefLink[]
  onClose: () => void
  /** Called after a resolve/re-import attempt lands (job reached DONE), so
   * the caller can refresh `useXrefLinks` and close the dialog once every
   * block is resolved. */
  onReimported: () => void
}

/**
 * Brief Goal: "임포트 결과에 미해결 XREF가 있으면 다이얼로그가 파일별
 * 목록을 보여주고, 사용자가 폴더를 지정하거나 파일을 개별 매칭하면
 * 프로젝트 검색 경로에 저장되고 재임포트가 실행된다." E2E scenario
 * (brief Constraints): "F10 호스트를 F10_grid.dxf 없이 임시 폴더에서
 * 열면 다이얼로그가 뜨고, 폴더 지정 후 그리드가 보인다."
 *
 * Resolution order itself is entirely the engine's
 * (`engine/src/halo_engine/ingest/xref.py`) -- this dialog only ever adds
 * a search path or a manual file match and asks for a re-import.
 */
export function UnresolvedXrefDialog({
  projectId,
  fileId,
  unresolved,
  onClose,
  onReimported,
}: UnresolvedXrefDialogProps) {
  const { t } = useTranslation()
  const [folderPath, setFolderPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runReimport = async (run: () => Promise<{ jobId: string }>): Promise<void> => {
    setBusy(true)
    setError(null)
    try {
      const { jobId } = await run()
      const status = await waitForJob(jobId)
      if (status !== 'DONE') {
        setError(t('xref.dialog.reimportFailed'))
        return
      }
      onReimported()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleAddFolder = (): void => {
    const trimmed = folderPath.trim()
    if (!trimmed) return
    void runReimport(async () => {
      const result = await updateSearchPaths(projectId, [trimmed], [fileId])
      setFolderPath('')
      return { jobId: result.jobIds[0] ?? '' }
    })
  }

  const handleMatchFile = (blockName: string): void => {
    void runReimport(async () => {
      const picked = await pickOneFile()
      if (!picked) throw new Error('cancelled')
      return resolveFileXref(fileId, blockName, picked)
    })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="xref-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="w-[440px] rounded-md border border-neutral-700 bg-neutral-900 p-4 text-sm text-neutral-200 shadow-xl">
        <h2 id="xref-dialog-title" className="mb-1 text-base font-semibold">
          {t('xref.dialog.title')}
        </h2>
        <p className="mb-3 text-xs text-neutral-400">{t('xref.dialog.description')}</p>

        <ul className="mb-3 max-h-48 overflow-y-auto rounded border border-neutral-800">
          {unresolved.map((link) => (
            <li
              key={link.blockName}
              className="flex items-center justify-between gap-2 border-b border-neutral-800 px-2 py-1.5 last:border-b-0"
            >
              <div className="min-w-0">
                <div className="truncate font-medium">{link.blockName}</div>
                <div className="truncate text-xs text-neutral-500">{link.declaredPath}</div>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  handleMatchFile(link.blockName)
                }}
                className="shrink-0 rounded border border-neutral-700 px-2 py-1 text-xs hover:bg-neutral-800 disabled:opacity-50"
              >
                {t('xref.dialog.matchFile')}
              </button>
            </li>
          ))}
        </ul>

        <div className="mb-3 flex gap-2">
          <input
            type="text"
            value={folderPath}
            onChange={(e) => {
              setFolderPath(e.target.value)
            }}
            placeholder={t('xref.dialog.addFolderPlaceholder')}
            disabled={busy}
            className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 placeholder:text-neutral-600"
          />
          <button
            type="button"
            disabled={busy || !folderPath.trim()}
            onClick={handleAddFolder}
            className="shrink-0 rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {t('xref.dialog.addFolder')}
          </button>
        </div>

        {busy && <p className="mb-2 text-xs text-neutral-500">{t('xref.dialog.reimporting')}</p>}
        {error && (
          <p role="alert" className="mb-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
          >
            {t('xref.dialog.close')}
          </button>
        </div>
      </div>
    </div>
  )
}
