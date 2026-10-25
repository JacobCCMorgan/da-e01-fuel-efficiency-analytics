# ELD event API and ingestion contract

This project executes HTTP ingestion against a local, explicitly simulated ELD source. The source serves the generated `data/raw/events.jsonl` file. It exercises pagination, late availability, revisions, duplicate delivery, quarantine and restart behavior without claiming a vendor connection, native J1939/J1708/OBD frame decoder or ELD certification.

The implementation is defined by [event_api.py](../src/fleet_fuel/event_api.py), [ingestion.py](../src/fleet_fuel/ingestion.py) and the field contract in [da_e01_contract.json](../contracts/da_e01_contract.json). [test_ingestion.py](../tests/test_ingestion.py) contains independent transport fixtures.

## Start and consume the service

After source generation, run these commands from the installed project environment:

```bash
python -m fleet_fuel.cli --root . serve --port 8765
```

In another terminal:

```bash
curl http://127.0.0.1:8765/health
curl 'http://127.0.0.1:8765/v1/events?limit=2'
python -m fleet_fuel.cli --root . ingest --url http://127.0.0.1:8765
```

`serve` binds to `127.0.0.1`; its CLI default port is `8765`. The Python `serve(root)` context manager selects an available local port by default. Both `ingest` without `--url` and the complete `run` command start and close this local service automatically and make actual HTTP requests to it.

The service has no authentication, authorization or TLS layer. Its deployment boundary is the local demonstration process. It serves the combined source snapshot; tenant consistency is checked by ingestion, not enforced through per-tenant API permissions. Only the two GET routes below are part of this JSON contract.

## Routes and parameters

| Route | Behavior | Successful response |
|---|---|---|
| `GET /health` | Reads the current index count and identifies the snapshot selected when the service started. | HTTP 200 with `status`, `source_kind`, `snapshot`, `total_events`. |
| `GET /v1/events` | Returns one page from the immutable source snapshot in sequence order. | HTTP 200 with `source_kind`, `snapshot`, `items`, `next_cursor`, `checkpoint_cursor`. |

All JSON responses sent by these routes use `application/json; charset=utf-8`. `source_kind` is always `synthetic_eld_api`. The health `status` is `ok`. `snapshot` is the SHA-256 of the source file bytes. `total_events` counts nonblank source lines, including duplicate attempts and malformed records; it is not the count of valid canonical observations.

| `/v1/events` parameter | Default | Meaning and limits |
|---|---|---|
| `limit` | `2000` | Integer from 1 through 10,000, inclusive. The service reads one extra match to determine whether another page exists. |
| `cursor` | No prior sequence | Opaque continuation token bound to the source SHA-256 and the last returned sequence. Reuse the returned token unchanged. |
| `available_since` | Empty string | Inclusive instant filter on `available_time`; requires an ISO timestamp with timezone and normalizes offsets to UTC. |
| `test_fault` | None | Test-only fault injection: `once_429`, `once_503` or `once_slow`. It is not an operational data filter. |

The first value is used when a recognized parameter is repeated. Unrecognized query parameters do not change the query. The standard ingestion client sends `limit`, `cursor` and, in tests, `test_fault`; it does not currently expose `available_since` through the CLI.

Both the timestamp filter and valid indexed availability times normalize to fixed-width UTC microsecond keys. Equivalent offsets therefore select the same events; a timezone-free filter is rejected. Original timestamps remain unchanged in the event envelopes. Keep the filter unchanged throughout a pagination session: the cursor binds the snapshot and sequence, not the filter or page size.

## Snapshot, ordering and cursor rules

At startup the service hashes `data/raw/events.jsonl` and prepares `data/api/event_index.sqlite`. It reuses an index only when the stored source SHA-256 and index-format version match and the event table exists. A different source file produces a new snapshot and rebuilt index. Source and index files must remain unchanged while a service instance is serving that snapshot.

The index orders attempts by normalized UTC availability time, `event_id`, numeric `revision`, then original `source_line`. The fixed-width UTC time keys preserve chronological ordering under text comparison. Invalid or missing availability times sort first and remain subject to ingestion quarantine. Each resulting row receives a stable integer `source_sequence` within the same snapshot and ordering version. Equal availability timestamps therefore remain separate positions; resume does not depend on a timestamp-only watermark.

