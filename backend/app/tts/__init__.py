"""WhollyMath backend package: tts.

The OFFLINE/build-time text-to-speech boundary — the ONLY place a TTS engine is called,
mirroring the ``llm/`` provider-abstraction discipline (CLAUDE.md §7: TTS is a new layer
boundary like ``llm/``). It pre-renders the FINITE templated spoken-string bank in the
locked ElevenLabs voice "Hope" into content-hashed cached audio plus a word-timing manifest
the avatar lip-syncs to (TalkingHead's ``speakAudio(audio, {words, wtimes, wdurations})``).

This package is NOT in the sub-100ms turn loop (CLAUDE.md §8.1). It is a build-time pipeline:
deterministic given a fixed provider, no LLM, no SymPy. The audio it emits is served as static
assets (CloudFront) so no kid-session text hits any API at runtime (the V2_TODO 2.1 privacy
invariant).

See ARCHITECTURE.md §13 (package layout) and V2_TODO.md slices 2.1 / 3.5 + "AVATAR DIRECTION".
"""
