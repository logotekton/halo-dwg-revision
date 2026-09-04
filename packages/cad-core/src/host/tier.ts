/**
 * The large-drawing tiers of ADR-0002 개정 2026-09-02 §5.
 *
 * The gate is the **entity count**, not the file size; size is only the O(1)
 * pre-parse estimator, and its density differs by a factor of eight between
 * DXF and DWG (`docs/spikes/large-file.md` §5.5). Both steps live here so the
 * renderer, the import job and the converter all use the same numbers.
 */

import type { CadHostWarning, EntityTier } from './types';

/** Measured density of an ASCII R2018 DXF (`docs/spikes/large-file.md` §5.5). */
export const DXF_BYTES_PER_ENTITY = 207;
/** Measured density of a DWG. */
export const DWG_BYTES_PER_ENTITY = 26;

/** Upper bound of tier A: full editing in the browser. */
export const TIER_A_MAX_ENTITIES = 250_000;
/** Upper bound of tier B: viewer gets a light DXF, engine keeps the full one. */
export const TIER_B_MAX_ENTITIES = 800_000;

export function tierOf(entityCount: number): EntityTier {
  if (entityCount <= TIER_A_MAX_ENTITIES) return 'A';
  if (entityCount <= TIER_B_MAX_ENTITIES) return 'B';
  return 'C';
}

export interface TierEstimate {
  tier: EntityTier;
  estimatedEntityCount: number;
  warnings: CadHostWarning[];
}

/**
 * First-stage estimate from the file size alone, before anything is parsed.
 *
 * The wording of the warnings is fixed by ADR-0002 개정 §6 and lives in
 * `ko.json`; "메모리 부족" style messages are forbidden there because the
 * failure has nothing to do with RAM.
 */
export function estimateEntityTier(input: {
  byteLength: number;
  format: 'dxf' | 'dwg';
}): TierEstimate {
  const density = input.format === 'dwg' ? DWG_BYTES_PER_ENTITY : DXF_BYTES_PER_ENTITY;
  const estimatedEntityCount = Math.round(input.byteLength / density);
  const tier = tierOf(estimatedEntityCount);
  return { tier, estimatedEntityCount, warnings: warningsForTier(tier, estimatedEntityCount) };
}

/** Stage-one warnings for a tier, empty for tier A. */
export function warningsForTier(tier: EntityTier, entityCount: number): CadHostWarning[] {
  if (tier === 'A') return [];
  return [
    {
      code: tier === 'B' ? 'tier-b' : 'tier-c',
      i18nKey: tier === 'B' ? 'viewer.warning.tierB' : 'viewer.warning.tierC',
      params: { count: entityCount },
    },
  ];
}

/**
 * Second-stage check once the real `entity_count` is known. Only reports when
 * the tier actually changed — ADR-0002 개정 §6: do not repeat the warning
 * during the open.
 */
export function tierChangeWarnings(
  estimated: EntityTier,
  actualEntityCount: number
): CadHostWarning[] {
  const actual = tierOf(actualEntityCount);
  if (actual === estimated) return [];
  if (actual === 'A') return [];
  return [
    {
      code: 'tier-changed',
      i18nKey: 'viewer.warning.tierChanged',
      params: { count: actualEntityCount },
    },
  ];
}
