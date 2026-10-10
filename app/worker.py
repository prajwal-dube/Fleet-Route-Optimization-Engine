import json,logging,os,time
from . import db
from .models import Request
from .routing import baseline,solve,validate_result
logging.basicConfig(level=logging.INFO)
def work_once():
    job=db.claim()
    if not job:return False
    if os.getenv('CRASH_AFTER_CLAIM')=='1':os._exit(42)
    try:
        req=Request.model_validate(job['payload']);started=time.perf_counter();dist=db.matrix(job['id'],req);matrix_seconds=time.perf_counter()-started
        base=baseline(req,dist)
        if base['feasible']:base['audit']=validate_result(req,dist,base)
        result=solve(req,dist);result['distance_matrix_m']=dist;result['matrix_seconds']=round(matrix_seconds,6);result['baseline']=base
        if base['feasible'] and result['feasible']:
            result['baseline_comparison']={'distance_reduction_pct':round(100*(base['distance_m']-result['distance_m'])/base['distance_m'],4) if base['distance_m'] else 0,'modeled_cost_reduction_pct':round(100*(base['cost_units']-result['cost_units'])/base['cost_units'],4) if base['cost_units'] else 0}
        completed=db.complete(job,'SUCCEEDED' if result['feasible'] else 'NO_SOLUTION',result)
        if completed:logging.info('completed %s: %s',job['id'],result['solver_status'])
    except Exception:
        logging.exception('job %s failed',job['id']);db.complete(job,'FAILED',error='optimizer failure; inspect worker logs')
    return True
if __name__=='__main__':
    while True:
        try:
            if not work_once():time.sleep(.2)
        except Exception:logging.exception('worker dispatch failure');time.sleep(1)