Index-format version changes invalidate the index cache, but are not encoded in cursors or snapshot-ledger directory names. If upgrading an existing mixed-offset source from an older ordering implementation, use a fresh ingestion workspace. `--from-start` preserves prior receipts and therefore does not reset sequence identities. The current frozen UTC source retains its ordering under this normalization change.

A returned item has three fields:

| Field | Meaning |
|---|---|
| `source_sequence` | Snapshot-local position used for pagination and receipt identity. |
| `source_line` | One-based original file line, preserving the location of duplicate and invalid attempts. |
| `envelope` | The source event object, or a malformed-line wrapper that retains the original text. |

The cursor encodes the snapshot and last sequence. Clients should treat it as opaque; it is not encrypted, signed or an authorization token. A page selects `seq > last_sequence`, applies the availability filter, and orders by sequence.

`next_cursor` is non-null only when another matching row exists. `checkpoint_cursor` is always returned, including at the end of the stream or for an empty page. On an empty page, it retains the prior sequence. Repeated requests using the same snapshot, ordering version, cursor, filter and limit return the same page. A new source SHA-256 makes an old cursor invalid; the supported client starts a separate snapshot ledger rather than mixing its records with the previous snapshot.

## Event envelope and revisions

The consumer requires these envelope keys:

| Field | Ingestion rule |
|---|---|
| `event_id` | Nonblank string. The event/revision namespace must be unique across the snapshot, including tenants. |
| `revision` | Positive integer; booleans are rejected. |
| `event_time` | ISO timestamp with timezone, representing event occurrence. |
| `available_time` | ISO timestamp with timezone, representing when this version became obtainable. It drives paging order independently of occurrence time. |
| `tenant_id` | Nonblank string that must equal `payload.tenant_id`. |
| `table` | Only `fuel_counter_observation` is accepted through this API in DA-E01. |
| `payload` | Object limited to the canonical table's declared columns, then validated for required fields, explicit enums, numeric finiteness and timestamp rules. |

The observation primary key is `(tenant_id, counter_observation_id)`. Its non-null fields are `provenance_id`, `tenant_id`, `counter_observation_id`, `device_id` and `signal_definition_id`. Other field-specific null conditions remain governed by the shared contract and downstream quality checks; an accepted HTTP envelope alone does not prove every relational or business rule.

Payloads containing validation answers or simulator-truth fields such as `true_fuel_l` or `expected_waste_label` are quarantined as `forbidden_payload_field`. Any other undeclared payload column is quarantined as `unknown_payload_field`. These records never enter the accepted staging file; their complete original envelopes remain in quarantine. Adding a supplier column requires an explicit reviewed contract change.

The closed column set applies to payload keys, compared case-sensitively with canonical names; nullable columns may be omitted. Forbidden-name detection runs first and is case-insensitive. [input_policy.py](../src/fleet_fuel/input_policy.py) defines the complete forbidden names and prefixes. Extra top-level envelope metadata is retained and is outside this payload-column rule.

Revisions are retained as versioned source observations. A higher envelope revision is not permission to overwrite a previously accepted canonical key. A correction that changes payload values must use the versioned observation identity defined by the source contract. The analytical stage selects eligible versions as of each report cutoff.

## Receipts, idempotence and quarantine

Each snapshot has its own SQLite receipt ledger at `data/ingestion/<snapshot>/receipts.sqlite`. SQLite here stores source paging and ingestion evidence; the operational database and analytical DuckDB have separate roles.

| Situation within one snapshot | Disposition | Reason |
|---|---|---|
| Receipt already exists for `(snapshot, source_sequence)` | No new receipt or canonical row | Counted as `already_received` in the current call. |
| Same `(event_id, revision)` and payload SHA-256 | `duplicate` | `same_event_revision` |
| Same `(event_id, revision)`, different payload SHA-256 | `quarantined` | `conflicting_event_revision` |
| New event identity, existing canonical key and identical payload SHA-256 | `duplicate` | `same_canonical_record` |
| New event identity, existing canonical key and changed payload SHA-256 | `quarantined` | `immutable_key_conflict` |
| New valid identity and canonical key | `accepted` | Stored once in the accepted ledger. |

