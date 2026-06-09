# app/helpneed/

The proactive **HelpNeed predictor**: the XGBoost training pipeline (EDM Cup data)
and the observe-only inference scored each turn. The committed artifact lives in
`artifacts/helpneed_v1.joblib`.

**Never calls an LLM** (invariant 1) and **never gates a turn** — it scores *after*
grading and feeds no transition, refuse-rule, or next-problem choice.
