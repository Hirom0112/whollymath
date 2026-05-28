/// <reference types="vite/client" />

// Build-time env the app reads (Vite inlines VITE_-prefixed vars). VITE_GOOGLE_CLIENT_ID
// enables Google sign-in (Slice PL.3.2); absent ⇒ the anonymous/guest path (the default).
interface ImportMetaEnv {
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
