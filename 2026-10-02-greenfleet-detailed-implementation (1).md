# GreenFleet Detailed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible decision-support prototype that predicts vessel fuel use and produces operationally feasible, auditable seven-day fleet plans with energy, cost, and lifecycle-emissions trade-offs.

**Architecture:** A typed Python domain layer owns validation, prediction, accounting, scheduling, and independent plan verification. Conventional and quantum-inspired methods call the same scenario evaluator. A thin Streamlit interface invokes that layer, persists immutable run artifacts, and presents supported decisions and unknowns explicitly.

**Tech Stack:** Proposed Python 3.11+, pandas, NumPy, scikit-learn, SciPy, pymoo, Streamlit, Plotly, pytest; Parquet and JSON. Pin tested versions and lock dependencies during Task 1. No quantum hardware or cloud service is required.

**Spec:** Original Problem Statement 26138 in `Pasted markdown.md`, reviewed proposal in `Pasted text.txt`, and the prior [implementation plan](2026-10-02-green-fleet-implementation-plan.md). This document incorporates the six corrections from the review. The original brief requests prediction, quantum-inspired optimization, alternative fuels and shore power, demand and schedule reliability, lifecycle emissions, regulation, benchmarks, case studies, and a delivery table.

## Global Constraints

- Distinguish source requirements from proposed prototype choices. Seven days, a 0.5-knot speed grid, 5–20 ships, 3–10 requests, eight weeks, and three contributors are planning assumptions; confirm them with the project owner.
- Fixed routes and fixed physical vessel capacities. Select capacity by assigning suitable vessels; no purchase, retrofit, unrestricted ocean routing, or live operational control in the prototype.
- Use UTC, nautical miles, knots, hours, kg, MJ, kWh, kg CO2e, cargo tonnes, and one configured currency and price date. Reject missing units and currency mismatches.
- Measured fuel records are necessary for empirical prediction claims. Synthetic records may demonstrate software behavior, never real-world accuracy or savings.
- Describe the predictor precisely as a **classical regression model with quantum-inspired tuning**. Confirm at the week-1 gate that this interpretation meets the sponsor's “quantum-inspired prediction” requirement; if it does not, define a separate predictive-model experiment and re-estimate scope.
- Within each optimization comparison, algorithms use the same predictor, candidate universe, fuel accounting and feasibility checker, with matched evaluation budgets. Predictor ablations change the estimates deliberately and are reported separately. Report negative results.
- Rules are scoped and versioned. Missing applicable rules yield compliance `unknown`; missing mandatory cost or lifecycle factors block that candidate from comparison. Neither condition is silently treated as zero.
- A heuristic failure proves nothing about mathematical feasibility. Only a sound structural witness or a complete exact search over an unpruned scenario may set run status `infeasible_proven`.

## Review Focus

1. A later trip must inherit the vessel's location, available time, and remaining onboard fuel after the earlier trip — test in Task 4.
2. Simultaneous users of one port must not exceed its aggregate fuel stock or shore-power connections — test in Task 4.
3. A capped or pruned candidate universe must not justify a whole-scenario infeasibility claim — test in Task 5.
4. Known-vessel future prediction and unseen-vessel prediction must have separate disjoint split manifests — test in Task 2.
5. Unknown regulatory coverage, unsupported predictions, and failed search must not collapse into one status — test in Tasks 1 and 8.

---

## 1. Proposed repository and ownership

No application repository was supplied. The following paths are a proposed new project, not claims about files already present. Start from the initial conventional path so each task ends in usable software.

```text
greenfleet/
  pyproject.toml
  configs/demo.yaml
  src/greenfleet/
    contracts.py       # typed records, units, statuses
    ingest.py          # CSV/Parquet loading, provenance, validation
    splits.py          # grouped time splits and manifest
    predict.py         # engineering/direct/hybrid models and intervals
    pathways.py        # fuel compatibility, provenance and factors
    accounting.py      # trip fuel, energy, cost and CO2e
    candidates.py      # bounded trip/reposition/shore options
    feasibility.py     # independent path, cargo, stock and rule checks
    qie.py             # reusable bit-amplitude optimizer
    solvers.py         # greedy, exact tiny case, ALNS, NSGA-II, QIE
    benchmarks.py      # paired experiments and metrics
    runs.py            # immutable run IDs, execution and cancellation
    reporting.py       # CSV/JSON/Markdown export
  app.py               # Streamlit orchestration only
  tests/               # one test module per responsibility
  docs/model-card.md
  docs/data-dictionary.md
  docs/case-study.md
  docs/user-guide.md
```

Do not put optimization calculations in Streamlit callbacks. Use Python entry points so tests, CLI benchmarks, and UI execute the same engine. Keep model files and run outputs outside source control; commit a small deterministic demonstration dataset and configuration only when license and sensitivity permit it.

## 2. Contracts, data shape, and validation

Use frozen typed records in `contracts.py`; data frames may be used at ingestion/training boundaries. The domain API uses explicit fields rather than positional tuples.

