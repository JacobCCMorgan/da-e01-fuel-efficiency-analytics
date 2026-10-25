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
        assert report['counts_reconcile'] is True
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
        assert second['counts_reconcile'] is True


@pytest.mark.parametrize('fault',['once_429','once_503','once_slow'])
def test_retry_without_duplicate_side_effects(source,fault):
    with serve(source) as url:
        result=ingest_api(source,url,limit=100,test_fault=fault,timeout=.06 if fault=='once_slow' else 3)
        assert result['retries']==1
        assert result['accepted_records']==2
        assert result['counts_reconcile'] is True


def test_cursor_rejects_different_snapshot():
    with pytest.raises(ValueError):read_cursor(cursor_token('first',3),'second')


def test_http_invalid_page_size_and_cursor(source):
    with serve(source) as url:
        assert requests.get(url+'/v1/events',params={'limit':0},timeout=3).status_code==400
        assert requests.get(url+'/v1/events',params={'cursor':cursor_token('wrong',4)},timeout=3).status_code==409


def test_malformed_json_is_quarantined_with_original_line(source):
    path=source/'data/raw/events.jsonl'
    malformed='{"event_id": "broken", this is not JSON}'
    with path.open('a') as stream:stream.write(malformed+'\n')
    with serve(source) as url:
        result=ingest_api(source,url,limit=2)
    assert result['total_receipts']=={'accepted':2,'duplicate':1,'quarantined':2}
    assert result['counts_reconcile'] is True
    quarantine=[json.loads(line) for line in (source/'data/ingestion/quarantine.jsonl').read_text().splitlines()]
    broken=next(r for r in quarantine if r['envelope'].get('transport_error')=='invalid_json')
    assert broken['reason']=='invalid_envelope'
    assert broken['envelope']['raw_line']==malformed


def test_changed_source_snapshot_has_separate_accepted_ledger(source):
    with serve(source) as url:first=ingest_api(source,url)
    path=source/'data/raw/events.jsonl'
    changed=json.loads(path.read_text().splitlines()[0])
    changed['payload']['fuel_total_l']=99
    path.write_text(json.dumps(changed)+'\n')
    with serve(source) as url:second=ingest_api(source,url)
    assert first['snapshot']!=second['snapshot']
    assert first['counts_reconcile'] is second['counts_reconcile'] is True
    assert second['total_receipts']=={'accepted':1}
    assert second['accepted_records']==1
    for report,count in [(first,2),(second,1)]:
        ledger=source/'data/ingestion'/report['snapshot']/'receipts.sqlite'
        with sqlite3.connect(ledger) as con:
            assert con.execute('SELECT count(*) FROM accepted').fetchone()[0]==count
    staged=[json.loads(line) for line in (source/'data/staged/events/fuel_counter_observation.jsonl').read_text().splitlines()]
    assert len(staged)==1 and staged[0]['fuel_total_l']==99


@pytest.mark.parametrize('change',[{'revision':True},{'event_id':123},{'event_id':{'bad':'type'}}])
def test_invalid_event_identity_is_quarantined_not_coerced(source,change):
    path=source/'data/raw/events.jsonl'
    malformed=json.loads(path.read_text().splitlines()[0]);malformed.update(change)
    path.write_text(json.dumps(malformed)+'\n')
    with serve(source) as url:result=ingest_api(source,url)
    assert result['total_receipts']=={'quarantined':1}
    assert result['accepted_records']==0
    assert result['counts_reconcile'] is True
    assert json.loads((source/'data/ingestion/quarantine.jsonl').read_text())['reason']=='invalid_event_identity'


@pytest.mark.parametrize('extra,reason',[
    ({'true_fuel_l':42},'forbidden_payload_field'),
    ({'expected_waste_label':True},'forbidden_payload_field'),
    ({'supplier_new_column':'unreviewed'},'unknown_payload_field'),
])
def test_unapproved_payload_fields_are_quarantined_before_staging(source,extra,reason):
    path=source/'data/raw/events.jsonl'
    event=json.loads(path.read_text().splitlines()[0]);event['payload'].update(extra)
    path.write_text(json.dumps(event)+'\n')
    with serve(source) as url:result=ingest_api(source,url)
    assert result['total_receipts']=={'quarantined':1}
    assert result['accepted_records']==0 and result['counts_reconcile'] is True
    assert (source/'data/staged/events/fuel_counter_observation.jsonl').read_text()==''
    quarantined=json.loads((source/'data/ingestion/quarantine.jsonl').read_text())
    assert quarantined['reason']==reason
    assert all(quarantined['envelope']['payload'][key]==value for key,value in extra.items())


@pytest.mark.parametrize('change',[
    {'table':[]},{'table':{}},{'event_time':123},{'available_time':123},{'tenant_id':['T01']},
])
def test_malformed_scalar_envelope_types_are_quarantined_without_crashing(source,change):
    path=source/'data/raw/events.jsonl'
    event=json.loads(path.read_text().splitlines()[0]);event.update(change)
    path.write_text(json.dumps(event)+'\n')
    with serve(source) as url:result=ingest_api(source,url)
    assert result['total_receipts']=={'quarantined':1}
    assert result['accepted_records']==0 and result['counts_reconcile'] is True


def test_available_since_uses_instants_and_rejects_naive_time(source):
    path=source/'data/raw/events.jsonl'
    original=[json.loads(line) for line in path.read_text().splitlines()]
    a,b=original[0],original[2]
    a['available_time']='2025-01-02T14:00:00+02:00'  #12:00UTC
    b['available_time']='2025-01-02T11:30:00Z'
    path.write_text(json.dumps(a)+'\n'+json.dumps(b)+'\n')
    with serve(source) as url:
        utc=requests.get(url+'/v1/events',params={'available_since':'2025-01-02T12:00:00Z'},timeout=3).json()
        offset=requests.get(url+'/v1/events',params={'available_since':'2025-01-02T13:00:00+01:00'},timeout=3).json()
        later=requests.get(url+'/v1/events',params={'available_since':'2025-01-02T13:00:00Z'},timeout=3).json()
        assert utc['items']==offset['items']
        assert [r['envelope']['event_id'] for r in utc['items']]==['E1']
        assert later['items']==[]
        assert requests.get(url+'/v1/events',params={'available_since':'2025-01-02T12:00:00'},timeout=3).status_code==400
    assert json.loads(path.read_text().splitlines()[0])['available_time']=='2025-01-02T14:00:00+02:00'

