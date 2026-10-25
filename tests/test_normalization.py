"""Hand-calculated unit conversions through the production normalization step."""
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from fleet_fuel.ingestion import load_json_table, normalize_counter_units


ROOT=Path(__file__).resolve().parents[1]


def _staged_database(tmp_path, records):
    fields=[f for f in json.loads((ROOT/'contracts/da_e01_contract.json').read_text())['fields']
            if f['table']=='fuel_counter_observation']
    path=tmp_path/'data/staged/events/fuel_counter_observation.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(''.join(json.dumps(r)+'\n' for r in records))
    con=duckdb.connect(':memory:')
    con.execute('CREATE SCHEMA normalized')
    con.execute('CREATE TABLE normalized.fuel_counter_observation ('+
                ','.join('"'+f['name']+'" '+f['type'] for f in fields)+')')
    load_json_table(con,'fuel_counter_observation',path,fields)
    return con,path


def test_us_gallons_miles_and_metric_values_use_tenant_composite_key(tmp_path):
    # Deliberately reuse the observation ID across tenants. Supplied canonical
    # values are wrong: normalization must use the raw value in the right row.
    con,path=_staged_database(tmp_path,[
      {'tenant_id':'T01','counter_observation_id':'shared','fuel_total_raw':10,'fuel_raw_unit':'US_gal',
       'odometer_raw':20,'distance_raw_unit':'mile','fuel_total_l':999,'odometer_km':999},
      {'tenant_id':'T02','counter_observation_id':'shared','fuel_total_raw':12.5,'fuel_raw_unit':'L',
       'odometer_raw':40.125,'distance_raw_unit':'km','fuel_total_l':777,'odometer_km':777}])
    original=path.read_bytes()
    try:
        report=normalize_counter_units(con)
        actual=con.execute('SELECT tenant_id,fuel_total_l,odometer_km,fuel_total_raw,odometer_raw FROM normalized.fuel_counter_observation ORDER BY tenant_id').fetchall()
        assert actual==[
          ('T01',Decimal('37.854118'),Decimal('32.186880'),Decimal('10'),Decimal('20')),
          ('T02',Decimal('12.500000'),Decimal('40.125000'),Decimal('12.5'),Decimal('40.125'))]
        assert report['rows']==report['fuel_value_mismatches']==report['distance_value_mismatches']==2
        assert report['unsupported_fuel_units']==report['unsupported_distance_units']==0
        assert con.execute('SELECT supplied_fuel_l,supplied_distance_km FROM audit.unit_normalization ORDER BY tenant_id').fetchall()==[(Decimal('999'),Decimal('999')),(Decimal('777'),Decimal('777'))]
        assert path.read_bytes()==original
    finally:con.close()


def test_missing_raw_and_unknown_units_are_null_with_audited_reasons(tmp_path):
    con,path=_staged_database(tmp_path,[
      {'tenant_id':'T01','counter_observation_id':'missing','fuel_total_raw':None,'fuel_raw_unit':'L',
       'odometer_raw':None,'distance_raw_unit':'km','fuel_total_l':88,'odometer_km':99},
      {'tenant_id':'T01','counter_observation_id':'unsupported','fuel_total_raw':5,'fuel_raw_unit':'unknown',
       'odometer_raw':7,'distance_raw_unit':'unknown','fuel_total_l':88,'odometer_km':99},
      {'tenant_id':'T01','counter_observation_id':'zero','fuel_total_raw':0,'fuel_raw_unit':'US_gal',
       'odometer_raw':0,'distance_raw_unit':'mile','fuel_total_l':0,'odometer_km':0}])
    original=path.read_bytes()
    try:
        report=normalize_counter_units(con)
        assert con.execute('SELECT counter_observation_id,fuel_total_l,odometer_km FROM normalized.fuel_counter_observation ORDER BY counter_observation_id').fetchall()==[
          ('missing',None,None),('unsupported',None,None),('zero',Decimal('0'),Decimal('0'))]
        assert con.execute('SELECT counter_observation_id,fuel_unit_status,distance_unit_status FROM audit.unit_normalization ORDER BY counter_observation_id').fetchall()==[
          ('missing','missing_raw_value','missing_raw_value'),('unsupported','unsupported_unit','unsupported_unit'),('zero','normalized','normalized')]
        assert report['unsupported_fuel_units']==report['unsupported_distance_units']==1
        assert report['missing_fuel_raw_values']==report['missing_distance_raw_values']==1
        assert report['fuel_value_mismatches']==report['distance_value_mismatches']==2
        assert path.read_bytes()==original
    finally:con.close()
