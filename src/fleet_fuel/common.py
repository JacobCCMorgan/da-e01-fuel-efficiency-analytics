"""Small deterministic file and contract utilities shared by pipeline stages."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def atomic_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')
    os.replace(temp, path)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def rows(path: Path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def contract(root: Path) -> dict:
    return json.loads((Path(root) / 'contracts/da_e01_contract.json').read_text())


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

