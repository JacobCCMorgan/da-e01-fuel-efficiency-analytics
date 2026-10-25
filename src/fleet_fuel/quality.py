"""Contract checks and original-requirement traceability for the fuel pipeline.

Checks inspect the delivered analytical database. Raw rejected records remain in
the receipt/quarantine layer and are not silently removed from the audit trail.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DERIVED_TABLES = {'fuel_paired_interval', 'fuel_weekly_metric', 'fuel_inventory_balance', 'fuel_report_run'}
OUTPUT_ARTIFACTS = {
    'DA-E01-O01': ['outputs/vehicle_weekly.csv', 'outputs/inventory_reconciliation.csv',
                   'outputs/interval_exclusions.csv', 'outputs/report_revisions.csv'],
    'DA-E01-O02': ['outputs/fleet_weekly.csv', 'outputs/purchase_detail.csv',
                   'outputs/efficiency_comparison.csv', 'outputs/review_candidates.csv', 'outputs/dashboard.html'],
    'DA-E01-O03': ['outputs/followup_evaluation.csv', 'outputs/followup_task_comparison.csv'],
}
SCENARIO_TESTS = {
    '01': ['tests/test_analysis.py::test_mpg_is_total_distance_over_total_consumption',
           'tests/test_simulation.py::test_independent_monthly_statement_controls'],
    '02': ['tests/test_analysis.py::test_production_interval_pairs_exact_common_boundaries',
           'tests/test_analysis.py::test_confirmed_wrap_is_recovered_but_unknown_negative_jump_is_not',
           'tests/test_analysis.py::test_coincident_boundary_readings_are_audited_not_zero_length_intervals'],
    '03': ['tests/test_analysis.py::test_tax_and_discount_are_applied_once',
           'tests/test_analysis.py::test_transaction_total_excludes_nonfuel_and_fees',
           'tests/test_simulation.py::test_independent_monthly_statement_controls'],
    '04': ['tests/test_analysis.py::test_unknown_inventory_movement_propagates',
           'tests/test_simulation.py::test_physical_mass_balance_and_planned_distance'],
    '05': ['tests/test_analysis.py::test_high_consumption_requires_load_pto_route_review_not_waste_label'],
    '06': ['tests/test_analysis.py::test_report_window_respects_daylight_saving_time',
           'tests/test_analysis.py::test_late_revision_changes_revised_but_not_initial',
           'tests/test_analysis.py::test_definition_received_late_cannot_rewrite_initial_view'],
    '07': ['tests/test_analysis.py::test_ambiguous_historical_assignment_is_excluded',
           'tests/test_analysis.py::test_both_endpoints_require_valid_definition_period',
           'tests/test_simulation.py::test_world_has_stable_ids_and_valid_intervals'],
    '08': ['tests/test_analysis.py::test_unanswered_review_is_not_a_negative_outcome',
           'tests/test_analysis.py::test_task_change_prevents_qualifying_followup_comparison',
           'tests/test_analysis.py::test_followup_is_standardized_to_baseline_task_distance_mix'],
}


def write_supporting_registries(root: Path) -> None:
    """Materialize shared-package identities from delivered source evidence.

    These registries are support metadata, not additional canonical DA-E01
    tables. They are never constructed by accepting whatever IDs appear in the
    database being checked.
    """
    config_path = root / 'config/simulation.json'
    generated_path = root / 'data/generation_manifest.json'
    if not (config_path.exists() and generated_path.exists()):
        return
    config = json.loads(config_path.read_text())
    generated = json.loads(generated_path.read_text())
    sources = [{
        'source_dataset_id': 'fleet-fuel-sample-v' + config['version'],
        'origin_type': 'synthetic', 'scope': 'fictional fleet operations and validation fixtures',
        'version': config['version'], 'seed': config['seed'],
        'evidence': ['config/simulation.json', 'data/generation_manifest.json', 'src/fleet_fuel/simulation.py'],
        'expected_generator_version': generated['generator_version'],
        'rights': 'Original synthetic demonstration; no real customer fleet records.',
    }]
    for path in sorted((root / 'data/public/snapshots').glob('*/manifest.json')):
        manifest = json.loads(path.read_text())
        normalized = root / manifest.get('normalized_path', '')
        if manifest.get('source_id') != 'S22-PUB-001' or manifest.get('status') != 'public_download_verified':
            continue
        valid_hash = (normalized.is_file() and hashlib.sha256(normalized.read_bytes()).hexdigest() == manifest.get('normalized_sha256'))
        sources.append({
            'source_dataset_id': 'EIA-' + manifest['snapshot_id'],
            'origin_type': 'public', 'scope': 'published diesel-price background; no operational entity identity linkage',
            'version': manifest['snapshot_id'], 'evidence': [path.relative_to(root).as_posix()],
            'normalized_sha256': manifest['normalized_sha256'], 'snapshot_hash_matches': valid_hash,
            'source_urls': [f['url'] for f in manifest['files']],
            'rights_url': manifest['rights_url'], 'historical_availability': manifest['historical_availability'],
        })
    (root / 'contracts/source_registry.json').write_text(json.dumps({
        'schema_version': '1.0.0', 'contract_role': 'External source_dataset key registry; outside the 26-table canonical subset.',
        'entries': sources}, ensure_ascii=False, indent=2) + '\n')
    definitions = {
        'FUEL-NORMAL': 'Baseline entity, trip, purchase and physical fuel-ledger records with stable cross-table identifiers.',
        'STATIONARY-WEEK-BOUNDARY': 'Explicit counter observations at local week boundaries; not a new operating trip.',
        'AMOUNT-ONLY-REFUND': 'A negative price adjustment with zero fuel quantity.',
        'INDEPENDENT-STATEMENT-CONTROL': 'Monthly accounting control totals maintained before source-row serialization.',
        'UNCALIBRATED-INVENTORY': 'Percentage tank level without a calibration reference; litres remain unknown.',
        'SYNTHETIC-REVIEW': 'Fictional report adoption and reviewer outcomes, including unanswered cases.',
        'SYNTHETIC-FOLLOWUP': 'Fictional action windows, follow-up exposure and task mix from the shared physical ledger.',
        'SYNTHETIC-PRICE': 'Fictional regional diesel price curves with simulated publication availability.',
        'WEEKLY-INVENTORY': 'Week-boundary tank stock observations from the physical fuel ledger.',
        'ODOMETER-RESET': 'Independent odometer reset supported by a fictional ECU service event.',
        'CONFIRMED-ROLLOVER': 'Fuel counter wrap with the configured 4096-litre modulus and explicit evidence.',
        'IDENTITY-OVERLAP': 'Deliberate conflicting vehicle-device effective periods; ambiguous assignment is not guessed.',
        'UNKNOWN-MOVEMENT': 'Maintenance drain recorded without a known volume; balance cannot be asserted.',
        'KNOWN-FUEL-TRANSFER': 'Measured transfer-in and maintenance-outflow records with movement references.',
        'FUEL-RESET': 'Fuel counter reset independent of the odometer reset.',
        'NONFUEL-LINE': 'Nonfuel purchase components excluded from fuel-volume and comparable-price denominators.',
    }
    entries = [{'synthetic_scenario_id': key, 'origin_type': 'synthetic', 'definition': value,
                'evidence': ['src/fleet_fuel/simulation.py', 'config/simulation.json'],
                'use_boundary': 'Scenario identity is validation metadata, not an analytical predictor.'}
               for key, value in definitions.items()]
    injection_path = root / 'validation/expected/injections.json'
    if injection_path.exists():
        grouped = {}
        for row in json.loads(injection_path.read_text()):
            grouped.setdefault(row['scenario_id'], []).append(row)
        for key, rows in grouped.items():
            entries.append({'synthetic_scenario_id': key, 'origin_type': 'synthetic',
                            'definition': '; '.join(sorted({row['expected'] for row in rows})),
                            'injected_record_ids': sorted({row['record_id'] for row in rows}),
                            'evidence': ['validation/expected/injections.json', 'src/fleet_fuel/simulation.py'],
                            'use_boundary': 'Injection truth is restricted to validation; missing packets create no source row.'})
    fixture_path = root / 'validation/expected/hand_cases.json'
    if fixture_path.exists():
        for row in json.loads(fixture_path.read_text()):
            entries.append({'synthetic_scenario_id': row['scenario_id'], 'origin_type': 'synthetic',
                            'definition': row['reason'], 'reference_metric': row['reference_metric'],
                            'expected': row['expected'], 'evidence': ['validation/expected/hand_cases.json'],
                            'use_boundary': 'Independent fixed arithmetic reference; not an input feature.'})
    (root / 'contracts/scenario_registry.json').write_text(json.dumps({
        'schema_version': '1.0.0', 'contract_role': 'External synthetic_scenario key registry; outside the 26-table canonical subset.',
        'entries': sorted(entries, key=lambda row: row['synthetic_scenario_id'])}, ensure_ascii=False, indent=2) + '\n')


def scenario_evidence(root: Path) -> dict[str, dict]:
    """Attach observed test outcomes; an absent test is never a passing test.

    Names are exact pytest function names. Class-based unittest fixtures are
    resolved through their final name because JUnit uses a class-qualified
    classname instead of a pytest node path for those cases.
    """
    source = root / 'validation/test_results.xml'
    observed = {}
    if source.exists():
        for case in ET.parse(source).getroot().iter('testcase'):
            status = ('failed' if case.find('failure') is not None or case.find('error') is not None
                      else 'skipped' if case.find('skipped') is not None else 'passed')
            observed.setdefault(case.get('name', ''), []).append(status)
    result = {}
    for number, nodes in SCENARIO_TESTS.items():
        tests = []
        for node in nodes:
            states = observed.get(node.split('::')[-1], [])
            status = ('not_run' if not states else 'failed' if 'failed' in states
                      else 'skipped' if 'skipped' in states else 'passed')
            tests.append({'test': node, 'status': status})
        status = ('test_mapping_pending' if not nodes else
                  'passed' if tests and all(t['status'] == 'passed' for t in tests) else
                  'failed' if any(t['status'] == 'failed' for t in tests) else 'not_fully_evaluated')
        result['DA-E01-V22-' + number] = {'status': status, 'tests': tests,
                                        'evidence_file': 'validation/test_results.xml' if source.exists() else None}
    return result


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def canonical_type(value: str) -> str:
    return value.upper().replace('TIMESTAMP WITH TIME ZONE', 'TIMESTAMPTZ').replace('INT64', 'BIGINT').replace('INT32', 'INTEGER')


def enum_values(field: dict) -> list[str] | None:
    """Accept only explicit, complete enum lists, never parse prose as rules."""
    text = field.get('valid_values', '')
    if field.get('type') == 'VARCHAR' and re.fullmatch(r'[A-Za-z0-9_/-]+(?:\|[A-Za-z0-9_/-]+)+', text):
        return text.split('|')
    return None


def build_traceability(root: Path, report: dict | None = None) -> list[dict]:
    root = Path(root)
    contract = json.loads((root / 'contracts/da_e01_contract.json').read_text())
    fields = {(f['table'], f['name']): f for f in contract['fields']}
    measured = {(f['table'], f['column']): f for f in (report or {}).get('fields', [])}
    lineage = contract['spec'].get('output_lineage', [])
    scenario_results = scenario_evidence(root)
    items = []
    for original in contract['spec'].get('original_requirements', contract['mappings']):
        table, column = original['table'], original['column']
        f = fields[(table, column)]
        supply = measured.get((table, column), {})
        output_ids = sorted({o['id'] for o in lineage if original['s21_id'] in o.get('field_ids', []) or f['field_id'] in o.get('upstream_closure_field_ids', [])} | set(original.get('output_ids', [])))
        output_mapping_basis = 'accepted_output_lineage'
        if not output_ids:
            # S2.1 supplementary P-fields were retained in the field contract,
            # but some have no explicit output edge in the original catalog.
            # Add a labeled support edge without rewriting that original map.
            output_mapping_basis = 'implementation_supporting_dependency'
            if table in {'fuel_output_review', 'fuel_action_followup'}:
                output_ids = ['DA-E01-O03']
            elif table in {'provenance_record', 'fuel_reference_case', 'fuel_report_run'}:
                output_ids = ['DA-E01-O01', 'DA-E01-O02', 'DA-E01-O03']
            elif table in {'fuel_market_price', 'fuel_region_mapping', 'fuel_station'}:
                output_ids = ['DA-E01-O02']
            else:
                output_ids = ['DA-E01-O01', 'DA-E01-O02']
        validation_numbers = (
            ['08'] if table in {'fuel_output_review', 'fuel_action_followup'} else
            ['04'] if table in {'fuel_inventory_balance', 'fuel_inventory_measurement', 'fuel_tank_scope', 'fuel_movement'} else
            ['01', '03'] if table in {'fuel_purchase_line', 'fuel_statement_control', 'fuel_station', 'fuel_market_price', 'fuel_region_mapping'} else
            ['02', '06', '07'] if table in {'fuel_counter_observation', 'fuel_counter_change', 'fuel_signal_definition', 'fuel_paired_interval'} else
            ['06', '07'] if table in {'provenance_record', 'fuel_report_run'} else
            ['01', '02', '03', '05', '06'] if table == 'fuel_weekly_metric' else
            ['07'])
        table_checks = [c for c in (report or {}).get('checks', []) if c.get('table') == table and (not c.get('column') or c['column'] == column)]
        relevant_failure = any(c['status'] == 'failed' and c['severity'] == 'error' for c in table_checks)
        if not report:
            status = 'implementation_pending'
        elif not supply:
            status = 'missing_table_or_column'
        elif relevant_failure:
            status = 'data_present_checks_failed'
        elif supply['non_null_count'] == 0:
            status = 'conditional_null_review_required' if f.get('nullable') else 'required_values_missing'
        else:
            status = 'data_present_contract_checks_passed'
        items.append({
            'project_id': 'DA-E01', 's21_id': original['s21_id'],
            'requirement_name': original.get('source_name', ''),
            'requirement_definition': original.get('source_definition', ''),
            'condition': original.get('requirement_condition', ''),
            'field_id': f['field_id'], 'table': table, 'column': column,
            'unit': f['unit'], 'output_ids': output_ids,
            'output_artifacts': [{'outcome_id': output_id, 'path': path, 'present': (root / path).is_file()}
                                 for output_id in output_ids for path in OUTPUT_ARTIFACTS[output_id]],
            'output_mapping_basis': output_mapping_basis,
            'supply_role': original.get('value_role', f.get('origin', '')),
            'source_file': f'data/raw/tables/{table}.jsonl' if table not in DERIVED_TABLES else '',
            'database_location': f'normalized.{table}.{column}',
            'implementation': 'src/fleet_fuel/analysis.py' if table in DERIVED_TABLES else 'src/fleet_fuel/simulation.py and ingestion pipeline',
            'calculation_rule': f.get('derivation', ''),
            'independent_validation_case_ids': [f'DA-E01-V22-{n}' for n in validation_numbers],
            'independent_validation': {f'DA-E01-V22-{n}': scenario_results[f'DA-E01-V22-{n}'] for n in validation_numbers},
            'actual_contract_check_ids': [c['id'] for c in table_checks],
            'row_count': supply.get('row_count'), 'non_null_count': supply.get('non_null_count'),
            'null_count': supply.get('null_count'), 'status': status,
            'interpretation': 'Field supply and contract checks are evidence of delivery; analytical correctness also requires the independent scenario tests and output review.'
        })
    destination = root / 'validation'
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'requirement_traceability.json').write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n')
    with (destination / 'requirement_traceability.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(items[0]) if items else ['project_id'])
        writer.writeheader()
        for row in items:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return items


def validate(root: Path) -> dict:
    """Validate canonical normalized tables and write observable check results."""
    import duckdb

    root = Path(root)
    contract = json.loads((root / 'contracts/da_e01_contract.json').read_text())
    write_supporting_registries(root)
    db_path = root / 'data/DA-E01.duckdb'
    result = {'project_id': 'DA-E01', 'database': 'data/DA-E01.duckdb',
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'normalized canonical data; raw rejected records are evaluated separately',
              'checks': [], 'tables': [], 'fields': [], 'status': 'failed'}

    def add(check_id, table, condition, violations=None, severity='error', column=None, detail=''):
        result['checks'].append({'id': check_id, 'table': table, 'column': column,
                                 'condition': condition, 'violations': violations,
                                 'status': 'passed' if violations == 0 else 'failed' if violations is not None else 'not_evaluated',
                                 'severity': severity, 'detail': detail})

    if not db_path.exists():
        add('database_exists', '', 'DuckDB file exists', 1, detail=str(db_path))
    else:
        con = duckdb.connect(str(db_path), read_only=True)
        actual = {row[0] for row in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='normalized'").fetchall()}
        field_map = {}
        for f in contract['fields']:
            field_map.setdefault(f['table'], []).append(f)
        usable = set()
        for table in contract['tables']:
            name = table['name']; q = f'normalized.{ident(name)}'
            add(f'{name}.exists', name, 'Canonical table exists', int(name not in actual))
            if name not in actual:
                continue
            columns = dict(con.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='normalized' AND table_name=?", [name]).fetchall())
            expected = field_map[name]
            usable.add(name)
            available = [f for f in expected if f['name'] in columns]
            counts = con.execute(f"SELECT count(*), " + ','.join(f'count({ident(f["name"])})' for f in available) + f' FROM {q}').fetchone() if available else (con.execute(f'SELECT count(*) FROM {q}').fetchone()[0],)
            row_count = counts[0]
            required_table = name in contract.get('spec', {}).get('required_tables', [])
            add(f'{name}.populated', name, 'Required table has executable records' if required_table else 'Enabled optional table has records', int(row_count == 0), 'error' if required_table else 'warning')
            result['tables'].append({'table': name, 'row_count': row_count, 'layer': table.get('layer'), 'required': required_table})
            for f in expected:
                column = f['name']; exists = column in columns
                add(f'{name}.{column}.exists', name, 'Column exists', int(not exists), column=column)
                if not exists:
                    usable.discard(name); continue
                add(f'{name}.{column}.type', name, f"Type is {f['type']}", int(canonical_type(columns[column]) != canonical_type(f['type'])), column=column, detail=f'actual={columns[column]}')
                non_null = counts[available.index(f) + 1]
                nulls = row_count - non_null
                result['fields'].append({'table': name, 'column': column, 'field_id': f['field_id'], 'row_count': row_count, 'non_null_count': non_null, 'null_count': nulls, 'nullable': f.get('nullable'), 'nullable_when': f.get('nullable_when', '')})
                if not f.get('nullable', True):
                    add(f'{name}.{column}.not_null', name, 'Required non-null value', nulls, column=column)
                values = enum_values(f)
                if values:
                    marks = ','.join('?' for _ in values)
                    bad = con.execute(f'SELECT count(*) FROM {q} WHERE {ident(column)} IS NOT NULL AND {ident(column)} NOT IN ({marks})', values).fetchone()[0]
                    add(f'{name}.{column}.enum', name, 'Value belongs to the explicit contract enum', bad, column=column)
                valid_values = f.get('valid_values', '')
                if f['type'] == 'VARCHAR' and valid_values.startswith('非空'):
                    bad = con.execute(f'SELECT count(*) FROM {q} WHERE {ident(column)} IS NOT NULL AND length(trim({ident(column)}))=0').fetchone()[0]
                    add(f'{name}.{column}.nonblank', name, 'Present identifier or text is not blank', bad, column=column)
                numeric_predicate = {
                    '>=0': f'{ident(column)} < 0',
                    '0 <= value <= 1': f'{ident(column)} < 0 OR {ident(column)} > 1',
                    '0 <= value <= 100': f'{ident(column)} < 0 OR {ident(column)} > 100',
                    '-840..840': f'{ident(column)} < -840 OR {ident(column)} > 840',
                }.get(valid_values)
                if numeric_predicate:
                    bad = con.execute(f'SELECT count(*) FROM {q} WHERE {numeric_predicate}').fetchone()[0]
                    add(f'{name}.{column}.range', name, f'Value satisfies {valid_values}', bad, column=column)
            if name not in usable:
                continue
            constraints = [table.get('primary_key', [])] + table.get('unique_constraints', [])
            for cols in {tuple(v) for v in constraints if v}:
                quoted = ','.join(map(ident, cols))
                duplicate = con.execute(f'SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {q} GROUP BY {quoted} HAVING count(*)>1)').fetchone()[0]
                add(f'{name}.unique.{"_".join(cols)}', name, f'Unique key {list(cols)}', int(duplicate))
                null_key = con.execute(f'SELECT count(*) FROM {q} WHERE ' + ' OR '.join(f'{ident(c)} IS NULL' for c in cols)).fetchone()[0]
                add(f'{name}.key_not_null.{"_".join(cols)}', name, 'Key columns are not null', null_key)

        for table in contract['tables']:
            name = table['name']
            if name not in usable: continue
            for i, fk in enumerate(table.get('foreign_keys', [])):
                ref = fk['ref_table']
                if ref not in usable:
                    registry_file = {'source_dataset': 'source_registry.json', 'synthetic_scenario': 'scenario_registry.json'}.get(ref)
                    registry_path = root / 'contracts' / registry_file if registry_file else None
                    if registry_path and registry_path.exists() and len(fk['columns']) == len(fk['ref_columns']) == 1:
                        records = json.loads(registry_path.read_text())['entries']
                        key = fk['ref_columns'][0]
                        ids = [row[key] for row in records]
                        add(f'{name}.registry.{ref}.unique', name, 'Supporting registry identifiers are unique', len(ids) - len(set(ids)))
                        if ref == 'source_dataset':
                            invalid_evidence = sum(row.get('snapshot_hash_matches') is False or
                                                   ('expected_generator_version' in row and row['expected_generator_version'] != row['version'])
                                                   for row in records)
                            add(f'{name}.registry.{ref}.evidence', name, 'Source registry matches source snapshot hashes and generator version', invalid_evidence)
                            if any(f['name'] == 'origin_type' for f in field_map[name]):
                                incompatible = 0
                                for record in records:
                                    incompatible += con.execute(
                                        f"SELECT count(*) FROM normalized.{ident(name)} WHERE source_dataset_id=? AND origin_type IN ('public','synthetic') AND origin_type<>?",
                                        [record['source_dataset_id'], record['origin_type']]).fetchone()[0]
                                add(f'{name}.registry.{ref}.origin', name, 'Public and synthetic records agree with their registered source nature', incompatible)
                        column = ident(fk['columns'][0])
                        where = column + ' IS NOT NULL'
                        if ids:
                            where += ' AND ' + column + ' NOT IN (' + ','.join('?' for _ in ids) + ')'
                        bad = con.execute(f'SELECT count(*) FROM normalized.{ident(name)} WHERE {where}', ids).fetchone()[0]
                        add(f'{name}.fk.{i}', name, f'{fk["columns"]} reference the delivered {ref} registry', bad,
                            detail=f'{registry_path.relative_to(root)}; external support metadata outside the canonical 26-table subset. Each ID must resolve to source or scenario evidence.')
                        continue
                    add(f'{name}.fk.{i}', name, 'Referenced canonical table available', None, detail=f'{ref}; {fk.get("condition", "")}')
                    continue
                columns, refs = fk['columns'], fk['ref_columns']
                where = ' AND '.join(f's.{ident(c)} IS NOT NULL' for c in columns)
                join = ' AND '.join(f's.{ident(a)}=r.{ident(b)}' for a,b in zip(columns,refs))
                bad = con.execute(f'SELECT count(*) FROM normalized.{ident(name)} s WHERE {where} AND NOT EXISTS (SELECT 1 FROM normalized.{ident(ref)} r WHERE {join})').fetchone()[0]
                add(f'{name}.fk.{i}', name, f'{columns} reference {ref}{refs}', bad, detail=fk.get('condition', '') + '; this check proves existence/tenant isolation; temporal resolution is checked in analytical tests.')

        # Null is not a business state. Source rows must explain it through
        # field-level provenance or a specific, contracted status column.
        if 'provenance_record' in usable:
            for table in contract['tables']:
                name = table['name']
                fs = field_map[name]
                if name not in usable or name == 'provenance_record' or not any(f['name']=='provenance_id' for f in fs):
                    continue
                for f in fs:
                    if not f.get('nullable'): continue
                    column=f['name']
                    state_path='$."'+name+'.'+column+'".state'
                    accepted_state = "json_extract_string(p.value_states, ?) IN ('missing','invalid','unknown','not_applicable','not_mature')"
                    special=[]
                    if name=='core_vehicle_device_assignment' and column in {'valid_to','known_to'}:
                        special.append(f"s.{ident(column+'_state')} IN ('open','unknown')")
                    if name=='fuel_market_price' and column=='price_published_at':
                        special.append("s.publication_precision='unknown'")
                    if name=='fuel_counter_observation':
                        if column.startswith('fuel_'):
                            special.append("s.fuel_validity IN ('not_available','error','unknown')")
                        elif column.startswith('distance_') or column.startswith('odometer'):
                            special.append("s.distance_validity IN ('not_available','error','unknown')")
                    explain = '(' + ' OR '.join([accepted_state]+special) + ')'
                    bad = con.execute(f'SELECT count(*) FROM normalized.{ident(name)} s LEFT JOIN normalized.provenance_record p USING(provenance_id) WHERE s.{ident(column)} IS NULL AND NOT coalesce({explain},false)',[state_path]).fetchone()[0]
                    add(f'{name}.{column}.null_state', name, 'Null source value has an explicit missing/unknown/inapplicable state', bad, column=column,detail='Field-level provenance.value_states or the specific canonical status field is required; zero is not a missing-value marker.')

        semantic = [
            ('fuel_report_run', 'week_window', 'report_week_end <= report_week_start', 'Report week is a positive interval'),
            ('fuel_report_run', 'asof', 'as_of_time < report_week_end', 'Report is produced after its observation window'),
            ('fuel_paired_interval', 'positive_window', 'paired_interval_end <= paired_interval_start', 'Paired interval duration is positive'),
            ('fuel_paired_interval', 'accepted_nonnegative', 'accepted AND (paired_fuel_l < 0 OR paired_distance_km < 0 OR paired_fuel_l IS NULL OR paired_distance_km IS NULL)', 'Accepted paired quantities are present and nonnegative'),
            ('fuel_paired_interval', 'accepted_exclusion', "accepted AND excluded_interval_reason IS NOT NULL AND excluded_interval_reason NOT IN ('','none')", 'Accepted interval has no exclusion reason'),
            ('fuel_weekly_metric', 'coverage_range', 'measurement_coverage < 0 OR measurement_coverage > 1', 'Coverage is a fraction between zero and one'),
            ('fuel_weekly_metric', 'market_coverage_range', 'benchmark_match_coverage < 0 OR benchmark_match_coverage > 1', 'Market matching coverage is a fraction'),
            ('fuel_weekly_metric', 'mpg_ratio', 'fuel_used_l > 0 AND mpg IS NOT NULL AND abs(mpg - (distance_travelled_km / 1.609344) / (fuel_used_l / 3.785411784)) > 0.0001', 'MPG uses the same accepted distance and fuel totals'),
            ('fuel_tank_scope', 'capacity_positive', 'tank_capacity_l <= 0', 'Known tank capacity is positive'),
            ('fuel_inventory_measurement', 'quantity_nonnegative', 'quantity_l < 0', 'Physical measured volume is nonnegative'),
            ('fuel_inventory_balance', 'balance_arithmetic', 'balance_consumption_l IS NOT NULL AND abs(balance_consumption_l - (opening_volume_l + refuel_volume_l + transfer_in_l - removed_l - closing_volume_l)) > 0.001', 'Inventory consumption reconciles opening, inflows, outflows and closing'),
            ('fuel_inventory_balance', 'net_transfer_arithmetic', 'net_transfer_l IS NOT NULL AND abs(net_transfer_l - (transfer_in_l - removed_l)) > 0.001', 'Net transfer subtracts verified removals exactly once'),
            ('fuel_purchase_line', 'refund_quantity', "adjustment_type='amount_refund' AND purchase_quantity_l <> 0", 'Amount-only refund does not invent a fuel volume'),
            ('core_vehicle_device_assignment', 'valid_period', 'valid_to IS NOT NULL AND valid_to <= valid_from', 'Assignment business interval is positive'),
            ('core_vehicle_device_assignment', 'known_period', 'known_to IS NOT NULL AND known_to <= known_from', 'Assignment knowledge interval is positive'),
        ]
        for table, start, end in [
            ('fuel_vehicle_context', 'vehicle_active_from', 'vehicle_active_to'),
            ('fuel_task_assignment', 'task_assignment_from', 'task_assignment_to'),
            ('fuel_task_assignment', 'task_start_at', 'task_end_at'),
            ('fuel_signal_definition', 'valid_from', 'valid_to'),
            ('fuel_card_assignment', 'card_vehicle_from', 'card_vehicle_to'),
            ('fuel_card_assignment', 'known_from', 'known_to'),
            ('fuel_region_mapping', 'valid_from', 'valid_to'),
            ('fuel_inventory_balance', 'period_start_at', 'period_end_at'),
            ('fuel_statement_control', 'statement_period_start', 'statement_period_end'),
            ('fuel_action_followup', 'baseline_window_start', 'baseline_window_end'),
            ('fuel_action_followup', 'followup_start', 'planned_followup_end'),
        ]:
            semantic.append((table, start + '_period',
                             f'{end} IS NOT NULL AND {start} IS NOT NULL AND {end} <= {start}',
                             f'Known interval {start} to {end} is positive'))
        for table, label, where, condition in semantic:
            if table not in usable: continue
            try:
                n = con.execute(f'SELECT count(*) FROM normalized.{ident(table)} WHERE {where}').fetchone()[0]
                add(f'{table}.semantic.{label}', table, condition, n)
            except duckdb.Error as exc:
                add(f'{table}.semantic.{label}', table, condition, None, detail=str(exc))
        con.close()
    errors = [c for c in result['checks'] if c['severity'] == 'error' and c['status'] != 'passed']
    result['summary'] = dict(Counter(c['status'] for c in result['checks']))
    result['error_count'] = len(errors)
    result['status'] = 'passed' if not errors else 'failed'
    result['coverage_note'] = 'Contract checks do not replace API integration tests, as-of replay, independent hand-calculated fixtures, or a review of source-rights and business interpretation.'
    destination = root / 'validation'; destination.mkdir(parents=True, exist_ok=True)
    trace = build_traceability(root, result)
    result['traceability_rows'] = len(trace)
    result['scenario_validation'] = scenario_evidence(root)
    (destination / 'quality_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result
