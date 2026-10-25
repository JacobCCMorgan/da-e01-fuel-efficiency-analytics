# Fuel metric definitions

DA-E01 answers three questions: how much fuel the vehicles consumed on comparable measurement intervals, how purchasing volume and price changed expenditure, and what a documented follow-up can and cannot establish. Fleet operations, investigations, and actions are synthetic. Public market prices are a separately labeled contextual input.

## Reproduce the calculations

After ingestion creates `data/DA-E01.duckdb`, run the project's analysis entry point or:

```bash
PYTHONPATH=src python -m fleet_fuel.analysis --root .
```

The executable calculations are in `sql/analytics.sql`. `src/fleet_fuel/analysis.py` creates report windows, materializes the canonical contract types, and exports the results. The `normalized` schema contains the four canonical derived tables. The `analytics` schema retains intermediate tables for inspection.

## Fail-closed analytical input boundary

`input_policy.py` checks the actual normalized schema before any report write: table names and columns must match the accepted DA-E01 contract, inputs must be base tables, and analytical inputs cannot contain simulator-truth or reference-answer fields. Extra columns, extra tables and substituted views stop the run.

Independent `fuel_reference_case` and `fuel_statement_control` records may be stored for quality verification, but are excluded from the analytical SQL read allowlist. Each `analytics.sql` statement is parsed and its relation names checked before execution. Reading those validation tables, an unapproved schema such as `validation.simulator_truth`, or an external file reader such as `read_csv` stops execution. The output summary records a passed input-policy check only after the checks run.

Negative tests inject forbidden payload columns, alter normalized input columns, substitute an input view, and attempt actual SQL reads of reference tables and a truth file. The guards reject these paths before the attempted result table is created. These are input controls for the declared pipeline, not a security sandbox for arbitrary changes to Python source code.

## Report time and source versions

Reports use Monday 00:00 in `America/Los_Angeles`, with the next Monday excluded. The first and last calendar weeks are retained even when the observation period covers only part of them. UTC boundary timestamps are stored explicitly. A daylight-saving week can contain 167 hours, so calendar windows are never replaced by a fixed number of seconds.

Each tenant and week has three views:

| View | Cutoff | Market-price policy |
|---|---|---|
| `initial` | Week end plus 48 elapsed hours | A synthetic price known by the cutoff, or a public price with actual historical availability evidence |
| `revised` | Week end plus 7 elapsed days | Same historical-availability rule; newly available operational corrections are eligible |
| `retrospective` | Latest retained source availability, at least the revised cutoff | Public historical observations may provide retrospective context |

The report ID is `<tenant>-FUEL-<Monday YYYYMMDD>-<view>`. Source-record versions are ranked only after applying the report cutoff. A record marked corrected remains usable for a historical report before its replacement becomes available. Withdrawn, deleted, or cancelled records are excluded when that state is the latest available version.

Downloading a 2025 price in 2026 establishes when the workflow retrieved it, not when that exact value was available in 2025. Public prices without historical publication evidence appear only in the retrospective view. Source refreshes create a new input snapshot instead of silently changing an older report.

## O01 Consumption and purchasing remain separate

### Common fuel and distance intervals

For every report cutoff, the pipeline selects available counter versions, resolves the device-to-vehicle assignment using both business validity and knowledge time, and finds consecutive observations from the same device. Fuel and distance must share measured start and end times. Both measurements must have a supported unit and valid reading, compatible signal definitions, and a single unambiguous task and vehicle assignment.

Fuel and distance changes are evaluated separately. A documented rollover with a known modulus can recover a negative difference; the modulus is converted from its documented source unit. An unknown negative jump, reset, ECU change, or incompatible definition breaks the interval. A fuel reset does not invent a distance reset. Definitions must be valid at both measurement endpoints and available by the report cutoff.

Intervals crossing a day or week boundary without a measurement at the boundary are excluded rather than prorated. Intervals entirely within a known operating task can bridge a missing packet when valid cumulative endpoints still define the whole interval. Packet arrival rate and consumption measurement coverage therefore measure different things.

