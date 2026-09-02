import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AppHeader } from '../components/AppHeader'
import { CommandLine } from '../components/CommandLine'
import { LeftDock } from '../components/LeftDock'
import { RightDock } from '../components/RightDock'
import { StatusBar } from '../components/StatusBar'
import { TabStrip } from '../components/TabStrip'
import { useFilesFeature } from '../features/files/useFilesFeature'
import { useDocumentsStore, type DocumentTab } from '../state/documents'
import { registerHaloTestHook } from '../test-hooks'
import { useShortcuts } from './useShortcuts'

function basename(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path // eslint-disable-line @typescript-eslint/prefer-nullish-coalescing -- also falls back on an empty-string segment (trailing slash), not just null/undefined
}

function toTab(path: string): DocumentTab {
  // fileId stands in for a real drawing-file id until W3-03's project API
  // is wired up (brief W3-01 Goal: "실제 임포트는 W3-02/03 병합 후 연결");
  // layers stays 0 until then too -- see apps/web/src/state/documents.ts.
  return { fileId: path, name: basename(path), layers: 0 }
}

export function App() {
  const { t } = useTranslation()
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)

  const tabs = useDocumentsStore((state) => state.tabs)
  const activeFileId = useDocumentsStore((state) => state.activeFileId)
  const openTab = useDocumentsStore((state) => state.openTab)
  const closeTab = useDocumentsStore((state) => state.closeTab)
  const setActive = useDocumentsStore((state) => state.setActive)
  const cycleActive = useDocumentsStore((state) => state.cycleActive)

  const { recent, openFiles, openRecent } = useFilesFeature()

  const handleOpen = useCallback((): void => {
    void openFiles().then((paths) => {
      paths.forEach((path) => {
        openTab(toTab(path))
      })
    })
  }, [openFiles, openTab])

  const handleOpenRecent = useCallback(
    (path: string): void => {
      openRecent(path)
      openTab(toTab(path))
    },
    [openRecent, openTab],
  )

  const handleCloseActiveTab = useCallback((): void => {
    if (activeFileId) closeTab(activeFileId)
  }, [activeFileId, closeTab])

  const toggleLeftDock = useCallback(() => {
    setLeftCollapsed((prev) => !prev)
  }, [])
  const toggleRightDock = useCallback(() => {
    setRightCollapsed((prev) => !prev)
  }, [])

  useShortcuts({
    onOpen: handleOpen,
    onCloseTab: handleCloseActiveTab,
    onCycleTab: () => {
      cycleActive(1)
    },
  })

  // docs/contracts/wave-3.md "테스트 훅": window.__haloTest.getDocuments().
  // Registered once; the getter reads the store live via getState() rather
  // than closing over a snapshot, so it stays correct as tabs change.
  useEffect(() => {
    registerHaloTestHook('getDocuments', () => useDocumentsStore.getState().tabs)
  }, [])

  return (
    <div className="flex h-screen flex-col bg-neutral-950 text-neutral-100">
      <AppHeader
        title={t('app.title')}
        canCloseActiveTab={activeFileId !== null}
        recentFiles={recent}
        leftDockCollapsed={leftCollapsed}
        rightDockCollapsed={rightCollapsed}
        onOpen={handleOpen}
        onOpenRecent={handleOpenRecent}
        onCloseActiveTab={handleCloseActiveTab}
        onToggleLeftDock={toggleLeftDock}
        onToggleRightDock={toggleRightDock}
      />
      <TabStrip tabs={tabs} activeFileId={activeFileId} onSelect={setActive} onClose={closeTab} />
      <div className="flex flex-1 overflow-hidden">
        <LeftDock collapsed={leftCollapsed} onToggle={toggleLeftDock} />
        {/* #viewer-root must stay an empty container -- W3-02's CadHost
            mounts the actual canvas into it directly. */}
        <main className="relative flex-1 overflow-hidden" aria-label={t('viewer.areaLabel')}>
          <div id="viewer-root" className="absolute inset-0" />
          {tabs.length === 0 && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-neutral-500">
              {t('viewer.placeholder')}
            </div>
          )}
        </main>
        <RightDock collapsed={rightCollapsed} onToggle={toggleRightDock} />
      </div>
      <CommandLine />
      <StatusBar />
    </div>
  )
}

export default App
