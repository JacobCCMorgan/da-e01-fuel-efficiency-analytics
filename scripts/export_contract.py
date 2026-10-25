"""Export dictionary, typed DuckDB DDL and requirement links from one contract."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def export(root: Path) -> dict:
    root = Path(root)
    source = root / 'contracts/da_e01_contract.json'
    contract = json.loads(source.read_text())
    fields = contract['fields']
    dictionary_path = root / 'contracts/field_dictionary.csv'
    with dictionary_path.open('w', newline='', encoding='utf-8-sig') as stream:
        keys = sorted({key for f in fields for key in f})
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list,dict)) else v for k,v in field.items()} for field in fields)
    sql = ['-- Generated from contracts/da_e01_contract.json. Do not edit this export.',
           '-- Key existence is checked by quality.py; temporal resolution uses analytical scenario tests.',
           'CREATE SCHEMA IF NOT EXISTS normalized;', '']
    docs = ['# DA-E01 data dictionary', '',
            'This dictionary is exported from the versioned contract. The CSV preserves every field attribute, including Chinese labels, null conditions, units, time availability and original requirement IDs.', '',
            'The 26 canonical tables contain 330 fields and support 153 original field requirements. Operational helper tables and raw HTTP receipts are separate from this contract.', '',
            '## Data layers', '', '| Table | Grain | Layer | Source plan | Key |', '|---|---|---|---|---|']
    for table in contract['tables']:
        name = table['name']; fs = [f for f in fields if f['table'] == name]
        sql.append(f'CREATE TABLE IF NOT EXISTS normalized."{name}" (')
        sql.append(',\n'.join(f'  "{f["name"]}" {f["type"]}' + (' NOT NULL' if not f.get('nullable', True) else '') for f in fs))
        sql.extend([');',''])
        docs.append('| ' + ' | '.join(str(v).replace('|',' / ') for v in [name,table['grain'],table['layer'],table['supply_mode'],', '.join(table['primary_key'])]) + ' |')
    for table in contract['tables']:
        name = table['name']; fs = [f for f in fields if f['table'] == name]
        docs.extend(['', f'## {name}', '', table['purpose'], '',
                     f"**History:** {table['version_rule']}", '',
                     f"**Time and frequency:** {table['time_range']} {table['frequency']}", '',
                     '**References:** ' + json.dumps(table.get('foreign_keys', []), ensure_ascii=False), '',
                     '| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |',
                     '|---|---|---|---|---|---|---|'])
        for f in fs:
            values = [f['field_id'],f['name'],f['zh'],f['type'],f['unit'],f['nullable_when'],f['definition']+' '+f['valid_values']]
            docs.append('| ' + ' | '.join(str(v).replace('|',' / ').replace('\n',' ') for v in values) + ' |')
    (root / 'contracts/schema.sql').write_text('\n'.join(sql)+'\n')
    (root / 'docs/data_dictionary.md').write_text('\n'.join(docs)+'\n')
    sys.path.insert(0, str(root/'src'))
    from fleet_fuel.quality import build_traceability
    # Documentation rebuilds preserve the latest measured evidence instead of
    # replacing a populated traceability register with a planning-only one.
    measured = root / 'validation/quality_report.json'
    rows = build_traceability(root, json.loads(measured.read_text()) if measured.exists() else None)
    return {'tables':len(contract['tables']), 'fields':len(fields), 'requirements':len(rows)}


if __name__ == '__main__':
    print(json.dumps(export(Path(__file__).resolve().parents[1])))
