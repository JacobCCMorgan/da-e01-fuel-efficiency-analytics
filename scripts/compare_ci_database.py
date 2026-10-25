#!/usr/bin/env python3
"""Compare a full PostgreSQL-built CI artifact against the local reference DB.

Database byte identity is not required because physical layouts can differ.
Every canonical field value, including provenance and availability timestamps,
must match after the shared logical-hash normalization. This command only reads
databases and writes comparison evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import duckdb


# Load the sibling by path so CLI and test imports use the exact same helper,
# regardless of current working directory or Python package search paths.
_helper_spec = importlib.util.spec_from_file_location(
    "fuel_verify_rebuild", Path(__file__).with_name("verify_rebuild.py")
)
_helper = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper)
logical_table_hash = _helper.logical_table_hash
SET_JSON_FIELDS = _helper.SET_JSON_FIELDS


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def identities(connection, name, primary_key):
    columns = ','.join(quoted(column) for column in primary_key)
    cursor = connection.execute(
        f'SELECT {columns} FROM normalized.{quoted(name)} ORDER BY {columns}'
    )
    digest = hashlib.sha256()
    count = 0
    while batch := cursor.fetchmany(10000):
        for row in batch:
            digest.update((json.dumps(row, separators=(',', ':'), default=str) + '\n').encode())
        count += len(batch)
    return {'rows': count, 'primary_key_sha256': digest.hexdigest()}


def records(connection, query):
    result = connection.execute(query)
    names = [column[0] for column in result.description]
    return [dict(zip(names, values)) for values in result.fetchall()]


def analytical_outcomes(connection):
    return {
        'fleet_totals': records(connection, """
            SELECT sum(fuel_used_l) fuel_used_l,
              sum(distance_travelled_km) distance_km,
              (sum(distance_travelled_km)/1.609344)/(sum(fuel_used_l)/3.785411784) fleet_mpg,
              sum(valid_paired_seconds)/nullif(sum(expected_observation_seconds),0) measurement_coverage,
              sum(comparable_fuel_amount) purchase_amount_usd,
              sum(purchase_quantity_l) purchased_l,
              sum(benchmark_amount_gap) market_background_gap_usd
            FROM analytics.fleet_weekly WHERE report_view='retrospective'
        """)[0],
        'financial_exclusions': records(connection, """
            SELECT financial_status,count(*) rows FROM analytics.purchase_detail
            WHERE report_view='retrospective' GROUP BY financial_status ORDER BY financial_status
        """),
        'market_sources': records(connection, """
            SELECT report_view,benchmark_view,count(*) rows,sum(effective_quantity_l) purchase_l
            FROM analytics.purchase_detail WHERE financial_status='comparable'
            GROUP BY report_view,benchmark_view ORDER BY report_view,benchmark_view
        """),
        'followup_statuses': records(connection, """
            SELECT comparison_status,count(*) cases FROM analytics.followup_evaluation
            GROUP BY comparison_status ORDER BY comparison_status
        """),
        'inventory_statuses': records(connection, """
            SELECT reconciliation_status,count(*) periods FROM analytics.inventory_reconciliation
            GROUP BY reconciliation_status ORDER BY reconciliation_status
        """),
    }


def differences(left, right, path='outcomes'):
    found = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                found.append({'field': path + '.' + key, 'reason': 'missing_key'})
            else:
                found.extend(differences(left[key], right[key], path + '.' + key))
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            found.append({'field': path, 'reason': 'different_group_count', 'reference': len(left), 'candidate': len(right)})
        else:
            for index, (a, b) in enumerate(zip(left, right)):
                found.extend(differences(a, b, f'{path}[{index}]'))
    elif isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
        if not math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-6):
            found.append({'field': path, 'reference': left, 'candidate': right, 'reason': 'numeric_difference'})
    elif left != right:
        found.append({'field': path, 'reference': left, 'candidate': right, 'reason': 'value_difference'})
    return found


def canonical_checks(reference, candidate, contract):
    """Compare every contract field, ordered by the declared primary key."""
    expected = {table['name']: table for table in contract['tables']}
    for connection in (reference, candidate):
        connection.execute("SET TimeZone='UTC'")
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        actual = {row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='normalized'"
        ).fetchall()}
        if actual != set(expected):
            raise ValueError(f'Canonical table mismatch: missing={set(expected)-actual}, extra={actual-set(expected)}')
    checks = []
    for name, table in expected.items():
        fields = [field for field in contract['fields'] if field['table'] == name]
        if not fields:
            raise ValueError(f'Canonical table has no field definitions: {name}')
        a = identities(reference, name, table['primary_key'])
        b = identities(candidate, name, table['primary_key'])
        a_values = logical_table_hash(reference, table, fields)
        b_values = logical_table_hash(candidate, table, fields)
        a['logical_values_sha256'] = a_values['sha256']
        b['logical_values_sha256'] = b_values['sha256']
        if a['rows'] != a_values['rows'] or b['rows'] != b_values['rows']:
            raise RuntimeError(f'Row count changed while comparing: {name}')
        checks.append({
            'table': name, 'field_count': len(fields),
            'fields': [field['name'] for field in fields],
            'reference': a, 'candidate': b, 'matches': a == b,
        })
        print('canonical field comparison:', name, 'equal' if a == b else 'DIFFERENT', flush=True)
    return checks


def compare(reference, candidate, contract_path):
    contract = json.loads(contract_path.read_text())
    with duckdb.connect(str(reference), read_only=True) as ref, duckdb.connect(str(candidate), read_only=True) as new:
        checks = canonical_checks(ref, new, contract)
        baseline = analytical_outcomes(ref)
        rebuilt = analytical_outcomes(new)
    mismatches = differences(baseline, rebuilt)
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed' if all(row['matches'] for row in checks) and not mismatches else 'failed',
        'reference_database': 'reference', 'candidate_database': 'candidate',
        'database_label_policy': 'Logical roles only; no private filesystem paths are published.',
        'reference_sha256': sha256(reference), 'candidate_sha256': sha256(candidate),
        'contract_sha256': sha256(contract_path),
        'canonical_table_count': len(contract['tables']),
        'canonical_field_count': len(contract['fields']), 'table_checks': checks,
        'reference_outcomes': baseline, 'candidate_outcomes': rebuilt,
        'outcome_differences': mismatches,
        'numeric_tolerance': {'absolute': 1e-6, 'relative': 1e-10, 'applies_to': 'Analytical aggregate outcomes only; canonical value hashes are exact.'},
        'scope': 'All contract fields in all canonical tables, plus primary-key identities and analytical aggregate outcomes.',
        'logical_normalization': {
            'implementation': 'scripts/verify_rebuild.py::logical_table_hash',
            'row_order': 'Declared canonical primary keys',
            'json_objects': 'Sorted keys',
            'unordered_json_arrays': sorted(SET_JSON_FIELDS),
            'timestamps': 'UTC representation; all event, availability, retrieval and as-of values preserved.',
        },
        'canonical_field_exclusions': [],
        'excluded_from_equality': [
            'Physical database page layout and storage encoding',
            'Runtime files outside canonical tables, such as source-extract directory locations',
        ],
        'limitations': 'Logical equivalence does not replace independent business-rule tests or establish real-fleet effectiveness.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-db', type=Path, required=True)
    parser.add_argument('--candidate-db', type=Path, required=True)
    parser.add_argument('--contract', type=Path, default=Path('contracts/da_e01_contract.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.reference_db, args.candidate_db, args.contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + '\n')
    print(json.dumps({'status': result['status'], 'canonical_tables': result['canonical_table_count'], 'evidence': args.output.name}))
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
