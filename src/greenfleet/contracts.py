from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from typing import Literal

RunStatus = Literal["completed", "infeasible_proven", "no_feasible_solution_found", "cancelled", "failed"]
ComplianceStatus = Literal["compliant", "noncompliant", "unknown"]
SupportStatus = Literal["supported", "engineering_only", "unsupported"]


class FrozenDict(dict):
    def _deny(self, *args, **kwargs):
        raise TypeError("immutable mapping")
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _deny

    def __deepcopy__(self, memo):
        return self


def freeze(value):
    if isinstance(value, dict):
        return FrozenDict({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


class Record:
    def __post_init__(self):
        for f in fields(self):
            object.__setattr__(self, f.name, freeze(getattr(self, f.name)))


def primitive(value):
    if is_dataclass(value):
        return {f.name: primitive(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(x) for x in value]
    return value


def digest(value) -> str:
    return sha256(json.dumps(primitive(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError("timestamp must explicitly use UTC")
    return dt.astimezone(timezone.utc)


def hours(start, end):
    return (end - start).total_seconds() / 3600


@dataclass(frozen=True)
class Tank(Record):
    capacity_kg: float
    initial_kg: float
    reserve_kg: float = 0


@dataclass(frozen=True)
class Vessel(Record):
    id: str
    type: str
    capacity_t: float
    draft_limit_m: float
    engine_id: str
    tanks: dict[str, Tank]
    min_speed_kn: float
    max_speed_kn: float
    initial_port: str
    initial_time: datetime
    power_coefficient: float | None = None
    auxiliary_kw: float = 0
    shore_acceptance_kw: float = 0
    hourly_cost: float = 0
    maintenance: tuple[tuple[datetime, datetime], ...] = ()
    power_source: str = ""


@dataclass(frozen=True)
class EngineFuel(Record):
    engine_id: str
    pathway_id: str
    efficiency: float
    auxiliary_efficiency: float
    source: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    auxiliary_compatible: bool = True


@dataclass(frozen=True)
class VoyageObservation(Record):
    id: str
    vessel_id: str
    voyage_id: str
    timestamp: datetime
    duration_h: float
    distance_nm: float
    speed_kn: float
    cargo_t: float
    fuel_mass_kg: float
    pathway_id: str
    engine_id: str
    speed_basis: str = "through_water"
    wave_m: float | None = 0
    wind_kn: float | None = 0
    auxiliary_kw: float = 0
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceRequest(Record):
    id: str
    origin: str
    destination: str
    distance_nm: float
    demand_t: float
    release: datetime
    deadline: datetime
    loading_h: float = 1
    unloading_h: float = 1
    allow_split: bool = False


@dataclass(frozen=True)
class Port(Record):
    id: str
    draft_limit_m: float
    fuel_stock: dict[str, float]
    bunkering_kg_h: float = 1000
    pumps: int = 1
    shore_sockets: int = 1
    shore_kw: float = 100
    grid_kg_kwh: float | None = .5
    tariff_kwh: float | None = .1
    berth_windows: tuple[tuple[datetime, datetime], ...] = ()
    replenishments: tuple[tuple[datetime, str, float], ...] = ()
    hourly_grid: dict[str, float] = field(default_factory=dict)
    hourly_tariff: dict[str, float] = field(default_factory=dict)
    grid_source: str = "synthetic demo-1"
    port_fee: float = 0
    berths: int = 10


@dataclass(frozen=True)
class FuelPathway(Record):
    id: str
    fuel_name: str
    production_route: str
    lhv_mj_kg: float
    price_per_kg: float | None
    wtw_g_mj: float | None
    source: str
    version: str
    currency: str = "USD"
    price_date: str = "2026-10-02"
    wtt_g_mj: float | None = None
    ttw_g_mj: float | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    jurisdiction: str = "synthetic"
    gwp: str = "synthetic fixture; no certified GWP"
    component_gases: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Rule(Record):
    id: str
    jurisdiction: str
    version: str
    metric: str
    unit: str
    threshold: float
    source: str
    severity: str = "hard"
    vessel_ids: tuple[str, ...] = ()
    pathway_ids: tuple[str, ...] = ()
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    applicability_known: bool = True


@dataclass(frozen=True)
class WeatherCase(Record):
    id: str
    time_multiplier: float = 1
    energy_multiplier: float = 1
    probability: float = 1
    required: bool = True
    provenance: str = "synthetic illustration"


@dataclass(frozen=True)
class Scenario(Record):
    id: str
    start: datetime
    end: datetime
    vessels: tuple[Vessel, ...]
    services: tuple[ServiceRequest, ...]
    ports: tuple[Port, ...]
    pathways: tuple[FuelPathway, ...]
    engine_fuels: tuple[EngineFuel, ...]
    weather_cases: tuple[WeatherCase, ...]
    rules: tuple[Rule, ...] = ()
    synthetic: bool = True
    currency: str = "USD"
    price_date: str = "2026-10-02"
    factor_version: str = "demo-1"
    rule_coverage_known: bool = False
    require_certified_compliance: bool = False
    inventory_cost: str = "initial_sunk"
    max_candidates: int = 2000
    departure_step_h: float = 2
    speed_step_kn: float = .5
    load_bands: tuple[float, ...] = (.5, 1)
    purchase_bands_kg: tuple[float, ...] = (100, 500)
    routes_nm: dict[str, float] = field(default_factory=dict)
    shore_enabled: bool = True
    normalization: tuple[float, float, float] = (1000000, 100000, 100000)
    weights: tuple[float, float, float] = (1/3, 1/3, 1/3)


@dataclass(frozen=True)
class Dataset(Record):
    scenario: Scenario
    observations: tuple[VoyageObservation, ...]
    manifest: dict
    quality_report: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Prediction(Record):
    rate_kg_h: float | None
    lower_kg_h: float | None
    upper_kg_h: float | None
    support_status: SupportStatus
    model_id: str

    def __post_init__(self):
        super().__post_init__()
        if self.support_status not in ("supported", "engineering_only", "unsupported"):
            raise ValueError("invalid support status")


@dataclass(frozen=True)
class Totals(Record):
    energy_mj: float = 0
    cost: float = 0
    emissions_kg_co2e: float = 0
    fuel_kg_by_pathway: dict[str, float] = field(default_factory=dict)
    electricity_kwh: float = 0

    @property
    def objectives(self):
        return (self.energy_mj, self.cost, self.emissions_kg_co2e)


@dataclass(frozen=True)
class Violation(Record):
    code: str
    entity_ids: tuple[str, ...] = ()
    observed: float | None = None
    limit: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class Candidate(Record):
    id: str
    vessel_id: str
    kind: str
    origin: str
    destination: str
    pathway_id: str
    start: datetime
    service_id: str | None = None
    speed_kn: float = 0
    distance_nm: float = 0
    cargo_t: float = 0
    loading_h: float = 0
    unloading_h: float = 0
    shore_kw: float = 0
    purchase_kg: float = 0
    duration_h: float = 0
    prediction: Prediction | None = None

    def end(self, case: WeatherCase | None = None):
        transit = self.distance_nm / self.speed_kn if self.speed_kn > 0 else 0
        return self.start + timedelta(hours=self.loading_h + self.unloading_h + self.duration_h + transit * (case.time_multiplier if case else 1))


@dataclass(frozen=True)
class CandidateSet(Record):
    items: tuple[Candidate, ...]
    complete: bool = True
    candidate_limit_reached: bool = False
    exclusions: dict[str, int] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    model_id: str = "engineering"
    scenario_hash: str = ""

    @property
    def hash(self):
        return digest(self)


@dataclass(frozen=True)
class Plan(Record):
    selected: tuple[Candidate, ...]
    provenance: dict = field(default_factory=dict)

    @property
    def hash(self):
        return digest(tuple(sorted(self.selected, key=lambda c: c.id)))


@dataclass(frozen=True)
class CandidateEstimate(Record):
    eligible: bool
    nominal: Totals
    cases: dict[str, Totals]
    exclusions: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlanEvaluation(Record):
    nominal: Totals
    cases: dict[str, Totals]
    consumption_cost: float
    purchase_cost: float
    rule_results: tuple[dict, ...]
    compliance_status: ComplianceStatus
    exclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchConfig(Record):
    budget: int = 128
    seed: int = 17
    population_size: int = 16
    timeout_s: float | None = None
    rotation: float = .08
    epsilon: float = .02
    reset_interval: int = 10
    reset_fraction: float = .1

    def __post_init__(self):
        super().__post_init__()
        if self.budget < 1 or self.population_size < 2 or not 0 < self.epsilon < math.pi/4 or self.rotation <= 0 or not 0 <= self.reset_fraction <= 1 or self.reset_interval < 1 or (self.timeout_s is not None and self.timeout_s <= 0):
            raise ValueError("invalid search configuration")


@dataclass(frozen=True)
class RunConfig(Record):
    method: str = "greedy"
    search: SearchConfig = field(default_factory=SearchConfig)


@dataclass(frozen=True)
class RunResult(Record):
    status: RunStatus
    plans: tuple[Plan, ...]
    violations: tuple[Violation, ...]
    compliance_status: ComplianceStatus
    metadata: dict

    def __post_init__(self):
        super().__post_init__()
        if self.status not in ("completed", "infeasible_proven", "no_feasible_solution_found", "cancelled", "failed"):
            raise ValueError("invalid run status")
        if self.compliance_status not in ("compliant", "noncompliant", "unknown"):
            raise ValueError("invalid compliance status")
