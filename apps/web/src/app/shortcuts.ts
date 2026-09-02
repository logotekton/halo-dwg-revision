/**
 * Pure keyboard-shortcut predicates (brief W3-01 Constraints: "단축키:
 * Cmd/Ctrl+O 열기, Cmd/Ctrl+W 탭 닫기, Ctrl+Tab 탭 전환"). Split out from
 * `useShortcuts.ts` so the matching logic is unit-testable without
 * mounting a component or touching the DOM.
 *
 * Cmd on macOS, Ctrl elsewhere -- `event.metaKey || event.ctrlKey` covers
 * both without a platform check. Ctrl+Tab is Ctrl-only (not Cmd+Tab, which
 * is the OS's own app switcher on macOS and must not be intercepted).
 */
export function isOpenShortcut(event: KeyboardEvent): boolean {
  return isPrimaryModifierOnly(event) && event.key.toLowerCase() === 'o'
}

export function isCloseTabShortcut(event: KeyboardEvent): boolean {
  return isPrimaryModifierOnly(event) && event.key.toLowerCase() === 'w'
}

export function isCycleTabShortcut(event: KeyboardEvent): boolean {
  return event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.key === 'Tab'
}

function isPrimaryModifierOnly(event: KeyboardEvent): boolean {
  return (event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey
}
