"""Run repeatable synthetic benchmark batches through the asynchronous HTTP API."""
import argparse,json,statistics,time,uuid
from pathlib import Path
import httpx
from scripts.generate import scenario
from app.models import Request
from app.routing import validate_result

def run(url,output,cases=None):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);rows=[]
    cases=cases or [(n,seed) for n in (50,100,150) for seed in (42,43,44)]
    with httpx.Client(trust_env=False,base_url=url,timeout=20) as client:
        for n,seed in cases:
            payload=scenario(n,seed);(out/f'input-{n}-{seed}.json').write_text(json.dumps(payload,indent=2)+'\n');t=time.perf_counter();r=client.post('/jobs',json=payload,headers={'Idempotency-Key':'benchmark-'+uuid.uuid4().hex});r.raise_for_status();admission=(time.perf_counter()-t)*1000;job=r.json()['job_id']
            while True:
                response=client.get('/jobs/'+job);response.raise_for_status();state=response.json()
                if state['status'] not in ('QUEUED','RUNNING'):break
                if time.perf_counter()-t>120:raise RuntimeError('job timeout')
                time.sleep(.1)
            wall=time.perf_counter()-t
            if state['status']!='SUCCEEDED':raise RuntimeError(f'job {job} did not solve: {state}')
            result=state['result'];audit=validate_result(Request.model_validate(payload),result['distance_matrix_m'],result);base=result['baseline']
            if not base['feasible']:raise RuntimeError('baseline not fully feasible; comparison invalid')
            validate_result(Request.model_validate(payload),result['distance_matrix_m'],base)
            (out/f'result-{n}-{seed}.json').write_text(json.dumps(state,indent=2)+'\n')
            row={'orders':n,'seed':seed,'job_id':job,'admission_ms':round(admission,3),'job_wall_seconds':round(wall,4),'matrix_seconds':result['matrix_seconds'],'solve_seconds':result['solve_seconds'],'baseline_distance_km':base['distance_m']/1000,'optimized_distance_km':result['distance_m']/1000,'baseline_cost':base['modeled_cost'],'optimized_cost':result['modeled_cost'],'baseline_vehicles':base['vehicles_used'],'optimized_vehicles':result['vehicles_used'],**result['baseline_comparison'],'audit':audit,'solver_status':result['solver_status']};rows.append(row);print(json.dumps(row),flush=True)
    summary={'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'case_count':len(rows),'total_destinations':sum(r['orders'] for r in rows),'cases':rows,'aggregate_distance_reduction_pct':round(100*(sum(r['baseline_distance_km'] for r in rows)-sum(r['optimized_distance_km'] for r in rows))/sum(r['baseline_distance_km'] for r in rows),4),'median_distance_reduction_pct':round(statistics.median(r['distance_reduction_pct'] for r in rows),4),'median_cost_reduction_pct':round(statistics.median(r['modeled_cost_reduction_pct'] for r in rows),4)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:8081');p.add_argument('--output',default='results/reproduction');a=p.parse_args();run(a.url,a.output)
