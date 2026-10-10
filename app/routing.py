"""Shared objective, feasible baseline, scalable OR-Tools routing, and independent audit."""
import math,time
from ortools.constraint_solver import pywrapcp,routing_enums_pb2
from .models import Request
SCALE=10000

def coefficients(v):
    return round(v.fuel_cost_per_km*SCALE/1000),round(v.driver_cost_per_hour*SCALE/3600),round(v.fixed_dispatch_cost*SCALE)

def travel_matrix(req,dist):
    n=len(req.orders)+1
    if len(dist)!=n or any(len(row)!=n for row in dist):raise ValueError('matrix shape mismatch')
    if any(not isinstance(d,int) or d<0 for row in dist for d in row):raise ValueError('distance must be nonnegative integer meters')
    return [[math.ceil(d/(req.speed_kmh*1000/3600)) for d in row] for row in dist]

def manifest(req,dist,paths,solver_status,wall=0):
    travel=travel_matrix(req,dist);seen=[];routes=[];total_distance=total_units=0;violations=[]
    for k,path in enumerate(paths):
        if not path:continue
        v=req.vehicles[k];now=v.shift_start;last=0;load=0;meters=0;stops=[]
        for node in path:
            if not 1<=node<=len(req.orders):raise ValueError('invalid route node')
            o=req.orders[node-1];arrival=now+travel[last][node];service=max(arrival,o.window_start);now=service+o.service_seconds
            load+=o.demand_kg;meters+=dist[last][node];seen.append(node)
            if service>o.window_end:violations.append(f'time window: {o.id}')
            stops.append({'order_id':o.id,'sequence':len(stops)+1,'arrival_seconds':arrival,'service_start_seconds':service,'departure_seconds':now,'waiting_seconds':service-arrival,'demand_kg':o.demand_kg})
            last=node
        meters+=dist[last][0];end=now+travel[last][0];duration=end-v.shift_start
        if load>v.capacity_kg:violations.append(f'capacity: {v.id}')
        if end>v.shift_end or duration>v.max_work_seconds:violations.append(f'shift: {v.id}')
        fuel,wage,fixed=coefficients(v);units=meters*fuel+duration*wage+fixed
        routes.append({'vehicle_id':v.id,'driver_id':v.driver_id,'load_kg':load,'distance_m':meters,'start_seconds':v.shift_start,'return_seconds':end,'driver_work_seconds':duration,'cost_units':units,'modeled_cost':units/SCALE,'stops':stops})
        total_distance+=meters;total_units+=units
    if sorted(seen)!=list(range(1,len(req.orders)+1)):violations.append('missing or duplicate orders')
    return {'solver_status':solver_status,'solve_seconds':round(wall,6),'objective_scale':SCALE,'distance_m':total_distance,'cost_units':total_units,'modeled_cost':total_units/SCALE,'vehicles_used':len(routes),'orders_served':len(seen),'feasible':not violations,'violations':violations,'routes':routes}

def validate_result(req,dist,result):
    """Recompute constraints and objective from route order IDs; don't trust solver flags."""
    lookup={o.id:i+1 for i,o in enumerate(req.orders)};vehicles={v.id:k for k,v in enumerate(req.vehicles)};paths=[[] for _ in req.vehicles];used=set()
    for route in result['routes']:
        k=vehicles[route['vehicle_id']]
        if k in used:raise ValueError('duplicate vehicle route')
        used.add(k);paths[k]=[lookup[s['order_id']] for s in route['stops']]
    audit=manifest(req,dist,paths,'INDEPENDENT_AUDIT')
    if not audit['feasible']:raise ValueError(str(audit['violations']))
    if audit['cost_units']!=result['cost_units'] or audit['distance_m']!=result['distance_m']:raise ValueError('objective or distance mismatch')
    for route in result['routes']:
        v=req.vehicles[vehicles[route['vehicle_id']]]
        if route['driver_id']!=v.driver_id:raise ValueError('wrong driver')
        expected=next(r for r in audit['routes'] if r['vehicle_id']==v.id)
        if route!=expected:raise ValueError('reported schedule differs from reconstructed feasible schedule')
    return {'passed':True,'capacity_violations':0,'time_window_violations':0,'shift_violations':0,'unserved_or_duplicate_orders':0}

