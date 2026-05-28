"""Evaluation harnesses (PROJECT.md §3.11, §4; ARCHITECTURE.md §11).

Evaluation runs — the false-positive-mastery harness, the three-arm baseline
comparison, the proactive A/B test — live here, separate from the systems they
measure. They are runs, not unit tests (CLAUDE.md §9): they exercise the
already-tested domain/mastery/persona/policy pieces end-to-end and report the
numbers the writeup quotes. No LLM, no DB, no SymPy here — they orchestrate.
"""
