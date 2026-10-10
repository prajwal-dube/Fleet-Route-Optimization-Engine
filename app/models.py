from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ID=Annotated[str,Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')]
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Point(Strict):
    lat: float=Field(ge=-90,le=90)
    lon: float=Field(ge=-180,le=180)
class Order(Strict):
    id: ID
    location: Point
    demand_kg: int=Field(gt=0,le=100000)
    window_start: int=Field(ge=0,le=86400)
    window_end: int=Field(ge=0,le=86400)
    service_seconds: int=Field(ge=1,le=7200,default=120)
    @model_validator(mode='after')
    def window(self):
        if self.window_end<self.window_start:raise ValueError('window end precedes start')
        return self
class Vehicle(Strict):
    id: ID
    driver_id: ID
    capacity_kg: int=Field(gt=0,le=1000000)
    shift_start: int=Field(ge=0,le=86400,default=0)
    shift_end: int=Field(ge=1,le=86400,default=28800)
    max_work_seconds: int=Field(gt=0,le=86400,default=28800)
    fuel_cost_per_km: float=Field(ge=0,le=100,default=.3)
    driver_cost_per_hour: float=Field(ge=0,le=1000,default=18)
    fixed_dispatch_cost: float=Field(ge=0,le=10000,default=5)
    @model_validator(mode='after')
    def shift(self):
        if self.shift_end<=self.shift_start:raise ValueError('empty vehicle shift')
        return self
class Request(Strict):
    depot: Point
    orders: list[Order]=Field(min_length=1,max_length=200)
    vehicles: list[Vehicle]=Field(min_length=1,max_length=30)
    speed_kmh: float=Field(gt=0,le=120,default=35)
    road_factor: float=Field(ge=1,le=3,default=1.3)
    solver: Literal['ortools','milp']='ortools'
    time_limit_seconds: int=Field(ge=1,le=30,default=5)
    @model_validator(mode='after')
    def unique(self):
        for name,ids in [('order',[o.id for o in self.orders]),('vehicle',[v.id for v in self.vehicles]),('driver',[v.driver_id for v in self.vehicles])]:
            if len(ids)!=len(set(ids)):raise ValueError(f'duplicate {name} ID')
        if self.solver=='milp' and (len(self.orders)>12 or len(self.vehicles)>5):raise ValueError('MILP demo limit: 12 orders and 5 vehicles; use ortools for larger batches')
        return self