| Record | Required fields and semantics |
|---|---|
| `Vessel` | `id`, `type`, `capacity_t`, `draft_limit_m`, `engine_id`, `fuel_tanks` mapping fuel to capacity/current mass kg, speed bounds knots, initial port/time, maintenance windows, auxiliary power profile |
| `EngineFuel` | `(engine_id, pathway_id)` compatibility, efficiency curve keyed by load/speed or documented constant, auxiliary compatibility, source and validity |
| `VoyageObservation` | ID, vessel/voyage IDs, timestamp, duration h, distance nm, speed basis, cargo t/draft, measured kg by fuel, sea features and quality flags |
| `ServiceRequest` | ID, origin/destination, route distance nm, demand t, release/deadline UTC, loading/unloading times h, allowed splitting flag; default `false` |
| `Port` | ID, berth windows, draft limit, fuel inventories and replenishment events by pathway, bunkering rates, shore-power sockets/kW and hourly grid factor/tariff |
| `FuelPathway` | ID, fuel name, production route, LHV MJ/kg, WtT and TtW factor provenance or a single WtW factor, compatible engines, price/kg, factor version and valid dates |
| `Rule` | ID, jurisdiction, vessel/voyage/fuel applicability, effective interval, exact metric/units and threshold, authoritative source, severity hard/advisory |
| `WeatherCase` | ID, probability for reporting, route/time-dependent transit-time multiplier and energy multiplier, provenance; a conservative feasibility case is identified separately |
| `Scenario` | horizon, requests, fleet, ports, pathways, rules, weather cases, candidate settings, price date, currency and factor version |
| `Candidate` | immutable vessel/service/pathway, cargo, departure/arrival/port intervals, speed, route, reposition link, shore-power option, per-case resource and accounting estimates |
| `Plan` | selected candidates, ordered vessel paths, refuelling transactions, berth/shore reservations, cargo allocation and provenance hashes |

Additional result types:

```python
RunStatus = Literal[
    "completed", "infeasible_proven", "no_feasible_solution_found",
    "cancelled", "failed",
]
ComplianceStatus = Literal["compliant", "noncompliant", "unknown"]
SupportStatus = Literal["supported", "engineering_only", "unsupported"]

@dataclass(frozen=True)
class Prediction:
    rate_kg_h: float | None
    lower_kg_h: float | None
    upper_kg_h: float | None
    support_status: SupportStatus
    model_id: str

@dataclass(frozen=True)
class Totals:
    energy_mj: float
    cost: float
    emissions_kg_co2e: float
    fuel_kg_by_pathway: dict[str, float]
    electricity_kwh: float

@dataclass(frozen=True)
class Violation:
    code: str
    entity_ids: tuple[str, ...]
    observed: float | None
    limit: float | None
    unit: str | None

@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    plans: tuple[Plan, ...]
    violations: tuple[Violation, ...]
    compliance_status: ComplianceStatus
    metadata: dict[str, object]
```

The actual implementations can add fields; do not remove these meanings. `completed` means at least one independently feasible plan was found and the search completed under its specified stopping rule, not that global optimality was proven. A plan can be `completed` while compliance is `unknown`; label that result “operationally feasible under configured constraints; compliance unverified.” Hard rules with known values must be enforced; if a scenario requires certified compliance and applicability is unknown, withhold a recommendation and show the missing rules.

Input format: `vessels.csv`, `observations.parquet`, `services.csv`, `ports.csv`, `pathways.csv`, `engine_fuels.csv`, `rules.json`, `scenario.json` or equivalent tables in one upload bundle. Each bundle includes `manifest.json` listing schema version, units by column, timezone, source, data-collection interval, license/sensitivity classification, factor dates, and SHA-256 digests. Ingestion creates an immutable normalized copy plus row-level quality report. Reject duplicate IDs, negative mass/cost, zero/negative duration, impossible speed or tank states, invalid factor units, malformed timestamps, unknown references, and overlapping maintenance availability. A value may be missing only when its field is explicitly optional. Never infer a missing fuel unit.

For real operating data, remove credentials and unnecessary personal information before upload; keep run artifacts local to the prototype environment. Report how many observations are excluded and why. A selected factor's value, units, source, pathway, jurisdiction, and date must travel into every exported run. Prefer measured flowmeter consumption with propulsion and auxiliary consumers identified; preserve engine state and cleaning/maintenance dates when available. Align weather to voyage position/time without using future observations at inference. A public three-vessel dataset such as FuelCast can exercise the prediction pipeline, but its passenger/offshore vessels do not validate claims about cargo fleets; check its license and target definition before use.

Core functions:

```python
load_bundle(path: Path) -> Dataset
validate_scenario(scenario: Scenario) -> list[Violation]
fingerprint_dataset(dataset: Dataset) -> str
```

## 3. Prediction design and experimental splits

The measured target for an observed vessel/engine/fuel is `fuel_mass_kg / duration_h`. Exclude records with engine changes or unresolved multi-fuel attribution. Describe whether speed is through water or over ground; do not mix them as the same feature. Standard features are vessel type/capacity, engine, cargo/draft, speed, wind/wave/current when present, and auxiliary load. Fit imputation and encoding inside each training fold, with a missingness indicator for optional fields. Sample weights may reflect duration, but fix them before benchmarking.

Implement and compare:

