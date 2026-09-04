import { useTranslation } from 'react-i18next'
import { AppHeader } from '../components/AppHeader'
import { StatusBar } from '../components/StatusBar'
import { CompareApp } from '../features/compare/CompareApp'
import { useCompareStore } from '../state/compare'

/**
 * App shell (brief R1-05 Goal 1): `AppHeader` (title + step indicator) +
 * `CompareApp` (screens A-D) + `StatusBar`. The previous Halo CAD shell
 * (menu bar, left/right docks, tab strip, command line, `features/files`'s
 * "열기" flow, `features/xref`'s dialog) is no longer rendered here -- R1
 * is a single guided compare flow, not a general CAD shell -- but none of
 * those components or their tests were deleted (CLAUDE.md's directory
 * ownership table keeps `apps/web/src/features/xref/**` and
 * `features/files/**` intact; this task only stops mounting them).
 * `#viewer-root` (R1-00a's CadHost mount point) is not in this file any
 * more -- it now lives inside `features/compare/ReviewScreen.tsx`, screen
 * C's placeholder, which is the only screen that will ever need it.
 */
export function App() {
  const { t } = useTranslation()
  const screen = useCompareStore((state) => state.screen)

  return (
    // Background/text colour come from `body` (styles/index.css's `--bg`/
    // `--text` tokens) -- this wrapper only needs the flex layout.
    <div className="flex h-screen flex-col">
      <AppHeader title={t('app.title')} currentScreen={screen} />
      <CompareApp />
      <StatusBar />
    </div>
  )
}

export default App
