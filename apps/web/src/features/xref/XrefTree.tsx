import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { XrefLink } from './api'

interface XrefTreeProps {
  hostName: string
  links: XrefLink[]
  loading?: boolean
  error?: string | null
  /**
   * Display-only layer-visibility toggle (brief Goal: "언로드/리로드
   * 토글은 표시 전용(정본 재생성 없이 레이어 xref$0$* 가시성으로)"). Wired
   * by whichever caller owns the live `CadHost` instance
   * (`packages/cad-core`, `apps/web/src/features/viewer/**` -- both
   * outside this task's "Files you own"); a no-op here just renders the
   * toggle disabled instead of crashing, so this component is usable
   * standalone before that wiring lands (report Follow-ups).
   */
  onToggleVisibility?: (blockName: string, visible: boolean) => void
}

/**
 * File panel's XREF tree (brief Goal: "파일 패널에 XREF 트리(호스트 -> 참조,
 * 상태 아이콘)"). One host file's `GET /files/{id}/xrefs` result as a flat
 * list under the host name -- the resolution graph itself can nest (brief
 * addendum 1: recursive DWG XREF targets), but `xref_link` rows are
 * per-host-per-block, so a second level of nesting would need a second
 * `GET .../xrefs` call per resolved target and is left for when that data
 * is actually surfaced (report Follow-ups).
 */
export function XrefTree({ hostName, links, loading, error, onToggleVisibility }: XrefTreeProps) {
  const { t } = useTranslation()
  const [visibility, setVisibility] = useState<Record<string, boolean>>({})

  const isVisible = (blockName: string): boolean => visibility[blockName] ?? true

  const toggle = (blockName: string): void => {
    const next = !isVisible(blockName)
    setVisibility((prev) => ({ ...prev, [blockName]: next }))
    onToggleVisibility?.(blockName, next)
  }

  return (
    <div className="text-xs">
      <div className="truncate px-1 py-0.5 font-medium text-neutral-300" title={hostName}>
        {hostName}
      </div>
      {loading && <p className="px-1 py-0.5 text-neutral-600">{t('xref.loading')}</p>}
      {error && (
        <p role="alert" className="px-1 py-0.5 text-red-400">
          {t('xref.loadError')}
        </p>
      )}
      {!loading && !error && links.length === 0 && (
        <p className="px-1 py-0.5 text-neutral-600">{t('xref.empty')}</p>
      )}
      {links.length > 0 && (
        <ul>
          {links.map((link) => {
            const resolved = link.status === 'RESOLVED'
            const visible = isVisible(link.blockName)
            return (
              <li key={link.blockName} className="flex items-center gap-1.5 py-0.5 pl-4 pr-1">
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${resolved ? 'bg-emerald-500' : 'bg-red-500'}`}
                />
                <span
                  className="min-w-0 flex-1 truncate text-neutral-300"
                  title={link.declaredPath}
                >
                  {link.blockName}
                </span>
                <span className="shrink-0 text-neutral-600">
                  {resolved ? t('xref.status.resolved') : t('xref.status.unresolved')}
                </span>
                <button
                  type="button"
                  disabled={!resolved}
                  title={t('xref.visibility.hint')}
                  onClick={() => {
                    toggle(link.blockName)
                  }}
                  className="shrink-0 rounded px-1 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-200 disabled:opacity-30 disabled:hover:bg-transparent"
                >
                  {visible ? t('xref.visibility.unload') : t('xref.visibility.reload')}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