1. Engineering baseline: documented useful-energy versus speed/load relation calibrated only on training data where calibration is used. Keep propulsion and hotel load separate.
2. Conventional histogram gradient boosting predicting measured fuel rate directly, with a fixed and documented search space and validation budget.
3. Physics-based shaft-power or input-energy curve plus a GBM residual correction using weather, draft and condition features. Obtain vessel/engine coefficients from documented sea-trial or training-only measurements; if these are absent, fit a constrained training-only curve and flag weaker physical provenance. Convert power to fuel using a validated engine/fuel map, never a guessed universal efficiency. Test plausibility across the speed/draft grid. Use this as the preferred *candidate* model, subject to held-out decision and prediction tests.
4. QIE-tuned versions of the best eligible direct and/or hybrid model in the same discrete tuning space. Label the method “QIE-tuned classical model.” Confirm this definition with the sponsor at the data gate.

Use two evaluations. **Temporal known-vessel:** for each eligible vessel, earlier complete voyages go to training, subsequent voyages to calibration/test, with no voyage ID shared and an embargo if adjacent aggregates overlap. **Unseen-vessel:** hold out complete vessel IDs, separately choose training/validation/calibration vessels, and evaluate on the held-out vessels only. Nested selection occurs inside the development partition; final test IDs never enter feature choice, imputation, tuning, interval calibration, or early stopping. Save explicit row/voyage/vessel IDs and time ranges in each split manifest. Report sample counts and applicability separately rather than averaging the two evaluations into one score.

Use a disjoint calibration set for residual-based prediction intervals. Define empirical coverage as the fraction of measured targets between interval endpoints, alongside interval width; stratify by vessel class when sample sizes permit and state when insufficient. Clamp impossible negative rate estimates to zero and record this transformation. Support checks compare fuel/engine compatibility, speed/load limits, categorical features, and documented range of sea states before inference. A speed outside validated bounds is `unsupported`, with no numeric ML estimate used for optimization. `engineering_only` uses a separately sourced, explicitly labelled model, especially for unobserved alternative fuels; exclude the pathway when engine efficiency or LHV is unavailable. Model uncertainty intervals do not by themselves prove robust feasibility.

Metrics: MAE, RMSE, WAPE `sum(abs(error)) / sum(actual)` with undefined WAPE if denominator is zero, coverage/width, training and inference duration. Report values by vessel type and operating regime with counts. Add a power/speed/draft plausibility diagnostic on a predeclared grid; low MAE cannot excuse physically implausible extrapolation. Compare the QIE tuner against fixed conventional tuning and random search under the same **number of model fits**, then report runtime separately. Time-lag and sequence models are an optional experiment only if high-frequency data and inference-time history exist; they are not the default for a voyage request with only planned inputs.

```python
make_splits(data: Dataset, protocol: Literal["future", "unseen_vessel"], seed: int) -> SplitManifest
fit_predictor(data: Dataset, split: SplitManifest, method: str, budget: int, seed: int) -> Predictor
Predictor.predict(points: list[OperatingPoint]) -> list[Prediction]
```

## 4. Accounting and robust trip estimates

For a transit option, establish estimated useful propulsion energy from the observed known-fuel model plus documented engine conversion, or directly from an engineering power curve. Under pathway `f`, compute required input energy `E_f = E_useful / efficiency(engine,f,load,speed)` and mass `m_f = E_f / LHV_f`. If a measured rate already represents **input fuel mass** for the same engine/fuel, calculate `m_f = rate_kg_h × duration_h` directly; do not divide by efficiency a second time. Auxiliary fuel uses its own load/efficiency. Shore electricity replaces the documented fraction of auxiliary demand at berth, bounded by socket kW × connection hours and vessel acceptance kW; it does not displace propulsion demand at sea.

`E_input = Σ_f m_f × LHV_f + 3.6 × electricity_kwh` in MJ. Distinguish grid energy from bunker energy in exports. `GHG = Σ_f E_f × WtW_f / 1000 + Σ_t electricity_kwh,t × grid_kg_co2e_per_kwh,t` when the fuel factor is g CO2e/MJ. If WtT and TtW are supplied separately, sum those once; if WtW is supplied, use it directly. Preserve component gases and the documented GWP convention in provenance. `Cost = Σ_f m_f × price_f + Σ_t kWh_t × tariff_t + charter_hours × hourly_rate + port_fees + applicable_configured_charges`. Account for consumed fuel and purchased fuel separately: fuel purchase costs may occur at bunkering while voyage consumption drives energy/emissions; ensure a scenario's total financial cost counts the intended inventory treatment once. For the MVP, set initial fuel inventory at a documented acquisition cost, or treat it as a sunk resource and report purchases and consumption cost separately. Choose and freeze one method in `scenario.json`.

Robust checks use explicit cases, for example nominal and a conservative adverse-weather case with documented time/energy multipliers; these are illustrative scenario parameters, not real forecasts. Require every selected transit to arrive before its deadline and retain its fuel reserve in the conservative case. ML upper intervals may enlarge the fuel estimate only where calibrated; engineering-only options use a separately declared reserve margin. Show nominal and conservative totals, and identify the case that binds. Do not call an interval a guarantee.

```python
evaluate_candidate(candidate: Candidate, scenario: Scenario, predictor: Predictor) -> CandidateEstimate
evaluate_plan(plan: Plan, scenario: Scenario) -> PlanEvaluation
```

Hand checks: 1000 MJ at 80 g CO2e/MJ equals 80 kg CO2e; 10 kWh at 0.5 kg CO2e/kWh equals 5 kg; shore energy displaces auxiliary input once; a WtW factor never has WtT added again. These numbers are test fixtures only, not marine pathway factors.

