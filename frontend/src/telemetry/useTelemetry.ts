// React lifecycle wrapper around TelemetryBuffer (Slice PL.2.2).
//
// Gives a component a stable `track(type, payload)` and owns the buffer's lifecycle: a
// periodic flush, a flush on page unload / unmount (so a closing tab doesn't lose its tail),
// and the ambient window signals (focus / blur / idle) that don't belong to any one widget.
// All best-effort — nothing here can block or break the surface (invariant 7).

import { useEffect, useMemo, useRef } from 'react';

import { type InterventionView } from '../api';

import { TelemetryBuffer, type TelemetryEventType } from './telemetry';

// How often to drain the buffer while the page is open.
const FLUSH_INTERVAL_MS = 10_000;
// No interaction for this long → one `idle` event (a single edge, not a repeating timer),
// matching the engagement-floor / idle framing the backend already reasons about (§3.6).
const IDLE_AFTER_MS = 30_000;

export interface Telemetry {
  track: (type: TelemetryEventType, payload?: Record<string, unknown>) => void;
}

/**
 * Wire a TelemetryBuffer to the page lifecycle for `sessionId`. Returns a stable `track`.
 *
 * `onNudge` (optional) fires when a flush response carries a mid-problem nudge (live loop Beat 1) —
 * kept in a ref so the latest handler is used without re-creating the buffer (which would lose the
 * pending tail). Additive-only: a nudge never blocks or alters the flush.
 */
export function useTelemetry(
  sessionId: string,
  onNudge?: (nudge: InterventionView) => void,
): Telemetry {
  const onNudgeRef = useRef(onNudge);
  onNudgeRef.current = onNudge;
  const buffer = useMemo(
    () => new TelemetryBuffer(sessionId, undefined, (n) => onNudgeRef.current?.(n)),
    [sessionId],
  );
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const armIdle = (): void => {
      if (idleTimer.current !== null) clearTimeout(idleTimer.current);
      idleTimer.current = setTimeout(() => {
        buffer.track('idle', { after_ms: IDLE_AFTER_MS });
      }, IDLE_AFTER_MS);
    };

    const onFocus = (): void => {
      buffer.track('focus');
      armIdle();
    };
    const onBlur = (): void => {
      buffer.track('blur');
      void buffer.flush();
    };
    const onActivity = (): void => {
      armIdle();
    };
    const onHide = (): void => {
      void buffer.flush();
    };

    window.addEventListener('focus', onFocus);
    window.addEventListener('blur', onBlur);
    window.addEventListener('pointerdown', onActivity);
    window.addEventListener('keydown', onActivity);
    window.addEventListener('pagehide', onHide);
    const interval = setInterval(() => {
      void buffer.flush();
    }, FLUSH_INTERVAL_MS);
    armIdle();

    return () => {
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('pointerdown', onActivity);
      window.removeEventListener('keydown', onActivity);
      window.removeEventListener('pagehide', onHide);
      clearInterval(interval);
      if (idleTimer.current !== null) clearTimeout(idleTimer.current);
      void buffer.flush(); // drain the tail on unmount
    };
  }, [buffer]);

  // `track` is stable for the buffer's lifetime, so consumers can depend on it freely.
  return useMemo(() => ({ track: buffer.track.bind(buffer) }), [buffer]);
}
