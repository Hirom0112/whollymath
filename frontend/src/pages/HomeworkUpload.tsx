import { useState } from 'react';

import { ApiError, hwSubmit } from '../api';
import { Mascot } from '../components/Mascot';
import './Homework.css';

/**
 * The MOBILE homework capture screen (PROJECT.md §3.4 two-star model). Reached on the phone by
 * scanning the QR the desktop shows (`/?hwupload=<token>`). The kid does the worksheet on paper,
 * snaps every page via a big friendly camera frame, and taps "All done"; the pages post to
 * `/hw/submit` and the desktop (polling) picks up the result for the read-back. Privacy by design:
 * "No faces, just math" — the camera points at paper, never the child (children's-data posture).
 */
export function HomeworkUpload({ token }: { token: string }): React.JSX.Element {
  const [pages, setPages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function addFiles(files: FileList | null): Promise<void> {
    if (files === null || files.length === 0) return;
    const encoded = await Promise.all(Array.from(files).map(fileToDataUrl));
    setPages((prev) => [...prev, ...encoded]);
  }

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await hwSubmit(token, pages);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // The token isn't in the (in-memory) store — the homework code expired (e.g. the server
        // restarted since the QR was made). A fresh QR is the fix; this can't be retried as-is.
        setError(
          'This homework code expired. On your computer, tap “Got homework?” again for a fresh QR code, then re-scan it.',
        );
      } else {
        // Surface the actual failure for diagnosis: a status (413/500…), a network error
        // ("Load failed"), or a non-JSON reply ("Unexpected token '<'" = hit the SPA fallback).
        const detail =
          err instanceof ApiError
            ? `server responded ${String(err.status)}`
            : err instanceof Error
              ? err.message
              : String(err);
        setError(`Couldn’t send — ${detail}. Tap “All done” to try again.`);
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <main className="wm-hw-mobile wm-hw-mobile--done">
        <div className="wm-hw-mobile-inner">
          <div className="wm-hw-mascot-wrap wm-hw-mascot-wrap--celebrate" aria-hidden="true">
            <Mascot />
          </div>
          <h1 className="wm-hw-mobile-title">All sent! 🎉</h1>
          <p className="wm-hw-mobile-sub">
            Head back to your computer — we’ll go through it together, one problem at a time.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="wm-hw-mobile">
      <div className="wm-hw-mobile-inner">
        <div className="wm-hw-mascot-wrap" aria-hidden="true">
          <Mascot />
        </div>
        <h1 className="wm-hw-mobile-title">Let’s scan your homework</h1>
        <p className="wm-hw-mobile-sub">
          Take a clear picture of <strong>every page</strong>. Lay each one flat and fill the frame.
        </p>
        <span className="wm-hw-mobile-privacy">📄 No faces, just math</span>

        <label className="wm-hw-capture">
          <input
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            hidden
            onChange={(e) => {
              void addFiles(e.currentTarget.files);
              e.currentTarget.value = ''; // allow re-adding the same file / another capture
            }}
          />
          <span className="wm-hw-capture-icon" aria-hidden="true">
            📷
          </span>
          <span className="wm-hw-capture-label">
            {pages.length === 0 ? 'Tap to take a photo' : 'Add another page'}
          </span>
          <span className="wm-hw-capture-corner wm-hw-capture-corner--tl" aria-hidden="true" />
          <span className="wm-hw-capture-corner wm-hw-capture-corner--tr" aria-hidden="true" />
          <span className="wm-hw-capture-corner wm-hw-capture-corner--bl" aria-hidden="true" />
          <span className="wm-hw-capture-corner wm-hw-capture-corner--br" aria-hidden="true" />
        </label>

        {pages.length > 0 && (
          <ul className="wm-hw-mobile-pages">
            {pages.map((src, i) => (
              <li key={i} className="wm-hw-mobile-thumb">
                <img src={src} alt={`Page ${String(i + 1)}`} />
                <span className="wm-hw-mobile-thumb-n">{i + 1}</span>
                <button
                  type="button"
                  className="wm-hw-mobile-remove"
                  aria-label={`Remove page ${String(i + 1)}`}
                  onClick={() => setPages((prev) => prev.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        {error !== null && (
          <p className="wm-hw-mobile-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="wm-hw-mobile-bar">
        <button
          type="button"
          className="wm-hw-mobile-done"
          disabled={pages.length === 0 || busy}
          onClick={() => void submit()}
        >
          {busy
            ? 'Sending…'
            : pages.length === 0
              ? 'Add a page to finish'
              : `All done — send ${String(pages.length)} ${pages.length === 1 ? 'page' : 'pages'}`}
        </button>
      </div>
    </main>
  );
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error('read failed'));
    reader.readAsDataURL(file);
  });
}
