# Reproducible fleet data

This dataset is a fictional operating scenario. It supports engineering checks and demonstrations of fuel analysis; it does not establish actual fleet savings, customer adoption, or company performance. Public price observations, when included, retain their own source identity and publication evidence. They never become observations from these fictional vehicles.

## World and profiles

The full world covers January–June 2025 with 3 tenants, 30 vehicles, 36 devices, 45 drivers, 12 facilities, 12 abstract route IDs and 1,800 trips. All reporting days use `America/Los_Angeles`; stored timestamps use UTC. The March daylight-saving transition and a Sunday-to-Monday trip are explicit boundary cases.

The smoke profile emits counter observations for a fixed subset of 100 trips. It keeps the complete purchase, movement and inventory ledgers and all 1,800 planned trips, so accounting controls still reconcile. Its sparse observation coverage is intentional: it is suitable for testing pipeline behavior, not reproducing full-profile operational statistics. The selected trip IDs are stable across runs and remain a subset of the full profile.

Facilities have representative coordinates. Route IDs represent task categories and facility relationships, not road-network geometry. Duration and distance are scenario parameters; no routing API accuracy or actual travel-time claim is implied. DA-E01 uses measured trip distance, not straight-line distances between facilities.

## Rebuild interface

The shared CLI calls this Python interface:

```python
from pathlib import Path
from fleet_fuel.simulation import generate

generate(Path("."), profile="full", seed=20261021)
```

A smoke replay uses `profile="smoke"`. The generator writes only source/master/validation tables. Paired intervals, weekly metrics, inventory balances and report runs are built by the analytical pipeline after ingestion and quality checks.

`config/simulation.json` records the scenario version, default seed, fuel rates, tank capacity, initial inventory and counter modulus. Fuel rates and tank parameters are read at generation time. Changing them creates a new scenario and requires regenerating data, updating the manifest and re-running validation. The calendar, entity counts, trip scheduling, anomaly cases and market-curve shape are versioned generator code rather than unrestricted configuration options.

The default seed is `20261021`. Each trip and each physical calculation has its own random stream: UTF-8 tokens separated by a unit-separator byte are hashed with SHA-256; the first 128 bits become an unsigned big-endian integer. Adding a separate stream therefore does not reorder every existing random draw.

The creation timestamp in the configuration identifies the original sample release. It is deliberately frozen for byte-identical regeneration. A pipeline replay records its own execution time separately; simulated historical availability is never represented as a real 2025 collection event.

## One physical ledger, several observable systems

1. Create tenant-scoped entities and the stable trip plan. Assign each vehicle a driver, device, tank, card and fuel/distance signal definition.
2. For each trip, determine load, moving duration, idle duration and PTO duration. Minute-level speed weights sum to the planned distance.
3. Compute travel fuel from distance, load, task type and vehicle condition. Add idle and PTO fuel using their own rates. Advance cumulative fuel, odometer and tank inventory together.
4. Refill the same physical tank. Produce a fuel-card transaction, movement entry and independent monthly statement control. An amount-only refund changes money without changing tank volume.
5. Observe the same counters every 60 seconds while operating. Apply resets, rollover, missing observations, delayed delivery and revisions to the observable records. Keep the underlying physical ledger in validation storage.
6. Measure tank inventory at local period boundaries. Preserve the movement ledger, including documented zero-transfer coverage and explicit unknown quantities.
7. Build source review and follow-up cases with mature, disputed, unavailable and immature outcomes. Analytical follow-up metrics are independently recomputed from accepted observation intervals.

This order prevents independently randomized tables from being joined into a contradictory vehicle history. The physical validation ledger is not an analytical input or a prediction feature.

The fuel-rate assumptions are intentionally understandable. They are not fitted to a production fleet or calibrated to proprietary J1939/OBD signals. The source protocol is labeled `synthetic`; decoded field locators do not claim to implement proprietary protocol definitions.

## Source and transport files

| Path | Purpose |
| --- | --- |
| `data/raw/tables/*.jsonl` | The 22 source, master, review and reference tables; all contract fields are present |
| `data/raw/events.jsonl` | Counter-event delivery attempts, including a replayed duplicate and a deliberately invalid payload |
| `data/raw/operations/trip_plan.jsonl` | Complete 1,800-trip plan |
| `data/raw/operations/trips.jsonl` | Operating trips selected by the active profile |
| `data/raw/operations/drivers.jsonl` | Forty-five fictional drivers |
| `data/raw/operations/facilities.json` and `routes.json` | Shared facility and abstract route definitions |
| `validation/expected/physical_trip_ledger.jsonl` | Isolated fuel/distance truth for physical conservation checks |
| `validation/expected/hand_cases.json` | Literal arithmetic and temporal examples independent of analytical SQL |
| `validation/expected/injections.json` | Injected faults, affected IDs and intended treatment |
| `validation/expected/review_cases.json` | Synthetic process-review states |
| `validation/expected/malformed_transport.jsonl` | Invalid JSON/envelope fixtures for loader tests |
| `data/generation_manifest.json` | Counts, seed, profile, source sizes and SHA-256 hashes |

