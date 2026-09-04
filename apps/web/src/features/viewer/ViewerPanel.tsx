import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { VIEWER_ROOT_ID, ensureCadHost } from './host';
import { useSelectionState, useViewerState } from './viewer-store';

/**
 * The 2D viewer panel: the `#viewer-root` container plus the small overlay that
 * reports what the host is doing.
 *
 * W3-01 owns the layout that hosts this component; the contract fixes the
 * container id, so the panel can be dropped into the shell unchanged. Every
 * string is an i18n key (CLAUDE.md rule 8) and every number comes from the
 * stores, never from the viewer directly.
 */
export function ViewerPanel(): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const state = useViewerState();
  const { handles } = useSelectionState();
  const { t } = useTranslation();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    // The host is created once and kept for the lifetime of the window: the
    // mlightcad viewer is a set of singletons, so mounting a second one would
    // fight the first (cadhost-proposal, "싱글턴 5종").
    void ensureCadHost(container).catch(() => {
      // `openFailed` / the status store carry the user-visible outcome.
    });
  }, []);

  const active = state.documents.find((document) => document.fileId === state.activeFileId);

  return (
    <div className="relative h-full w-full">
      <div
        id={VIEWER_ROOT_ID}
        ref={containerRef}
        className="h-full w-full bg-neutral-900"
        role="application"
        aria-label={t('viewer.canvasLabel')}
        data-status={state.status}
      />
      {state.status === 'idle' && state.documents.length === 0 ? (
        <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-neutral-500">
          {t('viewer.empty')}
        </p>
      ) : null}
      {state.progress ? (
        <p className="pointer-events-none absolute left-3 top-3 rounded bg-neutral-800/80 px-2 py-1 text-xs text-neutral-200">
          {t('viewer.progress', { percentage: Math.round(state.progress.percentage) })}
        </p>
      ) : null}
      {state.error ? (
        <p role="alert" className="absolute left-3 top-3 rounded bg-red-900/80 px-2 py-1 text-xs text-red-100">
          {t('viewer.error', { message: state.error })}
        </p>
      ) : null}
      <div
        data-testid="viewer-info"
        className="pointer-events-none absolute bottom-3 left-3 rounded bg-neutral-800/80 px-2 py-1 text-xs text-neutral-300"
      >
        {active
          ? t('viewer.info', {
              name: active.name,
              layers: active.layers,
              entities: active.entityCount,
              selected: handles.length,
            })
          : t('viewer.noDocument')}
      </div>
      {state.warnings.length > 0 ? (
        <ul className="absolute right-3 top-3 space-y-1 text-xs text-amber-200">
          {state.warnings.map((warning) => (
            <li key={warning.code} className="rounded bg-amber-900/70 px-2 py-1">
              {t(warning.i18nKey, warning.params)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default ViewerPanel;