## 5. Candidate generation and the scheduling model

First filter incompatible vessel/route/port/pathway combinations. Generate feasible discrete speed values within each vessel's validated interval at 0.5 knots, and departure slots on a configured grid (proposed 2 hours) plus exact release/closing boundaries. Cargo allocation defaults to one request per voyage without splitting; where `allow_split=true`, use configured load bands and cap total delivered cargo at the demand to avoid phantom overdelivery. Generate an explicit empty repositioning leg when a vessel must travel between ports, using the same fuel/weather accounting. Include fuel purchase and shore reservations as choices with quantities/times; do not hide their state inside a trip's independent score.

Prune only with documented **safe** conditions: incompatible engine/fuel, draft/capacity violation, departure outside horizon, arrival later than deadline even at maximum valid speed and best-case conditions, or a port with no supported pathway. Do not discard an option solely because it currently appears expensive; Pareto results may need it. Deduplicate identical states and retain stable candidate IDs. Log pre/post-filter counts by reason. The budget is `max_candidates` (proposed 200,000); if reached, return `candidate_limit_reached` in metadata and require explicit scenario narrowing or a separate approximate sampled mode. Any result from sampled mode is labelled approximate, and it cannot prove global infeasibility or completeness of a Pareto frontier.

Use a time-expanded directed graph per vessel. Nodes encode `(port, discretized time, onboard fuel state or linked continuous inventory variables)`; arcs are sailing service options, repositioning, waiting, bunkering, and berth actions. One unit of flow starts at each vessel's initial port/time and follows a valid path through the horizon. A ship may remain unused. Service selection variables `x_o ∈ {0,1}` correspond to selected service arcs; each unsplittable request has exactly one selected service arc with enough capacity, while split requests sum delivered tonnes to exactly their demand. Flow conservation, arc time intervals and vessel maintenance ensure sequence and no overlap. The independent checker reconstructs ordered physical paths from exported choices without relying on solver internals. If the selected operating area crosses distinct emissions zones, split a route at the boundary and check the applicable rule and allowed fuel choice on each sub-leg; defer arbitrary route geometry and fuel mixing until reliable segment data exists.

Fuel inventory per vessel/pathway at each selected event follows `I_after = I_before + purchase_kg - consumption_kg`, with `reserve_kg ≤ I_after ≤ tank_capacity_kg` in every conservative weather case. A fuel switch is allowed only if the vessel has compatible tanks/engine and a recorded changeover action. Each port/pathway's sum of purchases up to any replenishment event stays within available stock; its bunkering pumps/rates must cover simultaneous purchases. At each time interval, shore reservations must satisfy both sockets/connections and aggregate kW. Port service must fit opening and berth windows. Weather-case transit duration controls subsequent arrival and availability; a single robust sequence must remain feasible under all configured required cases, with waiting allowed after early arrival.

The three objectives are `min(energy_mj, operating_cost, lifecycle_kg_co2e)` over selected transit, hotel and reposition arcs and fuel/shore actions. Report mass kg separately by pathway because cross-fuel masses are not directly comparable. A conventional-fuel-only benchmark may minimize kg for a same-fuel case. Compute a Pareto archive after independent validation. Choose the “balanced” point by fixed, visible normalized bounds and user weights summing to one; record the chosen bounds and weights in each export. A changed normalization requires a new run manifest.

Use exact enumeration only for a deliberately tiny, fully enumerated fixture (e.g. ≤20 choice bits) to verify the frontier. Larger exact proof, if attempted, requires a formal complete solver/certificate; absent that, `no_feasible_solution_found` is the correct outcome when searches exhaust their budgets. A structural witness such as a request with demand above every compatible available ship's capacity **when splitting is forbidden** may prove infeasibility independently of candidate pruning. Check the witness against all scenario eligibility conditions before reporting it.

```python
build_candidates(scenario: Scenario, predictor: Predictor) -> CandidateSet
validate_plan(plan: Plan, scenario: Scenario, candidates: CandidateSet) -> list[Violation]
prove_simple_infeasibility(scenario: Scenario) -> Proof | None
solve(scenario: Scenario, candidates: CandidateSet, method: str, config: SearchConfig) -> RunResult
```

## 6. QIE search and baselines

Baseline order: constraint-aware greedy insertion, exhaustive tiny fixture, then **adaptive large-neighborhood search (ALNS)** as a domain-specific conventional comparator, NSGA-II and QIE using the same decode/repair/evaluate contract. Greedy does not claim optimality. ALNS repeatedly removes a set of service/fuel/shore choices and reinserts them while maintaining vessel paths, fuel inventory and port capacity; include random, worst-cost and related-request removal and greedy/regret insertion. Keep a Pareto archive across scalarized or ε-constrained ALNS runs using predeclared weights/thresholds. This is a proposed adaptation of published single-objective fleet ALNS, not a directly reproduced multi-objective result. The QIE encoding contains candidate selection bits plus discrete bunkering/shore-action choices; if the resulting state is invalid, deterministic repair removes conflicts, connects reachable repositioning paths, adds missing cargo where possible, and records remaining violations. Repair must not add choices outside the fixed candidate universe. All actual evaluations and repair calls count toward logged work; equal evaluation budget means equal calls to the shared plan evaluator. Also run a separate wall-clock-matched comparison.

