"""True binary arc MILP with time propagation; intentionally capped for teaching."""
import time,os
import pulp
from .routing import coefficients,travel_matrix,manifest,validate_result

def solve_milp(req,dist):
    started=time.perf_counter();travel=travel_matrix(req,dist);n=len(req.orders);end=n+1;customers=range(1,n+1);vehicles=range(len(req.vehicles));arcs=[(i,j,k) for k in vehicles for i in range(n+1) for j in range(1,n+2) if i!=j and not(i==0 and j==end)]
    model=pulp.LpProblem('CVRPTW',pulp.LpMinimize);x=pulp.LpVariable.dicts('x',arcs,cat='Binary');used=pulp.LpVariable.dicts('used',vehicles,cat='Binary');t={(i,k):pulp.LpVariable(f't_{i}_{k}',lowBound=0,upBound=86400) for k in vehicles for i in range(n+2)}
    M=2000000
    def node(i):return 0 if i==end else i
    for i in customers:model+=pulp.lpSum(x[i,j,k] for k in vehicles for j in range(1,n+2) if (i,j,k) in x)==1
    objective=[]
    for k,v in enumerate(req.vehicles):
        model+=pulp.lpSum(x[0,j,k] for j in customers)==used[k];model+=pulp.lpSum(x[i,end,k] for i in customers)==used[k]
        model+=t[0,k]==v.shift_start;model+=t[end,k]>=v.shift_start;model+=t[end,k]<=v.shift_start+min(v.shift_end-v.shift_start,v.max_work_seconds)*used[k]
        for i in customers:
            incoming=pulp.lpSum(x[j,i,k] for j in range(n+1) if (j,i,k) in x);outgoing=pulp.lpSum(x[i,j,k] for j in range(1,n+2) if (i,j,k) in x)
            model+=incoming==outgoing;model+=incoming<=used[k]
            o=req.orders[i-1];model+=t[i,k]>=o.window_start-M*(1-incoming);model+=t[i,k]<=o.window_end+M*(1-incoming)
        model+=pulp.lpSum(req.orders[i-1].demand_kg*x[i,j,k] for i in customers for j in range(1,n+2) if (i,j,k) in x)<=v.capacity_kg
        fuel,wage,fixed=coefficients(v);objective.append(fixed*used[k]+wage*(t[end,k]-v.shift_start)+pulp.lpSum(dist[node(i)][node(j)]*fuel*x[i,j,k] for i,j,kk in arcs if kk==k))
    # Positive service duration excludes disconnected cycles even at identical coordinates.
    for i,j,k in arcs:
        service=0 if i==0 else req.orders[i-1].service_seconds
        # Large travel arcs can be impossible; forbid them instead of using an invalid big-M.
        transit=travel[node(i)][node(j)]+service
        if transit>86400:model+=x[i,j,k]==0
        else:model+=t[j,k]>=t[i,k]+transit-M*(1-x[i,j,k])
    model+=pulp.lpSum(objective)
    if os.getenv('MILP_EXPORT_PATH'):model.writeLP(os.environ['MILP_EXPORT_PATH'])
    solver=pulp.PULP_CBC_CMD(msg=False,timeLimit=req.time_limit_seconds,threads=1,gapRel=0)
    model.solve(solver)
    # PuLP 3.x may label a time-limited incumbent 'Optimal' in model.status;
    # sol_status distinguishes proved optimal from integer-feasible incumbent.
    status=pulp.LpStatus[model.status];sol_status=model.sol_status
    if sol_status not in (pulp.LpSolutionOptimal,pulp.LpSolutionIntegerFeasible):return {'solver_status':'PROVEN_INFEASIBLE' if status=='Infeasible' else 'NO_SOLUTION_WITHIN_LIMIT','feasible':False,'routes':[],'solve_seconds':time.perf_counter()-started,'cbc_status':status,'cbc_solution_status':sol_status}
    paths=[]
    for k in vehicles:
        route=[];i=0;seen=set()
        if used[k].value()>.5:
            while i!=end:
                nxt=[j for j in range(1,n+2) if (i,j,k) in x and x[i,j,k].value() is not None and x[i,j,k].value()>.5]
                if len(nxt)!=1:raise ValueError('nonintegral or incomplete CBC route')
                j=nxt[0]
                if j in seen:raise ValueError('CBC subtour detected')
                seen.add(j)
                if j!=end:route.append(j)
                i=j
        paths.append(route)
    proven=sol_status==pulp.LpSolutionOptimal;result=manifest(req,dist,paths,'OPTIMAL_MILP' if proven else 'FEASIBLE_MILP',time.perf_counter()-started);result.update(optimality_proven=proven,cbc_status=status,cbc_solution_status=sol_status,variable_count=len(model.variables()),constraint_count=len(model.constraints),search_objective_units=pulp.value(model.objective));result['audit']=validate_result(req,dist,result);return result
