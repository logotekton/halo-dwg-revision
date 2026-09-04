import { useTranslation } from 'react-i18next'
import { ClusterRow } from './ClusterRow'
import type { Cluster, ClusterDecision } from '../reviewApi'

/** The right-hand panel's cloud-mark list, in cluster-number order (the same
 * order as the badges on the drawing and the revision table's rows). */
export function ClusterList({
  clusters,
  selected,
  onSelect,
  onDecide,
  onLabel,
  onNote,
}: {
  clusters: Cluster[]
  selected: number | null
  onSelect: (number: number) => void
  onDecide: (number: number, decision: ClusterDecision) => void
  onLabel: (number: number, text: string) => void
  onNote: (number: number, text: string) => void
}) {
  const { t } = useTranslation()

  if (clusters.length === 0) {
    return (
      <p className="p-2 text-xs" style={{ color: 'var(--muted)' }}>
        {t('compare.review.list.empty')}
      </p>
    )
  }

  return (
    <ul role="list" aria-label={t('compare.review.list.label')} className="flex flex-col gap-2">
      {clusters.map((cluster) => (
        <ClusterRow
          key={cluster.id}
          cluster={cluster}
          selected={cluster.number === selected}
          onSelect={onSelect}
          onDecide={onDecide}
          onLabel={onLabel}
          onNote={onNote}
        />
      ))}
    </ul>
  )
}
