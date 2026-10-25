"""Real PostgreSQL integration; skipped only when no service DSN is configured.

Each case owns a random schema and removes only that schema. These checks do
not treat a working snapshot pipeline or a trivial SQL query as PG integration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import uuid

import psycopg
import pytest

from fleet_fuel import operational
from fleet_fuel.common import ident, rows
from fleet_fuel.simulation import generate


requires_postgres = pytest.mark.skipif(
    not os.getenv("FUEL_POSTGRES_DSN"), reason="PostgreSQL service not configured"
)
ROOT = Path(__file__).resolve().parents[1]


def rewrite(path, records):
    path.write_text("".join(json.dumps(row) + "\n" for row in records))


@pytest.fixture(scope="module")
def sample_release(tmp_path_factory):
    root = tmp_path_factory.mktemp("postgres-sample-release")
    for directory in ("config", "contracts"):
        (root / directory).mkdir()
    shutil.copy(ROOT / "config/simulation.json", root / "config")
    shutil.copy(ROOT / "contracts/da_e01_contract.json", root / "contracts")
    generate(root, profile="smoke")
    return root


@pytest.fixture
def source(sample_release, tmp_path, monkeypatch):
    shutil.copytree(sample_release / "contracts", tmp_path / "contracts")
    shutil.copytree(sample_release / "data/raw/tables", tmp_path / "data/raw/tables")
    schema = "fuel_test_" + uuid.uuid4().hex
    monkeypatch.setenv("FUEL_POSTGRES_SCHEMA", schema)
    yield tmp_path, schema
    # This name is created by the fixture, never read from a user's environment.
    assert schema.startswith("fuel_test_")
    with psycopg.connect(operational.connection_string(), connect_timeout=5) as con:
        con.execute(f"DROP SCHEMA IF EXISTS {ident(schema)} CASCADE")


@requires_postgres
def test_bootstrap_repeat_is_idempotent_and_extract_is_complete(source):
    root, schema = source
    first = operational.bootstrap(root)
    again = operational.bootstrap(root)
    assert first["rows"] == again["rows"]
    assert set(first["rows"]) == operational.OPERATIONAL_TABLES
    assert first["inserted_records"] == sum(first["rows"].values())
    assert again["inserted_records"] == 0
    assert first["watermark"] == again["watermark"]
    snapshot = operational.extract(root)
    for table, expected_count in first["rows"].items():
        data = list(rows(snapshot / f"{table}.jsonl"))
        assert len(data) == expected_count
    followup = next(rows(snapshot / "fuel_action_followup.jsonl"))
    assert isinstance(followup["followup_task_mix"], list)
    assert snapshot.is_dir()
    assert not list(snapshot.parent.glob(".pending-*"))
    evidence = json.loads((root / "validation/postgres_extract.json").read_text())
    assert evidence["snapshot_watermark"] == first["watermark"]
    assert evidence["transaction"] == "repeatable_read_read_only"
    assert "postgresql://" not in json.dumps(first)


@requires_postgres
def test_reusing_an_immutable_key_with_changed_payload_fails(source):
    root, schema = source
    before = operational.bootstrap(root)
    path = root / "data/raw/tables/core_tenant.jsonl"
    data = list(rows(path))
    original_name = data[0]["tenant_name"]
    data[0]["tenant_name"] = "Changed without a versioned key"
    rewrite(path, data)
    with pytest.raises(operational.ImmutableRecordError, match="Immutable source content changed"):
        operational.bootstrap(root)
    with psycopg.connect(operational.connection_string()) as con:
        assert con.execute(
            f"SELECT tenant_name FROM {ident(schema)}.core_tenant WHERE tenant_id='T01'"
        ).fetchone()[0] == original_name
        assert con.execute(
            f"SELECT max(change_id) FROM {ident(schema)}.change_log"
        ).fetchone()[0] == before["watermark"]


@requires_postgres
def test_incremental_cursor_returns_new_committed_rows_once(source):
    root, schema = source
    before = operational.bootstrap(root)
    path = root / "data/raw/tables/core_device.jsonl"
    data = list(rows(path))
    for suffix in ("98", "99"):
        data.append({**data[0], "device_id": "T01-D" + suffix})
    rewrite(path, data)
    after = operational.bootstrap(root)
    assert after["inserted_records"] == 2
    first_page = operational.changes_since(before["watermark"], page_size=1)
    assert len(first_page) == 1
    second_page = operational.changes_since(first_page[-1]["change_id"], page_size=1)
    assert len(second_page) == 1
    assert first_page[0]["change_id"] < second_page[0]["change_id"]
    assert {first_page[0]["payload"]["device_id"], second_page[0]["payload"]["device_id"]} == {"T01-D98", "T01-D99"}
    assert operational.changes_since(second_page[-1]["change_id"]) == []


@requires_postgres
def test_failure_rolls_back_earlier_table_rows_and_change_log(source):
    root, schema = source
    before = operational.bootstrap(root)
    tenants = root / "data/raw/tables/core_tenant.jsonl"
    records = list(rows(tenants))
    rewrite(tenants, [{**records[0], "tenant_id": "T99"}] + records)
    devices = root / "data/raw/tables/core_device.jsonl"
    records = list(rows(devices))
    records[0]["device_model"] = "Unversioned incompatible replacement"
    rewrite(devices, records)
    with pytest.raises(operational.ImmutableRecordError):
        operational.bootstrap(root)
    with psycopg.connect(operational.connection_string()) as con:
        assert con.execute(
            f"SELECT count(*) FROM {ident(schema)}.core_tenant WHERE tenant_id='T99'"
        ).fetchone()[0] == 0
        assert con.execute(f"SELECT count(*) FROM {ident(schema)}.change_log").fetchone()[0] == sum(before["rows"].values())
        assert con.execute(f"SELECT max(change_id) FROM {ident(schema)}.change_log").fetchone()[0] == before["watermark"]


@requires_postgres
def test_typed_row_and_change_log_disagreement_is_not_silently_accepted(source):
    root, schema = source
    operational.bootstrap(root)
    with psycopg.connect(operational.connection_string()) as con:
        con.execute(
            f"UPDATE {ident(schema)}.core_tenant SET tenant_name='Unlogged direct mutation' WHERE tenant_id='T01'"
        )
    with pytest.raises(operational.ImmutableRecordError, match="Typed source row changed"):
        operational.bootstrap(root)


@requires_postgres
def test_extract_retains_one_snapshot_when_another_connection_commits(source, monkeypatch):
    root, schema = source
    before = operational.bootstrap(root)
    path = root / "data/raw/tables/core_device.jsonl"
    data = list(rows(path))
    rewrite(path, data + [{**data[0], "device_id": "T01-D99"}])
    original_json = operational.json_text
    committed = False

    def commit_during_first_table_serialization(value):
        nonlocal committed
        if not committed:
            committed = True
            # extract() has already read its watermark. This uses a second
            # real connection while the read-only snapshot is still open.
            operational.bootstrap(root)
        return original_json(value)

    monkeypatch.setattr(operational, "json_text", commit_during_first_table_serialization)
    snapshot = operational.extract(root)
    assert committed
    assert len(list(rows(snapshot / "core_device.jsonl"))) == before["rows"]["core_device"]
    with psycopg.connect(operational.connection_string()) as con:
        assert con.execute(f"SELECT count(*) FROM {ident(schema)}.core_device").fetchone()[0] == before["rows"]["core_device"] + 1
    evidence = json.loads((root / "validation/postgres_extract.json").read_text())
    assert evidence["snapshot_watermark"] == before["watermark"]


@pytest.mark.parametrize("cursor,page", [(-1, 1), (0, 0), (0, 10001), (True, 1), (0, False), (0.5, 1)])
def test_invalid_change_cursor_fails_before_opening_a_connection(cursor, page, monkeypatch):
    def unexpected_connection(*args, **kwargs):
        raise AssertionError("invalid request opened a database connection")
    monkeypatch.setattr(operational.psycopg, "connect", unexpected_connection)
    with pytest.raises(ValueError):
        operational.changes_since(cursor, page)
