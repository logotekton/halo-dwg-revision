import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface MenuItemDef {
  key: string
  label: string
  onSelect?: () => void
  disabled?: boolean
  /** For a toggle-style item (e.g. "왼쪽 도크 표시/숨김"): reflected as aria-pressed. */
  pressed?: boolean
}

export interface MenuDef {
  key: string
  label: string
  items: MenuItemDef[]
}

interface MenuBarProps {
  menus: MenuDef[]
}

/**
 * Minimal dropdown menu bar (File/Edit/View/Help per brief W3-01). Not a
 * design-system component -- CLAUDE.md rule 10 keeps this task's dependency
 * footprint to Zustand + Tailwind (see the task report's "Decisions" on
 * skipping shadcn/ui/Radix for this shell), so this is a small
 * hand-rolled implementation instead of pulling in a menu primitive.
 *
 * Every item without a real handler must render `disabled` (brief W3-01
 * Constraints: "동작 없는 항목은 비활성으로 표시") -- callers build `items`
 * accordingly; this component just renders what it's given.
 */
export function MenuBar({ menus }: MenuBarProps) {
  const { t } = useTranslation()
  const [openKey, setOpenKey] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (openKey === null) return

    const closeOnOutsideClick = (event: PointerEvent): void => {
      if (rootRef.current && event.target instanceof Node && !rootRef.current.contains(event.target)) {
        setOpenKey(null)
      }
    }
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setOpenKey(null)
    }

    window.addEventListener('pointerdown', closeOnOutsideClick)
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      window.removeEventListener('pointerdown', closeOnOutsideClick)
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [openKey])

  return (
    <div ref={rootRef} role="menubar" aria-label={t('menu.barLabel')} className="flex items-center gap-0.5">
      {menus.map((menu) => {
        const isOpen = openKey === menu.key
        return (
          <div key={menu.key} className="relative">
            <button
              type="button"
              role="menuitem"
              aria-haspopup="menu"
              aria-expanded={isOpen}
              onClick={() => {
                setOpenKey(isOpen ? null : menu.key)
              }}
              className={`rounded px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100 ${
                isOpen ? 'bg-neutral-800 text-neutral-100' : ''
              }`}
            >
              {menu.label}
            </button>
            {isOpen && (
              <div
                role="menu"
                aria-label={menu.label}
                className="absolute left-0 top-full z-20 mt-1 min-w-[200px] rounded border border-neutral-700 bg-neutral-900 py-1 shadow-lg"
              >
                {menu.items.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitem"
                    disabled={item.disabled}
                    aria-pressed={item.pressed}
                    onClick={() => {
                      if (item.disabled) return
                      item.onSelect?.()
                      setOpenKey(null)
                    }}
                    className={`block w-full truncate px-3 py-1.5 text-left text-xs ${
                      item.disabled
                        ? 'cursor-not-allowed text-neutral-600'
                        : 'text-neutral-200 hover:bg-neutral-800'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
