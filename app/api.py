import re,uuid
import psycopg
from fastapi import FastAPI,Header,HTTPException
from . import db
from .models import Request
app=FastAPI(title='Fleet Route Optimization Engine',version='1.0.0')
@app.get('/health/live')
def live():return {'status':'up'}
@app.get('/health/ready')
def ready():
    try:
        with db.connect() as c:c.execute('SELECT postgis_version()').fetchone();c.execute('SELECT 1 FROM jobs LIMIT 1')
        return {'status':'ready'}
    except psycopg.Error:raise HTTPException(503,'database/schema unavailable')
@app.post('/jobs',status_code=202)
def create(req:Request,idempotency_key:str=Header(...)):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',idempotency_key):raise HTTPException(422,'invalid idempotency key')
    try:row,created=db.submit(req,idempotency_key)
    except ValueError as e:raise HTTPException(409,str(e))
    except psycopg.Error:raise HTTPException(503,'database unavailable; retry same key')
    return {'job_id':str(row['id']),'status':row['status'],'created':created,'status_url':f"/jobs/{row['id']}"}
@app.get('/jobs/{job_id}')
def status(job_id:uuid.UUID):
    try:row=db.get(job_id)
    except psycopg.Error:raise HTTPException(503,'database unavailable')
    if row is None:raise HTTPException(404,'job not found')
    return row
