# app/policy/

The adaptation policy: surface-state transitions (S1–S5), the **refuse-rules** that
constrain what the UI will never do automatically, and the interleaving logic.

Decides the next UI state **deterministically** from the verdict + mastery signals.
The LLM never gates a transition, and the HelpNeed score never forces one (it is
observe-only).
