"""Small independent arithmetic cases exercise the production SQL."""

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from fleet_fuel.analysis import _create_followup, report_id, report_windows
from fleet_fuel.input_policy import InputPolicyError, execute_analysis_sql, validate_analysis_inputs

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql/analytics.sql").read_text()


@pytest.fixture
def db():
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    connection.execute(SQL.split("-- END MACROS")[0])
    yield connection
    connection.close()


def test_mpg_is_total_distance_over_total_consumption(db):
    # Two vehicles: 100 mi/10 gal and 100 mi/20 gal. Fleet = 200/30,
    # not the average of their respective 10 and 5 MPG values.
    actual = db.execute("SELECT fuel_mpg(321.8688,113.56235352)").fetchone()[0]
    assert actual == pytest.approx(200 / 30)
    assert actual != pytest.approx(7.5)


def test_zero_or_unknown_consumption_is_not_zero_efficiency(db):
    assert db.execute("SELECT fuel_mpg(50,0),fuel_mpg(50,NULL)").fetchone() == (None, None)


def test_price_volume_decomposition_reconciles_spend(db):
    # Baseline $22 = 20 L*$1.10; current $36 = 30 L*$1.20.
    price, volume = db.execute("SELECT fuel_price_effect(1.1,20,1.2),fuel_quantity_effect(20,1.2,30)").fetchone()
    assert float(price) == pytest.approx(2)
    assert float(volume) == pytest.approx(12)
    assert float(price + volume) == pytest.approx(14)


def test_tax_and_discount_are_applied_once(db):
    pretax, net = db.execute("""SELECT
      fuel_comparable_amount('pretax_gross',108,100,10,2,0,0),
      fuel_comparable_amount('tax_inclusive_net_fuel',108,100,10,2,0,0)""").fetchone()
    assert (pretax, net) == (108, 108)


def test_transaction_total_excludes_nonfuel_and_fees(db):
    value = db.execute("SELECT fuel_comparable_amount('transaction_total',121,100,10,2,3,10)").fetchone()[0]
    assert value == 108


def test_unknown_inventory_movement_propagates(db):
    known, unknown = db.execute("SELECT fuel_balance(100,40,5,80,10),fuel_balance(100,40,NULL,80,10)").fetchone()
    assert known == 55
    assert unknown is None


def test_high_consumption_requires_load_pto_route_review_not_waste_label(db):
    # A 35% task-specific difference with strong coverage is a review trigger.
    # Required PTO or payload could explain it; the algorithm cannot label waste.
    label=db.execute('SELECT fuel_efficiency_review(0.99,5,0.35)').fetchone()[0]
    assert label=='review_load_pto_route'
    assert 'waste' not in label


def test_report_window_respects_daylight_saving_time():
    left, right = report_windows(date(2025,3,3),date(2025,3,9))[0]
    assert (right.timestamp()-left.timestamp())/3600 == 167
    assert left.hour == right.hour == 0


def test_report_id_is_stable():
    assert report_id('T01',date(2025,3,3),'revised') == 'T01-FUEL-20250303-revised'


def _insert(connection, table, **values):
    names = list(values)
    connection.execute(f'INSERT INTO normalized.{table} ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',
                       [values[name] for name in names])


