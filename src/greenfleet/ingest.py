from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import types
from typing import get_args, get_origin, get_type_hints, Union

from .contracts import *


class BundleError(ValueError):
    def __init__(self, violations):
        self.violations = tuple(violations)
        super().__init__(", ".join(f"{v.code}: {'/'.join(v.entity_ids)}" for v in violations))


UNITS = {"fuel_mass": "kg", "duration": "h", "distance": "nm", "speed": "kn", "cargo": "t", "energy": "MJ", "electricity": "kWh", "emissions": "kg_CO2e", "price": "currency/kg"}


def _decode(kind, value):
    if value is None:
        return None
    origin, args = get_origin(kind), get_args(kind)
    if origin in (Union, types.UnionType):
        return _decode(next(a for a in args if a is not type(None)), value)
    if kind is datetime:
        return utc(value)
    if origin is tuple:
        return tuple(_decode(args[0] if len(args) == 2 and args[1] is Ellipsis else args[i], x) for i, x in enumerate(value))
    if origin is dict:
        return {k: _decode(args[1], v) for k, v in value.items()}
    if isinstance(kind, type) and issubclass(kind, Record):
        hints = get_type_hints(kind)
        unknown = set(value) - set(hints)
        if unknown:
            raise ValueError(f"unknown fields for {kind.__name__}: {sorted(unknown)}")
        return kind(**{k: _decode(hints[k], v) for k, v in value.items()})
    return value


def scenario_from_dict(value):
    return _decode(Scenario, value)


def validate_scenario(scenario: Scenario) -> list[Violation]:
    out = []
    def fail(code, *ids, value=None, limit=None, unit=None):
        out.append(Violation(code, tuple(ids), value, limit, unit))
    s = scenario
    if s.start >= s.end:
        fail("invalid_horizon", s.id)
    try:
        digest(s)
    except (ValueError, TypeError):
        fail("nonfinite_value", s.id)
    for table in (s.vessels,s.services,s.ports,s.pathways,s.rules,s.weather_cases):
        seen = set()
        for row in table:
            if row.id in seen:
                fail("duplicate_id", row.id)
            seen.add(row.id)
    ports = {p.id:p for p in s.ports}
    fuels = {f.id:f for f in s.pathways}
    for v in s.vessels:
        if v.initial_port not in ports or any(f not in fuels for f in v.tanks):
            fail("unknown_reference",v.id)
        if v.capacity_t <= 0 or v.draft_limit_m <= 0 or v.min_speed_kn <= 0 or v.max_speed_kn < v.min_speed_kn or min(v.auxiliary_kw,v.shore_acceptance_kw,v.hourly_cost) < 0 or (v.power_coefficient is not None and v.power_coefficient <= 0):
            fail("invalid_vessel",v.id)
        for f,t in v.tanks.items():
            if not 0 <= t.reserve_kg <= t.initial_kg <= t.capacity_kg:
                fail("invalid_tank",v.id,f)
        windows = sorted(v.maintenance)
        if any(a >= b for a,b in windows) or any(b > c for (_,b),(c,_) in zip(windows,windows[1:])):
            fail("overlapping_maintenance",v.id)
    for r in s.services:
        if r.origin not in ports or r.destination not in ports:
            fail("unknown_reference",r.id)
        if r.demand_t < 0:
            fail("negative_cargo",r.id)
        if r.demand_t == 0 or r.distance_nm <= 0 or r.release >= r.deadline or r.release < s.start or r.deadline > s.end or min(r.loading_h,r.unloading_h) < 0:
            fail("invalid_service",r.id)
    for p in s.ports:
        if any(f not in fuels for f in p.fuel_stock) or any(f not in fuels for _,f,_ in p.replenishments):
            fail("unknown_reference",p.id)
        values = list(p.fuel_stock.values()) + [q for _,_,q in p.replenishments] + [p.shore_kw,p.shore_sockets,p.pumps,p.port_fee,p.berths]
        values += [x for x in (p.grid_kg_kwh,p.tariff_kwh) if x is not None]
        values += list(p.hourly_grid.values()) + list(p.hourly_tariff.values())
        if any(x < 0 for x in values) or p.bunkering_kg_h <= 0 or p.draft_limit_m <= 0 or any(a >= b for a,b in p.berth_windows):
            fail("invalid_port",p.id)
    for f in s.pathways:
        if f.currency != s.currency or f.price_date != s.price_date:
            fail("currency_or_price_date_mismatch",f.id)
        if f.lhv_mj_kg <= 0 or any(x < 0 for x in (f.price_per_kg,f.wtw_g_mj,f.wtt_g_mj,f.ttw_g_mj) if x is not None):
            fail("invalid_factor",f.id)
    for e in s.engine_fuels:
        if e.pathway_id not in fuels or e.engine_id not in {v.engine_id for v in s.vessels}:
            fail("unknown_reference",e.engine_id,e.pathway_id)
        if not 0 < e.efficiency <= 1 or not 0 < e.auxiliary_efficiency <= 1:
            fail("invalid_efficiency",e.engine_id,e.pathway_id)
    if not s.weather_cases or s.weather_cases[0].time_multiplier != 1 or s.weather_cases[0].energy_multiplier != 1:
        fail("missing_nominal_weather",s.id)
    if not any(w.required for w in s.weather_cases):
        fail("missing_required_weather",s.id)
    if any(w.time_multiplier <= 0 or w.energy_multiplier <= 0 or w.probability < 0 for w in s.weather_cases):
        fail("invalid_weather",s.id)
    if s.inventory_cost not in ("initial_sunk","consumption"):
        fail("invalid_inventory_convention",s.id)
    if s.max_candidates < 1 or min(s.departure_step_h,s.speed_step_kn) <= 0 or not s.load_bands or any(not 0 < x <= 1 for x in s.load_bands) or any(x <= 0 for x in s.purchase_bands_kg):
        fail("invalid_candidate_settings",s.id)
    if len(s.weights) != 3 or len(s.normalization) != 3 or min(s.weights) < 0 or not math.isclose(sum(s.weights),1) or min(s.normalization) <= 0:
        fail("invalid_normalization",s.id)
    for r in s.rules:
        if r.severity not in ("hard","advisory") or r.threshold < 0:
            fail("invalid_rule",r.id)
    return out


