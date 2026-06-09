# app/api/

The HTTP layer: FastAPI routers + the services they call. Routes stay **thin** —
they validate, call a service, and return a view model.

Does **not** contain: business logic (lives in the services here + `domain/`,
`mastery/`, `policy/`) or raw DB queries (those live only in `db/` repositories).