def baseline(req,dist):
    """Nearest feasible next stop, filling each vehicle in input order; no hindsight."""
    start=time.perf_counter();travel=travel_matrix(req,dist);remaining=set(range(1,len(req.orders)+1));paths=[]
    for v in req.vehicles:
        path=[];last=0;now=v.shift_start;load=0
        while remaining:
            candidates=[]
            for node in remaining:
                o=req.orders[node-1];service=max(now+travel[last][node],o.window_start);end=service+o.service_seconds+travel[node][0]
                if load+o.demand_kg<=v.capacity_kg and service<=o.window_end and end<=min(v.shift_end,v.shift_start+v.max_work_seconds):candidates.append(node)
            if not candidates:break
            node=min(candidates,key=lambda i:(dist[last][i],i));o=req.orders[node-1];now=max(now+travel[last][node],o.window_start)+o.service_seconds;load+=o.demand_kg;remaining.remove(node);path.append(node);last=node
        paths.append(path)
    result=manifest(req,dist,paths,'GREEDY_FEASIBLE' if not remaining else 'GREEDY_PARTIAL',time.perf_counter()-start)
    result['unserved_order_ids']=[req.orders[i-1].id for i in sorted(remaining)];return result

def solve(req,dist):
    if req.solver=='milp':
        from .milp import solve_milp
        return solve_milp(req,dist)
    start=time.perf_counter();travel=travel_matrix(req,dist);n=len(dist);manager=pywrapcp.RoutingIndexManager(n,len(req.vehicles),0);routing=pywrapcp.RoutingModel(manager)
    callbacks=[]
    for k,v in enumerate(req.vehicles):
        fuel,_,fixed=coefficients(v)
        callback=lambda i,j,fuel=fuel:dist[manager.IndexToNode(i)][manager.IndexToNode(j)]*fuel
        callbacks.append(callback);idx=routing.RegisterTransitCallback(callback);routing.SetArcCostEvaluatorOfVehicle(idx,k);routing.SetFixedCostOfVehicle(fixed,k)
    service=[0]+[o.service_seconds for o in req.orders]
    cb=lambda i,j:travel[manager.IndexToNode(i)][manager.IndexToNode(j)]+service[manager.IndexToNode(i)]
    transit=routing.RegisterTransitCallback(cb);routing.AddDimension(transit,86400,86400,False,'Time');td=routing.GetDimensionOrDie('Time')
    for node,o in enumerate(req.orders,1):td.CumulVar(manager.NodeToIndex(node)).SetRange(o.window_start,o.window_end)
    for k,v in enumerate(req.vehicles):
        td.CumulVar(routing.Start(k)).SetRange(v.shift_start,v.shift_start);td.CumulVar(routing.End(k)).SetRange(v.shift_start,min(v.shift_end,v.shift_start+v.max_work_seconds));td.SetSpanUpperBoundForVehicle(v.max_work_seconds,k);td.SetSpanCostCoefficientForVehicle(coefficients(v)[1],k);routing.AddVariableMinimizedByFinalizer(td.CumulVar(routing.End(k)))
    demand=routing.RegisterUnaryTransitCallback(lambda i:0 if manager.IndexToNode(i)==0 else req.orders[manager.IndexToNode(i)-1].demand_kg)
    routing.AddDimensionWithVehicleCapacity(demand,0,[v.capacity_kg for v in req.vehicles],True,'Capacity')
    params=pywrapcp.DefaultRoutingSearchParameters();params.first_solution_strategy=routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION;params.local_search_metaheuristic=routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH;params.time_limit.seconds=req.time_limit_seconds
    solution=routing.SolveWithParameters(params)
    if solution is None:return {'solver_status':'NO_SOLUTION_WITHIN_LIMIT','routing_status_code':routing.status(),'solve_seconds':time.perf_counter()-start,'feasible':False,'routes':[],'note':'Search failure is not a proof of infeasibility.'}
    paths=[]
    for k in range(len(req.vehicles)):
        index=routing.Start(k);path=[]
        while not routing.IsEnd(index):
            node=manager.IndexToNode(index)
            if node:path.append(node)
            index=solution.Value(routing.NextVar(index))
        paths.append(path)
    result=manifest(req,dist,paths,'FEASIBLE_HEURISTIC',time.perf_counter()-start);result['routing_status_code']=routing.status();result['search_objective_units']=solution.ObjectiveValue();result['optimality_proven']=False
    if not result['feasible']:raise ValueError('solver route failed independent constraint reconstruction')
    result['audit']=validate_result(req,dist,result);return result
