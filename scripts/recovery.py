"""Reproduce crash-after-claim lease recovery on an idle Compose demo stack."""
import json,subprocess,time,uuid
from pathlib import Path
import httpx

def docker(*args):return subprocess.run(['docker','compose',*args],check=True,capture_output=True,text=True).stdout
def main():
    payload=json.loads(Path('data/example-milp.json').read_text());payload['time_limit_seconds']=5
    docker('stop','worker')
    try:
        with httpx.Client(base_url='http://localhost:8081',timeout=20,trust_env=False) as client:
            response=client.post('/jobs',json=payload,headers={'Idempotency-Key':'recovery-'+uuid.uuid4().hex});response.raise_for_status();job=response.json()['job_id']
            p=subprocess.Popen(['docker','compose','run','--rm','--no-deps','-e','CRASH_AFTER_CLAIM=1','-e','LEASE_SECONDS=5','worker','python','-m','app.worker'])
            if p.wait(timeout=60)!=42:raise RuntimeError('crash hook did not claim the intended idle job')
            assert client.get('/jobs/'+job).json()['status']=='RUNNING'
            docker('up','-d','--scale','worker=2','worker');started=time.monotonic()
            while time.monotonic()-started<90:
                state=client.get('/jobs/'+job).json()
                if state['status']=='SUCCEEDED':break
                time.sleep(.2)
            assert state['status']=='SUCCEEDED' and state['attempts']==2
            result=state['result'];assert result['audit']['passed'] and result['orders_served']==len(payload['orders'])
            Path('results/recovery-reproduction.json').write_text(json.dumps(state,indent=2)+'\n');print('PASS: crashed job reclaimed and completed on attempt 2')
    finally:docker('up','-d','--scale','worker=2','worker')
if __name__=='__main__':main()