QIE stores θ for each bit and samples `bit_i ∼ Bernoulli(sin²θ_i)`. Initialize θ to π/4 for unconstrained bits, use bounded rotations toward selected elites, cap θ in `[ε, π/2−ε]`, and periodically reset a documented fraction of bits to π/4 for diversity. For the multi-objective case, rank feasible plans by nondomination and crowding; rank infeasible plans after feasible ones by a normalized, documented vector of violations. Maintain an external archive of uniquely hashed, independently feasible nondominated plans. Use one seeded pseudorandom generator per run; save initial seeds, mutation/reset rates, rotation step, population size, stopping criteria, hashes and generation logs. Rotate toward an elite only where sampled bits differ; tie-breaking must be deterministic. Do not claim a quantum speedup from the name of the representation.

For prediction tuning, encode feature mask and bounded discrete hyperparameters in bits. Reject empty feature masks and invalid codes; use the same training-only validation split for QIE and random-search baselines. A model fit is the unit of budget. Keep predictor tuning's scalar loss separate from fleet search's multi-objective archive even if they share sampling utilities.

NSGA-II and QIE must consume identical immutable candidate-set hashes and identical independent feasibility/accounting functions. Hold population/evaluation budgets and stopping rules in a manifest. Include a small exact fixture to catch Pareto-ordering and repair errors. Observe convergence at evaluation counts, not just generations.

```python
qie_search(problem: SearchProblem, config: SearchConfig) -> SearchTrace
greedy_solve(scenario: Scenario, candidates: CandidateSet, config: SearchConfig) -> RunResult
exact_tiny_solve(scenario: Scenario, candidates: CandidateSet) -> RunResult
alns_solve(scenario: Scenario, candidates: CandidateSet, config: SearchConfig) -> RunResult
nsga2_solve(scenario: Scenario, candidates: CandidateSet, config: SearchConfig) -> RunResult
qie_solve(scenario: Scenario, candidates: CandidateSet, config: SearchConfig) -> RunResult
```

## 7. Rules, statuses, and decision presentation

Keep regulation evaluation independent from the generic user-defined emissions budget. Each versioned rule implements an applicability predicate and a named metric with exact units. Its result is `pass`, `fail`, `not_applicable`, or `unknown`, with provenance and calculations. Overall compliance is `noncompliant` if any applicable rule fails; `unknown` if applicable coverage or inputs cannot be established; otherwise `compliant` only for the explicitly configured rule set, labelled with its scope and date. A plan that fails an applicable hard rule is rejected by the feasibility checker and appears only in diagnostics, never as a recommendation. Requirements such as safety approvals for new fuels are not inferred from lifecycle emissions.

Status handling:

| Situation | Run | Compliance | Support / UI treatment |
|---|---|---|---|
| Feasible plan, complete configured rule coverage | `completed` | `compliant` or `noncompliant` for an advisory-rule failure | Show plan, exact rule scope and any advisory failures |
| Feasible plan, missing applicable rule | `completed` | `unknown` | Show operational plan with compliance unverified; withhold “compliant” label |
| Missing fuel intensity or cost factor | No candidate using that pathway | `unknown` if material to scope | Explain excluded pathway and missing source |
| Predictor outside support | No ML result for that option | Independent | Engineering-only option if validated; otherwise exclude |
| Sound structural impossibility | `infeasible_proven` | `unknown` | Show witness, no recommendation |
| Search or capped candidates find no plan | `no_feasible_solution_found` | `unknown` | Show limit, violations and next scenario control |
| Interrupted or unexpected error | `cancelled` or `failed` | `unknown` | Preserve log; no partial plan as final recommendation |

The UI exposes upload/validation, scenario controls, conventional baseline, optimization, Pareto chart, plan details and benchmark evidence. Display lowest cost, lowest emissions and balanced picks only from verified feasible plans. Provide a prominent synthetic-data label, method name, data support, factor and rule versions, nominal/conservative cases, and reason for every excluded option. The chart axes and units remain explicit. Export row-level deployment and purchase schedules, summary totals, rule-check results, model/split/candidate hashes, seeds, normalization and warnings. Sanitize uploaded filenames and use run-ID directories with atomic writes so two clicks or a cancellation cannot overwrite another run.

## 8. Benchmark and case-study protocol

Freeze datasets, split manifests, candidate-generation settings, factor versions and objective normalization before comparisons. Run 20 paired seeds for stochastic methods; record Python/dependency versions, CPU/memory, timeouts and evaluation counts. For prediction compare engineering, direct GBM, physics-residual GBM, random-search tuning and QIE tuning under identical fit budgets. For optimization compare greedy, tiny exact, ALNS, NSGA-II and QIE under equal evaluator calls **and** separate equal wall-clock budgets. Keep fit costs and candidate-generation time visible rather than excluding inconvenient overhead. ALNS is a necessary strong classical fleet comparator; showing only QIE versus generic NSGA-II would give a weak basis for a superiority claim.

Optimization metrics: feasible-run fraction, median and distribution of energy/cost/emissions of selected decisions, hypervolume using a declared frozen reference point and normalization, convergence by shared evaluation count, runtime, peak memory and exact-frontier gap on tiny cases. Hypervolume is undefined for a run without feasible plans; do not convert it to zero without a clearly stated separate convention. Prediction metrics and split protocols are in §3. Add **decision-level out-of-sample evaluation**: choose plans using development-period predictors, then recompute fuel/cost/emissions and schedule failures under held-out observed or independently simulated conditions, keeping the choice fixed. Report regret only where a comparable hindsight feasible optimum can actually be computed; otherwise report realized plan differences and violations. Historical records lack counterfactual fuel for unchosen assignments, so label model-based replay as such. Use paired confidence intervals or bootstrap intervals with the paired seed as the resampling unit. Report failures and resource limits.

