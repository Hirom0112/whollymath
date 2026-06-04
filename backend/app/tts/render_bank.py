"""Build-time entrypoint: render the spoken bank to cached Hope audio (Slice A).

Run as a script (``uv run python -m app.tts.render_bank``) to render the variable-free spoken
bank in voice Hope to the cache dir + manifest. This is an OFFLINE build step (CLAUDE.md §8.1),
not part of the API / turn loop. It loads ``ELEVENLABS_API_KEY`` from ``backend/.env`` via
python-dotenv (the same loader the rest of the backend uses), constructs the ElevenLabs
provider, and runs the batch.

Flags:
  --limit N        render only the first N enumerated strings (a small, quota-friendly subset).
  --locale L       restrict to one locale (``en`` or ``es-MX``); default renders both. A
                   single-locale render MERGES into the existing manifest (it no longer drops the
                   other locale's rows — the old footgun), so re-rendering one language is safe.
  --cache-dir P    write to an alternate cache dir (default ``app/tts/cache``).

The key is loaded, never printed. The script prints a short summary (counts + manifest path),
not the key or the audio.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from app.tts.batch import DEFAULT_CACHE_DIR, DEFAULT_LOCALES, MANIFEST_FILENAME, run_batch
from app.tts.provider import ElevenLabsProvider, Locale
from app.tts.spoken_bank import enumerate_deferred, enumerate_renderable


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the spoken bank to cached Hope audio.")
    parser.add_argument("--limit", type=int, default=None, help="render only the first N strings")
    parser.add_argument(
        "--locale",
        choices=["en", "es-MX"],
        default=None,
        help="restrict to one locale (default: both)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="cache output dir (default: app/tts/cache)",
    )
    args = parser.parse_args()

    # Load backend/.env so ELEVENLABS_API_KEY is available (dev); prod uses Secrets Manager.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    renderable = enumerate_renderable()
    subset = renderable[: args.limit] if args.limit is not None else renderable
    locales: tuple[Locale, ...] = (args.locale,) if args.locale else DEFAULT_LOCALES

    manifest = run_batch(
        ElevenLabsProvider(),
        cache_dir=args.cache_dir,
        locales=locales,
        strings=subset,
    )

    deferred = enumerate_deferred()
    print(f"Rendered {len(subset)} string(s) x {len(locales)} locale(s) -> {len(manifest)} clips")
    print(f"Total variable-free (renderable) bank: {len(renderable)}")
    print(f"Number-templated (deferred to splicing): {len(deferred)}")
    print(f"Manifest: {args.cache_dir / MANIFEST_FILENAME}")


if __name__ == "__main__":
    main()
