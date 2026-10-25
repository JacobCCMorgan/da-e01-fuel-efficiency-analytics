# Sources and acquisition

The fleet, vehicles, drivers, transactions, telemetry and investigation cases are synthetic. The only external numeric source in this release is EIA's published diesel-price history. Public prices supply **retrospective regional context**, not real fleet purchases or historical real-time information.

## Verified EIA snapshot

Source: U.S. Energy Information Administration. Source-page release date: **2026-10-20**. Retrieved **2026-10-25 UTC**. These dates describe the downloaded snapshot; the original publication time of each 2025 observation is unknown.

| Series | Geographic meaning | Official source |
| --- | --- | --- |
| `EMD_EPD2D_PTE_SCA_DPG` | California | [Weekly California history](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=EMD_EPD2D_PTE_SCA_DPG) |
| `EMD_EPD2D_PTE_R5XCA_DPG` | West Coast except California | [Weekly regional history](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=EMD_EPD2D_PTE_R5XCA_DPG) |

The adapter performed HTTPS GET downloads of both history pages and the [complete official diesel-history workbook](https://www.eia.gov/petroleum/gasdiesel/xls/psw18vwall.xls). This is an **official file-download integration**, not an EIA API call. No API key was required for these requests.

There are 62 selected values: 31 Mondays per region from 2024-12-02 through 2025-06-30, including 52 values in January–June 2025. All selected dates are present and no selected price is missing. Every selected HTML value agrees to the reported three decimal places with the workbook's `Data 1` sheet. This checks two formats of the same publication; it is not independent validation of EIA's measurements.

## Price meaning and permitted joins

Prices remain USD per **US gallon**, including taxes. Decimal strings preserve the source precision. A separately derived USD/L value divides by 3.785411784. The [EIA methodology](https://www.eia.gov/petroleum/gasdiesel/diesel_proc-methods.php) describes regional estimates from collected prices; these are not transaction-weighted prices paid by this synthetic fleet.

`CA` maps to California. `WEST_COAST_EX_CA` is a broad regional comparison for synthetic Nevada and Arizona purchases. It must never be labelled a Nevada or Arizona state price, a specific station price, or a realized discount.

`price_observation_date` is a date, not an invented publication timestamp. `price_published_at` and `historical_available_time` are null, with `publication_precision=unknown`. All rows carry `origin_type=public`, `allowed_use=retrospective_context_only`, the actual retrieval time, source URL, source row locator, and raw-file SHA256. A 2025 initial/revised report uses explicitly simulated available prices or reports the benchmark as unavailable. The later retrospective view may use the EIA snapshot, clearly labelled.

## Reproduce or refresh

Run from the repository root in the documented Python environment:

```bash
PYTHONPATH=src python -m fleet_fuel.sources --root .
```

The default path is offline: it verifies original-file hashes and the frozen normalized snapshot, then reuses them. A deliberate refresh is separate:

```bash
PYTHONPATH=src python -m fleet_fuel.sources --root . --refresh
```

Refresh creates a new timestamped raw directory and a content/version-identified normalized snapshot. Existing raw files remain unchanged. Downloads have a 30-second timeout, a 5 MiB bound, and at most three attempts with bounded backoff for transient errors. Nontransient HTTP errors and schema/coverage failures remain explicit errors. The caller may use the separately labelled synthetic background, retaining the public-source failure status.

`data/public/source_manifest.json` records the active snapshot, source files, retrieval receipts, sizes, hashes, coverage and HTML/XLS comparison. `data/public/snapshots/<snapshot_id>/` preserves each normalized snapshot. `data/public/fuel_prices.jsonl` and `.csv` are convenience exports of the current snapshot.

## Reuse and attribution

The [EIA reuse policy](https://www.eia.gov/about/copyrights_reuse.php), checked on 2026-10-25, permits reuse of EIA information products with source acknowledgement and publication date. This package uses numerical data and acquisition evidence. Reports do not reproduce the EIA logo, photographs or protected third-party material. The source-page date is preserved separately from unknown historical issue dates.

## Environment verification

The source adapter ran successfully in Linux/Python 3.12. The bundled environment is read-only, so project dependencies were installed in a separate workspace virtual environment using the same Python interpreter. Exact package versions are in `requirements.lock.txt`.

Native PostgreSQL could not be started in the local execution environment: server binaries and Docker were absent, and the OS exposed only a root UID/GID mapping. The local snapshot path was independently executed and rebuilt. `scripts/postgres_local.sh` remains available for supported normal-user environments.

The **full 1,800-trip PostgreSQL path** was subsequently verified against **PostgreSQL 16.15** in [GitHub Actions run 40227233022](https://github.com/JacobCCMorgan/da-e01-fuel-efficiency-analytics/actions/runs/40227233022), commit `55b6831eaa7f44849aad39537288654ba04cb701`. All 79 tests passed with zero skips. The workflow atomically loaded **8,193 records across 15 operational tables**, extracted one repeatable-read snapshot and completed full HTTP intake, DuckDB analysis and quality checks. [CI evidence](../validation/ci_full_run_40227233022.json) records the service version and execution scope.

The downloaded database's **330 canonical fields across 26 tables** exactly match the local reference under documented logical normalization, including provenance and availability times. The release now delivers this verified PostgreSQL-built database and its exact operational extract. [Adoption evidence](../validation/database_adoption.json) and the [full canonical comparison](../validation/ci_full_canonical_comparison_40227233022.json) bind the database hash and explain why the existing equivalent analytical report was retained. Local HTTP receipts remain separate evidence of a local replay of the same source snapshot; they are not relabelled as remote receipt timestamps.

Final source verification also passed in [run 40229112753](https://github.com/JacobCCMorgan/da-e01-fuel-efficiency-analytics/actions/runs/40229112753), commit `e0992b650a1686bd19dd50b5950b923be97ab6e0`: **103 tests, zero skips/failures/errors**, followed by the full 1,800-trip PostgreSQL pipeline. The delivered database keeps its producing run `40227233022` and original artifact hash; a successful newer source run does not change that provenance.

The [final-source canonical comparison](../validation/ci_final_canonical_comparison_40229112753.json) passed: the final CI database and delivered database match across all 330 canonical fields in 26 tables. Binary DuckDB/Parquet bytes may differ with storage layout or row order; the comparison checks documented logical values, including provenance and time fields.
