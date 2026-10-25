#!/usr/bin/env python3
"""Create verified, allowlisted DA-E01 release archives after a completed run.

Does not acquire data, rerun analysis, upload files or modify the source database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


TOP_LEVEL = {'README.md', 'README.zh-TW.md', 'LICENSE', 'pyproject.toml',
             'requirements.lock.txt', 'Makefile', '.gitignore', 'docker-compose.yml'}
SOURCE_DIRS = {'src', 'contracts', 'config', 'tests', 'sql', 'scripts', 'docs',
               'notebooks', 'reports', 'outputs', 'validation'}
SOURCE_SUFFIXES = {'.py', '.js', '.sh', '.sql', '.md', '.json', '.jsonl', '.csv', '.tsv',
                   '.toml', '.yml', '.yaml', '.txt', '.ipynb', '.png', '.svg',
                   '.jpg', '.jpeg', '.pdf', '.docx', '.html', '.xml'}
TEXT_SUFFIXES = SOURCE_SUFFIXES - {'.png', '.jpg', '.jpeg', '.pdf', '.docx'}
DERIVED_TABLES = {'fuel_paired_interval', 'fuel_weekly_metric', 'fuel_inventory_balance', 'fuel_report_run'}
CHUNK = 1024 * 1024
GIT_LIMIT = 100 * 1024 * 1024


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def permitted_path(relative: str) -> bool:
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or not p.parts:
        return False
    for index, part in enumerate(p.parts):
        if part.startswith('.') and not (index == 0 and part in {'.github', '.gitignore'}):
            return False
        if part in {'__pycache__', 'node_modules', 'artifacts'}:
            return False
    name = p.name.lower()
    if name.startswith(('~$', '.env')) or name.endswith(('.pyc', '.pyo', '.tmp', '.temp', '.bak', '.wal', '-wal', '-shm')):
        return False
    if name in {'credentials.json', 'token.json', 'tokens.json', 'id_rsa', 'id_ed25519'}:
        return False
    return True


def safe_file(root: Path, relative: str) -> Path:
    if not permitted_path(relative):
        raise ValueError(f'Prohibited archive path: {relative}')
    p = root / relative
    if not p.is_file() or p.is_symlink() or root not in p.resolve().parents:
        raise ValueError(f'Missing, linked or outside-root input: {relative}')
    return p


def text_hazards(data: bytes, root: Path) -> str | None:
    private = [str(root).encode(), ('/' + 'workspace/scratch/').encode(),
               ('/' + 'home/runner/work/').encode()]
    runtime_root = str(Path(sys.executable).resolve().parents[2])
    if runtime_root.startswith('/opt/'):
        private.append(runtime_root.encode())
    if any(prefix in data for prefix in private):
        return 'absolute_private_machine_path'
    credential_patterns = [rb'gh[pousr]_[A-Za-z0-9]{25,}',
                           rb'github_pat_[A-Za-z0-9_]{30,}',
                           rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
                           rb'postgres(?:ql)?://[^/\s:]+:[^@\s]+@']
    if any(re.search(pattern, data) for pattern in credential_patterns):
        return 'credential_like_content'
    return None


def inspect_file(root: Path, relative: str) -> dict:
    p = safe_file(root, relative)
    digest = hashlib.sha256()
    lines = 0
    tail = b''
    # Scan raw bytes too: source paths can remain in database/string metadata.
    with p.open('rb') as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
            lines += block.count(b'\n')
            hazard = text_hazards(tail + block, root)
            if hazard:
                raise ValueError(f'{hazard}: {relative}; normalize or remove before packaging')
            tail = block[-4096:]
    if p.suffix == '.docx':
        with zipfile.ZipFile(p) as document:
            for name in document.namelist():
                if name.endswith('.xml') and text_hazards(document.read(name), root):
                    raise ValueError(f'Private path or credential in document XML: {relative}')
    if p.suffix == '.pdf':
        from pypdf import PdfReader
        document = PdfReader(p)
        extracted = str(document.metadata or {}) + '\n' + '\n'.join(page.extract_text() or '' for page in document.pages)
        if text_hazards(extracted.encode('utf-8'), root):
            raise ValueError(f'Private path or credential in PDF content: {relative}')
    rows = None
    if p.suffix == '.jsonl':
        rows = lines + int(bool(p.stat().st_size) and not tail.endswith(b'\n'))
    elif p.suffix in {'.csv', '.tsv'}:
        with p.open(encoding='utf-8-sig', newline='') as stream:
            rows = max(0, sum(1 for _ in csv.reader(stream, delimiter='\t' if p.suffix == '.tsv' else ',')) - 1)
    elif p.suffix == '.parquet':
        import pyarrow.parquet as pq
        rows = pq.ParquetFile(p).metadata.num_rows
    if relative.startswith('data/public/'):
        origin, license_refs = 'public_EIA_or_acquisition_metadata', ['data/LICENSE.md#external-eia-information', 'docs/sources.md']
    elif relative.startswith('data/postgres_extract/'):
        origin, license_refs = 'synthetic_records_extracted_from_verified_postgresql', ['data/LICENSE.md#original-fictional-sample-data']
    elif relative.startswith('data/raw/'):
        origin, license_refs = 'synthetic_source', ['data/LICENSE.md#original-fictional-sample-data']
    elif relative.startswith(('data/staged/', 'data/ingestion/', 'validation/expected/')):
        origin, license_refs = 'synthetic_processed_or_validation', ['data/LICENSE.md#original-fictional-sample-data']
    elif relative.startswith(('data/normalized/', 'data/derived/')) or relative == 'data/DA-E01.duckdb':
        origin, license_refs = 'canonical_or_derived_with_record_level_origin', ['data/LICENSE.md']
    elif relative.startswith(('outputs/', 'reports/')):
        origin, license_refs = 'derived_analysis_and_presentation', ['LICENSE', 'data/LICENSE.md']
    else:
        origin, license_refs = 'project_code_documentation_or_execution_evidence', ['LICENSE']
    return {'path': relative, 'bytes': p.stat().st_size, 'sha256': digest.hexdigest(),
            'logical_rows': rows, 'source_origin': origin, 'license_refs': license_refs,
            'git_file_size_eligible': p.stat().st_size <= GIT_LIMIT}


def owned_build_inputs(root: Path, build: dict) -> set[str]:
    """Select exact staged/extracted inputs, never every historical extract."""
    entries = [entry for entry in build['inputs'].values()
               if entry['path'].startswith(('data/staged/', 'data/postgres_extract/'))]
    extracted = {entry['path'] for entry in entries if entry['path'].startswith('data/postgres_extract/')}
    if build.get('operational_source') == 'postgresql_extract':
        manifest = load(safe_file(root, 'validation/postgres_extract.json'))
        safe_file(root, 'validation/postgres_bootstrap.json')
        directory = manifest['directory']
        if manifest.get('status') != 'executed' or not re.fullmatch(r'data/postgres_extract/snapshot-[0-9]+-[a-zA-Z0-9]+', directory):
            raise ValueError('Invalid executed PostgreSQL extract manifest')
        expected = {directory + '/' + name + '.jsonl' for name in manifest['rows']}
        if extracted != expected:
            raise ValueError('PostgreSQL build inputs do not exactly match the active extract manifest')
    elif extracted:
        raise ValueError('PostgreSQL extract paths require a PostgreSQL source build')
    for entry in entries:
        safe_file(root, entry['path'])
        if file_hash(root / entry['path']) != entry['sha256']:
            raise ValueError(f'Build input changed: {entry["path"]}')
    return {entry['path'] for entry in entries}


def collect(root: Path) -> tuple[set[str], set[str], dict]:
    required = ['data/generation_manifest.json', 'validation/run_manifest.json',
                'validation/quality_report.json', 'validation/ingestion_report.json',
                'validation/build_report.json', 'data/normalized/manifest.json',
                'outputs/dashboard.html', 'notebooks/01_fuel_analysis.ipynb',
                'validation/test_results.xml', 'data/README.md', 'data/LICENSE.md']
    for name in required:
        safe_file(root, name)
    generation = load(root / 'data/generation_manifest.json')
    run = load(root / 'validation/run_manifest.json')
    quality = load(root / 'validation/quality_report.json')
    intake = load(root / 'validation/ingestion_report.json')
    if generation.get('profile') != 'full' or run.get('profile') != 'full':
        raise ValueError('DA-E01 v1 release requires the full profile')
    if run.get('status') != 'completed' or quality.get('status') != 'passed':
        raise ValueError('A completed run and passing quality report are required')
    if not intake.get('complete') or not intake.get('counts_reconcile'):
        raise ValueError('Incomplete or unreconciled event intake cannot be released')
    junit = ET.parse(root / 'validation/test_results.xml').getroot()
    suites = [node for node in junit.iter('testsuite') if not list(node.iterfind('testsuite'))]
    tests = {key: sum(int(node.get(key, '0')) for node in suites)
             for key in ['tests', 'failures', 'errors', 'skipped']}
    if not tests['tests'] or tests['failures'] or tests['errors']:
        raise ValueError('A nonempty JUnit result with no failures/errors is required')
    notebook = load(root / 'notebooks/01_fuel_analysis.ipynb')
    cells = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code' and ''.join(cell['source']).strip()]
    if not cells or any(cell.get('execution_count') is None for cell in cells):
        raise ValueError('Execute the final analytical notebook before packaging')
    if any(output.get('output_type') == 'error' for cell in cells for output in cell.get('outputs', [])):
        raise ValueError('Notebook contains an execution error')
    source = {name for name in TOP_LEVEL if (root / name).is_file()}
    for directory in SOURCE_DIRS:
        for p in sorted((root / directory).rglob('*')):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and permitted_path(rel) and p.suffix.lower() in SOURCE_SUFFIXES:
                source.add(rel)
    for p in sorted((root / '.github/workflows').glob('*.yml')):
        source.add(p.relative_to(root).as_posix())
    public = {p.relative_to(root).as_posix() for p in (root / 'data/public').rglob('*')
              if p.is_file() and permitted_path(p.relative_to(root).as_posix())}
    source.update(public)
    source.update({'data/README.md', 'data/LICENSE.md'})
    data = set(public) | {'data/README.md', 'data/LICENSE.md', 'data/generation_manifest.json', 'data/DA-E01.duckdb'}
    for entry in generation['sources']:
        rel = entry['path']
        if not rel.startswith('data/raw/'):
            raise ValueError(f'Unexpected generator ownership: {rel}')
        p = safe_file(root, rel)
        if p.stat().st_size != entry['bytes'] or file_hash(p) != entry['sha256']:
            raise ValueError(f'Generator-owned source changed: {rel}')
        data.add(rel)
    build = load(root / 'validation/build_report.json')
    data.update(owned_build_inputs(root, build))
    if build.get('operational_source') == 'postgresql_extract':
        data.update({'validation/postgres_bootstrap.json', 'validation/postgres_extract.json'})
    for name in ['validation/database_adoption.json', 'validation/local_intake_evidence.json',
                 'validation/local_http_ingestion.json', 'validation/ci_full_run_40227233022.json',
                 'validation/ci_full_canonical_comparison_40227233022.json']:
        if (root / name).is_file():
            data.add(name)
    normalized = load(root / 'data/normalized/manifest.json')
    data.add('data/normalized/manifest.json')
    for entry in normalized:
        rel = entry['path']
        if not rel.startswith('data/normalized/') or not rel.endswith('.parquet'):
            raise ValueError(f'Unexpected normalized ownership: {rel}')
        safe_file(root, rel)
        if file_hash(root / rel) != entry['sha256']:
            raise ValueError(f'Normalized export changed: {rel}')
        data.add(rel)
    for table in DERIVED_TABLES:
        rel = f'data/derived/{table}.parquet'
        if (root / rel).is_file():
            data.add(rel)
    snapshot = intake['snapshot']
    if not re.fullmatch('[0-9a-f]{64}', snapshot):
        raise ValueError('Unexpected active event snapshot identity')
    receipt = f'data/ingestion/{snapshot}/receipts.sqlite'
    safe_file(root, receipt)
    data.update({receipt, 'data/ingestion/quarantine.jsonl'})
    # Minimal evidence travels with the data package; the complete source evidence is in source ZIP.
    data.update({'validation/run_manifest.json', 'validation/build_report.json',
                 'validation/ingestion_report.json', 'validation/quality_report.json'})
    for database in ['data/DA-E01.duckdb', receipt]:
        for suffix in ('.wal', '-wal', '-shm'):
            sidecar = root / (database + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise ValueError(f'Database has an active sidecar; close and checkpoint it first: {database}')
    if run.get('database_sha256') != file_hash(root / 'data/DA-E01.duckdb'):
        raise ValueError('Database differs from the completed run manifest')
    return source, data, {'generation': generation, 'intake': intake, 'normalized': normalized,
                          'receipt': receipt, 'run': run, 'junit_counts': tests,
                          'notebook_executed_code_cells': len(cells)}


def database_rows(root: Path, metadata: dict) -> dict:
    import duckdb
    database = root / 'data/DA-E01.duckdb'
    with duckdb.connect(str(database), read_only=True) as con:
        names = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='normalized' ORDER BY table_name").fetchall()
        result = {'normalized.' + name: con.execute('SELECT count(*) FROM normalized."' + name.replace('"', '""') + '"').fetchone()[0]
                  for (name,) in names}
    if len(result) != 26:
        raise ValueError('Expected all 26 canonical tables')
    for item in metadata['normalized']:
        if result['normalized.' + item['table']] != item['rows']:
            raise ValueError(f'Parquet manifest/database row mismatch: {item["table"]}')
    receipt = root / metadata['receipt']
    with closing(sqlite3.connect(receipt.as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Receipt database integrity check failed')
        receipt_rows = {name: con.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                        for name in ['receipts', 'accepted', 'event_versions', 'checkpoints']}
        snapshots = {row[0] for row in con.execute('SELECT DISTINCT snapshot FROM receipts')}
        if snapshots != {metadata['intake']['snapshot']}:
            raise ValueError('Receipt database is not isolated to the active snapshot')
    if receipt_rows['receipts'] != metadata['intake']['expected_source_attempts']:
        raise ValueError('Receipt database/source attempt count mismatch')
    return {'canonical_tables': result, 'active_receipt_tables': receipt_rows}


def make_archive(root: Path, destination: Path, selected: set[str], entries: dict,
                 manifest: dict, stamp: tuple[int, ...]) -> dict:
    payload = json_bytes({**manifest, 'files': [entries[p] for p in sorted(selected)]})
    payload_hash = hashlib.sha256(payload).hexdigest()
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for relative in sorted(selected):
            info = zipfile.ZipInfo(relative, stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if relative.endswith('.sh') else 0o100644) << 16
            info.create_system = 3
            with safe_file(root, relative).open('rb') as source, archive.open(info, 'w', force_zip64=True) as target:
                for block in iter(lambda: source.read(CHUNK), b''):
                    target.write(block)
        info = zipfile.ZipInfo('release_file_manifest.json', stamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        info.create_system = 3
        archive.writestr(info, payload)
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != selected | {'release_file_manifest.json'}:
            raise ValueError('Archive membership is not exactly the allowlist')
        for name in names:
            if not permitted_path(name):
                raise ValueError(f'Unsafe archive member: {name}')
            checksum = hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(CHUNK), b''):
                    checksum.update(block)
            expected = payload_hash if name == 'release_file_manifest.json' else entries[name]['sha256']
            if checksum.hexdigest() != expected:
                raise ValueError(f'Archive content changed during packaging: {name}')
    return {'filename': destination.name, 'bytes': destination.stat().st_size,
            'sha256': file_hash(destination), 'file_count': len(selected) + 1,
            'uncompressed_bytes': sum(entries[p]['bytes'] for p in selected) + len(payload),
            'embedded_manifest_sha256': payload_hash, 'content_verification': 'all_members_sha256_verified'}


def package(root: Path) -> dict:
    root = root.resolve()
    source, data, metadata = collect(root)
    tables = database_rows(root, metadata)
    selected = source | data
    entries = {name: inspect_file(root, name) for name in sorted(selected)}
    entries['data/DA-E01.duckdb']['logical_rows'] = sum(tables['canonical_tables'].values())
    entries[metadata['receipt']]['logical_rows'] = tables['active_receipt_tables']['receipts']
    for item in metadata['normalized']:
        if entries[item['path']]['logical_rows'] != item['rows']:
            raise ValueError(f'Parquet file/manifest row mismatch: {item["path"]}')
    date = datetime.fromisoformat(metadata['generation']['created_at'].replace('Z', '+00:00'))
    stamp = (date.year, date.month, date.day, date.hour, date.minute, date.second // 2 * 2)
    common = {'project_id': 'DA-E01', 'release_version': '1.0.0',
              'format_version': '1.0.0', 'profile': metadata['generation']['profile'],
              'seed': metadata['generation']['seed'],
              'operational_mode': metadata['run']['operational_mode'],
              'database_execution_evidence': metadata['run'].get('database_execution_evidence'),
              'delivered_local_intake_evidence': 'validation/local_intake_evidence.json' if 'validation/local_intake_evidence.json' in selected else None,
              'junit_counts': metadata['junit_counts'],
              'notebook_executed_code_cells': metadata['notebook_executed_code_cells'],
              'zip_timestamp_policy': 'fixed_from_original_synthetic_release_creation_not_packaging_time',
              'source_ownership': 'generator_manifest_sources_only_for_data_raw',
              'table_rows': tables, 'raw_origin': 'synthetic',
              'public_origin': 'EIA_observations_with_actual_retrieval_and_unknown_historical_publication',
              'license_refs': ['LICENSE', 'data/LICENSE.md', 'docs/sources.md'],
              'omitted_rebuildable_files': ['data/api/event_index.sqlite'],
              'source_rebuild_entry': 'python -m fleet_fuel.cli run --profile full --operational snapshot',
              'git_excluded_large_files': [name for name in sorted(entries) if not entries[name]['git_file_size_eligible']]}
    artifacts = root / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.package-', dir=artifacts) as working:
        archives = []
        for name, members in [('source', source), ('data', data), ('complete', selected)]:
            dest = Path(working) / f'DA-E01_v1_{name}.zip'
            archives.append(make_archive(root, dest, members, entries, {**common, 'package': name}, stamp))
        manifest = {**common, 'archives': archives, 'files': list(entries.values()),
                    'membership': {'source': sorted(source), 'data': sorted(data), 'complete': sorted(selected)}}
        content = json_bytes(manifest)
        (Path(working) / 'release_manifest.json').write_bytes(content)
        checksum_lines = [f'{item["sha256"]}  {item["filename"]}' for item in archives]
        checksum_lines.append(hashlib.sha256(content).hexdigest() + '  release_manifest.json')
        (Path(working) / 'SHA256SUMS.txt').write_text('\n'.join(checksum_lines) + '\n')
        # Publish only after every archive passed membership and member-hash checks.
        for path in sorted(Path(working).iterdir()):
            os.replace(path, artifacts / path.name)
    return {'status': 'packaged_and_verified', 'artifacts': 'artifacts/',
            'archives': archives, 'manifest': 'artifacts/release_manifest.json'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(package(args.root), indent=2))


if __name__ == '__main__':
    main()
