import { useRef, useState } from 'react';

import { transcribeAnswer } from '../api';

import './WorkCamera.css';

// The in-lesson "snap your handwritten work" beat (HR.C1/C3) — the multimodal crown jewel pulled
// into the live lesson. Shown ONLY on lessons a learner works out on paper (the Tutor gates this on
// `problem.supports_written_work`), so mental/visual lessons never see it. Flow: tap → photograph
// the work → POST /transcribe-answer (Mathpix OCR when configured, a mock otherwise) → read the
// answer back ("I read this as 3/4 — right?") → on confirm, hand the transcribed answer to the
// Tutor's normal submit, so the SAME SymPy verifier grades it as a typed answer (§8.2 — OCR never
// decides correctness). An unreadable photo asks for a clearer one instead of grading a misread.
//
// "No faces, just math": the image is the page, posted for OCR and not retained by the client.

type CameraPhase = 'idle' | 'reading' | 'confirm' | 'unreadable' | 'error';

/** Read a File as a base64 data-URL (what /transcribe-answer accepts). */
function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === 'string' ? reader.result : '');
    };
    reader.onerror = () => {
      reject(new Error('Could not read the photo.'));
    };
    reader.readAsDataURL(file);
  });
}

/**
 * The camera capture + read-back affordance for a paper-worked lesson.
 *
 * `onConfirm` is the Tutor's answer submit (`submitAnswerValue`): the confirmed transcription is
 * submitted through the normal turn. `disabled` mirrors the form's disabled state (e.g. while a turn
 * is in flight). Self-contained: owns the hidden file input + the read-back confirm step; renders
 * nothing persistent beyond the trigger button and, transiently, the read-back panel.
 */
export function WorkCamera({
  onConfirm,
  disabled = false,
}: {
  onConfirm: (answer: string) => void | Promise<void>;
  disabled?: boolean;
}): React.JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<CameraPhase>('idle');
  const [readBack, setReadBack] = useState<string>('');

  function openCamera(): void {
    setPhase('idle');
    inputRef.current?.click();
  }

  async function onFileChosen(event: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    // Allow re-selecting the same file later (clear the input value).
    event.target.value = '';
    if (file === undefined) return;
    setPhase('reading');
    try {
      const dataUrl = await readAsDataUrl(file);
      const result = await transcribeAnswer(dataUrl);
      const answer = result.transcribed_answer;
      if (result.readable && answer != null && answer !== '') {
        setReadBack(answer);
        setPhase('confirm');
      } else {
        setPhase('unreadable');
      }
    } catch {
      // OCR/network failure must not break the lesson — offer a retake (the typed input still works).
      setPhase('error');
    }
  }

  async function confirm(): Promise<void> {
    const answer = readBack;
    setPhase('idle');
    await onConfirm(answer);
  }

  return (
    <div className="wm-workcam">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="wm-workcam-input"
        onChange={(e) => void onFileChosen(e)}
        // The page photo is for OCR only; never auto-uploaded anywhere else.
        aria-hidden="true"
        tabIndex={-1}
      />
      <button
        type="button"
        className="wm-workcam-trigger"
        onClick={openCamera}
        disabled={disabled || phase === 'reading'}
      >
        <CameraGlyph />
        {phase === 'reading' ? 'Reading…' : 'Snap my work'}
      </button>

      {phase === 'confirm' ? (
        <div className="wm-workcam-readback" role="dialog" aria-label="Confirm your snapped answer">
          <p className="wm-workcam-readback-q">
            I read this as <strong>{readBack}</strong> — right?
          </p>
          <div className="wm-workcam-readback-actions">
            <button
              type="button"
              className="wm-workcam-yes"
              onClick={() => void confirm()}
              disabled={disabled}
            >
              Yes, check it
            </button>
            <button type="button" className="wm-workcam-retake" onClick={openCamera}>
              Retake
            </button>
          </div>
        </div>
      ) : null}

      {phase === 'unreadable' || phase === 'error' ? (
        <div className="wm-workcam-readback" role="alert">
          <p className="wm-workcam-readback-q">
            {phase === 'unreadable'
              ? "I couldn't read that. Try a clearer photo of just the answer."
              : 'Something went wrong reading the photo. Try again.'}
          </p>
          <div className="wm-workcam-readback-actions">
            <button type="button" className="wm-workcam-retake" onClick={openCamera}>
              Retake
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** A small camera outline (inline, so no emoji and no asset — matches the app's icon style). */
function CameraGlyph(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" className="wm-workcam-glyph">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
        d="M3 8.5A1.5 1.5 0 0 1 4.5 7h2l1.2-1.8A1 1 0 0 1 8.5 4.7h7a1 1 0 0 1 .8.5L17.5 7h2A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"
      />
      <circle cx="12" cy="13" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
