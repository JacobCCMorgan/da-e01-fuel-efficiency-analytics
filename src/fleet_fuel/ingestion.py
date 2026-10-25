"""Audited HTTP ingestion and typed analytical-database loading."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import duckdb
import requests

from .common import atomic_json, contract, digest, ident, json_text, rows, utcnow
from .quality import enum_values
from .input_policy import forbidden_payload_field


DERIVED = {'fuel_report_run','fuel_paired_interval','fuel_weekly_metric','fuel_inventory_balance'}
EVENT_TABLES = {'fuel_counter_observation'}


def validate_envelope(event: dict, definitions: dict) -> tuple[str | None, str | None]:
    if not isinstance(event, dict) or not all(k in event for k in ('event_id','revision','available_time','event_time','tenant_id','table','payload')):
        return 'invalid_envelope', None
    table = event['table']
    if not isinstance(table,str) or table not in EVENT_TABLES or table not in definitions:
        return 'unsupported_table', None
    if (isinstance(event['revision'],bool) or not isinstance(event['revision'],int)
        or event['revision']<1 or not isinstance(event['event_id'],str)
        or not event['event_id'].strip()):
        return 'invalid_event_identity', None
    if not isinstance(event['tenant_id'],str) or not event['tenant_id'].strip():
        return 'invalid_envelope', None
    if any(not isinstance(event[key],str) for key in ('event_time','available_time')):
        return 'invalid_envelope', None
    payload = event['payload']
    if not isinstance(payload, dict) or payload.get('tenant_id') != event['tenant_id']:
        return 'tenant_mismatch', None
    if any(forbidden_payload_field(name) for name in payload):
        return 'forbidden_payload_field', None
    allowed={field['name'] for field in definitions[table]['fields']}
    if set(payload)-allowed:
        return 'unknown_payload_field', None
    try:
        for k in ('available_time','event_time'):
            d = datetime.fromisoformat(event[k].replace('Z','+00:00'))
            if d.tzinfo is None:
                return 'timezone_missing', None
        spec = definitions[table]
        for field in spec['fields']:
            value = payload.get(field['name'])
            if value is None:
                if not field.get('nullable', True):
                    return 'required_value_missing', None
                continue
            typ = field['type'].upper()
            allowed = enum_values(field)
            if allowed is not None and value not in allowed:
                return 'invalid_enum', None
            if typ in ('DOUBLE','FLOAT','INTEGER','BIGINT') or typ.startswith('DECIMAL'):
                if isinstance(value, bool) or not math.isfinite(float(value)):
                    return 'invalid_number', None
            if typ.startswith('TIMESTAMP'):
                d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
                if d.tzinfo is None:
                    return 'timezone_missing', None
        key = [payload.get(k) for k in spec['primary_key']]
        if any(x is None or x=='' for x in key):
            return 'missing_primary_key', None
    except (ValueError, TypeError, AttributeError):
        return 'invalid_payload_type', None
    return None, json_text(key)


def receipt_database(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS receipts (
      snapshot TEXT,source_sequence INTEGER,event_id TEXT,revision INTEGER,
      canonical_table TEXT,canonical_key TEXT,payload_sha256 TEXT,
      disposition TEXT,reason TEXT,source_line INTEGER,received_at TEXT,
      envelope_json TEXT,PRIMARY KEY(snapshot,source_sequence));
    CREATE TABLE IF NOT EXISTS accepted (
      canonical_table TEXT,canonical_key TEXT,event_id TEXT,revision INTEGER,
      payload_sha256 TEXT,payload_json TEXT,PRIMARY KEY(canonical_table,canonical_key));
    CREATE TABLE IF NOT EXISTS event_versions (
      event_id TEXT,revision INTEGER,payload_sha256 TEXT,PRIMARY KEY(event_id,revision));
    CREATE TABLE IF NOT EXISTS checkpoints (snapshot TEXT PRIMARY KEY,cursor TEXT);
    ''')
    return db


def ingest_api(root: Path, url: str, limit=2000, resume=True, test_fault=None, timeout=15, max_pages=None) -> dict:
    root=Path(root)
    c=contract(root)
    definitions={t['name']:{**t,'fields':[f for f in c['fields'] if f['table']==t['name']]} for t in c['tables']}
    started=utcnow()
    health=requests.get(url+'/health', timeout=timeout);health.raise_for_status()
    snapshot=health.json()['snapshot']
    db=receipt_database(root/'data/ingestion'/snapshot/'receipts.sqlite')
    state=db.execute('SELECT cursor FROM checkpoints WHERE snapshot=?',(snapshot,)).fetchone()
    cursor=state[0] if resume and state else None
    pages,retries,seen=0,0,0
    counters=Counter()
    while True:
        params={'limit':limit}
        if cursor: params['cursor']=cursor
        if test_fault: params['test_fault']=test_fault
        response=None
        for attempt in range(4):
            try:
                response=requests.get(url+'/v1/events',params=params,timeout=timeout)
                if response.status_code not in (429,500,502,503,504):
                    response.raise_for_status();break
            except (requests.Timeout,requests.ConnectionError):
                response=None
            if attempt==3:
                db.close()
                raise RuntimeError('source exhausted bounded retries; committed checkpoint retained')
            retries+=1
            time.sleep(min(.05*(2**attempt),.2))
        body=response.json()
        if body['snapshot']!=snapshot:
            raise RuntimeError('source snapshot changed during paging')
        with db:
            for item in body['items']:
                seq=item['source_sequence'];event=item['envelope'];seen+=1
                prior=db.execute('SELECT 1 FROM receipts WHERE snapshot=? AND source_sequence=?',(snapshot,seq)).fetchone()
                if prior:
                    counters['already_received']+=1;continue
                reason,key=validate_envelope(event,definitions)
                payload=event.get('payload') if isinstance(event,dict) else None
                payload_json=json_text(payload)
                sha=hashlib.sha256(payload_json.encode()).hexdigest()
                disposition='quarantined' if reason else 'accepted'
                eid=event.get('event_id') if isinstance(event,dict) else None
                rev=event.get('revision') if isinstance(event,dict) else None
                table=event.get('table') if isinstance(event,dict) else None
                # The complete malformed values remain in envelope_json. Audit
                # index columns retain only valid scalar identity types.
                eid=eid if isinstance(eid,str) else None
                rev=rev if isinstance(rev,int) and not isinstance(rev,bool) else None
                table=table if isinstance(table,str) else None
                if not reason:
                    version=db.execute('SELECT payload_sha256 FROM event_versions WHERE event_id=? AND revision=?',(eid,rev)).fetchone()
                    existing=db.execute('SELECT payload_sha256 FROM accepted WHERE canonical_table=? AND canonical_key=?',(table,key)).fetchone()
                    if version:
                        disposition='duplicate' if version[0]==sha else 'quarantined'
                        reason='same_event_revision' if version[0]==sha else 'conflicting_event_revision'
                    elif existing:
                        disposition='duplicate' if existing[0]==sha else 'quarantined'
                        reason='same_canonical_record' if existing[0]==sha else 'immutable_key_conflict'
                    else:
                        db.execute('INSERT INTO accepted VALUES (?,?,?,?,?,?)',(table,key,eid,rev,sha,payload_json))
                    if disposition!='quarantined':
                        db.execute('INSERT OR IGNORE INTO event_versions VALUES (?,?,?)',(eid,rev,sha))
                db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(snapshot,seq,eid,rev,table,key,sha,disposition,reason,item['source_line'],utcnow(),json_text(event)))
                counters[disposition]+=1
            cursor=body['checkpoint_cursor']
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES (?,?)',(snapshot,cursor))
        pages+=1
        if not body['next_cursor'] or (max_pages and pages>=max_pages):break
    total=dict(db.execute('SELECT disposition,count(*) FROM receipts WHERE snapshot=? GROUP BY disposition',(snapshot,)).fetchall())
    expected_count=health.json().get('total_events')
    accepted_count=db.execute('SELECT count(*) FROM accepted').fetchone()[0]
    staged=root/'data/staged/events';staged.mkdir(parents=True,exist_ok=True)
    for table in EVENT_TABLES:
        target=staged/(table+'.jsonl');temp=target.with_suffix('.tmp')
        with temp.open('w') as out:
            for (payload,) in db.execute('SELECT payload_json FROM accepted WHERE canonical_table=? ORDER BY canonical_key',(table,)):
                out.write(payload+'\n')
        os.replace(temp,target)
    quarantine=root/'data/ingestion/quarantine.jsonl'
    with quarantine.open('w') as out:
        for record in db.execute("SELECT source_sequence,reason,envelope_json FROM receipts WHERE disposition='quarantined' ORDER BY snapshot,source_sequence"):
            out.write(json_text({'source_sequence':record[0],'reason':record[1],'envelope':json.loads(record[2])})+'\n')
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.close()
    result={'mode':'http_simulated_eld_api','snapshot':snapshot,'started_at':started,'finished_at':utcnow(),'pages':pages,'retries':retries,'new_receipts':dict(counters),'total_receipts':total,'accepted_records':accepted_count,'expected_source_attempts':expected_count,'complete':not bool(body['next_cursor']),'checkpoint':cursor,'counts_reconcile':expected_count is not None and sum(total.values())==expected_count}
    atomic_json(root/'validation/ingestion_report.json',result)
    return result


def load_json_table(con, table: str, path: Path, fields: list[dict]):
    columns={f['name']:f['type'] for f in fields}
    col_literal='{'+','.join("'"+k.replace("'","''")+"':'"+v.replace("'","''")+"'" for k,v in columns.items())+'}'
    if not path.exists() or path.stat().st_size==0:
        return 0
    con.execute(f'INSERT INTO normalized.{ident(table)} BY NAME SELECT * FROM read_json(?,columns={col_literal},format=\'newline_delimited\')',[str(path)])
    return con.execute(f'SELECT count(*) FROM normalized.{ident(table)}').fetchone()[0]


def normalize_counter_units(con) -> dict:
    """Calculate canonical units from raw values and retain the supplied values.

    Only the normalized database is updated. Unknown units and absent raw values
    produce NULL, with an explicit audit reason; supplied canonical numbers are
    never used to fill the gap. Observation identity includes the tenant.
    """
    con.execute('CREATE SCHEMA IF NOT EXISTS audit')
    con.execute("""CREATE OR REPLACE TABLE audit.unit_normalization AS
      WITH converted AS (
        SELECT tenant_id,counter_observation_id,
          fuel_total_l AS supplied_fuel_l,odometer_km AS supplied_distance_km,
          CAST(fuel_total_raw*CASE fuel_raw_unit WHEN 'US_gal' THEN 3.785411784 WHEN 'L' THEN 1 END AS DECIMAL(20,6)) AS calculated_fuel_l,
          CAST(odometer_raw*CASE distance_raw_unit WHEN 'mile' THEN 1.609344 WHEN 'km' THEN 1 END AS DECIMAL(20,6)) AS calculated_distance_km,
          CASE WHEN fuel_raw_unit IS NULL OR fuel_raw_unit NOT IN ('US_gal','L') THEN 'unsupported_unit'
            WHEN fuel_total_raw IS NULL THEN 'missing_raw_value' ELSE 'normalized' END AS fuel_unit_status,
          CASE WHEN distance_raw_unit IS NULL OR distance_raw_unit NOT IN ('mile','km') THEN 'unsupported_unit'
            WHEN odometer_raw IS NULL THEN 'missing_raw_value' ELSE 'normalized' END AS distance_unit_status
        FROM normalized.fuel_counter_observation
      )
      SELECT *,supplied_fuel_l IS DISTINCT FROM calculated_fuel_l AS fuel_value_mismatch,
        supplied_distance_km IS DISTINCT FROM calculated_distance_km AS distance_value_mismatch
      FROM converted""")
    con.execute("""UPDATE normalized.fuel_counter_observation AS o SET
       fuel_total_l=a.calculated_fuel_l,odometer_km=a.calculated_distance_km
       FROM audit.unit_normalization a
       WHERE a.tenant_id=o.tenant_id AND a.counter_observation_id=o.counter_observation_id""")
    names=['rows','fuel_value_mismatches','distance_value_mismatches','unsupported_fuel_units',
           'unsupported_distance_units','missing_fuel_raw_values','missing_distance_raw_values']
    values=con.execute("""SELECT count(*),count(*) FILTER(WHERE fuel_value_mismatch),
      count(*) FILTER(WHERE distance_value_mismatch),count(*) FILTER(WHERE fuel_unit_status='unsupported_unit'),
      count(*) FILTER(WHERE distance_unit_status='unsupported_unit'),count(*) FILTER(WHERE fuel_unit_status='missing_raw_value'),
      count(*) FILTER(WHERE distance_unit_status='missing_raw_value') FROM audit.unit_normalization""").fetchone()
    return dict(zip(names,values))


def build_database(root: Path, operational_dir: Path|None=None) -> dict:
    root=Path(root);c=contract(root)
    target=root/'data/DA-E01.duckdb';temp=root/'data/build.tmp.duckdb'
    if temp.exists():temp.unlink()
    con=duckdb.connect(str(temp));con.execute("SET TimeZone='UTC'")
    con.execute((root/'contracts/schema.sql').read_text())
    counts={};inputs={}
    for t in c['tables']:
        name=t['name']
        if name in DERIVED:continue
        if name in EVENT_TABLES:
            path=root/'data/staged/events'/f'{name}.jsonl'
            if not path.exists():raise FileNotFoundError('Run the HTTP/event ingestion before building the database')
        else:
            candidate=(Path(operational_dir)/f'{name}.jsonl') if operational_dir else None
            path=candidate if candidate and candidate.exists() else root/'data/raw/tables'/f'{name}.jsonl'
        if not path.exists():raise FileNotFoundError(path)
        fields=[f for f in c['fields'] if f['table']==name]
        counts[name]=load_json_table(con,name,path,fields);inputs[name]={'path':str(path.relative_to(root)),'sha256':digest(path)}
    con.execute('CREATE SCHEMA IF NOT EXISTS operations')
    for p in sorted((root/'data/raw/operations').glob('*.jsonl')):
        if p.stat().st_size:
            con.execute(f'CREATE TABLE operations.{ident(p.stem)} AS SELECT * FROM read_json_auto(?)',[str(p)])
    public=root/'data/public/fuel_prices.jsonl'
    if public.exists() and public.stat().st_size:
        con.execute('CREATE SCHEMA IF NOT EXISTS external')
        con.execute('CREATE TABLE external.public_prices AS SELECT * FROM read_json_auto(?)',[str(public)])
        from .public_normalization import append_public_prices
        append_public_prices(root,con)
    normalization=normalize_counter_units(con)
    for t in c['tables']:
        counts[t['name']]=con.execute(f'SELECT count(*) FROM normalized.{ident(t["name"])}').fetchone()[0]
    con.execute('CHECKPOINT')
    con.close();os.replace(temp,target)
    result={'database':str(target.relative_to(root)),'rows':counts,'inputs':inputs,'unit_normalization':normalization,'operational_source':'postgresql_extract' if operational_dir else 'frozen_synthetic_snapshot','built_at':utcnow()}
    atomic_json(root/'validation/build_report.json',result)
    return result


def export_normalized(root: Path):
    root=Path(root);out=root/'data/normalized';out.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(root/'data/DA-E01.duckdb'),read_only=True)
    manifest=[]
    for (name,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='normalized' ORDER BY table_name").fetchall():
        path=out/(name+'.parquet')
        con.execute(f'COPY normalized.{ident(name)} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(path)])
        manifest.append({'table':name,'path':str(path.relative_to(root)),'rows':con.execute(f'SELECT count(*) FROM normalized.{ident(name)}').fetchone()[0],'sha256':digest(path)})
    con.close();atomic_json(out/'manifest.json',manifest)
    return manifest
