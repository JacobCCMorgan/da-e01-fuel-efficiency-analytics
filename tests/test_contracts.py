"""Contract and checker tests with deliberately bad independent examples."""
import json
from pathlib import Path

import duckdb

from fleet_fuel.quality import canonical_type, enum_values, scenario_evidence, validate


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_requirement_identity():
    contract = json.loads((ROOT/'contracts/da_e01_contract.json').read_text())
    assert len(contract['tables']) == 26
    assert len(contract['fields']) == 330
    ids = [m['s21_id'] for m in contract['mappings']]
    assert len(ids) == 153 and len(set(ids)) == 153
    assert {o['id'] for o in contract['spec']['output_lineage']} == {'DA-E01-O01','DA-E01-O02','DA-E01-O03'}


def test_schema_is_typed_and_executable():
    connection = duckdb.connect()
    connection.execute((ROOT/'contracts/schema.sql').read_text())
    columns = connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='normalized'").fetchone()[0]
    assert columns == 330
    assert connection.execute("SELECT data_type FROM information_schema.columns WHERE table_schema='normalized' AND table_name='fuel_purchase_line' AND column_name='purchase_amount'").fetchone()[0] == 'DECIMAL(20,6)'
    connection.close()


def test_enum_parser_ignores_prose_and_json():
    assert enum_values({'type':'VARCHAR','valid_values':'valid|error|unknown'}) == ['valid','error','unknown']
    assert enum_values({'type':'VARCHAR','valid_values':'USD|其他 ISO 代碼'}) is None
    assert enum_values({'type':'JSON','valid_values':'{"state":"valid|error"}'}) is None
    assert enum_values({'type':'VARCHAR','valid_values':'DA-E01|DS-E01'}) == ['DA-E01','DS-E01']
    assert enum_values({'type':'VARCHAR','valid_values':'km/h|mph'}) == ['km/h','mph']
    assert canonical_type('TIMESTAMP WITH TIME ZONE') == 'TIMESTAMPTZ'


def test_empty_database_does_not_pass(tmp_path):
    (tmp_path/'data').mkdir(); (tmp_path/'contracts').mkdir()
    (tmp_path/'contracts/da_e01_contract.json').write_text((ROOT/'contracts/da_e01_contract.json').read_text())
    duckdb.connect(str(tmp_path/'data/DA-E01.duckdb')).close()
    report = validate(tmp_path)
    assert report['status'] == 'failed'
    assert report['error_count'] == 26
    trace = json.loads((tmp_path/'validation/requirement_traceability.json').read_text())
    assert len(trace) == 153
    assert {r['status'] for r in trace} == {'missing_table_or_column'}


def test_duplicate_and_invalid_enum_are_detected(tmp_path):
    (tmp_path/'data').mkdir(); (tmp_path/'contracts').mkdir()
    contract = {'tables':[{'name':'example','layer':'source','primary_key':['id'],'unique_constraints':[],'foreign_keys':[]}],
                'fields':[{'table':'example','name':'id','type':'VARCHAR','nullable':False,'field_id':'F-ID','unit':'none','valid_values':'stable identifier','nullable_when':'never'},
                          {'table':'example','name':'state','type':'VARCHAR','nullable':False,'field_id':'F-STATE','unit':'none','valid_values':'valid|unknown','nullable_when':'never'}],
                'mappings':[], 'spec':{'required_tables':['example'],'original_requirements':[]}}
    (tmp_path/'contracts/da_e01_contract.json').write_text(json.dumps(contract))
    con=duckdb.connect(str(tmp_path/'data/DA-E01.duckdb'))
    con.execute("CREATE SCHEMA normalized; CREATE TABLE normalized.example(id VARCHAR,state VARCHAR); INSERT INTO normalized.example VALUES ('same','valid'),('same','impossible')")
    con.close()
    report=validate(tmp_path)
    failed={c['id']:c['violations'] for c in report['checks'] if c['status']=='failed'}
    assert failed['example.unique.id'] == 1
    assert failed['example.state.enum'] == 1


