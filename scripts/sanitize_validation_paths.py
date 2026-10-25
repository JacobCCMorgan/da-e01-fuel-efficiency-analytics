#!/usr/bin/env python3
"""Remove machine-specific prefixes from JUnit paths without changing results."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def result_signature(data: bytes) -> list:
    tree = ET.fromstring(data)
    # Deliberately omit locations/text; retain all result identities and outcomes.
    return [(node.tag, tuple(sorted((key, value) for key, value in node.attrib.items()
             if key in {'name', 'classname', 'tests', 'errors', 'failures', 'skipped',
                        'time', 'timestamp', 'type', 'message'})))
            for node in tree.iter()]


def sanitize(root: Path, backup_dir: Path, filenames: list[str] | None = None) -> dict:
    root = root.resolve()
    backup_dir = backup_dir.resolve()
    if backup_dir == root or root in backup_dir.parents:
        raise ValueError('Original evidence backups must be outside the deliverable root')
    paths = ([root / name for name in filenames] if filenames
             else sorted((root / 'validation').rglob('*.xml')))
    records = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() != '.xml':
            raise ValueError('Expected an existing JUnit XML file')
        rel = path.resolve().relative_to(root).as_posix()
        before = path.read_bytes()
        content = before.decode('utf-8')
        # Exact local checkout, then GitHub Actions' repeated repository prefix.
        content = content.replace(str(root) + '/', './')
        runner_prefix = '/' + 'home/runner/work/'
        content = re.sub(re.escape(runner_prefix) + r'[^/\s<>]+/[^/\s<>]+/', './', content)
        after = content.encode('utf-8')
        if result_signature(before) != result_signature(after):
            raise RuntimeError('JUnit result identity or outcome changed during path normalization')
        if before == after:
            continue
        original_hash = sha256(before)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f'{path.stem}.{original_hash}.xml'
        if backup.exists() and backup.read_bytes() != before:
            raise RuntimeError('Existing immutable evidence backup does not match')
        if not backup.exists():
            backup.write_bytes(before)
        path.write_bytes(after)
        records.append({'path': rel, 'original_sha256': original_hash,
                        'portable_sha256': sha256(after),
                        'original_bytes': len(before), 'portable_bytes': len(after),
                        'normalization': 'machine_prefix_to_relative_dot_slash',
                        'result_signature_unchanged': True,
                        'original_location': 'private_external_backup_not_in_release',
                        'checksum_policy': 'original_checksum_replaced_by_portable_checksum'})
    target = root / 'validation/path_normalization.json'
    previous = json.loads(target.read_text()) if target.exists() else {'version': '1.0.0', 'records': []}
    known = {(r['path'], r['original_sha256'], r['portable_sha256']) for r in previous['records']}
    previous['records'].extend(r for r in records
                               if (r['path'], r['original_sha256'], r['portable_sha256']) not in known)
    previous['scope'] = 'JUnit filesystem locations only; counts, outcomes, timing and skip reasons preserved'
    previous['note'] = 'Portable files have new hashes; original checksums no longer identify the normalized bytes.'
    target.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + '\n')
    return {'normalized_files': len(records), 'evidence': 'validation/path_normalization.json'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--file', action='append', dest='filenames')
    args = p.parse_args()
    backup = args.backup_dir or args.root.resolve().parent / 'work' / 'validation_originals'
    print(json.dumps(sanitize(args.root, backup, args.filenames)))


if __name__ == '__main__':
    main()