Case-study matrix: conventional baseline; each of LNG, methanol, hydrogen and ammonia **when backed by valid vessel, pathway and port data**; shore power off/on; increased demand; adverse weather; changed prices; changed grid and production-pathway intensity. Show objective changes and binding constraints, not a blanket “green fuel” ranking. Benchmark 10/50/100-vessel generated scenarios if candidate creation fits the declared cap, and publish cap/timeouts explicitly. Ablate predictor tuning alone, fleet search alone, and their combination. State that synthetic case studies illustrate software behavior only.

```python
run_benchmarks(config_path: Path, output_dir: Path) -> Path  # experiment manifest
execute_run(scenario: Scenario, config: RunConfig, output_dir: Path) -> RunResult
export_run(result: RunResult, output_dir: Path) -> list[Path]
```

## 9. Build sequence and acceptance tests

Each task follows write failing test → run the focused test to observe failure → implement minimum behavior → rerun focused tests → commit. CI runs the full suite after each integrated milestone. Tests below pin behavior; no supplied repository or operational data has been executed yet.

### Task 1 — contracts, loader and a thin fixture UI (week 1)

**Files:** `pyproject.toml`, `configs/demo.yaml`, `contracts.py`, `ingest.py`, `app.py`, `tests/test_ingest.py`, `tests/test_app_smoke.py`, `docs/data-dictionary.md`.

**Interfaces produced:** `load_bundle`, `validate_scenario`, `fingerprint_dataset`, status types in §2. The UI initially loads a tagged synthetic scenario and shows its validation report; later tasks add engine results.

- [ ] Write `test_rejects_missing_units_and_bad_rows`: fuel 1 tonne explicitly converts to 1000 kg; missing unit, duplicate observation ID, zero duration and negative cargo each produce a distinct error. Write `test_status_domains` asserting run/compliance/support strings cannot be interchanged.
- [ ] Run `pytest tests/test_ingest.py tests/test_app_smoke.py -q`; expect failure before implementation.
- [ ] Implement typed records, immutable manifest hashing, deterministic fixtures, loader, quality report and the UI fixture/validation page.
- [ ] Rerun those tests; expect pass. Launch Streamlit once and verify the fixture and error display.
- [ ] Commit Task 1. At its gate, obtain data availability, region/rules and sponsor acceptance of the QIE-tuned classical predictor definition.

### Task 2 — leakage-safe conventional prediction (weeks 1–2)

**Files:** `splits.py`, `predict.py`, `tests/test_splits.py`, `tests/test_predict.py`, `docs/model-card.md`.

**Interfaces produced:** `make_splits`, `fit_predictor`, `Predictor.predict` in §3.

- [ ] Write `test_future_and_unseen_splits`: future protocol has disjoint voyage IDs and ordered times for known vessels; unseen protocol has disjoint vessel IDs. Write `test_no_preprocessing_leakage` with future-shifted values and `test_unsupported_speed` returning no ML numeric value.
- [ ] Run `pytest tests/test_splits.py tests/test_predict.py -q`; expect failure.
- [ ] Implement split manifests, engineering baseline, direct GBM, physics-residual GBM when power curves/engine maps exist, training-only preprocessing, disjoint interval calibration and model card. Leave QIE tuning for Task 6.
- [ ] Rerun tests; expect pass and separate known/unseen sample counts. Show baseline metrics in the fixture UI, labelled synthetic.
- [ ] Commit Task 2.

### Task 3 — pathway and accounting engine (week 3)

**Files:** `pathways.py`, `accounting.py`, `tests/test_accounting.py`.

**Interfaces produced:** `evaluate_candidate`, `evaluate_plan` in §4.

- [ ] Write `test_accounting_units`: 1000 MJ × 80 g/MJ = 80 kg, and 10 kWh × 0.5 kg/kWh = 5 kg. Write `test_no_double_counting`, `test_incompatible_engine`, `test_missing_factor_excludes_option` and `test_purchase_vs_consumption_cost`.
- [ ] Run `pytest tests/test_accounting.py -q`; expect failure.
- [ ] Implement separate sea/auxiliary/shore calculations, robust energy estimates, factor provenance, fuel inventories' financial convention, and exclusion reasons.
- [ ] Rerun tests; expect pass; inspect one hand-calculated fixture report.
- [ ] Commit Task 3.

### Task 4 — candidate paths and independent feasibility (weeks 3–4)

**Files:** `candidates.py`, `feasibility.py`, `tests/test_candidates.py`, `tests/test_feasibility.py`.

**Interfaces produced:** `build_candidates`, `validate_plan`, `prove_simple_infeasibility` in §5.

