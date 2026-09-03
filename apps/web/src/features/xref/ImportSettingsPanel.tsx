import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getImportSettings, updateImportSettings, type ImportSettings } from './api'

interface ImportSettingsPanelProps {
  projectId: string
}

function TextList({
  items,
  placeholder,
  addLabel,
  removeLabel,
  emptyLabel,
  onChange,
}: {
  items: string[]
  placeholder: string
  addLabel: string
  removeLabel: string
  emptyLabel?: string
  onChange: (next: string[]) => void
}) {
  const [draft, setDraft] = useState('')

  const add = (): void => {
    const trimmed = draft.trim()
    if (!trimmed || items.includes(trimmed)) return
    onChange([...items, trimmed])
    setDraft('')
  }

  return (
    <div>
      {items.length === 0 && emptyLabel && <p className="mb-1 text-xs text-neutral-600">{emptyLabel}</p>}
      {items.length > 0 && (
        <ul className="mb-2">
          {items.map((item) => (
            <li key={item} className="flex items-center justify-between gap-2 py-0.5">
              <span className="min-w-0 flex-1 truncate text-xs text-neutral-300" title={item}>
                {item}
              </span>
              <button
                type="button"
                aria-label={`${removeLabel}: ${item}`}
                onClick={() => {
                  onChange(items.filter((existing) => existing !== item))
                }}
                className="shrink-0 rounded px-1 text-xs text-neutral-500 hover:bg-neutral-800 hover:text-neutral-200"
              >
                {removeLabel}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
          }}
          placeholder={placeholder}
          className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 placeholder:text-neutral-600"
        />
        <button
          type="button"
          disabled={!draft.trim()}
          onClick={add}
          className="shrink-0 rounded border border-neutral-700 px-2 py-1 text-xs hover:bg-neutral-800 disabled:opacity-50"
        >
          {addLabel}
        </button>
      </div>
    </div>
  )
}

/**
 * "설정 UI는 단순 텍스트 목록" (brief addendum 3): a project's XREF search
 * paths and its `import.ignore_patterns` exclusion list, both edited as
 * plain add/remove text lists. Reachable from wherever the wave-3b
 * settings surface ends up mounting it -- not wired into the app shell
 * here (`apps/web/src/app/App.tsx`/dock components are outside this
 * task's "Files you own"; report Follow-ups).
 */
export function ImportSettingsPanel({ projectId }: ImportSettingsPanelProps) {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<ImportSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    getImportSettings(projectId)
      .then((result) => {
        if (!cancelled) setSettings(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const save = (next: ImportSettings): void => {
    setSettings(next)
    setSaved(false)
    updateImportSettings(projectId, next)
      .then(() => {
        setSaved(true)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err))
      })
  }

  if (error) {
    return (
      <p role="alert" className="p-2 text-xs text-red-400">
        {t('xref.settings.saveError')}
      </p>
    )
  }
  if (!settings) return null

  return (
    <div className="p-2 text-xs">
      <h3 className="mb-1 font-medium text-neutral-300">{t('xref.settings.searchPathsTitle')}</h3>
      <TextList
        items={settings.searchPaths}
        placeholder={t('xref.settings.searchPathsPlaceholder')}
        addLabel={t('xref.settings.addPath')}
        removeLabel={t('xref.settings.removePath')}
        emptyLabel={t('xref.settings.searchPathsEmpty')}
        onChange={(searchPaths) => {
          save({ ...settings, searchPaths })
        }}
      />

      <h3 className="mb-1 mt-3 font-medium text-neutral-300">
        {t('xref.settings.ignorePatternsTitle')}
      </h3>
      <TextList
        items={settings.ignorePatterns}
        placeholder={t('xref.settings.ignorePatternsPlaceholder')}
        addLabel={t('xref.settings.addPattern')}
        removeLabel={t('xref.settings.removePattern')}
        onChange={(ignorePatterns) => {
          save({ ...settings, ignorePatterns })
        }}
      />

      {saved && <p className="mt-2 text-neutral-600">{t('xref.settings.saved')}</p>}
    </div>
  )
}