def _fixture_db():
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC';CREATE SCHEMA normalized;CREATE SCHEMA analytics")
    contract=json.loads((ROOT/'contracts/da_e01_contract.json').read_text())
    for table in contract['tables']:
        fields=[f for f in contract['fields'] if f['table']==table['name']]
        connection.execute('CREATE TABLE normalized.'+table['name']+' ('+
                           ','.join('"'+f['name']+'" '+f['type'] for f in fields)+')')
    connection.execute("""CREATE TABLE analytics.report_context(
      tenant_id VARCHAR,output_id VARCHAR,report_week_start TIMESTAMPTZ,
      report_week_end TIMESTAMPTZ,as_of_time TIMESTAMPTZ,report_view VARCHAR,
      metric_version VARCHAR,metric_owner VARCHAR,input_snapshot JSON)""")
    for view,asof in [('initial','2025-01-15T08:00:00Z'),('revised','2025-01-20T08:00:00Z'),('retrospective','2026-10-25T00:00:00Z')]:
        connection.execute('INSERT INTO analytics.report_context VALUES (?,?,?,?,?,?,?,?,?)',
          ['T','T-FUEL-20250106-'+view,'2025-01-06T08:00:00Z','2025-01-13T08:00:00Z',asof,view,'1','analyst','{}'])
    _insert(connection,'core_tenant',tenant_id='T',tenant_name='Fictional',report_timezone='America/Los_Angeles',base_currency='USD')
    _insert(connection,'core_vehicle',tenant_id='T',vehicle_id='V',vehicle_class='heavy',fuel_type='diesel')
    for pid in ['assignment-p','task-p','fuel-def-p','distance-def-p']:
        _provenance(connection,pid,pid,'1','2025-01-01T00:00:00Z')
    _insert(connection,'core_vehicle_device_assignment',tenant_id='T',assignment_id='A',vehicle_id='V',device_id='D',
            valid_from='2025-01-01T00:00:00Z',known_from='2025-01-01T00:00:00Z',valid_to_state='open',known_to_state='open',
            resolution_status='resolved',provenance_id='assignment-p')
    _insert(connection,'fuel_task_assignment',tenant_id='T',provenance_id='task-p',task_assignment_id='task-assignment',task_id='trip',
            task_type='linehaul',vehicle_id='V',task_assignment_from='2025-01-01T00:00:00Z',
            task_start_at='2025-01-06T09:00:00Z',task_end_at='2025-01-06T10:00:00Z')
    for sid,kind,unit in [('SF','fuel','L'),('SD','distance','km')]:
        _insert(connection,'fuel_signal_definition',tenant_id='T',signal_definition_id=sid,
                provenance_id='fuel-def-p' if sid=='SF' else 'distance-def-p',source_ecu_id='ECU',signal_kind=kind,
                signal_unit=unit,counter_modulus=100 if sid=='SF' else None,valid_from='2025-01-01T00:00:00Z')
    return connection


def _provenance(connection,pid,logical,version,available):
    _insert(connection,'provenance_record',provenance_id=pid,tenant_id='T',source_system_id='fixture',
            source_record_id=logical,record_version=version,record_state='active',event_time=available,
            available_time=available,retrieved_at=available,origin_type='synthetic')


def _observation(connection,name,minute,fuel,distance,version='1',available=None):
    at=f'2025-01-06T09:{minute:02}:00Z'
    pid=name+'-p'+version
    _provenance(connection,pid,name,version,available or at)
    _insert(connection,'fuel_counter_observation',tenant_id='T',provenance_id=pid,
            counter_observation_id=name+'-r'+version,vehicle_id='V',device_id='D',
            fuel_total_l=fuel,odometer_km=distance,fuel_measured_at=at,distance_measured_at=at,
            fuel_validity='valid',distance_validity='valid',signal_validity='valid',fuel_raw_unit='L',distance_raw_unit='km',
            fuel_total_raw=fuel,odometer_raw=distance,signal_definition_id='SF',distance_definition_id='SD')


def _run_pairs(connection):
    # Execute the actual production script through its paired_result stage.
    section=SQL.split('-- Version selection is applied before financial filtering:')[0]
    connection.execute(section)


def test_production_interval_pairs_exact_common_boundaries():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        _run_pairs(c)
        rows=c.execute("SELECT paired_fuel_l,paired_distance_km,accepted FROM analytics.paired_result ORDER BY paired_interval_id").fetchall()
        assert len(rows)==3
        assert all((float(f),float(d),ok)==(10,20,True) for f,d,ok in rows)
    finally:c.close()


def test_coincident_boundary_readings_are_audited_not_zero_length_intervals():
    c=_fixture_db()
    try:
        _observation(c,'boundary',0,100,1000);_observation(c,'trip-read',0,100,1000);_observation(c,'next',1,110,1020)
        _run_pairs(c)
        assert c.execute('SELECT count(*) FROM analytics.interval_candidates WHERE elapsed_seconds=0 AND NOT pair_accepted').fetchone()[0]==3
        assert c.execute('SELECT count(*) FROM analytics.paired_result').fetchone()[0]==3
        assert c.execute('SELECT count(*) FROM analytics.paired_result WHERE paired_interval_end<=paired_interval_start').fetchone()[0]==0
    finally:c.close()


def test_late_revision_changes_revised_but_not_initial():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        _observation(c,'o1',1,115,1020,version='2',available='2025-01-17T12:00:00Z')
        _run_pairs(c)
        values=dict(c.execute('SELECT report_view,fuel_delta FROM analytics.interval_candidates').fetchall())
        assert float(values['initial'])==10
        assert float(values['revised'])==15
        assert float(values['retrospective'])==15
    finally:c.close()