- [ ] Write `test_two_trip_fuel_balance` so trip 2 fails without enough fuel and passes after a valid purchase; `test_port_contention` so concurrent shore connections and cumulative bunkering stock are enforced; `test_location_and_time` so unreachable/overlapping/repositioning paths fail; `test_weather_case_deadline` and `test_candidate_cap_cannot_prove_infeasibility`.
- [ ] Run `pytest tests/test_candidates.py tests/test_feasibility.py -q`; expect failure.
- [ ] Implement stable bounded candidate creation, safe-pruning log, explicit reposition/shore/bunkering actions, fuel state reconstruction and independent validator.
- [ ] Rerun tests; expect pass; inspect pre/post-pruning counts and violation entity IDs.
- [ ] Commit Task 4.

### Task 5 — usable conventional planner and mid-project baseline (week 4)

**Files:** `solvers.py`, `tests/test_solvers.py`, `app.py`.

**Interfaces produced:** `greedy_solve`, `exact_tiny_solve`, and `solve(..., method="greedy"|"exact_tiny")`.

- [ ] Write `test_exact_hand_frontier` with ≤20 bits and hand-calculated objective triples, `test_greedy_is_checked`, `test_infeasible_witness` for unsplittable demand above every eligible vessel, and `test_exhausted_search_is_not_proof` for incomplete search.
- [ ] Run `pytest tests/test_solvers.py -q`; expect failure.
- [ ] Implement greedy insertion, exhaustive tiny enumeration, sound witness validation and status handling. Connect the baseline UI to real engine results. Record a frozen fleet-instance set for later ALNS/NSGA-II/QIE comparison.
- [ ] Rerun tests; expect pass. Complete a feasible and an impossible end-to-end demo by the end of week 4.
- [ ] Commit Task 5.

### Task 6 — QIE tuning and multi-objective search (weeks 5–6)

**Files:** `qie.py`, `solvers.py`, `predict.py`, `tests/test_qie.py`, `tests/test_solvers.py`, `tests/test_predict.py`.

**Interfaces produced:** `qie_search`, `alns_solve`, `nsga2_solve`, `qie_solve`, and `fit_predictor(..., method="qie_tuned")`.

- [ ] Write `test_seed_and_budget`, `test_probabilities_bounded`, `test_final_test_never_tunes`, `test_same_candidate_and_evaluator_hash`, `test_alns_preserves_paths_inventory`, and `test_nondominated_feasible_archive`. Include a tiny fixture comparison to the exact frontier.
- [ ] Run focused QIE/solver/predictor tests; expect failure.
- [ ] Implement QIE sampling/rotation/reset, repair/logging, QIE predictor tuning, ALNS destroy/repair and scalarization/ε-constraint adapter, NSGA-II adapter, shared evaluation and archive. Keep hyperparameter codes and feature masks bounded. If the eight-week schedule becomes constrained, preserve ALNS and QIE fleet comparison before optional time-series/advanced predictor work.
- [ ] Rerun focused tests; expect pass. Revalidate every archived plan independently.
- [ ] Commit Task 6.

### Task 7 — reproducible benchmarks and case studies (weeks 6–7)

**Files:** `benchmarks.py`, `tests/test_benchmarks.py`, `docs/case-study.md`.

**Interfaces produced:** `run_benchmarks` in §8.

- [ ] Write `test_paired_manifest` asserting shared dataset/split/candidate/factor hashes, budgets, seeds and hardware; `test_undefined_metrics` ensures infeasible hypervolume and zero-denominator WAPE remain unavailable; `test_heldout_decision_evaluation` holds a chosen plan fixed while evaluating held-out conditions.
- [ ] Run `pytest tests/test_benchmarks.py -q`; expect failure.
- [ ] Implement manifest, 20-seed paired experiment runner, honest timeouts, figures/tables, ablations and scenario matrix. Freeze reference points before reading outcomes.
- [ ] Rerun tests; expect pass. Execute the complete benchmark only when real data and sourced factors are available; otherwise publish a clearly synthetic demonstration and defer empirical conclusions.
- [ ] Commit Task 7.

### Task 8 — complete UI, exports and handover (weeks 7–8)

**Files:** `runs.py`, `reporting.py`, `app.py`, `tests/test_runs.py`, `tests/test_reporting.py`, `docs/user-guide.md`.

**Interfaces produced:** `execute_run`, `export_run` in §8.

- [ ] Write `test_export_matches_evaluation`, `test_unknown_compliance_separate_from_completed_run`, `test_cancelled_run_has_no_final_recommendation`, and `test_duplicate_clicks_do_not_overwrite_artifacts`.
- [ ] Run focused tests; expect failure.
- [ ] Implement immutable run manifest, progress/cancellation, Pareto chart, visible assumptions and rule scope, plans and exclusions, atomic CSV/JSON/Markdown exports, and user guide.
- [ ] Run `pytest -q`; expect pass. Manually walk through feasible, impossible, missing-factor and unknown-rule scenarios and open each exported artifact.
- [ ] Commit Task 8 and capture reproducibility evidence.

## 10. Delivery table and gates

| Deliverable | Artifact | Acceptance evidence |
|---|---|---|
| Mathematical model | §4–5 and implementation equations | Exact tiny instance agrees with hand calculation |
| Data package | Schema, validator, manifest, fixture and data dictionary | Invalid inputs rejected; stable hashes and split IDs |
| Prediction | Engineering, direct and physics-residual GBM, QIE tuning, model card | Separate temporal/unseen metrics, coverage, physical plausibility and support flags |
| Accounting | Sourced alternative-fuel and shore-power pathways | Unit/double-counting tests and factor provenance |
| Fleet optimization | Greedy, exact tiny, ALNS, NSGA-II, QIE, checker | Each exported plan independently feasible; strong classical comparison |
| Benchmark report | Paired runs, convergence, scale, ablations, held-out decision evaluation | Reproducible hashes, budgets, seeds and honest failures |
| Planner platform | Streamlit views and CSV/JSON/Markdown outputs | Feasible, impossible and unknown-status demos |
| Case study and handover | Case matrix, guide, limitations and demo script | Another contributor reproduces the fixture run |

