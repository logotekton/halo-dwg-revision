import { StepIndicator } from './StepIndicator'
import type { CompareScreen } from '../state/compare'

/**
 * App shell header (brief R1-05 Goal 1): title + the A→D step indicator.
 * The menu bar, dock toggles, and "열기"/"최근 파일" controls this header
 * used to render (`docs/contracts/wave-3.md`) are gone -- the compare flow
 * has no menu, no docks, and no open-file concept; `MenuBar.tsx` and
 * `OpenFilesButton.tsx` are left in place (not deleted) but nothing renders
 * them any more.
 */
interface AppHeaderProps {
  title: string
  currentScreen: CompareScreen
}

export function AppHeader({ title, currentScreen }: AppHeaderProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-neutral-800 bg-neutral-900 px-4">
      <span className="text-sm font-semibold text-neutral-100">{title}</span>
      <StepIndicator current={currentScreen} />
    </header>
  )
}
