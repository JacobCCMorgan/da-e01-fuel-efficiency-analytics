"""Reassemble and verify DA-E01 split ZIPs using Python 3, with no dependencies.

Usage: python reassemble_archives.py DA-E01_v1_data.parts.json
Place this script, the manifest and all numbered parts in the same directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):
            result.update(block)
    return result.hexdigest()


def safe_name(name):
    if not isinstance(name,str) or not name or Path(name).name!=name or '/' in name or '\\' in name or name in {'.','..'}:
        raise ValueError('Manifest file names must be simple basenames')
    return name


def reassemble(manifest_path):
    manifest_path=manifest_path.resolve()
    manifest=json.loads(manifest_path.read_text())
    if manifest['format']!='raw_byte_parts_v1':
        raise ValueError('Unsupported manifest format')
    base=manifest_path.parent
    output=base/safe_name(manifest['original_filename'])
    if output.exists():
        if output.stat().st_size==manifest['original_bytes'] and digest(output)==manifest['original_sha256']:
            print(f'Already complete and SHA256 verified: {output.name}')
            return output
        raise FileExistsError(f'Refusing to replace an existing different file: {output}')
    parts=[]
    for number,entry in enumerate(manifest['parts'],1):
        name=safe_name(entry['filename'])
        if name!=f'{output.name}.part{number:03d}':
            raise ValueError('Parts must follow the declared sequential names')
        part=base/name
        if part.stat().st_size!=entry['bytes'] or digest(part)!=entry['sha256']:
            raise ValueError(f'Part size or SHA256 does not match: {part.name}')
        parts.append(part)
    temporary=output.with_name(output.name+'.assembling')
    if temporary.exists():
        raise FileExistsError(f'Remove an earlier incomplete temporary file first: {temporary}')
    total=hashlib.sha256();size=0
    try:
        with temporary.open('xb') as stream:
            for part in parts:
                with part.open('rb') as source:
                    while block:=source.read(1024*1024):
                        stream.write(block);total.update(block);size+=len(block)
        if size!=manifest['original_bytes'] or total.hexdigest()!=manifest['original_sha256']:
            raise ValueError('Reassembled archive does not match the original SHA256')
        os.replace(temporary,output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f'Reassembled and SHA256 verified: {output.name} ({size:,} bytes)')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    reassemble(parser.parse_args().manifest)
