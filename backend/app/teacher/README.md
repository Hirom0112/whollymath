# app/teacher/

Read-side services for the **teacher and parent dashboards**: class roster, per-child
mastery + HelpNeed signals (with the trustworthy-KC guard), trends, and reminders.

Aggregation over `db/` repositories only — no turn-loop logic here. Per-child access
is ownership-scoped (BOLA) for the parent surface; see [`AUTH.md`](../../../AUTH.md).
