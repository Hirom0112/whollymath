import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { transcribeAnswer } from '../api';

import { WorkCamera } from './WorkCamera';

// Mock the api client so no network is touched; we drive the OCR read-back result per test.
// (vitest hoists vi.mock above the imports, so the mocked module is what `transcribeAnswer` binds to.)
vi.mock('../api', () => ({
  transcribeAnswer: vi.fn(),
}));

const mockedTranscribe = vi.mocked(transcribeAnswer);

afterEach(() => {
  vi.restoreAllMocks();
  mockedTranscribe.mockReset();
});

function pickFile(): void {
  const input = document.querySelector<HTMLInputElement>('.wm-workcam-input');
  if (input === null) throw new Error('camera input not rendered');
  const file = new File(['fake-bytes'], 'work.png', { type: 'image/png' });
  fireEvent.change(input, { target: { files: [file] } });
}

describe('WorkCamera', () => {
  it('reads the answer back and submits the confirmed transcription', async () => {
    mockedTranscribe.mockResolvedValue({ transcribed_answer: '3/4', readable: true });
    const onConfirm = vi.fn();
    render(<WorkCamera onConfirm={onConfirm} />);

    pickFile();

    // The read-back appears for the learner to confirm BEFORE grading.
    await waitFor(() => {
      expect(screen.getByText(/i read this as/i)).toBeInTheDocument();
    });
    expect(screen.getByText('3/4')).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled(); // not submitted until confirmed

    fireEvent.click(screen.getByRole('button', { name: /yes, check it/i }));
    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith('3/4');
    });
  });

  it('asks for a retake when the photo is unreadable, and never submits', async () => {
    mockedTranscribe.mockResolvedValue({ transcribed_answer: null, readable: false });
    const onConfirm = vi.fn();
    render(<WorkCamera onConfirm={onConfirm} />);

    pickFile();

    await waitFor(() => {
      expect(screen.getByText(/couldn't read that/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /retake/i })).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('shows a retry on an OCR/network error rather than crashing', async () => {
    mockedTranscribe.mockRejectedValue(new Error('network down'));
    const onConfirm = vi.fn();
    render(<WorkCamera onConfirm={onConfirm} />);

    pickFile();

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
