// Google Sign-In via Google Identity Services (Slice PL.3.2).
//
// Real account auth: when a Google OAuth client id is configured (VITE_GOOGLE_CLIENT_ID),
// this loads the GIS script and prompts the One Tap / popup flow; the credential it returns
// is the Google ID token, which the app sends to our backend as a Bearer (api.setAuthToken)
// for verification. The backend keys the learner to the Google `sub`, so the same login on
// any device resolves to the same persisted state.
//
// Gated + graceful: with no client id configured (the default locally and in the demo), this
// is inert — `isGoogleConfigured()` is false and the UI falls back to the anonymous/guest
// path, exactly as before PL.3. Going live is the operational step of setting the client id.

const GIS_SRC = 'https://accounts.google.com/gsi/client';

/** The configured Google OAuth client id, or null when accounts aren't set up for this build. */
export function googleClientId(): string | null {
  const id = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  return typeof id === 'string' && id.trim() !== '' ? id.trim() : null;
}

/** Whether real Google sign-in is available (a client id is configured). */
export function isGoogleConfigured(): boolean {
  return googleClientId() !== null;
}

// Minimal shape of the GIS global we use (the script attaches `google.accounts.id`).
interface GoogleIdApi {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: { credential: string }) => void;
      }) => void;
      prompt: () => void;
    };
  };
}

function loadGisScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${GIS_SRC}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = GIS_SRC;
    script.async = true;
    script.onload = () => {
      resolve();
    };
    script.onerror = () => {
      reject(new Error('failed to load Google Identity Services'));
    };
    document.head.appendChild(script);
  });
}

/**
 * Prompt the Google sign-in flow and resolve with the ID token, or null if Google isn't
 * configured / the script can't load. Never throws — a failed sign-in falls back to the
 * anonymous path so the learner is never blocked from continuing.
 */
export async function promptGoogleSignIn(): Promise<string | null> {
  const clientId = googleClientId();
  if (clientId === null) return null;
  try {
    await loadGisScript();
    const gis = (globalThis as { google?: GoogleIdApi }).google;
    if (gis === undefined) return null;
    return await new Promise<string | null>((resolve) => {
      gis.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          resolve(response.credential || null);
        },
      });
      gis.accounts.id.prompt();
    });
  } catch {
    return null;
  }
}
