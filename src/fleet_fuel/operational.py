"""Transactional PostgreSQL source with immutable keys and auditable extraction."""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .common import atomic_json, contract, ident, json_text, rows, utcnow


OPERATIONAL_TABLES = {
    "core_tenant", "core_vehicle", "core_device", "core_vehicle_device_assignment",
    "fuel_vehicle_context", "fuel_task_assignment", "fuel_purchase_line",
    "fuel_card_assignment", "fuel_station", "fuel_tank_scope",
    "fuel_inventory_measurement", "fuel_movement", "fuel_statement_control",
    "fuel_output_review", "fuel_action_followup",
}


class ImmutableRecordError(RuntimeError):
    """An existing technical key was reused for different source content."""


def connection_string():
    dsn = os.environ.get("FUEL_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError(
            "Set FUEL_POSTGRES_DSN for the PostgreSQL service; snapshot mode does not require it."
        )
    return dsn


def source_schema():
    """Allow isolated integration-test schemas without dropping a user's data."""
    name = os.environ.get("FUEL_POSTGRES_SCHEMA", "fleet_ops")
    if not name or len(name.encode("utf-8")) > 63:
        raise ValueError("PostgreSQL schema name must contain 1–63 UTF-8 bytes")
    return name


def postgres_type(field):
    source = field["type"].upper()
    return {"DOUBLE": "DOUBLE PRECISION", "JSON": "JSONB"}.get(source, source)


def source_values(row, fields):
    return [
        Jsonb(row.get(f["name"]))
        if f["type"].upper() == "JSON" and row.get(f["name"]) is not None
        else row.get(f["name"])
        for f in fields
    ]


def bootstrap(root: Path) -> dict:
    """Load one source release atomically; repeat identical releases safely.

    A correction must use a new versioned primary key. Mutating an already
    published row is rejected, including disagreement between its typed value
    and its immutable change-log payload. No success manifest is written when
    any table fails. The transaction also covers schema/table creation.
    """
    root = Path(root)
    c = contract(root)
    schema_name = source_schema()
    schema = ident(schema_name)
    table_specs = [t for t in c["tables"] if t["name"] in OPERATIONAL_TABLES]
    source = {
        t["name"]: list(rows(root / "data/raw/tables" / f'{t["name"]}.jsonl'))
        for t in table_specs
    }
    wanted = {
        row["provenance_id"]
        for records in source.values()
        for row in records
        if row.get("provenance_id")
    }
    available = {
        row["provenance_id"]: row["available_time"]
        for row in rows(root / "data/raw/tables/provenance_record.jsonl")
        if row["provenance_id"] in wanted
    }
    counts = {}
    inserted = 0
    with psycopg.connect(connection_string(), connect_timeout=5) as con:
        # Serializing this writer also preserves committed change-cursor order.
        con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (schema_name,))
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        con.execute(
            f"CREATE TABLE IF NOT EXISTS {schema}.change_log ("
            "change_id BIGSERIAL PRIMARY KEY,canonical_table TEXT NOT NULL,"
            "record_key TEXT NOT NULL,payload JSONB NOT NULL,"
            "available_time TIMESTAMPTZ,UNIQUE(canonical_table,record_key))"
        )
        for t in table_specs:
            name = t["name"]
            table = f"{schema}.{ident(name)}"
            fields = [f for f in c["fields"] if f["table"] == name]
            definitions = ",".join(
                ident(f["name"]) + " " + postgres_type(f)
                + (" NOT NULL" if not f.get("nullable", True) else "")
                for f in fields
            )
            pk = ",".join(ident(k) for k in t["primary_key"])
            con.execute(f"CREATE TABLE IF NOT EXISTS {table} ({definitions},PRIMARY KEY ({pk}))")
            cols = ",".join(ident(f["name"]) for f in fields)
            slots = ",".join(["%s"] * len(fields))
            cast_slots = ",".join("%s::" + postgres_type(f) for f in fields)
            predicate = " AND ".join(ident(k) + "=%s" for k in t["primary_key"])
            for row in source[name]:
                key_values = [row[k] for k in t["primary_key"]]
                key = json_text(key_values)
                values = source_values(row, fields)
                prior = con.execute(
                    f"SELECT payload = %s::jsonb FROM {schema}.change_log "
                    "WHERE canonical_table=%s AND record_key=%s",
                    (Jsonb(row), name, key),
                ).fetchone()
                if prior is not None and not prior[0]:
                    raise ImmutableRecordError(f"Immutable source content changed: {name} {key}")
                existing = con.execute(
                    f"SELECT ROW({cols}) IS NOT DISTINCT FROM ROW({cast_slots}) "
                    f"FROM {table} WHERE {predicate}",
                    (*values, *key_values),
                ).fetchone()
                if existing is not None and not existing[0]:
                    raise ImmutableRecordError(f"Typed source row changed: {name} {key}")
                if (prior is None) != (existing is None):
                    raise ImmutableRecordError(f"Source/change-log disagreement: {name} {key}")
                if existing is None:
                    con.execute(f"INSERT INTO {table} ({cols}) VALUES ({slots})", values)
                    timestamp = available.get(row.get("provenance_id"))
                    con.execute(
                        f"INSERT INTO {schema}.change_log "
                        "(canonical_table,record_key,payload,available_time) VALUES (%s,%s,%s,%s)",
                        (name, key, Jsonb(row), timestamp),
                    )
                    inserted += 1
            counts[name] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        version = con.execute("SELECT version()").fetchone()[0]
        watermark = con.execute(
            f"SELECT coalesce(max(change_id),0) FROM {schema}.change_log"
        ).fetchone()[0]
    result = {
        "status": "executed", "engine": version, "schema": schema_name,
        "rows": counts, "inserted_records": inserted, "watermark": watermark,
        "executed_at": utcnow(), "source_kind": "synthetic_operational_postgresql",
        "transaction": "all_tables_atomic", "immutable_key_policy": "reject_conflicting_payload",
    }
    atomic_json(root / "validation/postgres_bootstrap.json", result)
    return result


