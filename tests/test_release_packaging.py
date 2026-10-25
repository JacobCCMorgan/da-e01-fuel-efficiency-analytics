"""Portable release boundaries and unchanged JUnit outcomes."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


def module(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


packaging = module('package_release')
normalizer = module('sanitize_validation_paths')


@pytest.mark.parametrize('path', ['../secret', '/absolute/file', 'data/.temp',
                                 'src/__pycache__/module.pyc', '.env',
                                 'data/receipts.sqlite-wal', 'credentials.json'])
def test_prohibited_release_paths_are_rejected(path):
    assert not packaging.permitted_path(path)


def test_explicit_ci_workflow_and_regular_source_paths_are_allowed():
    assert packaging.permitted_path('.github/workflows/ci.yml')
    assert packaging.permitted_path('src/fleet_fuel/analysis.py')
    assert packaging.permitted_path('data/ingestion/abc/receipts.sqlite')


def test_unsafe_content_is_rejected_without_mutating_input(tmp_path):
    p = tmp_path / 'evidence.txt'
    original = ('source: ' + str(tmp_path / 'private')).encode()
    p.write_bytes(original)
    with pytest.raises(ValueError, match='absolute_private_machine_path'):
        packaging.inspect_file(tmp_path, 'evidence.txt')
    assert p.read_bytes() == original


def test_archive_members_are_exact_and_repeatable(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'example.csv').write_text('id,value\n1,7\n')
    entry = packaging.inspect_file(root, 'example.csv')
    assert entry['logical_rows'] == 1
    kwargs = dict(root=root, selected={'example.csv'}, entries={'example.csv': entry},
                  manifest={'project_id': 'test'}, stamp=(2025, 1, 1, 0, 0, 0))
    first = packaging.make_archive(destination=tmp_path / 'a.zip', **kwargs)
    second = packaging.make_archive(destination=tmp_path / 'b.zip', **kwargs)
    assert first['sha256'] == second['sha256']
    with zipfile.ZipFile(tmp_path / 'a.zip') as archive:
        assert set(archive.namelist()) == {'example.csv', 'release_file_manifest.json'}
        assert archive.read('example.csv') == b'id,value\n1,7\n'
        assert json.loads(archive.read('release_file_manifest.json'))['files'][0]['sha256'] == entry['sha256']


def test_junit_path_normalization_preserves_results_and_original(tmp_path):
    root = tmp_path / 'project'
    validation = root / 'validation'
    validation.mkdir(parents=True)
    original = (f'<testsuites><testsuite name="tests" tests="1" skipped="1" failures="0" time="0.5">'
                f'<testcase name="test_service" classname="tests.service" time="0.2">'
                f'<skipped type="pytest.skip" message="service unavailable">'
                f'{root}/tests/test_service.py:10: service unavailable</skipped>'
                f'</testcase></testsuite></testsuites>').encode()
    path = validation / 'tests.xml'
    path.write_bytes(original)
    result = normalizer.sanitize(root, tmp_path / 'private_backup')
    portable = path.read_bytes()
    assert result['normalized_files'] == 1
    assert b'./tests/test_service.py' in portable
    assert normalizer.result_signature(original) == normalizer.result_signature(portable)
    assert next((tmp_path / 'private_backup').glob('*.xml')).read_bytes() == original
    evidence = json.loads((validation / 'path_normalization.json').read_text())
    assert evidence['records'][0]['portable_sha256'] == normalizer.sha256(portable)
    assert normalizer.sanitize(root, tmp_path / 'private_backup')['normalized_files'] == 0