def test_confirmed_wrap_is_recovered_but_unknown_negative_jump_is_not():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,95,1000);_observation(c,'o1',1,5,1020)
        _run_pairs(c)
        assert c.execute("SELECT count(*) FROM analytics.paired_result WHERE accepted").fetchone()[0]==0
        _provenance(c,'wrap-p','wrap','1','2025-01-06T09:01:00Z')
        _insert(c,'fuel_counter_change',tenant_id='T',provenance_id='wrap-p',counter_change_id='wrap',
                counter_change_at='2025-01-06T09:01:00Z',counter_change_type='confirmed_wrap',counter_change_evidence='fixture modulus 100 L',
                vehicle_id='V',device_id='D',signal_definition_id='SF',signal_kind='fuel')
        _run_pairs(c)
        rows=c.execute('SELECT paired_fuel_l,accepted FROM analytics.paired_result').fetchall()
        assert all(float(f)==10 and ok for f,ok in rows)
    finally:c.close()


def test_ambiguous_historical_assignment_is_excluded():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        _insert(c,'core_vehicle_device_assignment',tenant_id='T',assignment_id='conflict',vehicle_id='V2',device_id='D',
                valid_from='2025-01-01T00:00:00Z',known_from='2025-01-01T00:00:00Z',
                valid_to_state='open',known_to_state='open',resolution_status='ambiguous',provenance_id='assignment-p')
        _run_pairs(c)
        assert c.execute("SELECT count(*) FROM analytics.paired_result WHERE excluded_interval_reason='ambiguous_assignment'").fetchone()[0]==3
    finally:c.close()


def test_definition_received_late_cannot_rewrite_initial_view():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        c.execute("UPDATE normalized.provenance_record SET available_time='2025-01-17T12:00:00Z' WHERE provenance_id='fuel-def-p'")
        _run_pairs(c)
        states=dict(c.execute('SELECT report_view,pair_accepted FROM analytics.interval_candidates').fetchall())
        assert states=={'initial':False,'revised':True,'retrospective':True}
    finally:c.close()


def test_both_endpoints_require_valid_definition_period():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        c.execute("UPDATE normalized.fuel_signal_definition SET valid_from='2025-01-06T09:00:30Z' WHERE signal_definition_id='SF'")
        _run_pairs(c)
        assert c.execute('SELECT count(*) FROM analytics.paired_result WHERE accepted').fetchone()[0]==0
    finally:c.close()


def test_unanswered_review_is_not_a_negative_outcome():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        _run_pairs(c)
        _insert(c,'fuel_output_review',tenant_id='T',review_case_id='unanswered',vehicle_id='V',
          adoption_status='not_responded',review_outcome='unknown',output_id='T-FUEL-20250106-revised',evidence_origin='synthetic')
        _create_followup(c)
        assert c.execute('SELECT adoption_status,comparison_status,change_l_per_100km FROM analytics.followup_evaluation').fetchone()==('not_responded','no_action_observed',None)
    finally:c.close()


def test_task_change_prevents_qualifying_followup_comparison():
    c=_fixture_db()
    try:
        for minute in range(3):_observation(c,'o'+str(minute),minute,100+10*minute,1000+20*minute)
        c.execute("UPDATE normalized.fuel_task_assignment SET task_end_at='2025-01-06T09:02:00Z'")
        _run_pairs(c)
        _insert(c,'fuel_output_review',tenant_id='T',review_case_id='changed',vehicle_id='V',
          adoption_status='adopted',review_reason='task changed',review_outcome='observed',
          output_id='T-FUEL-20250106-revised',evidence_origin='synthetic')
        _insert(c,'fuel_action_followup',tenant_id='T',review_case_id='changed',vehicle_id='V',action_followup_id='f',
          action_time='2025-01-06T09:01:00Z',baseline_window_start='2025-01-06T09:00:00Z',baseline_window_end='2025-01-06T09:01:00Z',
          followup_start='2025-01-06T09:01:00Z',outcome_observation_end='2025-01-06T09:02:00Z',planned_followup_end='2025-01-06T09:02:00Z')
        _create_followup(c)
        state,change,b,f=c.execute('SELECT comparison_status,change_l_per_100km,baseline_coverage,followup_coverage FROM analytics.followup_evaluation').fetchone()
        assert (state,change,b,f)==('task_mix_changed',None,1.0,1.0)
    finally:c.close()