The payload hash uses normalized JSON serialization with sorted object keys. Receipt identity is separate from payload identity: every new source attempt receives an audit disposition, even when it does not create a new accepted observation.

Malformed source JSON becomes an envelope with `transport_error: invalid_json` and `raw_line`; ingestion quarantines it as `invalid_envelope` without dropping the original line. Other validation reasons include `unsupported_table`, `invalid_event_identity`, `tenant_mismatch`, `timezone_missing`, `required_value_missing`, `invalid_enum`, `invalid_number`, `missing_primary_key` and `invalid_payload_type`.

Each page's receipts, accepted identities and checkpoint are committed in one transaction. A restart resumes from the committed checkpoint. `--from-start` ignores the checkpoint for reading but retains the ledger, so previously received attempts do not produce duplicate side effects. It does not delete audit history or create a fresh snapshot.

After ingestion:

- Accepted payloads are exported in canonical-key order to `data/staged/events/fuel_counter_observation.jsonl` through a temporary file and atomic replacement.
- Rejected envelopes are exported to `data/ingestion/quarantine.jsonl`; the snapshot-specific SQLite ledger retains their receipt history.
- `validation/ingestion_report.json` records the source SHA-256, expected source attempts, dispositions, accepted count, retries, checkpoint and completion state.

Completion requires exhaustion of `next_cursor`. Reconciliation compares all accepted, duplicate and quarantined receipts against `/health.total_events`. A deliberately partial test run can have `complete: false` and fail full-source reconciliation until it resumes. The current staged and quarantine JSONL exports represent the current snapshot; prior snapshot ledgers remain separately available.

## HTTP failures and retry policy

| Condition | HTTP response | Behavior |
|---|---|---|
| Unknown GET path | 404, `{"error":"not_found"}` | No page returned. |
| Invalid limit or datetime query, with no cursor parameter | 400, `{"error":"invalid_query_or_snapshot_cursor"}` | Query rejected. |
| Invalid query when a cursor parameter is present, including a different snapshot | 409, `{"error":"invalid_query_or_snapshot_cursor"}` | Client must inspect the query or restart against the correct snapshot. This status is not restricted to snapshot mismatch. |
| Injected `once_429` or `once_503` | 429 or 503, `{"error":"simulated_transient"}`, `Retry-After: 0` | First request for that fault/cursor position fails. |
| Injected `once_slow` | First response delayed by 0.15 seconds | A sufficiently short client timeout triggers the timeout retry path. |

Fault state is scoped to a service instance and keyed by `(test_fault, last_sequence)`. “Once” means once at that cursor position, not once over the whole multi-page run. The retry tests deliberately use a single page. Restarting the server resets this test state.

The page client allows four attempts total for HTTP 429, 500, 502, 503 and 504, request timeouts and connection errors. Between attempts it waits 0.05, 0.10 and 0.20 seconds. It uses this bounded schedule rather than interpreting `Retry-After`. Exhaustion raises an error and leaves the last committed checkpoint intact. Other HTTP failures are raised without this retry loop. The initial `/health` request has the configured timeout but does not use the page retry loop. Default request timeout is 15 seconds.

## Verification and boundaries

[The ingestion tests](../tests/test_ingestion.py) check independently specified duplicate/quarantine counts, exact replay without new accepted rows, resume across equal availability times, changed-snapshot separation, wrong-snapshot cursor rejection, invalid page size, preservation of malformed source text, malformed scalar types, forbidden or unknown payload columns, equivalent-offset timestamp filters, rejection of timezone-free filters, and successful retries after each of the three injected faults. Their fixtures assert expected counts rather than using the production parser's output as the expected answer.

The full pipeline verifies source-attempt reconciliation before building the analytical database. Database validation then checks the canonical schema, keys, references, enums, null-state explanations and calculation constraints. An HTTP success is therefore a transport result, not a claim that the observation is analytically usable.

This contract covers a frozen local snapshot and a single ingestion writer. It does not claim a continuously changing vendor feed, cursor authentication, concurrent consumer coordination, production rate-limit compliance, live vehicle connectivity or regulatory certification. Public EIA price acquisition uses its separate HTTPS file adapter and is not represented as an ELD API endpoint.
