/**
 * Normalises mlightcad's document lifecycle into a state machine the renderer
 * can trust.
 *
 * Two measured quirks make this necessary (`docs/spikes/mlightcad-api.md` C.4):
 *
 * - **`documentCreated` can arrive after `documentActivated`** — measured order
 *   on the spike fixture was `documentToBeOpened(253ms) → documentActivated(301)
 *   → documentCreated(1496)`. A tab UI driven by `documentCreated` therefore
 *   shows tabs in the wrong order, or twice.
 * - **There is no "render finished" event.** Idle is polled through
 *   `waitUntilIdle()`, so "rendering → ready" is a transition this machine owns
 *   rather than something the viewer tells us.
 *
 * The machine is pure: it never touches mlightcad or the DOM, which is what
 * makes the ordering rules testable (`test/host-state-machine.test.ts`).
 */

import type { CadHostStatus } from './types';

export type DocumentState = 'opening' | 'parsed' | 'rendering' | 'ready' | 'failed' | 'closed';

/** Raw lifecycle events, already mapped from `AcApDocManager.events`. */
export type DocumentSignal =
  | 'toBeOpened'
  | 'created'
  | 'activated'
  | 'toBeDestroyed'
  | 'destroyed';

export interface DocumentRecord {
  fileId: string;
  name: string;
  state: DocumentState;
  /** Set once the document reached `ready`, milliseconds since `begin()`. */
  durationMs?: number;
  message?: string;
}

const TERMINAL: ReadonlySet<DocumentState> = new Set<DocumentState>(['closed']);

export class DocumentStateMachine {
  private readonly records = new Map<string, DocumentRecord>();
  private readonly order: string[] = [];
  private readonly startedAt = new Map<string, number>();
  private activeFileId: string | null = null;

  constructor(private readonly now: () => number = () => Date.now()) {}

  /** Registers an open in flight. Re-opening a known file resets its record. */
  begin(fileId: string, name: string): DocumentRecord {
    const record: DocumentRecord = { fileId, name, state: 'opening' };
    if (!this.records.has(fileId)) this.order.push(fileId);
    this.records.set(fileId, record);
    this.startedAt.set(fileId, this.now());
    return record;
  }

  /**
   * Applies one lifecycle signal.
   *
   * `created` never moves a document backwards: a document already `rendering`
   * or `ready` stays there when the late `documentCreated` finally lands, and
   * `activated` implies `parsed` even if `created` has not arrived yet.
   */
  signal(fileId: string, signal: DocumentSignal): DocumentRecord | null {
    const record = this.records.get(fileId);
    if (!record) return null;
    switch (signal) {
      case 'toBeOpened':
        if (record.state === 'closed') record.state = 'opening';
        break;
      case 'created':
      case 'activated':
        if (record.state === 'opening') record.state = 'parsed';
        if (signal === 'activated' && record.state !== 'failed') this.activeFileId = fileId;
        break;
      case 'toBeDestroyed':
        break;
      case 'destroyed':
        record.state = 'closed';
        if (this.activeFileId === fileId) this.activeFileId = null;
        break;
    }
    return record;
  }

  /** Called when the bytes are parsed and the view started drawing. */
  beginRender(fileId: string): DocumentRecord | null {
    const record = this.records.get(fileId);
    if (!record || TERMINAL.has(record.state) || record.state === 'failed') return record ?? null;
    record.state = 'rendering';
    return record;
  }

  /** Called after `waitUntilIdle()` resolves. */
  renderIdle(fileId: string): DocumentRecord | null {
    const record = this.records.get(fileId);
    if (!record || TERMINAL.has(record.state) || record.state === 'failed') return record ?? null;
    record.state = 'ready';
    record.durationMs = this.now() - (this.startedAt.get(fileId) ?? this.now());
    this.activeFileId ??= fileId;
    return record;
  }

  fail(fileId: string, message: string): DocumentRecord | null {
    const record = this.records.get(fileId);
    if (!record) return null;
    record.state = 'failed';
    record.message = message;
    return record;
  }

  /** Removes a document entirely (after `closeDocument()` resolved). */
  forget(fileId: string): void {
    this.records.delete(fileId);
    this.startedAt.delete(fileId);
    const at = this.order.indexOf(fileId);
    if (at >= 0) this.order.splice(at, 1);
    if (this.activeFileId === fileId) this.activeFileId = this.order[this.order.length - 1] ?? null;
  }

  get(fileId: string): DocumentRecord | undefined {
    return this.records.get(fileId);
  }

  /** Documents in the order they were opened — the tab order of the shell. */
  documents(): DocumentRecord[] {
    return this.order
      .map((fileId) => this.records.get(fileId))
      .filter((record): record is DocumentRecord => record !== undefined);
  }

  active(): string | null {
    return this.activeFileId;
  }

  /** Marks a document active without a viewer round trip (after `activate()`). */
  setActive(fileId: string): void {
    if (this.records.has(fileId)) this.activeFileId = fileId;
  }

  /**
   * Host-wide status derived from the documents: the worst state wins, so a
   * single document still opening keeps the status bar honest while other tabs
   * are ready.
   */
  status(): CadHostStatus {
    const states = this.documents().map((record) => record.state);
    if (states.length === 0) return 'idle';
    if (states.some((state) => state === 'opening')) return 'opening';
    if (states.some((state) => state === 'parsed' || state === 'rendering')) return 'rendering';
    if (states.some((state) => state === 'ready')) return 'ready';
    if (states.every((state) => state === 'failed')) return 'failed';
    return 'idle';
  }
}
