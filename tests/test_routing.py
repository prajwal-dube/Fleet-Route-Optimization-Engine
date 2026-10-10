import copy,itertools
import pytest
from pydantic import ValidationError
from app.models import Request
from app.routing import manifest,solve,baseline,validate_result

def request(solver='ortools'):
    return Request.model_validate({'depot':{'lat':0,'lon':0},'orders':[{'id':str(i),'location':{'lat':0,'lon':i*.01},'demand_kg':2,'window_start':0,'window_end':10000,'service_seconds':60} for i in range(1,5)],'vehicles':[{'id':f'v{i}','driver_id':f'd{i}','capacity_kg':4,'shift_end':10000,'max_work_seconds':10000} for i in range(2)],'solver':solver,'time_limit_seconds':3})
def distance():return [[abs(i-j)*1000 for j in range(5)] for i in range(5)]
@pytest.mark.parametrize('solver',['ortools','milp'])
def test_full_service_and_constraints(solver):
    req=request(solver);result=solve(req,distance());assert result['feasible'];assert result['orders_served']==4;assert result['vehicles_used']==2;assert validate_result(req,distance(),result)['passed']
def test_milp_matches_exhaustive_optimum():
    req=request('milp');d=distance();costs=[]
    for p in itertools.permutations(range(1,5)):
        for cut in range(5):
            r=manifest(req,d,[list(p[:cut]),list(p[cut:])],'ENUMERATION')
            if r['feasible']:costs.append(r['cost_units'])
    result=solve(req,d);assert result['optimality_proven'];assert result['cost_units']==min(costs);assert abs(result['search_objective_units']-min(costs))<.01
@pytest.mark.parametrize('solver',['ortools','milp'])
def test_impossible_capacity_no_partial_result(solver):
    req=request(solver);req.orders[0].demand_kg=20;r=solve(req,distance());assert not r['feasible'];assert r['routes']==[]
@pytest.mark.parametrize('solver',['ortools','milp'])
def test_waiting_and_tight_window(solver):
    req=request(solver);req.orders=req.orders[:1];req.vehicles=req.vehicles[:1];req.orders[0].window_start=1000;req.orders[0].window_end=1000;r=solve(req,[[0,1000],[1000,0]]);assert r['feasible'];stop=r['routes'][0]['stops'][0];assert stop['service_start_seconds']==1000;assert stop['waiting_seconds']>0
@pytest.mark.parametrize('solver',['ortools','milp'])
def test_shift_return_constraint(solver):
    req=request(solver);req.orders=req.orders[:1];req.vehicles=req.vehicles[:1];req.vehicles[0].shift_end=100;r=solve(req,[[0,1000],[1000,0]]);assert not r['feasible']
def test_validator_detects_tampering():
    req=request();r=solve(req,distance());bad=copy.deepcopy(r);bad['routes'][0]['stops'][0]['service_start_seconds']=999999
    with pytest.raises(ValueError):validate_result(req,distance(),bad)
    bad=copy.deepcopy(r);bad['routes'][0]['stops'].append(bad['routes'][0]['stops'][0])
    with pytest.raises(ValueError):validate_result(req,distance(),bad)
def test_invalid_payloads():
    data=request().model_dump();data['orders'][0]['location']['lat']=91
    with pytest.raises(ValidationError):Request.model_validate(data)
    data=request().model_dump();data['orders'][1]['id']=data['orders'][0]['id']
    with pytest.raises(ValidationError):Request.model_validate(data)
    data=request().model_dump();data['orders'][0]['location']['lon']=float('nan')
    with pytest.raises(ValidationError):Request.model_validate(data)
    data=request().model_dump();data['orders'][0]['window_start']=99999
    with pytest.raises(ValidationError):Request.model_validate(data)
def test_nearest_feasible_baseline():
    req=request();r=baseline(req,distance());assert r['feasible'];assert validate_result(req,distance(),r)['passed']