**Gate at week 1:** obtain access to measured fuel data and relevant ship/port/rule scope, and confirm the predictive-method interpretation. Without data, complete a labelled simulation demonstrator and defer accuracy claims. **Gate at week 4:** conventional end-to-end verified plan. **Gate at week 7:** freeze comparative evidence; choose the best supported default, even when conventional. Before running comparisons, declare the primary operational selection rule: among methods that pass all hard constraints, prefer the method with the best held-out decision outcome for the agreed cost/emissions weighting, with feasibility rate and runtime as guardrails; report the full Pareto and prediction metrics as secondary evidence. Do not change weights after observing results. **Gate at week 8:** reproducible export, visible assumptions, correct statuses, and domain review before any operational deployment.

## 11. Remaining decisions requiring domain input

Record these in a versioned `decision-log.md` during Task 1 rather than burying defaults in code: target ship classes and trade lanes; measured fuel-data availability, quality and licensing; splitting of cargo requests; allowable departure granularity; fuel inventory cost convention; source and vintage of pathway/grid factors; applicable regulatory jurisdictions and rule versions; operational weather/reserve policy; sponsor acceptance of QIE-tuned regression; deployment and access-control requirements. The program can ship a documented demonstration profile while these remain unresolved, but must label unsupported or unknown conclusions.

## 12. Research check and design implications (2 October 2026)

The following are primary research papers or the official methodology, not evidence that the proposed system has achieved their results. The changes they justify are already integrated in §§2–10.

| Source | What its evidence supports | Decision here and limit of transfer |
|---|---|---|
| [Bourchas & Papalambrou, *Scientific Knowledge–Guided Machine Learning for Vessel Power Prediction*, 2026 preprint](https://arxiv.org/abs/2602.18403) | Sea-trial power curves plus learned residuals can preserve a power/speed relationship and help in sparse operating regions in the authors' vessel tests. | Add a physics-residual GBM candidate and a plausibility grid. Compare it with direct GBM on our vessel classes; the paper's power target is not automatically our fuel target. |
| [Viga et al., *FuelCast*, 2025 preprint](https://arxiv.org/abs/2510.08217) | A public three-vessel fuel benchmark with high-frequency operational and weather records evaluates tabular/temporal models; temporal context helped in its studied tasks. | Use only as a licensed pipeline/benchmark shakeout when appropriate. Its cruise/offshore fleet, operational regimes and target do not establish cargo-vessel generalization. Add lagged features only if the intended planner has that history at decision time. |
| [Zhen et al., *Ship fleet scheduling and deployment optimization considering carbon and sulfur emissions*, EJOR 2026](https://research.polyu.edu.hk/en/publications/ship-fleet-scheduling-and-deployment-optimization-considering-car/) | Authors formulate a maritime fleet/speed/schedule model and report strong large-instance performance for adaptive large-neighborhood search. | Add ALNS as a domain-specific conventional comparator. Their reported gap and regulatory model belong to their instances; our multi-objective ALNS adaptation must be tested anew. |
| [He et al., *Distributionally robust optimization of sailing speed, bunkering, and fuel switching*, TRC 2026](https://research.polyu.edu.hk/en/publications/distributionally-robust-optimization-of-sailing-speed-bunkering-a/) | Joint speed, bunker, fuel-switch and uncertain-price decisions matter; sub-leg segmentation enables regional-rule treatment in their dual-fuel liner model. | Keep fuel stock across trips, use segments when a route crosses applicable zones, and test price/weather sensitivity. Wasserstein chance constraints are follow-on research, not an unexplained MVP dependency. |
| [Kumar et al., *Benchmarking GPU-optimized QIEO*, 2024 preprint](https://arxiv.org/abs/2412.08992) | QIEO beat a GA on three continuous benchmark functions under that paper's settings. | Retain QIE as the research method, but do not import its speedup as a fleet claim. Compare QIE with ALNS and NSGA-II on the actual constrained discrete problem, counting repair and end-to-end runtime. |
| [IMO, 2024 LCA Guidelines, MEPC.391(81)](https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.391%2881%29.pdf) | Specifies WtT, TtW, WtW boundaries, CO2/CH4/N2O and fuel/energy-carrier pathway data including electricity. | Track feedstock/pathway, engine-specific factors and methane/nitrous oxide provenance, and avoid double counting. This methodology alone is not a certification or a complete emissions regulation set. |

These papers do **not** establish a universal best predictor, universal best optimizer, or guaranteed green-fuel ordering. The proposed project's best method must be selected on its own held-out vessels, routes and sourced pathway data. In particular, a lower prediction MAE can still produce a worse schedule; decision-level validation is the final empirical gate. The supplied problem statement and reviewed proposal establish product scope; the candidate cap, chosen methods, schedule and team size remain proposed engineering choices. No product code, empirical prediction, or fleet benchmark has yet been executed.
