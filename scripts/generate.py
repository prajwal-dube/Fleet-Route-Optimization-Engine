"""Deterministic synthetic logistics data; no real road network or traffic data."""
import argparse,json,math,random
from pathlib import Path

def scenario(n,seed):
    rng=random.Random(seed);orders=[]
    for i in range(n):
        angle=rng.uniform(0,2*math.pi);radius=.06*math.sqrt(rng.random())
        orders.append({'id':f'order-{i:03}','location':{'lat':18.5204+radius*math.cos(angle),'lon':73.8567+radius*math.sin(angle)},'demand_kg':rng.randint(2,5),'window_start':0,'window_end':14400 if i%3==0 else 21600,'service_seconds':rng.randint(90,180)})
    return {'depot':{'lat':18.5204,'lon':73.8567},'orders':orders,'vehicles':[{'id':f'truck-{i}','driver_id':f'driver-{i}','capacity_kg':50,'shift_start':0,'shift_end':28800,'max_work_seconds':28800,'fuel_cost_per_km':.3,'driver_cost_per_hour':18,'fixed_dispatch_cost':5} for i in range(math.ceil(n/10))],'speed_kmh':35,'road_factor':1.3,'solver':'ortools','time_limit_seconds':5}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--orders',type=int,default=100);p.add_argument('--seed',type=int,default=42);p.add_argument('--output',default='data/example-100.json');a=p.parse_args();Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(scenario(a.orders,a.seed),indent=2)+'\n')
