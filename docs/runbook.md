# Rebuild and investigation runbook

Run commands from the repository root using Python 3.12 and the pinned environment. Source inputs, generated products and manifests use relative paths. The CLI's `--root` option is global and therefore precedes the subcommand; omitting it uses the current working directory.

## 1. Install the environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m fleet_fuel.cli --help
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. PostgreSQL server binaries are separate system dependencies, not Python packages. `requirements.lock.txt` records the versions used for this release; changing dependencies requires re-running the checks.

## 2. Run the complete snapshot workflow

```bash
python -m fleet_fuel.cli run --profile full --operational snapshot
python -m pytest -q
```

The run regenerates fictional source data, uses the local HTTP event interface, verifies the frozen public snapshot, builds DuckDB, analyzes, validates, exports and reports. Inspect the CLI exit code and the new manifests; an earlier existing dashboard is not evidence that the latest run succeeded.

The default seed is `20261021`. Change the scenario deliberately:

```bash
python -m fleet_fuel.cli run --profile full --operational snapshot --seed 20261022
```

A different seed changes the generated scenario. It does not justify reusing the default release's numeric report or claiming identical results. The scenario has separately seeded streams so adding an unrelated stream does not reorder every draw.

For a shorter workflow check:

```bash
python -m fleet_fuel.cli run --profile smoke --operational snapshot --skip-report
```

The smoke world retains 1,800 planned trips and financial controls but observes a stable 100-trip subset. Its low measurement coverage is intentional. Use full mode for the delivered analytical report. Each run replaces generated outputs under its target root; use a separate checkout/copy when retaining multiple scenarios.

## 3. Run individual stages

These stages support debugging and explanation. Preserve their order and use the same target root:

```bash
python -m fleet_fuel.cli generate --profile full --seed 20261021
python -m fleet_fuel.sources --root .
python -m fleet_fuel.cli ingest
python -m fleet_fuel.cli build
python -m fleet_fuel.cli analyze
python -m fleet_fuel.cli validate
python -m fleet_fuel.cli export
python -m fleet_fuel.cli report
```

`ingest` uses the local event service. `serve` exposes the same synthetic source for inspection; use `python -m fleet_fuel.cli serve --help` for the current port options. The server binds to loopback, not a public interface. `/health` identifies the synthetic source snapshot; `/v1/events` provides cursor-paginated delivery ordered by availability. Do not represent this endpoint as an ELD vendor API.

`build` requires staged accepted events. `analyze` requires the built database. `validate` after analysis checks derived tables as well as sources. `report` uses current calculated values; it does not rerun ingestion. The `export` command produces normalized Parquet files and a manifest.

## 4. Exercise a real PostgreSQL source

Install PostgreSQL through the supported method for your operating system and run under a regular local account. The optional helper requires `initdb`, `pg_ctl`, `createdb` and `psql` on `PATH`:

```bash
bash scripts/postgres_local.sh start
export FUEL_POSTGRES_DSN="dbname=fleet_fuel host=$PWD/data/postgres_socket port=55432"
python -m fleet_fuel.cli run --profile full --operational postgres
python -m pytest tests/test_postgres.py -q
bash scripts/postgres_local.sh stop
```

The helper exposes only a private Unix socket, with no TCP listener. `FLEET_PG_DATA`, `FLEET_PG_SOCKET` and `FLEET_PG_PORT` change its paths/port; update the application DSN accordingly. Existing separately managed services can be used directly through `FUEL_POSTGRES_DSN`. Keep passwords outside the repository and do not commit a connection string containing credentials.

The default application schema is `fleet_ops`; `FUEL_POSTGRES_SCHEMA` selects an isolated schema. Individual source steps are available:

```bash
python -m fleet_fuel.cli postgres-bootstrap
python -m fleet_fuel.cli postgres-extract
```

Bootstrap writes all operational tables atomically. A conflicting payload for an already published technical key fails; correct data through a new versioned key. Extract uses a read-only repeatable-read snapshot and records the watermark. A successful extract manifest, successful service tests and an actual service version establish this path's execution. Snapshot-mode success does not.

## 5. Keep or refresh public evidence

Offline verification of frozen EIA files:

```bash
python -m fleet_fuel.sources --root .
```

Intentional network refresh:

```bash
python -m fleet_fuel.sources --root . --refresh
```

Refresh retains prior raw files and creates new timestamped evidence and a content/version-identified normalized snapshot. Rebuild analysis after refresh to use it. Review the source manifest, HTML/XLS agreement and coverage before accepting new evidence. A current retrieval time is never backdated to a 2025 publication time. Initial/revised 2025 views therefore exclude public records lacking historical availability evidence.

A blocked download or hash mismatch is an explicit failure. Do not rename synthetic background prices as public observations. The separately labelled simulated benchmark can support historical replay while the public-source limitation is recorded.

## 6. Inspect and execute the notebook

After a full build, open `notebooks/01_fuel_analysis.ipynb` with the same virtual environment. To execute it programmatically without adding a notebook server:

