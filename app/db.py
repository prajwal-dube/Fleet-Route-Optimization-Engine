import hashlib,json,os,uuid
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .models import Request

def connect():return psycopg.connect(os.getenv('DATABASE_URL','postgresql://fleet:fleet@localhost:5432/fleet'),row_factory=dict_row,connect_timeout=5)
def migrate():
    with connect() as c:c.execute(Path(__file__).with_name('schema.sql').read_text())
def submit(req:Request,key:str):
    payload=req.model_dump(mode='json');digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest();job_id=uuid.uuid4()
    with connect() as c:
        row=c.execute('INSERT INTO jobs(id,idempotency_key,payload_hash,payload) VALUES(%s,%s,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING id,status',(job_id,key,digest,Jsonb(payload))).fetchone()
        if row is None:
            old=c.execute('SELECT id,status,payload_hash FROM jobs WHERE idempotency_key=%s',(key,)).fetchone()
            if old['payload_hash']!=digest:raise ValueError('idempotency key belongs to a different request')
            return old,False
        c.execute('INSERT INTO locations(job_id,node,position) VALUES(%s,0,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)',(job_id,req.depot.lon,req.depot.lat))
        for node,o in enumerate(req.orders,1):c.execute('INSERT INTO locations(job_id,node,order_id,position,demand_kg,window_start,window_end,service_seconds) VALUES(%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s,%s,%s)',(job_id,node,o.id,o.location.lon,o.location.lat,o.demand_kg,o.window_start,o.window_end,o.service_seconds))
        for v in req.vehicles:c.execute('INSERT INTO vehicles VALUES(%s,%s,%s,%s,%s,%s,%s)',(job_id,v.id,v.driver_id,v.capacity_kg,v.shift_start,v.shift_end,v.max_work_seconds))
        return row,True

def matrix(job_id,req):
    n=len(req.orders)+1;dist=[[0]*n for _ in range(n)]
    with connect() as c:
        rows=c.execute('SELECT a.node i,b.node j,round(ST_Distance(a.position,b.position)*%s)::bigint meters FROM locations a JOIN locations b ON a.job_id=b.job_id WHERE a.job_id=%s ORDER BY a.node,b.node',(req.road_factor,job_id)).fetchall()
    if len(rows)!=n*n:raise ValueError('incomplete PostGIS location matrix')
    for r in rows:dist[r['i']][r['j']]=r['meters']
    return dist

def get(job_id):
    with connect() as c:return c.execute('SELECT id,status,attempts,result,error,created_at,completed_at FROM jobs WHERE id=%s',(job_id,)).fetchone()

def claim():
    token=uuid.uuid4()
    with connect() as c:
        # Exhausted crashed jobs become terminal rather than remaining RUNNING forever.
        c.execute("UPDATE jobs SET status='FAILED',error='retry budget exhausted',completed_at=now() WHERE status='RUNNING' AND lease_until<now() AND attempts>=3")
        row=c.execute("SELECT id,payload FROM jobs WHERE attempts<3 AND (status='QUEUED' OR (status='RUNNING' AND lease_until<now())) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if row is None:return None
        seconds=int(os.getenv('LEASE_SECONDS','120'))
        if seconds<5:raise ValueError('LEASE_SECONDS must be at least 5')
        c.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease_token=%s,lease_until=now()+%s*interval '1 second' WHERE id=%s",(token,seconds,row['id']))
        row['token']=token;return row

def complete(job,status,result=None,error=None):
    with connect() as c:
        # Token fencing: a crashed/slow worker cannot overwrite a newer attempt.
        owned=c.execute("SELECT id FROM jobs WHERE id=%s AND lease_token=%s AND status='RUNNING' FOR UPDATE",(job['id'],job['token'])).fetchone()
        if owned is None:return False
        if result and result.get('feasible'):
            for r in result['routes']:
                c.execute('INSERT INTO routes VALUES(%s,%s,%s,%s,%s,%s,%s)',(job['id'],r['vehicle_id'],r['driver_id'],r['load_kg'],r['distance_m'],r['return_seconds'],r['modeled_cost']))
                for stop in r['stops']:c.execute('INSERT INTO stops VALUES(%s,%s,%s,%s,%s,%s,%s)',(job['id'],r['vehicle_id'],stop['sequence'],stop['order_id'],stop['arrival_seconds'],stop['service_start_seconds'],stop['departure_seconds']))
        c.execute('UPDATE jobs SET status=%s,result=%s,error=%s,lease_until=NULL,completed_at=now() WHERE id=%s',(status,Jsonb(result) if result else None,error,job['id']));return True