def extract(root: Path) -> Path:
    """Publish all tables from one read-only repeatable-read snapshot atomically."""
    root = Path(root)
    base = root / "data/postgres_extract"
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=base))
    c = contract(root)
    schema_name = source_schema()
    schema = ident(schema_name)
    counts = {}
    try:
        with psycopg.connect(connection_string(), connect_timeout=5) as con:
            with con.transaction():
                con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                watermark = con.execute(
                    f"SELECT coalesce(max(change_id),0) FROM {schema}.change_log"
                ).fetchone()[0]
                for t in c["tables"]:
                    name = t["name"]
                    if name not in OPERATIONAL_TABLES:
                        continue
                    cols = [f["name"] for f in c["fields"] if f["table"] == name]
                    sql = (
                        "SELECT " + ",".join(ident(n) for n in cols)
                        + f" FROM {schema}.{ident(name)} ORDER BY "
                        + ",".join(ident(k) for k in t["primary_key"])
                    )
                    n = 0
                    with con.cursor(name="extract_" + name) as cursor:
                        cursor.execute(sql)
                        with (staging / (name + ".jsonl")).open("w") as stream:
                            for values in cursor:
                                stream.write(json_text(dict(zip(cols, values))) + "\n")
                                n += 1
                    counts[name] = n
        published = base / f"snapshot-{watermark}-{uuid.uuid4().hex[:12]}"
        os.replace(staging, published)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    atomic_json(root / "validation/postgres_extract.json", {
        "status": "executed", "schema": schema_name, "snapshot_watermark": watermark,
        "directory": str(published.relative_to(root)), "rows": counts,
        "extracted_at": utcnow(), "transaction": "repeatable_read_read_only",
    })
    return published


def changes_since(last_change_id: int, page_size: int = 1000) -> list[dict]:
    """Return an exclusive, monotonically ordered cursor page from committed rows."""
    if isinstance(last_change_id, bool) or not isinstance(last_change_id, int):
        raise ValueError("change cursor must be an integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise ValueError("page size must be an integer")
    if last_change_id < 0 or not 1 <= page_size <= 10000:
        raise ValueError("invalid change cursor/page size")
    schema = ident(source_schema())
    with psycopg.connect(connection_string(), connect_timeout=5) as con:
        data = con.execute(
            f"SELECT change_id,canonical_table,record_key,payload FROM {schema}.change_log "
            "WHERE change_id>%s ORDER BY change_id LIMIT %s",
            (last_change_id, page_size),
        ).fetchall()
    return [dict(zip(["change_id", "table", "record_key", "payload"], row)) for row in data]