The event envelope contains `event_id`, `revision`, `available_time`, `event_time`, `tenant_id`, `table` and `payload`. Observation revisions have separate canonical IDs; their provenance retains a common logical source ID. Transport retries preserve the same logical ID and revision. API delivery sorts by availability, logical ID and revision; raw generator order is not a global event-time ordering.

Source rows have unique canonical primary keys. An invalid raw unit is deliberately preserved for quarantine by ingestion. It is not silently converted or accepted as a normalized unit. This distinguishes an input-quality fixture from a valid analytical observation.

Identifiers are tenant-scoped, for example `T01-V01`, `T01-D01`, `T01-R01`, and `T01-V01-TR001`. The review/output reference format is `T01-FUEL-20250303-revised`, where the date is the local Monday and the suffix is `initial`, `revised` or `retrospective`.

## Versions, availability and missing states

Every source row that supports provenance points to a `provenance_record`. Provenance includes the source logical ID, version, event time, available time, timezone/UTC offset, origin, scenario ID and raw file/line reference. The table manifest labels master tables that do not have record-level provenance as synthetic.

Nulls in source rows carry a `value_states` entry keyed by `table.column`, with a status and reason. Missing fuel, invalid distance, unknown calibration, an unmetered drain and immature follow-up outcomes remain distinguishable. No value is replaced with zero merely to make a ratio or balance computable.

A corrected record remains available to an earlier snapshot until its successor becomes available. The March transaction correction therefore changes a later snapshot without changing the earlier report. `available_time` is simulated delivery evidence; `retrieved_at` identifies the actual sample release.

Source amounts retain their declared basis. Some invoices report pretax fuel subtotal plus tax minus discount; others report tax-inclusive net fuel amount. Extra nonfuel lines and amount-only refunds are explicit. Monthly statement controls are accumulated in the source accounting process before source-file serialization, rather than produced by the reporting transformation being checked. Six-decimal per-line quantity rounding allows less than 0.0001 L difference in these monthly checks.

## Injected scenarios

| Scenario | Observable evidence and expected treatment |
| --- | --- |
| Device replacement | T01-V01 changes device on April 1; T02-V05 changes on May 1; use effective intervals |
| History gap | T03-V10 has no device assignment April 4–6; do not infer a known attribution |
| History overlap | T03-D09 has a conflicting assignment April 4–6; quarantine ambiguous attribution |
| Fuel/odometer resets | Separate service evidence marks discontinuities; avoid negative deltas across reset boundaries |
| Fuel rollover | T02-V02 wraps a confirmed 4,096 L counter; modulus is stored in the signal's raw unit |
| Missing packets | Two T01-V03 trip observations are absent; retain lost coverage |
| Missing fuel only | T02-V03 retains a distance observation with unavailable fuel |
| Invalid distance | A T02-V04 counter record has invalid distance and usable fuel evidence |
| Unknown unit | A T03-V04 raw record has an unknown unit; ingestion must quarantine it |
| Delayed delivery | Two T01-V02 observations arrive four days later; cutoff behavior must differ |
| Counter revision | One T02-V03 observation is corrected three days later; use the latest available revision |
| Transaction revision | T01-V02 has an $8 price credit with unchanged physical volume |
| Nonfuel and refund | Thirty nonfuel lines and thirty amount-only refunds test financial/physical separation |
| Transfers and drain | A known 20 L transfer, known 15 L drain and unknown drain test inventory semantics |
| Uncalibrated inventory | T03-V09 has raw level percent but unknown litres at one boundary |
| DST and week boundary | The local day has 23 hours; a cross-week trip must be allocated by elapsed UTC time |
| Review outcomes | Accepted, partly accepted, rejected and unreviewed cases; confirmed, disputed, lost and immature follow-ups |

The smoke subset includes most named faults; the complete profile is required to exercise all anomaly timings and report calculations. Tests also retain tiny literal examples so an incorrect production transformation cannot define its own expected answer.

## Validation and limits

`tests/test_simulation.py` checks stable identifiers, profile selection, UTC elapsed intervals, exact source field coverage, canonical-key uniqueness, explicit null states, accounting controls, physical conservation, version timing, duplicate/invalid transport, isolated truth, DST arithmetic and byte-identical replay.

The eight hand-authored reference cases are arithmetic fixtures, not external expert endorsements. Synthetic review cases exercise workflow handling, not causal evidence of operational improvement. Follow-up comparisons must still screen observation coverage, task mix and outcome maturity. Differences before and after an action are descriptive unless an independent evaluation design supports causality.

The dataset demonstrates reproducible calculations and behavior under specified faults. Real deployment would need verified signal definitions, sensor calibration, production delivery characteristics, contractual source access and actual operating context. Those requirements are not represented as completed work by this sample release.
