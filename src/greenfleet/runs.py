from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json
import os
import traceback
from .contracts import *
from .ingest import validate_scenario,fingerprint_dataset
from .candidates import build_candidates
from .solvers import solve
from .feasibility import validate_plan
from .accounting import evaluate_plan


def atomic_write(path,content):
    path=Path(path)
    temp=path.with_name(path.name+"."+uuid4().hex+".tmp")
    try:
        with temp.open("xb") as f:
            f.write(content.encode("utf-8") if isinstance(content,str) else content)
            f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_json(path,value):
    atomic_write(path,json.dumps(primitive(value),indent=2,allow_nan=False))


def execute_run(scenario,config,output_dir,*,cancel=None,progress=None,dataset=None):
    run_id="run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid4().hex
    root=Path(output_dir)/run_id
    root.mkdir(parents=True,exist_ok=False)
    started=perf_counter()
    from .benchmarks import hardware_manifest
    base={"run_id":run_id,"created_utc":datetime.now(timezone.utc).isoformat(),"scenario":primitive(scenario),"scenario_hash":digest(scenario),"dataset_hash":fingerprint_dataset(dataset) if dataset is not None else digest(scenario),"dataset_hash_scope":"bundle" if dataset is not None else "scenario only; no observations used","factor_hash":digest((scenario.pathways,scenario.engine_fuels,scenario.ports)),"rule_hash":digest(scenario.rules),"config":primitive(config),"synthetic":scenario.synthetic,"hardware":hardware_manifest(),"normalization":scenario.normalization,"weights":scenario.weights,"warnings":["Synthetic data and physical coefficients; not operational advice."] if scenario.synthetic else []}
    atomic_json(root/"manifest.json",base)
    result=None
    try:
        if cancel and cancel():
            raise InterruptedError("cancelled before execution")
        violations=validate_scenario(scenario)
        if violations:
            result=RunResult("failed",(),tuple(violations),"unknown",{"error":"invalid scenario"})
        else:
            predictor=None;split_hash=None
            fit_start=perf_counter()
            if config.predictor_method!="engineering":
                if dataset is None:
                    raise ValueError("a measured or labelled synthetic dataset is required for ML prediction")
                from .splits import make_splits
                from .predict import fit_predictor
                dataset=replace(dataset,scenario=scenario)
                split=make_splits(dataset,config.split_protocol,config.search.seed)
                predictor=fit_predictor(dataset,split,config.predictor_method,config.fit_budget,config.search.seed)
                split_hash=split.hash
                atomic_json(root/"split.json",split)
            fit_s=perf_counter()-fit_start
            gen_start=perf_counter()
            candidates=build_candidates(scenario,predictor,cancel)
            generation_s=perf_counter()-gen_start
            result=solve(scenario,candidates,config.method,config.search,cancel,progress)
            if cancel and cancel():
                raise InterruptedError("cancelled during execution")
            if result.status=="completed":
                final=[v for p in result.plans for v in validate_plan(p,scenario,candidates)]
                if final:
                    result=RunResult("failed",(),tuple(final),"unknown",{**result.metadata,"error":"final independent validation failed"})
            result=replace(result,metadata={**result.metadata,"split_hash":split_hash,"predictor_method":config.predictor_method,"fit_seconds":fit_s,"fit_count":getattr(predictor,"fit_count",0),"candidate_generation_s":generation_s,"model_id":getattr(predictor,"model_id",digest((scenario.vessels,scenario.engine_fuels,scenario.pathways))),"evaluations_by_plan":{p.hash:primitive(evaluate_plan(p,scenario)) for p in result.plans}})
    except InterruptedError as exc:
        result=RunResult("cancelled",(),(),"unknown",{"error":str(exc)})
    except Exception as exc:
        atomic_write(root/"error.log",traceback.format_exc())
        result=RunResult("failed",(),(),"unknown",{"error":f"{type(exc).__name__}: {exc}"})
    result=replace(result,metadata={**base,**result.metadata,"run_id":run_id,"end_to_end_s":perf_counter()-started,"output_directory":str(root.resolve())})
    atomic_json(root/"result.json",result)
    atomic_write(root/"run.log",f"status={result.status}\ncompliance={result.compliance_status}\nerror={result.metadata.get('error','')}\nevaluations={result.metadata.get('evaluations',0)}\n")
    return result
