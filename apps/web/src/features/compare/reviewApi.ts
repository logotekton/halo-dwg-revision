import { engineFetch } from '../../api/engine'
import { EngineHttpError } from './api'

/**
 * Engine client for screen C's three endpoints (`docs/contracts/r1.md` §7,
 * R1-06's `api/routers/compare_clusters.py`):
 *
 * - `GET  /compare/pairs/{pair_id}/clusters`            -> {@link ClustersSidecar}
 * - `PATCH /compare/pairs/{pair_id}/clusters/{number}`  -> {@link Cluster}
 * - `GET  /compare/pairs/{pair_id}/compare-dxf`         -> DXF bytes + `ETag`
 *
 * Types are a hand-kept snake_case mirror of
 * `packages/schema/gen/ts/compare/{clusters-sidecar,cluster,change}.d.ts`,
 * for the same two reasons `features/compare/api.ts` (R1-05) gives at the top
 * of its own file: adding `@halo-cad/schema` to `apps/web/package.json` is
 * outside this task's "Files you own", and the renderer already keeps that
 * kind of mirror by convention (`apps/web/src/api/types.ts`). The field names
 * are the wire's, so a mismatch with the schema shows up as a type error at
 * the one place the JSON is read rather than being renamed twice.
 */

export type ClusterDecision = 'pending' | 'approved' | 'ignored'

export type ClusterKind =
  | 'added'
  | 'removed'
  | 'modified'
  | 'moved'
  | 'text'
  | 'dimension'
  | 'blockdef'
  | 'mixed'

export type ChangeKind = Exclude<ClusterKind, 'mixed'>

/** `[x0, y0, x1, y1]` in the after sheet's world millimetres. */
export type CompareBBox = [number, number, number, number]

export interface CloudMark {
  handle?: string | null
  /** `[x, y, bulge]` vertices, counter-clockwise and closed. */
  points: [number, number, number][]
}

export interface ClusterBadge {
  shape_handle?: string | null
  text_handle?: string | null
  center: [number, number]
}

export interface Cluster {
  id: string
  number: number
  signature?: string
  bbox: CompareBBox
  kind: ClusterKind
  label: string
  user_label: string | null
  decision: ClusterDecision
  note: string | null
  change_ids: string[]
  cloud: CloudMark
  badge: ClusterBadge
}

export interface Change {
  id: string
  seq: number
  kind: ChangeKind
  etype: string
  layer: string
  before_handle?: string | null
  after_handle?: string | null
  bbox: CompareBBox
  delta?: Record<string, unknown> | null
  minor: boolean
  /** One or more `compare.yaml` fold reasons joined with `+`, or null. */
  minor_reason?: string | null
  cluster_id?: string | null
  compare_handles?: { added?: string[]; removed?: string[] }
  provenance: Record<string, unknown>
}

export interface SidecarFrame {
  bbox: CompareBBox
  scale_denominator: number | null
  scale_factor: number
  offset_before: [number, number]
}

export interface SidecarCounts {
  clusters: number
  changes: number
  minor: number
  approved: number
  ignored: number
}

export interface ClustersSidecar {
  schema_version: string
  pair_id: string
  pair_key: string
  run_date: string
  /** `REV-<YYYYMMDD>` -- the layer the clouds and badges were drawn on. */
  layer: string
  frame: SidecarFrame
  clusters: Cluster[]
  changes: Change[]
  /** Compare-DXF handle -> `c<number>`; the viewer's click-to-cluster table. */
  handle_to_cluster: Record<string, string>
  counts: SidecarCounts
}

/**
 * `PATCH` body. An absent key leaves the column alone and an explicit `null`
 * clears it (R1-06's `ClusterDecisionRequest` uses `exclude_unset=True`), so
 * clearing a label is `{ user_label: null }` and not `{}`.
 */
export interface ClusterPatch {
  decision?: ClusterDecision
  user_label?: string | null
  note?: string | null
}

function pairPath(pairId: string): string {
  return `/api/v1/compare/pairs/${encodeURIComponent(pairId)}`
}

async function failure(res: Response, what: string): Promise<EngineHttpError> {
  const detail = await res.text().catch(() => '')
  return new EngineHttpError(res.status, `${what} failed (${String(res.status)}): ${detail}`)
}

/** `GET /compare/pairs/{pair_id}/clusters` -- the sidecar with the database's
 * decisions merged in. 409 until the pair has been compared. */
export async function getClusters(pairId: string): Promise<ClustersSidecar> {
  const path = `${pairPath(pairId)}/clusters`
  const res = await engineFetch(path)
  if (!res.ok) throw await failure(res, path)
  return (await res.json()) as ClustersSidecar
}

/** `PATCH /compare/pairs/{pair_id}/clusters/{number}` -- the only write screen
 * C makes. Returns the stored cluster, which the store swaps in over its own
 * optimistic copy. */
export async function patchCluster(
  pairId: string,
  number: number,
  patch: ClusterPatch,
): Promise<Cluster> {
  const path = `${pairPath(pairId)}/clusters/${String(number)}`
  const res = await engineFetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw await failure(res, path)
  return (await res.json()) as Cluster
}

export interface CompareDxfResult {
  /** True for a 304: the caller's cached bytes are still current. */
  notModified: boolean
  bytes: ArrayBuffer | null
  etag: string | null
}

/**
 * `GET /compare/pairs/{pair_id}/compare-dxf`.
 *
 * `ifNoneMatch` is the ETag of the bytes the caller already holds; the engine
 * answers 304 when the file's sha256 still matches, which is what keeps a
 * sheet from being re-downloaded every time the user walks back into it
 * (brief Constraints: "비교 DXF 바이트는 짝마다 한 번만 받고 ETag로 캐시").
 */
export async function getCompareDxf(
  pairId: string,
  ifNoneMatch?: string | null,
): Promise<CompareDxfResult> {
  const path = `${pairPath(pairId)}/compare-dxf`
  const headers: Record<string, string> = {}
  if (ifNoneMatch) headers['If-None-Match'] = ifNoneMatch
  const res = await engineFetch(path, { headers })
  if (res.status === 304) return { notModified: true, bytes: null, etag: ifNoneMatch ?? null }
  if (!res.ok) throw await failure(res, path)
  return { notModified: false, bytes: await res.arrayBuffer(), etag: res.headers.get('ETag') }
}