The exclusion order is:

1. Ambiguous or unavailable vehicle assignment.
2. Unsupported units.
3. Invalid readings or signal definitions.
4. Counter discontinuity or incompatible source definition.
5. Nonaligned measurement times.
6. A calendar boundary that cannot be allocated.
7. No unique operating task containing the interval.

`fuel_paired_interval` stores accepted and excluded intervals, source observation IDs, segment IDs, cutoff, and input provenance. Excluded measurements have no accepted fuel/distance quantity.

Coincident boundary and trip readings can produce a zero-duration candidate. Such candidates remain in the analytical exclusion audit but are not materialized as canonical intervals, whose end must be later than their start.

### Efficiency and coverage

The storage units are litres and kilometres. Display MPG uses the US gallon:

- Miles = kilometres / 1.609344.
- US gallons = litres / 3.785411784.
- MPG = total eligible miles / total eligible US gallons.

Fleet MPG uses sums over the same accepted intervals. It is not the average of vehicle MPG values. Missing or nonpositive fuel denominators produce a null efficiency value.

Measurement coverage is accepted paired seconds divided by the expected operating seconds from the task schedule known at the report cutoff. Inactive weeks have zero expected exposure and no efficiency claim. The independent distance-only calculation can remain valid where fuel readings are unusable. Purchasing expenditure per kilometre is supplied only when that distance calculation covers the expected weekly operating window.

### Comparable efficiency review

Efficiency exceptions use vehicle/week/task rows so that mixed task weeks are not treated as one homogeneous peer group. A comparison uses the same vehicle and task in the immediately preceding calendar week, and the median of other vehicles in the same tenant, vehicle class, task, week and report view. Eligible observations have at least 95% coverage and positive fuel and distance; a peer comparison requires at least three other vehicles.

A value at least 20% above the eligible peer median triggers a load/PTO/route review. This threshold is an explicit investigation rule, not a trained anomaly detector or proof of waste. Payload and necessary PTO remain relevant explanations even after task stratification. The export retains coverage, peer count, baseline values and relative differences so the threshold can be changed and its effect inspected.

## O02 Purchasing and price differences

Purchase records retain volume, monetary components, original and posting times, product, currency, card assignment, and record versions. Comparisons require diesel, USD, a supported amount basis, and an unambiguous card-to-vehicle assignment. Nonfuel products, pending/cancelled records, unknown amount bases, and other currencies are separately counted.

The comparable fuel amount depends on the recorded basis:

| Source amount basis | Comparable amount |
|---|---|
| Pretax gross | Fuel subtotal + attributable fuel tax - attributable discount |
| Tax-inclusive net fuel | Already-net fuel amount |
| Tax-inclusive before discount | Tax-inclusive subtotal - discount |
| Transaction total | Total less separately known fees and nonfuel amount |

Components are applied once. A pure monetary refund contributes no negative fuel volume. An adjustment linked to an original line is attributed to that original purchase's operating period for weighted-price analysis; its actual posting time still controls availability. The exported transaction detail retains both the original and attributed timestamps.

Weighted purchase price is comparable net fuel amount divided by the corresponding net purchased litres. It is distinct from ECU consumption efficiency and from an estimated consumption cost.

For the same vehicle's consecutive USD-diesel purchasing periods with observed prices and quantities, the monetary expenditure bridge uses a fixed order:

- Price effect = (current price - previous price) × previous volume.
- Quantity effect = current price × (current volume - previous volume).

The two effects sum to the expenditure change for the matched purchasing cohort. Missing prices or quantities prevent decomposition. Duty mix is retained as separate context: a quantity contribution does not establish inefficiency, and two weeks both labeled mixed are not treated as homogeneous operational peers. Operational comparisons use the task-specific efficiency table instead.

### Market context

Market matching requires the configured station-state mapping, compatible diesel/tax/unit assumptions, and a price observation from the relevant week. The reference amount is purchased litres / 3.785411784 × USD per US gallon. The price gap is the comparable amount from the same matched transactions minus their reference amount. Matching coverage is reported with its volume denominator.

