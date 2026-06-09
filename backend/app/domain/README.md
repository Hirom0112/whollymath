# app/domain/

**Layer 1 of the synthetic-learner harness:** knowledge components, misconceptions,
problem generators, and the **SymPy verifier**. The single source of truth the
mastery model, personas, and transfer test all reference.

The **only** place SymPy and math-correctness logic live (ARCHITECTURE.md §14
invariant 5). If you are deciding "is this answer correct?", it happens here — never
in `llm/`.
