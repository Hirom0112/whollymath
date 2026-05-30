// Behavioral telemetry buffer (Slice PL.2.2; PROJECT.md §3.12, ARCHITECTURE.md §15.3).
//
// Captures the RAW interaction stream — how a learner works a problem, not just the final
// answer — and flushes it asynchronously to POST /events. The governing principle is
// "capture richly, act conservatively" (invariant 9): this only records, it never changes
// what the UI does. Flushing is fire-and-forget and best-effort: a failed flush is swallowed
// and the events are kept for the next attempt, so telemetry can NEVER break or block the
// learner's experience (invariant 7 — the server endpoint is likewise lenient + off the
// turn loop).

import { postEvents, type InteractionEventIn, type InterventionView } from '../api';

/** The behavioral event tags we record. An open string on the wire; this union documents
 *  the vocabulary the app actually emits so callers stay consistent. */
export type TelemetryEventType =
  | 'problem_presented'
  | 'first_interaction'
  | 'answer_edit'
  | 'numberline_move'
  | 'hint_request'
  | 'submit'
  | 'focus'
  | 'blur'
  | 'idle';

// Flush when the buffer reaches this many events, so a busy session doesn't grow unbounded
// between interval flushes. Well under the server's 200-per-batch cap.
const FLUSH_AT = 25;

/** A buffer that accumulates events and flushes them to the server in batches.
 *
 * Not React-aware — pure logic, so it is unit-testable without a DOM. `track` stamps each
 * event with the client clock and buffers it; `flush` drains the buffer in one POST and, on
 * failure, restores the drained events to the FRONT of the buffer so nothing is lost. */
export class TelemetryBuffer {
  private readonly sessionId: string;
  private buffer: InteractionEventIn[] = [];
  private readonly now: () => number;
  // Called when a flush response carries a mid-problem nudge (live loop Beat 1). Additive-only:
  // surfacing a nudge never blocks or alters the flush; it just lets the surface voice the tip.
  private readonly onNudge?: (nudge: InterventionView) => void;

  // `now` is injectable so tests are deterministic (the harness forbids a real clock here).
  constructor(
    sessionId: string,
    now: () => number = () => Date.now(),
    onNudge?: (nudge: InterventionView) => void,
  ) {
    this.sessionId = sessionId;
    this.now = now;
    this.onNudge = onNudge;
  }

  /** Buffer one event; auto-flush (fire-and-forget) once the buffer is large enough. */
  track(eventType: TelemetryEventType, payload: Record<string, unknown> = {}): void {
    this.buffer.push({
      event_type: eventType,
      payload,
      client_ts: new Date(this.now()).toISOString(),
    });
    if (this.buffer.length >= FLUSH_AT) void this.flush();
  }

  /** How many events are waiting to be sent (for tests / lifecycle decisions). */
  get pending(): number {
    return this.buffer.length;
  }

  /** Send the buffered events. Best-effort: on failure the drained events are re-buffered
   *  (at the front, preserving order) so the next flush retries them. Never throws. */
  async flush(): Promise<void> {
    if (this.buffer.length === 0) return;
    const batch = this.buffer;
    this.buffer = [];
    const res = await postEvents(this.sessionId, batch);
    if (res === null) {
      this.buffer = [...batch, ...this.buffer];
      return;
    }
    // A mid-problem nudge the live loop offered on this flush (Beat 1) — hand it to the surface.
    if (res.nudge != null && this.onNudge !== undefined) this.onNudge(res.nudge);
  }
}