```bash
python -m ipykernel install --user --name fleet-fuel --display-name "Fleet fuel analytics"
python - <<'PYNOTE'
from pathlib import Path
import nbformat
from nbclient import NotebookClient
root = Path.cwd()
path = root / "notebooks/01_fuel_analysis.ipynb"
notebook = nbformat.read(path, as_version=4)
NotebookClient(notebook, timeout=180, kernel_name="fleet-fuel", resources={"metadata": {"path": str(root)}}).execute()
nbformat.write(notebook, path)
PYNOTE
```

The kernel registration is a normal user-level Jupyter setting; omit it if your notebook tool already selects this virtual environment. The notebook reads the database and should not modify inputs. An execution error must remain visible rather than being replaced by a handwritten output.

A provided alternative executes the trusted project notebook through IPython in the current process, without opening a kernel socket:

```bash
python scripts/execute_notebook_inprocess.py notebooks/01_fuel_analysis.ipynb --root .
```

It records actual outputs and execution counts and fails on cell errors. Run it after the final `report` command, because report generation rewrites the notebook. To check dashboard filtering and view separation with Node.js:

```bash
node scripts/check_dashboard.js outputs/dashboard.html
```

This checks the embedded data and dashboard JavaScript with a controlled DOM/Plotly stub. It is a functional check of filters, view isolation and empty/reset behavior; it does not replace visual browser review. Both helpers are included in the source package.

## 7. Review the outputs

| Evidence | What to check |
| --- | --- |
| `data/generation_manifest.json` | Profile, seed, counts and source hashes |
| `data/public/source_manifest.json` | Actual source URLs, retrieval timestamps, hashes and selected coverage |
| `validation/ingestion_report.json` | Accepted/rejected/duplicate counts and reconciliation |
| `validation/build_report.json` | Loaded paths, hashes and actual operational mode |
| `validation/quality_report.json` | Check results, violations and field coverage |
| `validation/requirement_traceability.csv` | Requirements mapped to fields and checks |
| `outputs/analytics_summary.json` | Calculated totals, view/origin distinctions and limits |
| `outputs/report_content.json` | Structured values and figure interpretation used in the report |
| `data/normalized/manifest.json` | Exported table counts and hashes |
| `validation/postgres_bootstrap.json`, `validation/postgres_extract.json` | PostgreSQL evidence only when that path ran |

Open `outputs/dashboard.html` directly, or serve the checkout locally:

```bash
python -m http.server 8000 --bind 127.0.0.1
```

Then navigate to `http://127.0.0.1:8000/outputs/dashboard.html`. Use the initial/revised/retrospective selector first; never combine rows across those views. From a flagged vehicle/week, follow `output_id`, `vehicle_id`, cutoff and contributing provenance back to canonical tables. For source evidence, inspect the raw file/line locator and hash.

## 8. Diagnose failures

| Symptom | Response |
| --- | --- |
| Source snapshot cursor mismatch | Keep evidence of the earlier snapshot; start a new intake for the new snapshot instead of forcing an old cursor |
| Duplicate delivery | Inspect receipts; identical source identity/revision must not create another accepted row |
| Unknown unit or malformed envelope | Inspect quarantine and the validation fixture; do not replace invalid values with zero |
| Unexpected MPG | Check aligned intervals, units, reset/rollover treatment, assignment history, denominator and coverage |
| Price mismatch | Check currency, tax basis, fees, discounts, refund attribution, state mapping, origin and cutoff |
| Inventory discrepancy | Check same-tank boundaries, calibration, movement completeness, uncertainty and ECU coverage |
| PostgreSQL unavailable in your environment | Preserve that failure and use explicitly labelled snapshot mode; the recorded remote CI success does not make a new local service attempt successful |
| Different totals after replay | Compare seed, profile, contract, source snapshot, dependency versions and report view before interpreting differences |

## Execution status

The full local release verified actual HTTP requests to the synthetic event service, real EIA downloads, DuckDB snapshot analysis and quality checks. The [isolated rebuild report](../validation/rebuild_report.json) shows 26 logically matching canonical tables, 28 byte-identical generated source files and a seed-change check that changes results while preserving quality invariants. Report rendering is checked separately from that rebuild proof.

The local container could not run a native PostgreSQL server because it lacked binaries and a supported non-root user setup. That local limitation remains; **remote service integration has been verified**. [GitHub Actions run 40226254641](https://github.com/JacobCCMorgan/da-e01-fuel-efficiency-analytics/actions/runs/40226254641), job `121268156571`, passed at commit `ad396bfd66ad4f67ec753fb8dfa20c29bb902a1b` using PostgreSQL **16.15**. Its 61 tests passed with zero skips, including six real-service tests. The subsequent smoke pipeline atomically loaded 6,493 operational records, took a repeatable-read extract, and completed HTTP intake, DuckDB analysis and quality checks.

[CI summary](../validation/ci_run_40226254641.json), [CI test results](../validation/ci_tests_40226254641.xml), [bootstrap](../validation/ci/run-40226254641/validation/postgres_bootstrap.json) and [extract](../validation/ci/run-40226254641/validation/postgres_extract.json) retain this evidence. The remote check used the smoke profile; it is not a full-profile PostgreSQL load/performance test. Later local test runs can still skip the six service tests because no local DSN is configured. Read local and remote result files separately, with their tested commit and execution scope.
