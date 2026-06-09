# app/db/

SQLAlchemy models, Alembic migration wiring, and the **repositories** — the only
place database queries live. Services call repositories; nothing else touches a
session.

Does **not** contain: business logic, or any persistence on the sub-100 ms
decision path (writes happen alongside/after the response — invariant 7).
