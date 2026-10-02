from __future__ import annotations
from dataclasses import dataclass, replace
import time
import math
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from .contracts import Prediction, Record, digest


@dataclass(frozen=True)
class OperatingPoint(Record):
    vessel_id: str
    vessel_type: str
    capacity_t: float
    engine_id: str
    pathway_id: str
    speed_kn: float
    cargo_t: float
    wave_m: float | None = 0
    wind_kn: float | None = 0
    auxiliary_kw: float = 0
    speed_basis: str = "through_water"


NUMERIC=["capacity_t","speed_kn","cargo_t","wave_m","wind_kn","auxiliary_kw"]
CATEGORICAL=["vessel_type","engine_id","pathway_id","speed_basis"]


def point_from_observation(o,s):
    v=next(v for v in s.vessels if v.id==o.vessel_id)
    return OperatingPoint(v.id,v.type,v.capacity_t,o.engine_id,o.pathway_id,o.speed_kn,o.cargo_t,o.wave_m,o.wind_kn,o.auxiliary_kw,o.speed_basis)


def point_frame(points):
    return pd.DataFrame([{k:getattr(p,k) for k in NUMERIC+CATEGORICAL} for p in points]).replace({None:np.nan})


def engineering_rate(p,s):
    v=next((v for v in s.vessels if v.id==p.vessel_id),None)
    f=next((f for f in s.pathways if f.id==p.pathway_id),None)
    e=next((e for e in s.engine_fuels if e.engine_id==p.engine_id and e.pathway_id==p.pathway_id),None)
    if not v or not f or not e or not v.power_coefficient or not v.power_source or not e.source or f.lhv_mj_kg<=0 or e.efficiency<=0:
        raise ValueError("engineering model lacks sourced curve/engine/fuel map")
    return (v.power_coefficient*p.speed_kn**3/e.efficiency+p.auxiliary_kw/e.auxiliary_efficiency)*3.6/f.lhv_mj_kg


class Predictor:
    def __init__(self,scenario,split,method,model,fit_rows,cal_rows,seed,params,features,fit_seconds):
        self.scenario,self.split,self.method,self.model=scenario,split,method,model
        self.fit_ids=tuple(o.id for o in fit_rows)
        self.calibration_ids=tuple(o.id for o in cal_rows)
        self.features=features
        self.model_id=digest({"method":method,"rows":fit_rows,"calibration":cal_rows,"params":params,"seed":seed,"features":features,"physical":(scenario.vessels,scenario.engine_fuels,scenario.pathways)})
        points=[point_from_observation(o,scenario) for o in fit_rows]
        frame=point_frame(points)
        self.bounds={k:(float(frame[k].min()),float(frame[k].max())) for k in ["speed_kn","cargo_t","wave_m","wind_kn"]}
        self.categories={k:set(frame[k]) for k in CATEGORICAL}
        self.preprocessing_statistics={k:None if frame[k].isna().all() else float(frame[k].median()) for k in NUMERIC}
        self.fit_seconds=fit_seconds
        self.tuning_history=[]
        self.fit_count=0 if method=="engineering" else 1
        self.q=0.
        residuals=[]
        for o in cal_rows:
            p=point_from_observation(o,scenario)
            if self.supported(p):
                residuals.append(abs(o.fuel_mass_kg/o.duration_h-self._raw([p])[0]))
        if residuals:
            level=min(1,math.ceil((len(residuals)+1)*.9)/len(residuals))
            self.q=float(np.quantile(residuals,level,method="higher"))
        self.interval_calibrated=bool(residuals)

    def supported(self,p):
        v=next((v for v in self.scenario.vessels if v.id==p.vessel_id),None)
        if not v or not v.min_speed_kn<=p.speed_kn<=v.max_speed_kn or not 0<=p.cargo_t<=v.capacity_t:
            return False
        if not any(e.engine_id==p.engine_id and e.pathway_id==p.pathway_id for e in self.scenario.engine_fuels):
            return False
        if self.method=="engineering":
            try:
                engineering_rate(p,self.scenario)
                return True
            except ValueError:
                return False
        return all(getattr(p,k) in values for k,values in self.categories.items()) and all(getattr(p,k) is None or lo<=getattr(p,k)<=hi for k,(lo,hi) in self.bounds.items())

    def _raw(self,points):
        if self.method=="engineering":
            return np.array([engineering_rate(p,self.scenario) for p in points])
        with threadpool_limits(limits=1):
            values=self.model.predict(point_frame(points))
        if self.method=="residual":
            values+=np.array([engineering_rate(p,self.scenario) for p in points])
        return np.maximum(0,values)

    def predict(self,points):
        output=[]
        for p in points:
            if not self.supported(p):
                output.append(Prediction(None,None,None,"unsupported",self.model_id))
                continue
            rate=float(self._raw([p])[0])
            output.append(Prediction(rate,max(0,rate-self.q) if self.interval_calibrated else None,rate+self.q if self.interval_calibrated else None,"engineering_only" if self.method=="engineering" else "supported",self.model_id))
        return output


