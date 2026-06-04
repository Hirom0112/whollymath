import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { installAudioUnlock } from './components/avatar/audioUnlock';
import './styles/tokens.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found');
}

// Arm the Safari/iOS audio unlock at startup so the learner's FIRST gesture anywhere — the
// "Start learning" tap on the landing page — blesses the guide's <audio> element. By the time a
// hint fires (even an auto, HelpNeed-timed one with no click of its own), the voice is already
// approved and plays. Installing here (not just in the tutor) is why it survives navigation.
installAudioUnlock();

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
