CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS jobs (
 id UUID PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 payload_hash TEXT NOT NULL,
 payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','NO_SOLUTION','FAILED')),
 attempts INTEGER NOT NULL DEFAULT 0,
 lease_token UUID,
 lease_until TIMESTAMPTZ,
 result JSONB,
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_dispatch ON jobs(status,lease_until,created_at);
CREATE TABLE IF NOT EXISTS locations (
 job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 node INTEGER NOT NULL,
 order_id TEXT,
 position GEOGRAPHY(POINT,4326) NOT NULL,
 demand_kg INTEGER NOT NULL DEFAULT 0,
 window_start INTEGER,
 window_end INTEGER,
 service_seconds INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(job_id,node)
);
CREATE INDEX IF NOT EXISTS locations_spatial ON locations USING GIST(position);
CREATE TABLE IF NOT EXISTS vehicles (
 job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 vehicle_id TEXT NOT NULL,
 driver_id TEXT NOT NULL,
 capacity_kg INTEGER NOT NULL CHECK(capacity_kg>0),
 shift_start INTEGER NOT NULL,
 shift_end INTEGER NOT NULL,
 max_work_seconds INTEGER NOT NULL,
 PRIMARY KEY(job_id,vehicle_id)
);
CREATE TABLE IF NOT EXISTS routes (
 job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 vehicle_id TEXT NOT NULL,
 driver_id TEXT NOT NULL,
 load_kg INTEGER NOT NULL,
 distance_m BIGINT NOT NULL,
 return_seconds INTEGER NOT NULL,
 modeled_cost NUMERIC NOT NULL,
 PRIMARY KEY(job_id,vehicle_id),
 FOREIGN KEY(job_id,vehicle_id) REFERENCES vehicles(job_id,vehicle_id)
);
CREATE TABLE IF NOT EXISTS stops (
 job_id UUID NOT NULL,
 vehicle_id TEXT NOT NULL,
 sequence INTEGER NOT NULL,
 order_id TEXT NOT NULL,
 arrival_seconds INTEGER NOT NULL,
 service_start_seconds INTEGER NOT NULL,
 departure_seconds INTEGER NOT NULL,
 PRIMARY KEY(job_id,vehicle_id,sequence),
 UNIQUE(job_id,order_id),
 FOREIGN KEY(job_id,vehicle_id) REFERENCES routes(job_id,vehicle_id) ON DELETE CASCADE
);