def _fit_model(rows,s,method,seed,params=None,features=None):
    points=[point_from_observation(o,s) for o in rows]
    numeric=features or NUMERIC
    pre=ColumnTransformer([("num",SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),numeric),("cat",OneHotEncoder(handle_unknown="ignore",sparse_output=False),CATEGORICAL)])
    model=make_pipeline(pre,HistGradientBoostingRegressor(max_iter=40,max_leaf_nodes=15,min_samples_leaf=5,early_stopping=False,random_state=seed,**(params or {})))
    y=np.array([o.fuel_mass_kg/o.duration_h for o in rows])
    if method=="residual":
        y-=np.array([engineering_rate(p,s) for p in points])
    with threadpool_limits(limits=1):
        model.fit(point_frame(points),y)
    return model


def fit_predictor(data,split,method,budget,seed):
    if method not in ("engineering","direct","residual"):
        raise ValueError("unknown predictor method")
    if budget<1:
        raise ValueError("fit budget must be positive")
    partitions=[set(getattr(split,x)) for x in ("train","validation","calibration","test")]
    if any(a&b for i,a in enumerate(partitions) for b in partitions[i+1:]):
        raise ValueError("split leakage")
    rows={o.id:o for o in data.observations}
    train=[rows[x] for x in split.train]
    calibration=[rows[x] for x in split.calibration]
    if not train:
        raise ValueError("no training rows after embargo")
    start=time.perf_counter()
    model=None if method=="engineering" else _fit_model(train,data.scenario,method,seed)
    return Predictor(data.scenario,split,method,model,train,calibration,seed,{},NUMERIC,time.perf_counter()-start)


def metrics(actual,predicted,lower=None,upper=None):
    if not len(actual):
        return {"mae":None,"rmse":None,"wape":None,"coverage":None,"interval_width":None}
    a,p=np.array(actual),np.array(predicted)
    result={"mae":float(np.mean(abs(a-p))),"rmse":float(np.sqrt(np.mean((a-p)**2))),"wape":float(np.sum(abs(a-p))/np.sum(a)) if np.sum(a)!=0 else None,"coverage":None,"interval_width":None}
    if lower is not None and all(x is not None for x in lower+upper):
        result.update(coverage=float(np.mean((a>=lower)&(a<=upper))),interval_width=float(np.mean(np.array(upper)-lower)))
    return result


def prediction_report(p,data):
    rows=[o for o in data.observations if o.id in p.split.test]
    start=time.perf_counter()
    results=p.predict([point_from_observation(o,data.scenario) for o in rows])
    supported=[(o,r) for o,r in zip(rows,results) if r.rate_kg_h is not None]
    report=metrics([o.fuel_mass_kg/o.duration_h for o,r in supported],[r.rate_kg_h for o,r in supported],[r.lower_kg_h for o,r in supported],[r.upper_kg_h for o,r in supported])
    report.update(test_count=len(rows),supported_count=len(supported),unsupported_count=len(rows)-len(supported),protocol=p.split.protocol,synthetic=data.scenario.synthetic,model_id=p.model_id,split_hash=p.split.hash,fit_seconds=p.fit_seconds,inference_seconds=time.perf_counter()-start,partition_counts={k:len(getattr(p.split,k)) for k in ("train","validation","calibration","test")},by_vessel_type={})
    for vt in {v.type for v in data.scenario.vessels}:
        ids={v.id for v in data.scenario.vessels if v.type==vt}
        subset=[(o,r) for o,r in supported if o.vessel_id in ids]
        report["by_vessel_type"][vt]={"count":len(subset),**metrics([o.fuel_mass_kg/o.duration_h for o,r in subset],[r.rate_kg_h for o,r in subset])}
    grid=[]
    for v in data.scenario.vessels:
        if not rows:
            continue
        template=point_from_observation(next(o for o in data.observations if o.vessel_id==v.id),data.scenario)
        values=p.predict([replace(template,speed_kn=float(speed)) for speed in np.linspace(v.min_speed_kn,v.max_speed_kn,5)])
        grid.extend(r.rate_kg_h for r in values if r.rate_kg_h is not None)
    report["plausibility"]={"negative_rates":sum(x<0 for x in grid),"grid_count":len(grid),"clamped_at_zero":sum(x==0 for x in grid),"note":"Predeclared five-speed grid; diagnostics, not proof of extrapolation validity."}
    return report
