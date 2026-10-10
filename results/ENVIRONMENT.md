# Measurement environment — 2026-10-09 UTC

- Ubuntu 24.04.3 userland, Linux x86_64 sandbox; kernel reported 6.18.44.
- Host CPU model reported AMD EPYC 9V74 80-Core Processor. Allocated quota: `cpu.max = 800000 100000`, equivalent to **8 logical CPUs of quota**, not 80 allocated cores.
- Memory limit: `8589934592`, **8 GiB**. CPU/RAM utilization was not sampled; these are sandbox limits.
- Python **3.12.14**, FastAPI **0.115.12**, Pydantic **2.13.5**, Uvicorn **0.34.0**, psycopg **3.2.6**, OR-Tools **9.12.4544**, PuLP **3.1.1** with bundled CBC.
- PostgreSQL **16.15**, PostGIS **3.4.2**, GEOS **3.12.1**, PROJ **9.4.0**. Exact database version strings are in `database-evidence.json`.
- One API process, two asynchronous worker processes, one native PostgreSQL/PostGIS instance. Jobs submitted sequentially by one local HTTP client, with 100 ms completion polling. Concurrent worker queue claims were validated separately.
- Each benchmark instance: one depot, 50/100/150 stops, seeds 42/43/44. Fleet size `ceil(stops/10)`; capacity 50 kg per vehicle; demand 2–5 kg; customer service 90–180 s; windows 0–4 or 0–6 hours; fixed eight-hour shifts/work limits.
- Synthetic coordinates distributed within a roughly .06-degree radius around Pune. WGS84 PostGIS spheroidal distances multiplied by 1.3 and rounded to meters. Travel time uses 35 km/h and ceilings to whole seconds.
- Cost coefficients: .3 currency/km fuel, 18 currency/hour work, 5 currency per vehicle dispatch. Work includes travel, service and waiting. Same cost/matrix data for baseline and optimizer.
- OR-Tools guided local search time limit five seconds per benchmark, all orders mandatory. No global optimality proof for the 50/100/150-stop results.
- Small API MILP instance: four customers, two vehicles, PostGIS matrix, 10-second configured CBC limit; solved and proved optimal in 0.359137 s. CBC uses one thread.
- Baseline: deterministic nearest feasible next stop, filling vehicles in input order. It obeys the same capacity/time/shift rules; all nine baselines served all customers.
- Lease-recovery test: real worker exit after claim, five-second lease, second attempt, four uniquely persisted stops. Default normal lease is 120 s.

## Timing and interpretation

`admission_ms` measures the client's HTTP POST until its durable 202 receipt. `matrix_seconds` times PostGIS matrix construction. `solve_seconds` times the solver/model work. `job_wall_seconds` spans submission to observed terminal result and includes queue wait, matrix, solve, persistence and client polling. These nine single-request timings are not a concurrent API throughput or p95 benchmark. The search budget limits search; Python model building, matrix work and I/O are outside or around solver limits.

Aggregate distance reduction = `(sum baseline meters - sum optimized meters) / sum baseline meters`. Median cost/distance reductions are medians of the nine per-instance percentages. All figures are measured outcomes of these deterministic synthetic scenarios; not predictions or empirical road mileage savings. Returned routes were independently audited, but global optimality of OR-Tools routes is not claimed.

## Native runtime accommodations

Docker was unavailable, so real services/client ran as native processes in one isolated network namespace. PostgreSQL required a test-only namespace ownership compatibility shim because only UID 0 is mapped; it reports the non-root UID/file ownership expected by PostgreSQL. SQL, PostGIS distance calculations, transactions, fsync and concurrency settings were unchanged. The application/Docker deployment does not depend on this shim. Default PostgreSQL shared_buffers 128 MiB and max_connections 100 were retained. Native PostGIS libraries and their normal extension control metadata were materialized from Ubuntu packages. PROJ data used the package's local database.

Docker Compose YAML was parsed; image builds/container execution were not tested. The supplied PostGIS 16-3.4 tag matches the tested major families but is not digest-pinned. No independent load host, calibrated storage, live traffic, physical delivery observations, large concurrent solver throughput, sustained capacity, or HA failover tests were performed. Reproduce on your own machine before making deployment-specific performance claims.
