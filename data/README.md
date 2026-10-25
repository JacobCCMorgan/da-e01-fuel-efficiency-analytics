# Data release guide

This directory contains several representations with different jobs. The original operating scenario is fictional and reproducible; actual EIA prices remain a separate public source. The [source register](../docs/sources.md), [simulation design](../docs/simulation.md), [data dictionary](../docs/data_dictionary.md) and [data terms](LICENSE.md) explain their meanings.

| Path | What it contains | Why it is retained |
| --- | --- | --- |
| `generation_manifest.json` | Seed, profile, world counts, owned source paths, byte sizes and hashes | Defines which generated raw files belong to this release |
| `raw/tables/*.jsonl` | Canonical source, master, review and reference records | Original fictional system records before intake/analysis |
| `raw/events.jsonl` | HTTP delivery source, including duplicates and deliberately invalid input | Rebuilds the event service and tests delivery behavior |
| `raw/operations/` | Drivers, facilities, routes, plans and selected trips | Explains the shared operating world and scheduling exposure |
| `public/raw/` | Official EIA downloads and acquisition receipts | Verifiable external evidence with actual retrieval time |
| `public/snapshots/` | Versioned normalized public price snapshots | Keeps a refresh from silently rewriting old evidence |
| `public/source_manifest.json` | Active public snapshot, coverage, source hashes and comparison results | Selects and validates public inputs |
| `postgres_extract/<snapshot>/` | The 15 operational tables extracted from the verified full PostgreSQL CI run | Exact operational inputs used to build the delivered database |
| `staged/events/fuel_counter_observation.jsonl` | Accepted counter observations after HTTP intake | Exact input to analytical normalization, separate from rejected deliveries |
| `ingestion/<snapshot>/receipts.sqlite` | Current snapshot delivery receipts, accepted keys, versions and checkpoints | Audits retries, duplicates, rejects and resume state |
| `ingestion/quarantine.jsonl` | Rejected records with reasons | Keeps invalid data visible without accepting it as a measurement |
| `DA-E01.duckdb` | Canonical and analytical tables plus intermediate audit data | Ready-to-query database for analysis, report and notebook |
| `normalized/*.parquet` | Typed canonical table exports with a manifest | Portable tabular interchange and independent row/hash checks |
| `derived/*.parquet` | Four canonical calculated tables | Direct access to paired intervals, report runs, weekly metrics and inventory balances |

The API's SQLite event index is a cache, not a new data source. The release package omits that cache and reconstructs it from `raw/events.jsonl` when the HTTP service starts. Only the active ingestion receipt snapshot is packaged; temporary or inactive copies are excluded. These receipts describe the local HTTP replay. The delivered DuckDB comes from the verified full PostgreSQL CI build; its remote intake report is preserved separately. [Local intake evidence](../validation/local_intake_evidence.json) establishes the same source snapshot and counts without changing either execution’s timestamps.

A full-profile generation has 1,800 observed trips. The smoke profile retains the complete planned world and accounting controls but emits observations for 100 stable trips, so its business metrics are intentionally incomplete. The release packager requires the full profile.

## Query the ready database

After installing the documented environment:

```python
import duckdb

with duckdb.connect("data/DA-E01.duckdb", read_only=True) as con:
    result = con.sql("""
        SELECT tenant_id, report_week_start, mpg, measurement_coverage
        FROM analytics.fleet_weekly
        WHERE report_view = 'revised'
        ORDER BY tenant_id, report_week_start
    """).df()
print(result.head())
```

Use `DESCRIBE analytics.fleet_weekly` or the [metric definitions](../docs/metrics.md) to inspect columns before extending a query. Keep initial, revised and retrospective views separate. Do not add all versions together or use later public retrievals in a historical as-of calculation.

Source provenance distinguishes `synthetic` and `public` records. The public normalization projects 62 EIA observations into each tenant's reference scope; 186 canonical reference rows still describe only 62 external observations. Record-level source IDs and hashes preserve this distinction.

The isolated expected-answer ledger is under `validation/expected/`, outside this directory's analytical inputs. It is used to test physical consistency and known injected cases, not to calculate the reported operational result.

The [delivery guide](../docs/delivery.md) explains the source/data/complete ZIPs, hash verification, ownership rules and the difference between archive creation and verified upload.
