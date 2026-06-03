# app/notifications/

Outbound notifications. **Email only** for now: the COPPA parental-email
verification (Slice auth/parent-child). SES in prod, logging fallback in dev.

Does **not** contain: in-app messaging, push, SMS, or anything on the turn loop.