def fingerprint_dataset(dataset: Dataset) -> str:
    return digest(dataset)


def load_bundle(path: Path, *, verify_digests=True) -> Dataset:
    path = Path(path)
    raw = json.loads((path / "bundle.json" if path.is_dir() else path).read_text(encoding="utf-8-sig"))
    return load_bundle_dict(raw, verify_digests=verify_digests)


def load_bundle_dict(raw, *, verify_digests=True):
    manifest = raw.get("manifest",{})
    problems = []
    required = ("schema_version","units","timezone","source","collection_interval","license","sensitivity","factor_dates","digests")
    for key in required:
        if key not in manifest:
            problems.append(Violation("missing_manifest_field",(key,)))
    if manifest.get("timezone") != "UTC" or manifest.get("schema_version") != 1:
        problems.append(Violation("invalid_manifest"))
    for key, unit in UNITS.items():
        actual = manifest.get("units",{}).get(key)
        if actual is None:
            problems.append(Violation("missing_unit",(key,)))
        elif actual != unit and not (key == "fuel_mass" and actual == "tonne"):
            problems.append(Violation("invalid_unit",(key,)))
    if problems:
        raise BundleError(problems)
    if verify_digests:
        for section in ("scenario","observations"):
            try:
                matches = manifest["digests"].get(section) == digest(raw[section])
            except (KeyError,ValueError,TypeError):
                matches = False
            if not matches:
                problems.append(Violation("digest_mismatch",(section,)))
    try:
        scenario = scenario_from_dict(raw["scenario"])
        problems.extend(validate_scenario(scenario))
    except (ValueError,TypeError,KeyError) as exc:
        raise BundleError(problems+[Violation("malformed_scenario",(str(exc),))]) from exc
    obs, quality, seen = [],[],set()
    vessel_map = {v.id:v for v in scenario.vessels}
    for row in raw.get("observations",[]):
        key = str(row.get("id","missing"))
        try:
            values = dict(row)
            values["fuel_mass_kg"] = values.pop("fuel_mass") * (1000 if manifest["units"]["fuel_mass"] == "tonne" else 1)
            o = _decode(VoyageObservation,values)
            if key in seen:
                problems.append(Violation("duplicate_id",(key,)))
            seen.add(key)
            if o.duration_h <= 0:
                problems.append(Violation("invalid_duration",(key,)))
            if o.cargo_t < 0:
                problems.append(Violation("negative_cargo",(key,)))
            if not math.isfinite(o.fuel_mass_kg) or min(o.fuel_mass_kg,o.distance_nm,o.auxiliary_kw) < 0:
                problems.append(Violation("invalid_measurement",(key,)))
            v = vessel_map.get(o.vessel_id)
            if v is None or o.pathway_id not in {f.id for f in scenario.pathways} or o.engine_id != v.engine_id:
                problems.append(Violation("unknown_reference",(key,)))
            elif not v.min_speed_kn <= o.speed_kn <= v.max_speed_kn or o.cargo_t > v.capacity_t or o.speed_basis not in ("through_water","over_ground"):
                problems.append(Violation("invalid_operating_point",(key,)))
            digest(o)
            if set(o.quality_flags) & {"engine_change","unresolved_multi_fuel"}:
                quality.append({"id":key,"excluded":True,"reason":list(o.quality_flags)})
            else:
                obs.append(o)
        except (ValueError,TypeError,KeyError) as exc:
            problems.append(Violation("malformed_observation",(key,str(exc))))
    if problems:
        raise BundleError(problems)
    return Dataset(scenario,tuple(obs),manifest,tuple(quality))


