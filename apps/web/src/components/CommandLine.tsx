import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useViewerStore } from '../state/viewer'

/**
 * Bottom command line. Brief W3-01 "Defaults for ambiguity": "명령줄은 입력
 * 히스토리만 구현. 실행은 viewer 스토어의 pendingCommand에 넣어 W3-02가
 * 소비" -- this component only tracks input history locally (Up/Down to
 * recall) and hands a submitted line to `viewer.submitCommand`; it does not
 * interpret or execute anything itself.
 */
export function CommandLine() {
  const { t } = useTranslation()
  const submitCommand = useViewerStore((state) => state.submitCommand)
  const [value, setValue] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState<number | null>(null)

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === 'Enter') {
      const trimmed = value.trim()
      if (trimmed) {
        submitCommand(trimmed)
        setHistory((prev) => [...prev, trimmed])
      }
      setValue('')
      setHistoryIndex(null)
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (history.length === 0) return
      const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1)
      const entry = history[nextIndex]
      if (entry !== undefined) {
        setHistoryIndex(nextIndex)
        setValue(entry)
      }
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (historyIndex === null) return
      const nextIndex = historyIndex + 1
      if (nextIndex >= history.length) {
        setHistoryIndex(null)
        setValue('')
        return
      }
      const entry = history[nextIndex]
      if (entry !== undefined) {
        setHistoryIndex(nextIndex)
        setValue(entry)
      }
    }
  }

  return (
    <div className="flex h-8 shrink-0 items-center gap-2 border-t border-neutral-800 bg-neutral-950 px-3">
      <label htmlFor="halo-command-line" className="sr-only">
        {t('commandLine.label')}
      </label>
      <input
        id="halo-command-line"
        type="text"
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
        }}
        onKeyDown={handleKeyDown}
        placeholder={t('commandLine.placeholder')}
        className="w-full bg-transparent text-xs text-neutral-200 outline-none placeholder:text-neutral-600"
      />
    </div>
  )
}
