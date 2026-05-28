"""Google OIDC identity layer (Slice PL.3).

See ``README.md`` in this directory. The only thing this layer produces is a
``learner_id`` for persistence/continuity — the verified identity (sub/email) NEVER
reaches the mastery model, the policy, or the LLM (ARCHITECTURE.md §14 invariant 8).
"""
