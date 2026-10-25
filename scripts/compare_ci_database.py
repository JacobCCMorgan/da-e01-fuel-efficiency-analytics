#!/usr/bin/env python3
"""Compare a full PostgreSQL-built CI artifact against the local reference DB.

Byte identity is not required: runtime timestamps, physical DuckDB layouts and
source-extract paths differ. Canonical identities and analytical outcomes must
agree. This command only reads databases and writes comparison evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import duckdb


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


def compare(reference, candidate, contract_path):
    contract = json.loads(contract_path.read_text())
    expected = {table['name']: table for table in contract['tables']}
    checks = []
    with duckdb.connect(str(reference), read_only=True) as ref, duckdb.connect(str(candidate), read_only=True) as new:
        for connection in (ref, new):
            connection.execute("SET TimeZone='UTC'")
            connection.execute("SET memory_limit='512MB'")
            actual = {row[0] for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='normalized'"
            ).fetchall()}
            if actual != set(expected):
                raise ValueError(f'Canonical table mismatch: missing={set(expected)-actual}, extra={actual-set(expected)}')
        for name, table in expected.items():
            a = identities(ref, name, table['primary_key'])
            b = identities(new, name, table['primary_key'])
            checks.append({'table': name, 'reference': a, 'candidate': b, 'matches': a == b})
        baseline = analytical_outcomes(ref)
        rebuilt = analytical_outcomes(new)
    mismatches = differences(baseline, rebuilt)
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed' if all(row['matches'] for row in checks) and not mismatches else 'failed',
        'reference_database': str(reference), 'candidate_database': str(candidate),
        'reference_sha256': sha256(reference), 'candidate_sha256': sha256(candidate),
        'canonical_table_count': len(expected), 'table_checks': checks,
        'reference_outcomes': baseline, 'candidate_outcomes': rebuilt,
        'outcome_differences': mismatches,
        'numeric_tolerance': {'absolute': 1e-6, 'relative': 1e-10},
        'scope': 'Canonical counts and primary-key sets; fleet KPIs and financial/market/followup/inventory group outcomes.',
        'excluded_from_equality': [
            'Execution and retrieval timestamps', 'Physical database layout and byte order',
            'Machine-specific source-extract paths',
        ],
        'limitations': 'This comparison does not assert byte-identical non-key field values in every source row. Separate contract and calculation tests remain required.',
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
    print(json.dumps({'status': result['status'], 'canonical_tables': result['canonical_table_count'], 'evidence': str(args.output)}))
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
