// Google account sign-in (Slice PL.3.2): the GIS flow + client-id gating. The bearer-token
// plumbing it feeds lives in ../api (setAuthToken / fetchMe).
export { googleClientId, isGoogleConfigured, promptGoogleSignIn } from './google';
