import os,uuid,concurrent.futures
import pytest
from fastapi.testclient import TestClient
from app import db
from app.models import Request
from app.api import app
from app.routing import solve
from tests.test_routing import request
pytestmark=pytest.mark.skipif(os.getenv('INTEGRATION')!='1',reason='real PostgreSQL/PostGIS required')
def test_postgis_matrix_and_atomic_ingestion():
    req=request();job,created=db.submit(req,uuid.uuid4().hex);assert created
    d=db.matrix(job['id'],req);assert d[0][0]==0;assert abs(d[0][1]-1447)<3;assert d[0][1]==d[1][0]
    with db.connect() as c:
        assert c.execute('SELECT count(*) n FROM locations WHERE job_id=%s',(job['id'],)).fetchone()['n']==5
        assert c.execute('SELECT count(*) n FROM vehicles WHERE job_id=%s',(job['id'],)).fetchone()['n']==2
def test_concurrent_idempotency():
    req=request();key=uuid.uuid4().hex
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(lambda _:db.submit(req,key),range(16)))
    assert len({str(r[0]['id']) for r in rows})==1;assert sum(r[1] for r in rows)==1
    req.orders[0].demand_kg=3
    with pytest.raises(ValueError):db.submit(req,key)
def test_leases_fence_stale_worker_and_transactional_manifest():
    # Isolate dispatch tests from other queued fixtures.
    with db.connect() as c:c.execute("UPDATE jobs SET status='FAILED' WHERE status='QUEUED'")
    req=request();created,_=db.submit(req,uuid.uuid4().hex);first=db.claim();assert first['id']==created['id']
    with db.connect() as c:c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(first['id'],))
    second=db.claim();assert second['id']==first['id'];assert second['token']!=first['token'];result=solve(req,db.matrix(first['id'],req))
    assert not db.complete(first,'SUCCEEDED',result);assert db.complete(second,'SUCCEEDED',result);assert not db.complete(second,'SUCCEEDED',result)
    with db.connect() as c:
        assert c.execute('SELECT count(*) n FROM stops WHERE job_id=%s',(first['id'],)).fetchone()['n']==4
        assert c.execute('SELECT attempts,status FROM jobs WHERE id=%s',(first['id'],)).fetchone()=={'attempts':2,'status':'SUCCEEDED'}
def test_api_validation_and_conflicts():
    client=TestClient(app);payload=request().model_dump();key=uuid.uuid4().hex
    a=client.post('/jobs',json=payload,headers={'Idempotency-Key':key});assert a.status_code==202
    b=client.post('/jobs',json=payload,headers={'Idempotency-Key':key});assert b.json()['job_id']==a.json()['job_id'];assert not b.json()['created']
    payload['orders'][0]['demand_kg']=3;assert client.post('/jobs',json=payload,headers={'Idempotency-Key':key}).status_code==409
    assert client.post('/jobs',json={}).status_code==422;assert client.get('/jobs/not-uuid').status_code==422;assert client.get('/jobs/'+str(uuid.uuid4())).status_code==404;assert client.get('/health/ready').status_code==200
