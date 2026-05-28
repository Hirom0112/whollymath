import { afterEach, describe, expect, it, vi } from 'vitest';

import { TelemetryBuffer } from './telemetry';

// The buffer is pure logic (Slice PL.2): it accumulates events and flushes them in batches,
// best-effort, never throwing. These pin that contract; the fire-and-forget POST itself is
// mocked (CLAUDE.md §9 — don't reach the real server).

function mockFetchOk(ok: boolean): ReturnType<typeof vi.fn> {
  const fn = vi.fn(() => Promise.resolve({ ok } as Response));
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TelemetryBuffer', () => {
  it('buffers events and flushes them in one batch', async () => {
    const fetchFn = mockFetchOk(true);
    const buffer = new TelemetryBuffer('sess-1', () => 1000);
    buffer.track('submit', { latency_ms: 42 });
    buffer.track('hint_request');
    expect(buffer.pending).toBe(2);

    await buffer.flush();
    expect(buffer.pending).toBe(0);
    expect(fetchFn).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String((fetchFn.mock.calls[0][1] as RequestInit).body));
    expect(body.session_id).toBe('sess-1');
    expect(body.events).toHaveLength(2);
    expect(body.events[0]).toMatchObject({ event_type: 'submit', payload: { latency_ms: 42 } });
    expect(body.events[0].client_ts).toBe(new Date(1000).toISOString());
  });

  it('flushing an empty buffer makes no request', async () => {
    const fetchFn = mockFetchOk(true);
    await new TelemetryBuffer('sess-1').flush();
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it('re-buffers events when a flush fails, so nothing is lost', async () => {
    mockFetchOk(false);
    const buffer = new TelemetryBuffer('sess-1');
    buffer.track('focus');
    await buffer.flush();
    // The failed batch is restored for the next attempt.
    expect(buffer.pending).toBe(1);
  });

  it('never throws when the network rejects (fire-and-forget)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('offline'))),
    );
    const buffer = new TelemetryBuffer('sess-1');
    buffer.track('blur');
    await expect(buffer.flush()).resolves.toBeUndefined();
    expect(buffer.pending).toBe(1); // kept for retry
  });

  it('auto-flushes once the buffer reaches the batch threshold', async () => {
    const fetchFn = mockFetchOk(true);
    const buffer = new TelemetryBuffer('sess-1');
    for (let i = 0; i < 25; i++) buffer.track('answer_edit', { i });
    // The 25th track triggers an auto-flush (fire-and-forget); let it settle.
    await Promise.resolve();
    await Promise.resolve();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });
});