Public regional prices describe regional market context. A gap is not an executable station offer or proven saving. Synthetic prices are labeled synthetic even if their region names match the public adapter's canonical geography.

## Inventory reconciliation

Inventory periods use actual consecutive boundary measurements of the same tank scope. Only recorded movements into or out of that scope are included. Refuel movements and purchase transactions are not counted twice.

The balance is opening volume + refuel + other inflows - closing volume - verified outflows. Unknown movement quantities propagate to an unknown balance. Explicit zero movement records or equivalent ledger completeness evidence distinguish a confirmed absence from missing records. Uncalibrated boundaries and unknown uncertainty prevent a verified balance claim.

The initial implementation adds endpoint uncertainty bounds conservatively. It does not assume measurement errors are independent. ECU consumption is compared on the corresponding physical period, and a discrepancy can reflect incomplete ECU coverage as well as an inventory issue. The report preserves these distinctions.

The canonical state `uncertainty_known` means the same-scope boundaries, endpoint uncertainty and complete movement ledger support calculating an inventory balance. It does not mean the ECU independently agrees. `incomplete_movements` and `boundary_mismatch` preserve unresolved cases; the analytical export adds a more specific reason and the independent ECU comparison.

## O03 Investigation and follow-up

`fuel_output_review` records adoption separately from merely receiving a report. `fuel_action_followup` retains action evidence, baseline and actual observation windows, planned follow-up end, and active investigation time excluding waiting.

The analytical evaluation recomputes fuel and distance from the eligible measurement intervals within each baseline/follow-up window. It records differences from supplied outcome values. Comparability requires a mature observed window, at least 95% measurement coverage in both windows, positive distances, and a consistent recorded task set. Explicit task changes remain a limitation even if the aggregate task names overlap.

In addition to the unadjusted before/after rate, the pipeline calculates each task's fuel per100km and weights follow-up rates by baseline task distance shares. This holds the recorded task mix constant. The export includes both rates and the maximum distance-share shift. Payload, route difficulty and necessary PTO are not fully controlled; task standardization is descriptive and does not remove these causal limitations.

Cases with no action, no observation, immature windows, lost follow-up, missing exposure, insufficient coverage, changed task mix, or zero distance remain separate. A qualifying before/after change is descriptive only. It does not establish a causal saving or real customer adoption.

## Outputs and interpretation

| File | Purpose |
|---|---|
| `vehicle_weekly.csv` | Vehicle-level metrics with view, week boundaries, purchases, and decomposition inputs |
| `fleet_weekly.csv` | Tenant/week totals using aggregate numerators and denominators |
| `purchase_detail.csv` | Attributed transactions, exclusions, amount basis, benchmark origin and matching |
| `inventory_reconciliation.csv` | Physical inventory periods, uncertainty, ECU comparison and unresolved gaps |
| `followup_evaluation.csv` | Investigation/action chain, recomputed windows and comparability decisions |
| `followup_task_comparison.csv` | Baseline/follow-up fuel, distance and task shares used for standardization |
| `interval_exclusions.csv` | Excluded interval counts and seconds by report view and reason |
| `report_revisions.csv` | Initial-versus-revised changes with unchanged reporting semantics |
| `coverage_sensitivity.csv` | Fleet metrics at fixed coverage thresholds of 0%, 90%, 95%, and 99% |
| `efficiency_comparison.csv` | Task-specific same-vehicle prior values, peer medians, coverage and review flags |

The canonical tables retain input provenance even where a presentation CSV omits a large JSON array. Use the report ID and vehicle ID to return from a chart to the exact canonical row and its contributing observations.

The tests include independent arithmetic for totals, tax handling, price/quantity effects and inventory uncertainty, plus real production-SQL fixtures for aligned counters, late revisions, rollovers and conflicting historical assignments. Passing these checks validates the implemented behavior for the specified cases; it does not establish accuracy on a real fleet.