def test_null_requires_an_explicit_state(tmp_path):
    (tmp_path/'data').mkdir(); (tmp_path/'contracts').mkdir()
    tables=[{'name':n,'layer':'source','primary_key':['provenance_id'],'unique_constraints':[],'foreign_keys':[]} for n in ['example','provenance_record']]
    fields=[]
    for table,name,kind,nullable in [('example','provenance_id','VARCHAR',False),('example','value','INTEGER',True),('provenance_record','provenance_id','VARCHAR',False),('provenance_record','value_states','JSON',False)]:
        fields.append({'table':table,'name':name,'type':kind,'nullable':nullable,'field_id':table+'.'+name,'unit':'none','valid_values':'contract value','nullable_when':'unknown only' if nullable else 'never'})
    contract={'tables':tables,'fields':fields,'mappings':[],'spec':{'required_tables':['example','provenance_record'],'original_requirements':[]}}
    (tmp_path/'contracts/da_e01_contract.json').write_text(json.dumps(contract))
    con=duckdb.connect(str(tmp_path/'data/DA-E01.duckdb'))
    con.execute('CREATE SCHEMA normalized; CREATE TABLE normalized.example(provenance_id VARCHAR,value INTEGER); CREATE TABLE normalized.provenance_record(provenance_id VARCHAR,value_states JSON)')
    con.execute("INSERT INTO normalized.example VALUES ('p1',NULL),('p2',NULL)")
    con.execute('INSERT INTO normalized.provenance_record VALUES (?,?),(?,?)',['p1',json.dumps({'example.value':{'state':'unknown','reason':'not observed'}}),'p2','{}'])
    con.close()
    report=validate(tmp_path)
    check=next(c for c in report['checks'] if c['id']=='example.value.null_state')
    assert check['violations']==1


def test_unexecuted_or_failed_scenario_is_not_passing_evidence(tmp_path):
    assert scenario_evidence(tmp_path)['DA-E01-V22-02']['status'] == 'not_fully_evaluated'
    (tmp_path/'validation').mkdir()
    (tmp_path/'validation/test_results.xml').write_text('''<testsuites><testsuite>
      <testcase name="test_production_interval_pairs_exact_common_boundaries"/>
      <testcase name="test_confirmed_wrap_is_recovered_but_unknown_negative_jump_is_not"><failure>unexpected wrap</failure></testcase>
    </testsuite></testsuites>''')
    result=scenario_evidence(tmp_path)
    assert result['DA-E01-V22-02']['status']=='failed'
    assert result['DA-E01-V22-01']['status']=='not_fully_evaluated'


def test_unregistered_external_source_is_rejected(tmp_path):
    (tmp_path/'data').mkdir(); (tmp_path/'contracts').mkdir()
    field={'table':'example','name':'source_dataset_id','type':'VARCHAR','nullable':False,
           'field_id':'F-SOURCE','unit':'none','valid_values':'nonempty identifier'}
    contract={'tables':[{'name':'example','layer':'source','primary_key':['source_dataset_id'],
              'foreign_keys':[{'columns':['source_dataset_id'],'ref_table':'source_dataset','ref_columns':['source_dataset_id']}]}],
              'fields':[field],'mappings':[],'spec':{'required_tables':['example'],'original_requirements':[]}}
    (tmp_path/'contracts/da_e01_contract.json').write_text(json.dumps(contract))
    (tmp_path/'contracts/source_registry.json').write_text(json.dumps({'entries':[{'source_dataset_id':'registered','origin_type':'synthetic'}]}))
    con=duckdb.connect(str(tmp_path/'data/DA-E01.duckdb'))
    con.execute("CREATE SCHEMA normalized;CREATE TABLE normalized.example(source_dataset_id VARCHAR);INSERT INTO normalized.example VALUES ('registered'),('unregistered')")
    con.close()
    report=validate(tmp_path)
    check=next(c for c in report['checks'] if c['id']=='example.fk.0')
    assert check['violations']==1
    assert report['status']=='failed'
