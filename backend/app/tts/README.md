# app/tts/

Voice synthesis (ElevenLabs) for the V2 talking guide: a pre-rendered, content-hash
cached audio bank plus serve-time live synth for dynamic lines.

**Off the turn loop** — never on the sub-100 ms graded path. Falls back to
captions-only when `ELEVENLABS_API_KEY` is unset, and the `WHOLLYMATH_LIVE_SYNTH=0`
kill-switch disables live synthesis entirely.
