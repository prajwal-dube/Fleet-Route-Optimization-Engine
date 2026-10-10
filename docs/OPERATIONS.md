# Operations and assumptions

## Durable asynchronous dispatch

A POST transaction writes the job, its geospatial locations, and fleet rows together. A unique idempotency key and canonical payload hash make request retries safe; changed payloads using the same key return 409. Workers claim queued jobs using `FOR UPDATE SKIP LOCKED`, assign a unique lease token, and increment attempts. The database queue survives API or worker restarts.

Default leases last 120 seconds; solver time is capped at 30 seconds per request. An expired RUNNING job may be retried, at most three attempts. Token fencing prevents a stale worker from overwriting a newer attempt. Job completion and all route/stop records commit in one transaction. A job that exhausted leases becomes FAILED rather than remaining RUNNING forever. Ordinary optimizer exceptions are terminal FAILED and logged; they are not retried indefinitely. If the database is unreachable, worker dispatch reconnects and lease recovery applies after the outage.

Leases are not renewed by a heartbeat. A heavily stalled worker can exceed its lease, causing duplicate computation; only the current token can commit. Increase the lease for a slow environment while retaining the bounded solver timeout. Do not set a lease below normal computation time outside deliberate recovery tests.

`CRASH_AFTER_CLAIM=1` is a test hook: worker exits with code 42 after claiming a job. `LEASE_SECONDS=5` makes recovery observable in seconds during the delivered test; production/demo normal operation uses 120. Crash-after-claim was tested. API restarts, full-machine failure, long database partitions, and crash-during-final-commit were not separately injected.

Do not run database integration tests on a shared production/demo workload: dispatcher tests terminalize queued fixtures so they can isolate lease claims. Use an idle dedicated test database with worker services stopped. Data is retained until the database volume is explicitly deleted; no retention/scheduling cleanup is automatic.

## Geographic and logistics assumptions

Distances come from `ST_Distance` over WGS84 geography points, measured on the spheroid in meters, multiplied by a user-selected constant road factor and rounded to integer meters. The default road factor is 1.3. This is a modeled approximation, **not** a road-network route, map provider matrix, live traffic feed, or validated real delivery mileage. Travel time assumes constant speed and rounds up to whole seconds. All benchmarks use exactly the same matrix for the baseline and optimizer.

One depot, one trip per vehicle, all orders loaded at the depot, positive weights/services, no splitting, no pickup operations, no replenishment, and all deliveries mandatory. Each driver is assigned to exactly one vehicle. Shifts and maximum total working time are explicit numerical constraints; legal jurisdictional rest breaks, labor rules, and real driving-hour compliance are not implemented. Times are integer seconds from the scenario's reference time, not timezone-aware dates. Fuel and wage inputs use one abstract currency consistently; no conversion or actual expenditure measurement is implied.

Broad benchmark delivery windows are 0–4 or 0–6 hours, within 8-hour shifts. Binding waiting-window and impossible-shift/capacity cases are tested separately. No claim is made that optimization eliminated violations from an invalid baseline: the reported baseline is already feasible. The measured result is zero observed violations in returned optimized schedules.

## Baseline and objective

Baseline: take vehicles in input order, repeatedly add the nearest remaining customer whose capacity, service-start window, and immediate return to depot remain feasible. It is deterministic and auditable; it is a simple heuristic, not a commercial planner. Partial greedy results are never used for percentage comparisons. Mileage and modeled-cost improvements are reported separately. The optimizer minimizes total modeled fuel, labor, and dispatch cost; it may trade higher mileage for lower overall cost on other inputs.

## Deployment boundaries

The API uses sync database functions in FastAPI's threadpool; the CPU-bound solver runs in a separate worker process. Scale workers with `docker compose up -d --scale worker=2`. No solver runs in the HTTP request thread, and no in-process background task is the durable queue.

The Compose stack binds HTTP to localhost and provides demo database credentials. It is a development service, without authentication, tenant separation, TLS, per-user quotas, or database connection pooling. Swagger documentation is at `/docs`. Deploy privately until those controls, queue admission/backpressure, resource limits, monitoring, and tested HA storage are added. PostgreSQL/PostGIS is a single instance; distributed workers do not establish database high availability.

The delivered tests used real native PostgreSQL/PostGIS, FastAPI HTTP, and worker processes. Docker configuration was parsed, not built or executed in this environment. Python dependency versions are pinned; container image tags are not digest-pinned. Reproduce tests after recording exact image digests and hardware for deployment-specific claims.
