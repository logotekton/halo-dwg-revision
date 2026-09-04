import { useTranslation } from 'react-i18next'
import type { ZwcadStatus, ZwcadUnavailableReason } from '../api'

const REASON_KEYS: Record<ZwcadUnavailableReason, string> = {
  not_windows: 'zwcad.reason.not_windows',
  comtypes_missing: 'zwcad.reason.comtypes_missing',
  not_registered: 'zwcad.reason.not_registered',
  com_error: 'zwcad.reason.com_error',
}

/**
 * Screen A's converter chip (brief Goal 4: "`available`이면 'ZWCAD 변환',
 * 아니면 '자체 변환기'와 사유").
 */
export function ZwcadChip({ status }: { status: ZwcadStatus }) {
  const { t } = useTranslation()
  const reasonKey = status.reason ? REASON_KEYS[status.reason] : undefined

  return (
    <span className="hc-chip" data-active={String(status.available)}>
      {status.available ? t('zwcad.chip.zwcad') : t('zwcad.chip.builtin')}
      {!status.available && reasonKey && ` · ${t(reasonKey)}`}
    </span>
  )
}
