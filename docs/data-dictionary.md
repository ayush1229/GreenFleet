# Bundle schema v1

The supported portable upload is one JSON bundle (`bundle.json`) containing
`manifest`, `scenario`, and `observations`. This is the equivalent-table form of
the multi-file contract in the plan. Times are ISO 8601 UTC with explicit offsets.
The loader normalizes to frozen records and produces row/entity violations.

Manifest: `schema_version`, `units`, `timezone`, `source`, `collection_interval`,
`license`, `sensitivity`, `factor_dates`, `digests`. Digests are SHA-256 of canonical
JSON for each data section (sorted keys, compact separators, no NaN). Units are
explicit: fuel_mass kg or tonne, duration h, distance nm, speed kn, cargo t,
energy MJ, electricity kWh, emissions kg_CO2e, price currency/kg. Currency and
price dates live on the scenario and pathways. Missing fuel units are rejected.

Observations carry id, vessel_id, voyage_id, timestamp, duration_h, distance_nm,
speed_kn, speed_basis, cargo_t, fuel_mass (converted to fuel_mass_kg), pathway_id,
engine_id, wave_m, wind_kn, auxiliary_kw and quality_flags. Unresolved multi-fuel
attribution and engine changes are excluded from training with reported counts.

Scenario tables: vessels (capacity/draft, engine, speed limits, power coefficient,
tanks, initial state, maintenance, auxiliary/shore power); ports (opening windows,
draft, fuel stock, replenishments, pumps/rates, shore sockets/power/grid/tariff);
services (origin/destination, distance, release/deadline, handling, demand/splitting);
pathways (LHV, WtW or WtT+TtW, factor provenance, price/currency/vintage);
engine_fuels (compatibility/efficiency and source); weather cases (time/energy
multipliers); rules (scope, units, threshold, applicability, effective dates,
severity). All physical coefficients in the fixture are **synthetic**.

Actions are immutable service/reposition/purchase/changeover candidates. Service
actions explicitly include shore reservations during loading and unloading.
Purchase actions specify port, pathway, quantity and pump duration. Plans reference
candidate IDs; exports expand them into schedules and reconstruct fuel inventory.

Run status, compliance status and prediction support are independent domains.
`completed` certifies a verified operational plan under configured assumptions,
not regulatory certification or global optimality.
