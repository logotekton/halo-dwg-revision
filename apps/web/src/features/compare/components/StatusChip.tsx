import { useTranslation } from 'react-i18next'
import type { PairStatus } from '../api'

/** One `.hc-badge-<status>` class per `docs/contracts/r1.md` §3
 * `sheet_pair.status` value (styles/index.css). */
export function StatusChip({ status }: { status: PairStatus }) {
  const { t } = useTranslation()
  return <span className={`hc-badge hc-badge-${status}`}>{t(`compare.sheets.filter.${status}`)}</span>
}