def demo_dataset() -> Dataset:
    start = datetime(2026,10,2,tzinfo=timezone.utc)
    fuel = FuelPathway("diesel","conventional","synthetic fixture",40,.8,80,"synthetic; not sourced marine data","demo-1")
    fleet = tuple(Vessel(f"V{i+1}","cargo",500+100*i,5,"demo-engine",{"diesel":Tank(10000,8000,100)},10,11,"A",start,.1+i*.005,10,50,power_source="synthetic cubic shaft curve") for i in range(8))
    ports = tuple(Port(x,12,{"diesel":100000},berth_windows=((start,start+timedelta(days=7)),)) for x in ("A","B"))
    services = (ServiceRequest("S1","A","B",40,300,start,start+timedelta(hours=10)),ServiceRequest("S2","B","A",40,300,start+timedelta(hours=12),start+timedelta(hours=24)))
    s = Scenario("synthetic-demo",start,start+timedelta(days=7),fleet,services,ports,(fuel,),(EngineFuel("demo-engine","diesel",.4,.4,"synthetic efficiency"),),(WeatherCase("nominal",probability=.8),WeatherCase("adverse",1.2,1.15,.2)),routes_nm={"A>B":40,"B>A":40})
    observations=[]
    for v in fleet:
        for j in range(32):
            speed=10+.5*(j%3)
            rate=(v.power_coefficient*speed**3+v.auxiliary_kw)*3.6/.4/40
            observations.append(VoyageObservation(f"{v.id}-{j}",v.id,f"voyage-{v.id}-{j}",start-timedelta(days=40)+timedelta(days=j),4,speed*4,speed,300,1000 if len(observations)==0 else rate*4*(1+.01*(j%4)),"diesel",v.engine_id,wave_m=float(j%3),wind_kn=float(j%5),auxiliary_kw=v.auxiliary_kw))
    manifest={"schema_version":1,"units":UNITS,"timezone":"UTC","source":"deterministic synthetic generator v1","collection_interval":[observations[0].timestamp.isoformat(),observations[-1].timestamp.isoformat()],"license":"CC0 synthetic fixture","sensitivity":"public synthetic","factor_dates":[s.price_date],"digests":{}}
    return Dataset(s,tuple(observations),manifest)


def write_demo_bundle(path: Path) -> Path:
    path=Path(path)
    path.mkdir(parents=True,exist_ok=True)
    d=demo_dataset()
    raw=primitive(d)
    raw.pop("quality_report")
    raw["manifest"]["units"]["fuel_mass"]="tonne"
    for row in raw["observations"]:
        row["fuel_mass"]=row.pop("fuel_mass_kg")/1000
    raw["manifest"]["digests"]={k:digest(raw[k]) for k in ("scenario","observations")}
    target=path/"bundle.json"
    target.write_text(json.dumps(raw,indent=2,allow_nan=False),encoding="utf-8")
    return target
