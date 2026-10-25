"""Fail-closed boundary between operational inputs and validation answers."""
from __future__ import annotations

import re


CANONICAL_TABLES=frozenset('''core_tenant core_vehicle core_device core_vehicle_device_assignment
provenance_record fuel_vehicle_context fuel_task_assignment fuel_signal_definition
fuel_counter_observation fuel_counter_change fuel_purchase_line fuel_card_assignment
fuel_station fuel_market_price fuel_region_mapping fuel_tank_scope fuel_inventory_measurement
fuel_movement fuel_inventory_balance fuel_statement_control fuel_reference_case
fuel_output_review fuel_action_followup fuel_report_run fuel_paired_interval fuel_weekly_metric'''.split())
VALIDATION_ONLY_TABLES=frozenset({'fuel_reference_case','fuel_statement_control'})
ANALYSIS_INPUT_TABLES=CANONICAL_TABLES-VALIDATION_ONLY_TABLES
ANALYTICS_TABLES=frozenset('''report_context observations_asof observation_context interval_candidates
paired_result purchase_versions purchase_detail weekly_result inventory_result followup_task_comparison
followup_evaluation fleet_weekly inventory_reconciliation interval_exclusions report_revisions
coverage_sensitivity task_efficiency efficiency_comparison'''.split())


class InputPolicyError(ValueError):
    """An unapproved input would enter the analytical boundary."""


def forbidden_payload_field(name: str) -> bool:
    name=name.lower()
    return (name.startswith(('true_','latent_','oracle_','ground_truth_','simulator_truth_'))
            or name in {'ground_truth','scenario_truth','expected_value','expected_waste_label',
                        'expected_target','reference_answer','reference_label','gold_answer','gold_label','target_label'}
            or bool(re.match(r'^expected_(?:waste|target|label|answer|fuel|consumption|outcome)(?:_|$)',name)))


def validate_analysis_inputs(con, contract: dict) -> dict:
    """Reject schema drift before any report or analytical table is written.

    Independent statement/reference controls may be stored in normalized, but
    they are explicitly excluded from the SQL read allowlist below.
    """
    declared={t['name'] for t in contract['tables']}
    if declared!=CANONICAL_TABLES:
        raise InputPolicyError('DA-E01 canonical table allowlist differs from the accepted contract')
    actual=dict(con.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='normalized'").fetchall())
    if set(actual)!=CANONICAL_TABLES:
        raise InputPolicyError('Unapproved or missing normalized input tables: '+str(sorted(set(actual)^CANONICAL_TABLES)))
    for table in sorted(CANONICAL_TABLES):
        if actual[table]!='BASE TABLE':
            raise InputPolicyError('Normalized inputs must be materialized base tables: '+table)
        expected={f['name'] for f in contract['fields'] if f['table']==table}
        columns={r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='normalized' AND table_name=?",[table]).fetchall()}
        if columns!=expected:
            raise InputPolicyError('Noncontract columns in '+table+': '+str(sorted(columns^expected)))
        if table in ANALYSIS_INPUT_TABLES and any(forbidden_payload_field(name) for name in columns):
            raise InputPolicyError('Validation-answer or simulator-truth columns in analytical input '+table)
    return {'status':'passed','canonical_tables':len(CANONICAL_TABLES),
            'validation_only_tables':sorted(VALIDATION_ONLY_TABLES),
            'policy':'contract_columns_and_explicit_relation_allowlist'}


def execute_analysis_sql(con, sql: str) -> None:
    """Execute only approved SQL relations; external readers fail before use.

    DuckDB's statement parser resolves relations, including CTEs. Each statement
    is checked before execution; earlier stages can therefore supply later ones.
    This is a data-input guard, not a sandbox for arbitrary Python code.
    """
    allowed={'normalized.'+n for n in ANALYSIS_INPUT_TABLES}|{'analytics.'+n for n in ANALYTICS_TABLES}
    external=re.compile(r"\b(?:read_[a-z0-9_]*|[a-z0-9_]+_scan|query|query_table|glob)\s*\(|\b(?:from|join)\s*'",re.I)
    for statement in con.extract_statements(sql):
        if external.search(statement.query):
            raise InputPolicyError('External file/query readers are not approved analytical inputs')
        if str(statement.type)!='StatementType.CREATE':
            raise InputPolicyError('Only declared CREATE stages are allowed in analytics.sql')
        names={re.sub(r'\s+AS\s+.*$','',name,flags=re.I).replace('"','')
               for name in con.get_table_names(statement.query,qualified=True)}
        denied=names-allowed
        if denied:
            raise InputPolicyError('Unapproved analytical relations: '+', '.join(sorted(denied)))
        con.execute(statement.query)
