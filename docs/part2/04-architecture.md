# 4. Architecture

← [3. Scope](03-scope.md) · [Overview](README.md) · [5. Data model and authorization](05-data-model-and-authorization.md) →

```mermaid
flowchart LR
  subgraph Clients
    SPA["React SPA<br/>Members · Roles · Assets · Screens · Playlists · Schedules"]
    PL["Browser player"]
  end
  subgraph API["API: modular monolith (Node 22 + TypeScript, Fastify)"]
    MOD["identity · teams · policy · folders · assets<br/>screens · content · assignment · audit"]
    DG["device-gateway"]
  end
  W["Job worker (pg-boss)<br/>same codebase"]
  PG[("PostgreSQL 16<br/>state · ACL · jobs · audit")]
  S3[("Private S3-compatible bucket")]
  MAIL["Email provider"]
  SPA -- "REST + OpenAPI<br/>cookie session + CSRF, X-Team-Id" --> MOD
  PL -- "device token<br/>poll + heartbeat" --> DG
  MOD --> PG
  DG --> PG
  MOD -- "enqueue in the same tx" --> W
  W --> PG
  W -- "thumbnails, metadata" --> S3
  MOD --> MAIL
  SPA -. "presigned PUT (upload)" .-> S3
  PL -. "signed GET, 5-min TTL" .-> S3
```

*PROPOSED. One deployable API plus a worker from the same codebase; files never pass through the API.*

| Choice | Why | Rejected alternative |
|---|---|---|
| Modular monolith | Assign, Move and quota need transactions spanning Teams, folders and Screens: plain `BEGIN … COMMIT` | Microservices: sagas and ops overhead for 2 engineers |
| PostgreSQL + row locks | Quota sums, unique memberships, TOCTOU protection, `pg_trgm` search | — |
| ACLs in Postgres | Snapshot inheritance makes evaluation leaf-only (one folder row) | OpenFGA/SpiceDB: a second store adds lag exactly where revoke-then-assign needs read-your-writes |
| pg-boss queue | Small workloads; enqueue in the same transaction = free outbox | Redis/SQS |
| Presigned upload/download | API never streams gigabytes; reads only after `authorize()` | Public CDN URLs: can't be revoked |
| Server-side sessions | Removing a member takes effect on the next request | JWTs that outlive a removal |
| REST | Per-route authorization is easier to review and test exhaustively | GraphQL (SCIO's public API); can be layered on later |

---

← [3. Scope](03-scope.md) · [Overview](README.md) · [5. Data model and authorization](05-data-model-and-authorization.md) →
