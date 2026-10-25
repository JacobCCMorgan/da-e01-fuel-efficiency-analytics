"""A matching row count and primary key must not hide changed source values."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_database_comparison', ROOT / 'scripts/compare_ci_database.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONTRACT = {
    'tables': [{'name': 'sample', 'primary_key': ['record_id']}],
    'fields': [
        {'table': 'sample', 'name': 'record_id', 'type': 'VARCHAR'},
        {'table': 'sample', 'name': 'amount', 'type': 'DECIMAL(18,6)'},
        {'table': 'sample', 'name': 'available_time', 'type': 'TIMESTAMPTZ'},
        {'table': 'sample', 'name': 'payload', 'type': 'JSON'},
        {'table': 'sample', 'name': 'input_provenance_ids', 'type': 'JSON'},
    ],
}


def database():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA normalized')
    con.execute('''CREATE TABLE normalized.sample (
      record_id VARCHAR,amount DECIMAL(18,6),available_time TIMESTAMPTZ,
      payload JSON,input_provenance_ids JSON)''')
    con.execute('INSERT INTO normalized.sample VALUES (?,?,?,?,?)', [
        'record-1', 100, '2025-01-01T00:00:00Z',
        json.dumps({'a': 1, 'b': [10, 20]}), json.dumps(['p1', 'p2']),
    ])
    return con


@pytest.mark.parametrize('mutation', [
    'UPDATE normalized.sample SET amount=101',
    'UPDATE normalized.sample SET amount=NULL',
    "UPDATE normalized.sample SET available_time='2025-01-01T00:00:01Z'",
    "UPDATE normalized.sample SET payload='{\"a\":1,\"b\":[20,10]}'",
])
def test_nonkey_value_change_fails_despite_identical_counts_and_keys(mutation):
    with database() as reference, database() as candidate:
        candidate.execute(mutation)
        check = module.canonical_checks(reference, candidate, CONTRACT)[0]
        assert check['reference']['rows'] == check['candidate']['rows'] == 1
        assert check['reference']['primary_key_sha256'] == check['candidate']['primary_key_sha256']
        assert check['reference']['logical_values_sha256'] != check['candidate']['logical_values_sha256']
        assert check['matches'] is False


def test_only_declared_unordered_json_sets_and_object_order_are_normalized():
    with database() as reference, database() as candidate:
        candidate.execute('UPDATE normalized.sample SET payload=?,input_provenance_ids=?', [
            '{"b":[10,20],"a":1}', '["p2","p1"]',
        ])
        check = module.canonical_checks(reference, candidate, CONTRACT)[0]
        assert check['field_count'] == 5
        assert check['matches'] is True