def test_followup_is_standardized_to_baseline_task_distance_mix():
    # Baseline: A=30L/100km, B=10L/100km =>20L/100km.
    # Follow-up: A=20L/100km, B=30L/300km =>raw12.5L/100km.
    # Keep baseline's50/50task mix: standardized15, change-5 (not-7.5).
    c=_fixture_db()
    try:
        c.execute('DELETE FROM normalized.fuel_task_assignment')
        for minute,(fuel,km) in enumerate([(100,1000),(130,1100),(140,1200),(160,1300),(190,1600)]):
            _observation(c,'o'+str(minute),minute,fuel,km)
        for minute,task in enumerate(['A','B','A','B']):
            _insert(c,'fuel_task_assignment',tenant_id='T',provenance_id='task-p',vehicle_id='V',task_assignment_id='ta'+str(minute),
              task_id='t'+str(minute),task_type=task,task_assignment_from='2025-01-01T00:00:00Z',
              task_start_at=f'2025-01-06T09:0{minute}:00Z',task_end_at=f'2025-01-06T09:0{minute+1}:00Z')
        _run_pairs(c)
        _insert(c,'fuel_output_review',tenant_id='T',review_case_id='mix',vehicle_id='V',adoption_status='adopted',review_outcome='observed')
        _insert(c,'fuel_action_followup',tenant_id='T',review_case_id='mix',vehicle_id='V',action_followup_id='f',
          action_time='2025-01-06T09:02:00Z',baseline_window_start='2025-01-06T09:00:00Z',baseline_window_end='2025-01-06T09:02:00Z',
          followup_start='2025-01-06T09:02:00Z',outcome_observation_end='2025-01-06T09:04:00Z',planned_followup_end='2025-01-06T09:04:00Z')
        _create_followup(c)
        row=c.execute('SELECT baseline_l_per_100km,followup_l_per_100km,standardized_followup_l_per_100km,standardized_change_l_per_100km FROM analytics.followup_evaluation').fetchone()
        assert row==pytest.approx((20,12.5,15,-5))
    finally:c.close()


@pytest.mark.parametrize('extra_column',['true_fuel_l','supplier_new_column'])
def test_analysis_rejects_noncontract_input_columns(extra_column):
    c=_fixture_db()
    try:
        c.execute('ALTER TABLE normalized.fuel_counter_observation ADD COLUMN '+extra_column+' DOUBLE')
        with pytest.raises(InputPolicyError,match='Noncontract columns'):
            validate_analysis_inputs(c,json.loads((ROOT/'contracts/da_e01_contract.json').read_text()))
        assert c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='analytics' AND table_name='paired_result'").fetchone()[0]==0
    finally:c.close()


def test_analysis_rejects_added_truth_table_and_substituted_input_view():
    c=_fixture_db();contract=json.loads((ROOT/'contracts/da_e01_contract.json').read_text())
    try:
        c.execute('CREATE TABLE normalized.simulator_truth(true_fuel_l DOUBLE)')
        with pytest.raises(InputPolicyError,match='Unapproved or missing'):validate_analysis_inputs(c,contract)
        c.execute('DROP TABLE normalized.simulator_truth; DROP TABLE normalized.fuel_counter_observation')
        c.execute('CREATE VIEW normalized.fuel_counter_observation AS SELECT 42 AS true_fuel_l')
        with pytest.raises(InputPolicyError,match='base tables'):validate_analysis_inputs(c,contract)
    finally:c.close()


@pytest.mark.parametrize('relation',['normalized.fuel_reference_case','normalized.fuel_statement_control','validation.simulator_truth'])
def test_analysis_sql_blocks_validation_only_relations(relation):
    c=_fixture_db()
    try:
        c.execute('CREATE SCHEMA validation;CREATE TABLE validation.simulator_truth(true_fuel_l DOUBLE);INSERT INTO validation.simulator_truth VALUES(999)')
        with pytest.raises(InputPolicyError,match='Unapproved analytical relations'):
            execute_analysis_sql(c,'CREATE TABLE analytics.paired_result AS SELECT * FROM '+relation)
        assert c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='analytics' AND table_name='paired_result'").fetchone()[0]==0
    finally:c.close()


def test_analysis_sql_blocks_external_truth_file_reader(tmp_path):
    c=_fixture_db();truth=tmp_path/'truth.csv';truth.write_text('true_fuel_l\n999\n')
    try:
        with pytest.raises(InputPolicyError,match='External file/query readers'):
            execute_analysis_sql(c,"CREATE TABLE analytics.paired_result AS SELECT * FROM read_csv('"+str(truth)+"')")
        assert c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='analytics' AND table_name='paired_result'").fetchone()[0]==0
    finally:c.close()


def test_approved_production_sql_passes_input_gates():
    c=_fixture_db()
    try:
        _observation(c,'o0',0,100,1000);_observation(c,'o1',1,110,1020)
        result=validate_analysis_inputs(c,json.loads((ROOT/'contracts/da_e01_contract.json').read_text()))
        assert result['status']=='passed'
        execute_analysis_sql(c,SQL)
        assert c.execute('SELECT count(*) FROM analytics.paired_result WHERE accepted').fetchone()[0]==3
    finally:c.close()
