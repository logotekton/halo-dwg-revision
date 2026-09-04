import { useRef, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import type { Cluster, ClusterDecision } from '../reviewApi'

/**
 * One cloud mark: number badge, kind, the label (editable), the decision chip
 * and the 승인·무시 buttons, plus a free memo (brief R1-08 Goal 1).
 *
 * The row edits `user_label` and `note` only; `label` is the engine's
 * automatic wording (`compare/labels.py`) and is what shows through until the
 * user types over it.
 */

const DECISION_STYLE: Record<ClusterDecision, CSSProperties> = {
  pending: { color: 'var(--muted)', borderColor: 'var(--muted)' },
  approved: { color: 'var(--ok)', borderColor: 'var(--ok)' },
  ignored: { color: 'var(--warn)', borderColor: 'var(--warn)' },
}

export function ClusterRow({
  cluster,
  selected,
  onSelect,
  onDecide,
  onLabel,
  onNote,
}: {
  cluster: Cluster
  selected: boolean
  onSelect: (number: number) => void
  onDecide: (number: number, decision: ClusterDecision) => void
  onLabel: (number: number, text: string) => void
  onNote: (number: number, text: string) => void
}) {
  const { t } = useTranslation()
  const displayLabel = cluster.user_label ?? cluster.label

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(displayLabel)
  // Enter and Escape both take the input away, and removing a focused element
  // can still fire `blur` -- without this the Escape path would immediately
  // save the very draft it just discarded.
  const skipBlur = useRef(false)

  function startEditing(): void {
    setDraft(displayLabel)
    setEditing(true)
  }

  function commitLabel(): void {
    setEditing(false)
    if (draft !== displayLabel) onLabel(cluster.number, draft)
  }

  function cancelLabel(): void {
    setEditing(false)
    setDraft(displayLabel)
  }

  return (
    <li
      role="listitem"
      data-testid={`cluster-row-${String(cluster.number)}`}
      data-selected={String(selected)}
      data-decision={cluster.decision}
      className="hc-panel-2 flex flex-col gap-1 p-2 text-xs"
      style={selected ? { borderColor: 'var(--accent-2)' } : undefined}
      onClick={() => {
        onSelect(cluster.number)
      }}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="hc-chip font-mono"
          data-testid={`cluster-number-${String(cluster.number)}`}
          aria-label={t('compare.review.zoomTo', { number: cluster.number })}
          onClick={(event) => {
            event.stopPropagation()
            onSelect(cluster.number)
          }}
        >
          {cluster.number}
        </button>
        <span style={{ color: 'var(--muted)' }}>{t(`compare.review.kind.${cluster.kind}`)}</span>
        <span className="hc-badge ml-auto" data-testid={`cluster-decision-${String(cluster.number)}`} style={DECISION_STYLE[cluster.decision]}>
          {t(`compare.review.decision.${cluster.decision}`)}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {editing ? (
          <input
            className="hc-input flex-1"
            autoFocus
            aria-label={t('compare.review.labelEdit', { number: cluster.number })}
            placeholder={t('compare.review.labelPlaceholder')}
            value={draft}
            onClick={(event) => {
              event.stopPropagation()
            }}
            onChange={(event) => {
              setDraft(event.target.value)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                skipBlur.current = true
                commitLabel()
              } else if (event.key === 'Escape') {
                skipBlur.current = true
                cancelLabel()
              }
              event.stopPropagation()
            }}
            onBlur={() => {
              if (skipBlur.current) {
                skipBlur.current = false
                return
              }
              commitLabel()
            }}
          />
        ) : (
          <button
            type="button"
            className="hc-btn flex-1 justify-start"
            aria-label={t('compare.review.labelEdit', { number: cluster.number })}
            onClick={(event) => {
              event.stopPropagation()
              onSelect(cluster.number)
              startEditing()
            }}
          >
            {displayLabel}
          </button>
        )}

        <button
          type="button"
          className="hc-btn"
          data-testid={`cluster-approve-${String(cluster.number)}`}
          aria-label={t('compare.review.approveAria', { number: cluster.number })}
          onClick={(event) => {
            event.stopPropagation()
            onDecide(cluster.number, 'approved')
          }}
        >
          {t('compare.review.approve')}
        </button>
        <button
          type="button"
          className="hc-btn"
          data-testid={`cluster-ignore-${String(cluster.number)}`}
          aria-label={t('compare.review.ignoreAria', { number: cluster.number })}
          onClick={(event) => {
            event.stopPropagation()
            onDecide(cluster.number, 'ignored')
          }}
        >
          {t('compare.review.ignore')}
        </button>
      </div>

      {/* Uncontrolled, and re-keyed on the stored memo: the field keeps what
          the user is typing without a state sync, and a memo that changed
          somewhere else (a reload, or this row's own save landing) replaces
          the field rather than fighting it. */}
      <input
        key={`note-${cluster.note ?? ''}`}
        className="hc-input"
        aria-label={t('compare.review.noteEdit', { number: cluster.number })}
        placeholder={t('compare.review.notePlaceholder')}
        defaultValue={cluster.note ?? ''}
        onClick={(event) => {
          event.stopPropagation()
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          event.stopPropagation()
        }}
        onBlur={(event) => {
          const value = event.target.value
          if (value !== (cluster.note ?? '')) onNote(cluster.number, value)
        }}
      />
    </li>
  )
}
