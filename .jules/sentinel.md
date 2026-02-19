## 2026-02-19 - [SQL Injection and Permissive CORS in DB Explorer]
**Vulnerability:** Unauthenticated arbitrary SQL execution via `/api/db/query` and `/api/db/export` combined with `allow_origins=["*"]`.
**Learning:** Development tools (like DB viewers) integrated into the main application can accidentally expose the entire database to the public or to malicious websites via CORS if not properly guarded. Even if intended for local use, the lack of origin restriction allows cross-site request forgery.
**Prevention:** Always restrict CORS origins to trusted domains, especially when exposing powerful endpoints. Implement read-only guards (like `validate_sql`) for query-only endpoints.
