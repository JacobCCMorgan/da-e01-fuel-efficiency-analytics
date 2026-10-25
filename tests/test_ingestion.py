import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import requests

from fleet_fuel.event_api import serve, read_cursor, cursor_token
from fleet_fuel.ingestion import ingest_api


@pytest.fixture
def source(tmp_path):
    project=Path(__file__).resolve().parents[1]
    (tmp_path/'contracts').mkdir();shutil.copy(project/'contracts/da_e01_contract.json',tmp_path/'contracts/da_e01_contract.json')
    (tmp_path/'data/raw').mkdir(parents=True)
    def event(n, **changes):
        obj={'event_id':f'E{n}','revision':1,'available_time':'2025-01-02T12:00:00+00:00','event_time':'2025-01-02T11:59:00+00:00','tenant_id':'T01','table':'fuel_counter_observation','payload':{'tenant_id':'T01','counter_observation_id':f'O{n}','provenance_id':f'P{n}','device_id':'D01','signal_definition_id':'SD01','fuel_total_l':n*10,'odometer_km':n*30}}
        obj.update(changes);return obj
    data=[event(1),event(1),event(2),event(3,tenant_id='T02')]
    (tmp_path/'data/raw/events.jsonl').write_text('\n'.join(json.dumps(x) for x in data)+'\n')
    return tmp_path


def test_duplicate_and_tenant_quarantine_have_independent_expected_counts(source):
    with serve(source) as url:
        report=ingest_api(source,url,limit=1)
        assert report['total_receipts']=={'accepted':2,'duplicate':1,'quarantined':1}
        rerun=ingest_api(source,url,resume=False)
        assert rerun['new_receipts']=={'already_received':4}
        assert rerun['accepted_records']==2
    bad=json.loads((source/'data/ingestion/quarantine.jsonl').read_text())
    assert bad['reason']=='tenant_mismatch'


def test_checkpoint_resume_does_not_skip_equal_available_times(source):
    with serve(source) as url:
        first=ingest_api(source,url,limit=1,max_pages=2)
        assert first['complete'] is False
        second=ingest_api(source,url,limit=1)
        assert second['complete'] is True
        assert sum(second['total_receipts'].values())==4


@pytest.mark.parametrize('fault',['once_429','once_503','once_slow'])
def test_retry_without_duplicate_side_effects(source,fault):
    with serve(source) as url:
        result=ingest_api(source,url,limit=100,test_fault=fault,timeout=.06 if fault=='once_slow' else 3)
        assert result['retries']==1
        assert result['accepted_records']==2


def test_cursor_rejects_different_snapshot():
    with pytest.raises(ValueError):read_cursor(cursor_token('first',3),'second')


def test_http_invalid_page_size_and_cursor(source):
    with serve(source) as url:
        assert requests.get(url+'/v1/events',params={'limit':0},timeout=3).status_code==400
        assert requests.get(url+'/v1/events',params={'cursor':cursor_token('wrong',4)},timeout=3).status_code==409

