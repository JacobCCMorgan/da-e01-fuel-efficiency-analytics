# Release packages and verification

The release separates rebuildable source from ready-to-query data. All archives use repository-relative paths, so the source and data ZIPs can be extracted into the same directory. The complete ZIP contains their union once. Packaging does not upload files, rerun analysis or claim that a remote delivery succeeded.

| Package | Intended use | Contents |
| --- | --- | --- |
| `DA-E01_v1_source.zip` | Review and rebuild independently | Code, contracts, configuration, SQL, tests, scripts, documentation, notebook, reports, figures, analytical CSVs, validation evidence and frozen public source evidence |
| `DA-E01_v1_data.zip` | Inspect the completed data release | PostgreSQL-built DuckDB, exact operational extract, generator-owned raw inputs, accepted staged events, normalized/derived Parquet, public evidence, active local HTTP receipt database, quarantine and key build manifests |
| `DA-E01_v1_complete.zip` | Obtain the entire project in one download | Deduplicated union of source and data package contents |
| `release_manifest.json` | Verify file membership and provenance | Per-file SHA-256, bytes, logical row counts where applicable, origin, license references, package membership and archive hashes |
| `SHA256SUMS.txt` | Check download integrity | Hashes of all three archives and the external release manifest |

Each ZIP contains its own `release_file_manifest.json`. That embedded manifest describes the package's files without creating a circular dependency on the archive's own checksum. The external manifest adds final archive hashes. Database logical-row counts describe canonical tables; receipt counts describe delivery attempts, not additional vehicle observations.

## Build the release

First finish the full pipeline, reports, notebook execution and tests. Close database writers and readers before packaging. Preserve the source snapshot and all validation records. The packager expects a completed full-profile `validation/run_manifest.json`, a passing canonical quality report, complete reconciled intake and normalized export manifest. JUnit must have at least one test and no failures/errors; skipped service tests remain recorded. Every nonempty notebook code cell must have an execution count and no error output.

Normalize machine-specific JUnit paths without changing results:

```bash
python scripts/sanitize_validation_paths.py --root .
```

The normalizer keeps the original XML in a private sibling work directory outside the deliverable. It changes only known absolute checkout prefixes to `./`, checks result identities/counts/timing/outcomes, and writes `validation/path_normalization.json` with original and portable hashes. The portable XML has a new checksum; the original hash must not be advertised as its current hash. Re-run normalization after producing new JUnit results.

Create and verify all archives:

```bash
python scripts/package_release.py --root .
```

Outputs appear under `artifacts/`. This command performs the following checks before publishing its completed archives:

1. Use explicit code/document directories and extension allowlists. Raw scenario files are selected only from `data/generation_manifest.json` ownership records, with matching hashes and sizes.
2. Select normalized exports from their manifest, staged inputs and the exact PostgreSQL extract from the build manifest, and only the active snapshot's local receipt database from the ingestion manifest. PostgreSQL build inputs must exactly match the executed extract manifest; every extract file hash is checked.
3. Reject unsafe paths, hidden temporary files, symlinks, credential-like content and absolute private machine paths. Inspect Word document XML as well as ordinary file bytes.
4. Require closed/checkpointed databases without nonempty WAL/shared-memory sidecars. Open DuckDB read-only to verify 26 canonical table counts against normalized manifests, and check SQLite integrity and receipt counts.
5. Verify that the DuckDB bytes still match the completed run's database hash. Count JSONL/CSV rows and read Parquet metadata for the manifest.
6. Write ZIP members in sorted order with fixed timestamps from the original synthetic release timestamp and fixed permissions. Identical input bytes yield identical archives; a changed execution log is a changed input.
7. Reopen every archive, verify exact allowlisted membership and recompute every member's SHA-256. Only after all three archives pass are the completed files published under `artifacts/`.

The packager does not redact or rewrite raw source evidence. If a private path appears outside the explicitly normalized JUnit export, packaging fails so the underlying artifact can be reviewed. It does not silently mark an unfinished test or unavailable service successful.

## What is intentionally omitted

- Hidden editor/temporary files, Python caches, environments, credentials, database WAL/shared-memory files and previous packaging work.
- Unowned leftovers under `data/raw/`, inactive HTTP receipt snapshots and stale receipt copies.
- `data/api/event_index.sqlite`, which is a rebuildable local-service cache of the included raw event file. Including it would duplicate the same events without adding source evidence.
- Git internals and prior ZIP archives.

The active receipt database is retained because delivery outcomes and checkpoints are evidence. The accepted staged file is retained because it is the exact analytical intake, even though it can also be rebuilt. These have different purposes from the omitted API index.

## Verify and use a downloaded package

In the directory containing the downloads:

```bash
sha256sum -c SHA256SUMS.txt
python -m zipfile -t DA-E01_v1_complete.zip
python -m zipfile -e DA-E01_v1_complete.zip DA-E01_v1
```

If you downloaded only one ZIP, compare that ZIP's SHA-256 with its matching line in `SHA256SUMS.txt`; the complete checksum command also expects the other listed files. Extract the source package to rebuild using the README instructions. Extract both source and data packages together, or the complete package, to inspect the ready database and execute the notebook without regenerating data first.

Files larger than 100 MiB are listed in `git_excluded_large_files` in the manifest. They belong in release/download storage rather than ordinary Git commits. The source repository retains the generator, contracts, frozen public inputs and build commands; a separate repository delivery log must record verified upload locations. Archive creation alone does not establish Google Drive or GitHub publication.

Data terms remain in [data/LICENSE.md](../data/LICENSE.md). Public EIA source evidence is separately identified and is not relicensed as fictional sample data. Analytical outputs can depend on both origins; consult provenance rather than treating a whole mixed database as one source.

## Verified database adoption

The ready database is the full-profile PostgreSQL CI artifact identified by `validation/database_adoption.json`. Its 26 tables and 330 fields match the independently rebuilt local reference; normalized Parquet was re-exported from the adopted database and quality checks re-executed. The exact 15-table operational extract is included. Local HTTP receipts are retained with explicit local-execution labels and matching snapshot/count checks; the CI intake evidence stays separate. Existing reports and notebook outputs were retained under the canonical-equivalence evidence, not represented as newly executed remote presentation steps.
