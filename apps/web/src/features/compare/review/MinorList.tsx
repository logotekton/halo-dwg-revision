import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { Change } from '../reviewApi'

/**
 * "접힌 항목 n건" -- the changes the fold rules dropped (`minor: true`),
 * grouped by `minor_reason` (brief R1-08 Goal 1). They draw nothing on the
 * canvas and get no cloud mark; this list is the only place they are visible,
 * which is what makes 접기 auditable rather than silent.
 */

/** A reason may be several fold reasons joined with `+`
 * (`docs/contracts/r1.md` §3, e.g. `layer_only+color_only`); each part is
 * translated on its own so the pair reads as "레이어만 + 색만". */
export function minorReasonKeys(reason: string | null | undefined): string[] {
  if (!reason) return ['unknown']
  const parts = reason
    .split('+')
    .map((part) => part.trim())
    .filter((part) => part !== '')
  return parts.length > 0 ? parts : ['unknown']
}

export interface MinorGroup {
  reason: string
  changes: Change[]
}

/** Groups by the raw `minor_reason` string (so `layer_only+color_only` is its
 * own group, not two half-groups), reason-sorted for a stable list. */
export function groupMinorChanges(changes: Change[]): MinorGroup[] {
  const groups = new Map<string, Change[]>()
  for (const change of changes) {
    if (!change.minor) continue
    const reason = change.minor_reason ?? ''
    const bucket = groups.get(reason)
    if (bucket) bucket.push(change)
    else groups.set(reason, [change])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([reason, items]) => ({ reason, changes: items }))
}

export function MinorList({
  changes,
  expanded,
  onToggle,
}: {
  changes: Change[]
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const groups = useMemo(() => groupMinorChanges(changes), [changes])
  const total = useMemo(() => groups.reduce((sum, group) => sum + group.changes.length, 0), [groups])

  if (total === 0) return null

  return (
    <div className="mt-2">
      <button
        type="button"
        className="hc-btn w-full"
        data-testid="minor-toggle"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        {t('compare.review.minor.toggle', { count: total })}
      </button>

      {expanded && (
        <ul
          role="list"
          aria-label={t('compare.review.minor.listLabel')}
          data-testid="minor-list"
          className="mt-1 flex flex-col gap-1"
        >
          {groups.map((group) => (
            <li
              role="listitem"
              key={group.reason || 'unknown'}
              className="flex items-center justify-between px-2 py-1 text-xs"
              style={{ color: 'var(--muted)' }}
            >
              <span>
                {minorReasonKeys(group.reason)
                  .map((key) => t(`compare.review.minorReason.${key}`))
                  .join(' + ')}
              </span>
              <span className="font-mono">
                {t('compare.review.minor.groupCount', { count: group.changes.length })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
