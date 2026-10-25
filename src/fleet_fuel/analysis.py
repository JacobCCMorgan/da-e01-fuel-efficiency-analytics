"""Reproducible fuel reporting from normalized, versioned operational inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .input_policy import execute_analysis_sql, validate_analysis_inputs

METRIC_VERSION = "fuel-metrics-1.0.0"
REPORT_ZONE = ZoneInfo("America/Los_Angeles")
MIN_FOLLOWUP_COVERAGE = 0.95


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def _records(connection, sql: str, parameters=None) -> list[dict]:
    cursor = connection.execute(sql, parameters or [])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def report_id(tenant_id: str, week_start: date, view: str) -> str:
    """A report's ID is independent of machine time and execution order."""
    return f"{tenant_id}-FUEL-{week_start:%Y%m%d}-{view}"


def report_windows(start: date, end: date) -> list[tuple[datetime, datetime]]:
    """Full Monday windows, including partial first/last observation weeks."""
    monday = start - timedelta(days=start.weekday())
    result = []
    while monday <= end:
        following = monday + timedelta(days=7)
        result.append((datetime.combine(monday, time.min, REPORT_ZONE),
                       datetime.combine(following, time.min, REPORT_ZONE)))
        monday = following
    return result


def _create_reports(connection, root: Path, config: dict) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS analytics")
    connection.execute("""CREATE OR REPLACE TABLE analytics.report_context(
        tenant_id VARCHAR, output_id VARCHAR, report_week_start TIMESTAMPTZ,
        report_week_end TIMESTAMPTZ, as_of_time TIMESTAMPTZ, report_view VARCHAR,
        metric_version VARCHAR, metric_owner VARCHAR, input_snapshot JSON)""")
    tenants = [row[0] for row in connection.execute(
        "SELECT tenant_id FROM normalized.core_tenant ORDER BY tenant_id").fetchall()]
    available = connection.execute("""SELECT greatest(max(available_time),max(retrieved_at))
        FROM normalized.provenance_record""").fetchone()[0]
    if available is None:
        raise ValueError("No source availability timestamp; cannot build reports")
    snapshot = {"data_version": config.get("data_version", "1.0.0"),
                "seed": config["seed"], "scope": "DA-E01",
                "sources": {}}
    for file in sorted((root / "data/raw/tables").glob("*.jsonl")):
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        snapshot["sources"][file.name] = digest.hexdigest()
    rows = []
    for tenant in tenants:
        for left, right in report_windows(date.fromisoformat(config["start"]),
                                          date.fromisoformat(config["end"])):
            # Add fixed elapsed hours to the UTC boundary; DST never changes a
            # 48-hour arrival allowance into 47 or 49 hours.
            right_utc = right.astimezone(timezone.utc)
            for view, cutoff in [("initial", right_utc + timedelta(hours=48)),
                                 ("revised", right_utc + timedelta(days=7)),
                                 ("retrospective", max(available, right_utc + timedelta(days=7)))]:
                rows.append((tenant, report_id(tenant, left.date(), view), left, right,
                             cutoff, view, METRIC_VERSION, "fleet_analytics",
                             json.dumps({**snapshot, "view": view,
                              "public_price_policy": "retrospective_only_without_historical_availability_evidence"})))
    connection.executemany("INSERT INTO analytics.report_context VALUES (?,?,?,?,?,?,?,?,?)", rows)


def _canonical(connection, contract: dict, table: str, query: str) -> None:
    fields = [field for field in contract["fields"] if field["table"] == table]
    casts = ",\n".join(f'CAST("{field["name"]}" AS {field["type"]}) AS "{field["name"]}"'
                       for field in fields)
    connection.execute(f'CREATE OR REPLACE TABLE normalized."{table}" AS '
                       f'SELECT {casts} FROM ({query}) AS source')


def _export(connection, root: Path, name: str, query: str) -> None:
    path = root / "outputs" / f"{name}.csv"
    connection.execute("COPY (" + query + ") TO ? (HEADER, DELIMITER ',', NULL '')", [str(path)])


def _create_followup(connection) -> None:
    connection.execute("""
    CREATE OR REPLACE TABLE analytics.followup_task_comparison AS
    WITH task_totals AS (
      SELECT r.tenant_id,r.review_case_id,r.vehicle_id,i.task_type,
        sum(i.fuel_delta) FILTER(WHERE i.prior_fuel_at>=f.baseline_window_start AND i.fuel_measured_at<=f.baseline_window_end) AS baseline_fuel_l,
        sum(i.distance_delta) FILTER(WHERE i.prior_fuel_at>=f.baseline_window_start AND i.fuel_measured_at<=f.baseline_window_end) AS baseline_distance_km,
        sum(i.fuel_delta) FILTER(WHERE i.prior_fuel_at>=f.followup_start AND i.fuel_measured_at<=f.outcome_observation_end) AS followup_fuel_l,
        sum(i.distance_delta) FILTER(WHERE i.prior_fuel_at>=f.followup_start AND i.fuel_measured_at<=f.outcome_observation_end) AS followup_distance_km
      FROM normalized.fuel_output_review r
      JOIN normalized.fuel_action_followup f ON f.tenant_id=r.tenant_id AND f.review_case_id=r.review_case_id
      JOIN analytics.interval_candidates i ON i.tenant_id=r.tenant_id AND i.assigned_vehicle=r.vehicle_id
        AND i.report_view='retrospective' AND i.pair_accepted
        AND ((i.prior_fuel_at>=f.baseline_window_start AND i.fuel_measured_at<=f.baseline_window_end)
          OR (i.prior_fuel_at>=f.followup_start AND i.fuel_measured_at<=f.outcome_observation_end))
      GROUP BY ALL
    )
    SELECT *,baseline_distance_km/nullif(sum(baseline_distance_km) OVER w,0) AS baseline_distance_share,
      followup_distance_km/nullif(sum(followup_distance_km) OVER w,0) AS followup_distance_share,
      baseline_fuel_l/nullif(baseline_distance_km,0)*100 AS baseline_l_per_100km,
      followup_fuel_l/nullif(followup_distance_km,0)*100 AS followup_l_per_100km
    FROM task_totals WINDOW w AS (PARTITION BY tenant_id,review_case_id);

    CREATE OR REPLACE TABLE analytics.followup_evaluation AS
    WITH joined AS (
      SELECT r.tenant_id,r.review_case_id,r.vehicle_id,r.output_id,
        r.adoption_status,r.review_reason,r.review_outcome,r.evidence_origin,
        f.action_followup_id,f.action_id,f.action_type,f.action_time,
        f.baseline_window_start,f.baseline_window_end,f.followup_start,
        f.outcome_observation_end,f.planned_followup_end,
        f.observed_fuel_l AS recorded_followup_fuel_l,
        f.followup_distance_km AS recorded_followup_distance_km,
        f.active_review_seconds,f.baseline_review_seconds,f.investigation_seconds,
        f.followup_task_mix,
        b.fuel_l AS baseline_fuel_l,b.distance_km AS baseline_distance_km,
        b.seconds AS baseline_valid_seconds,b.expected_seconds AS baseline_expected_seconds,
        b.task_types AS baseline_task_types,
        a.fuel_l AS followup_fuel_l,a.distance_km AS followup_distance_km,
        a.seconds AS followup_valid_seconds,a.expected_seconds AS followup_expected_seconds,
        a.task_types AS observed_followup_task_types,
        mix.standardized_followup_l_per_100km,mix.max_task_distance_share_change
      FROM normalized.fuel_output_review r
      LEFT JOIN normalized.fuel_action_followup f
        ON f.tenant_id=r.tenant_id AND f.review_case_id=r.review_case_id
      LEFT JOIN LATERAL (
        SELECT sum(i.fuel_delta) FILTER(WHERE i.pair_accepted) AS fuel_l,
          sum(i.distance_delta) FILTER(WHERE i.pair_accepted) AS distance_km,
          coalesce(sum(i.elapsed_seconds) FILTER(WHERE i.pair_accepted),0) AS seconds,
          (SELECT sum(epoch(least(t.task_end_at,f.baseline_window_end)-greatest(t.task_start_at,f.baseline_window_start)))
             FROM normalized.fuel_task_assignment t WHERE t.tenant_id=r.tenant_id AND t.vehicle_id=r.vehicle_id
             AND t.task_start_at<f.baseline_window_end AND t.task_end_at>f.baseline_window_start) AS expected_seconds,
          list_sort(list_distinct(list(i.task_type))) AS task_types
        FROM analytics.interval_candidates i
        WHERE i.tenant_id=r.tenant_id AND i.assigned_vehicle=r.vehicle_id AND i.report_view='retrospective'
          AND i.prior_fuel_at>=f.baseline_window_start AND i.fuel_measured_at<=f.baseline_window_end
      ) b ON true
      LEFT JOIN LATERAL (
        SELECT sum(i.fuel_delta) FILTER(WHERE i.pair_accepted) AS fuel_l,
          sum(i.distance_delta) FILTER(WHERE i.pair_accepted) AS distance_km,
          coalesce(sum(i.elapsed_seconds) FILTER(WHERE i.pair_accepted),0) AS seconds,
          (SELECT sum(epoch(least(t.task_end_at,f.outcome_observation_end)-greatest(t.task_start_at,f.followup_start)))
             FROM normalized.fuel_task_assignment t WHERE t.tenant_id=r.tenant_id AND t.vehicle_id=r.vehicle_id
             AND t.task_start_at<f.outcome_observation_end AND t.task_end_at>f.followup_start) AS expected_seconds,
          list_sort(list_distinct(list(i.task_type))) AS task_types
        FROM analytics.interval_candidates i
        WHERE i.tenant_id=r.tenant_id AND i.assigned_vehicle=r.vehicle_id AND i.report_view='retrospective'
          AND i.prior_fuel_at>=f.followup_start AND i.fuel_measured_at<=f.outcome_observation_end
      ) a ON true
      LEFT JOIN LATERAL (
        SELECT CASE WHEN bool_and(coalesce(baseline_distance_km>0 AND followup_distance_km>0,false))
          THEN sum(baseline_distance_share*followup_l_per_100km) END AS standardized_followup_l_per_100km,
          max(abs(baseline_distance_share-followup_distance_share)) AS max_task_distance_share_change
        FROM analytics.followup_task_comparison t
        WHERE t.tenant_id=r.tenant_id AND t.review_case_id=r.review_case_id
      ) mix ON true
    ), assessed AS (
      SELECT *,baseline_valid_seconds/nullif(baseline_expected_seconds,0) AS baseline_coverage,
        followup_valid_seconds/nullif(followup_expected_seconds,0) AS followup_coverage,
        baseline_fuel_l/nullif(baseline_distance_km,0)*100 AS baseline_l_per_100km,
        followup_fuel_l/nullif(followup_distance_km,0)*100 AS followup_l_per_100km,
        CASE WHEN action_followup_id IS NULL OR action_time IS NULL THEN 'no_action_observed'
          WHEN lower(coalesce(review_outcome,'')) IN ('lost_to_followup','lost','lost_followup') THEN 'lost_to_followup'
          WHEN outcome_observation_end IS NULL THEN 'not_observed'
          WHEN outcome_observation_end<planned_followup_end THEN 'not_mature'
          WHEN baseline_expected_seconds IS NULL OR followup_expected_seconds IS NULL THEN 'no_operating_exposure'
          WHEN baseline_valid_seconds/nullif(baseline_expected_seconds,0)<0.95
            OR followup_valid_seconds/nullif(followup_expected_seconds,0)<0.95 THEN 'insufficient_coverage'
          WHEN baseline_task_types IS DISTINCT FROM observed_followup_task_types
            OR lower(coalesce(review_reason,'')) LIKE '%task%'
            OR lower(coalesce(review_outcome,'')) LIKE '%task%' THEN 'task_mix_changed'
          WHEN baseline_distance_km<=0 OR followup_distance_km<=0 THEN 'zero_distance'
          ELSE 'comparable_descriptive_only' END AS comparison_status
      FROM joined
    )
    SELECT *,CASE WHEN comparison_status='comparable_descriptive_only'
      THEN followup_l_per_100km-baseline_l_per_100km END AS change_l_per_100km,
      CASE WHEN comparison_status='comparable_descriptive_only'
        THEN standardized_followup_l_per_100km-baseline_l_per_100km END AS standardized_change_l_per_100km,
      followup_fuel_l-recorded_followup_fuel_l AS source_recalculation_difference_l,
      'Synthetic operational exercise; no causal saving or real customer adoption established.' AS interpretation_limit
    FROM assessed
    """)


def _create_output_views(connection) -> None:
    connection.execute("""
    CREATE OR REPLACE TABLE analytics.fleet_weekly AS
    SELECT tenant_id,report_week_start,report_week_end,report_view,
      count(*) AS vehicle_rows,count(*) FILTER(WHERE expected_observation_seconds>0) AS operating_vehicles,
      sum(fuel_used_l) AS fuel_used_l,sum(distance_travelled_km) AS distance_travelled_km,
      fuel_mpg(sum(distance_travelled_km),sum(fuel_used_l)) AS mpg,
      sum(valid_paired_seconds)/nullif(sum(expected_observation_seconds),0) AS measurement_coverage,
      sum(valid_paired_seconds) AS valid_paired_seconds,sum(expected_observation_seconds) AS expected_observation_seconds,
      sum(comparable_fuel_amount) AS comparable_fuel_amount,sum(purchase_l) AS purchase_quantity_l,
      sum(comparable_fuel_amount)/nullif(sum(purchase_l),0) AS weighted_purchase_price_usd_per_l,
      sum(benchmark_amount) AS benchmark_amount,sum(benchmark_amount_gap) AS benchmark_amount_gap,
      sum(benchmark_matched_quantity_l)/nullif(sum(benchmark_eligible_quantity_l),0) AS benchmark_match_coverage,
      sum(purchase_price_effect) AS purchase_price_effect,sum(purchase_quantity_effect) AS purchase_quantity_effect,
      count(*) FILTER(WHERE measurement_coverage<0.95) AS low_coverage_vehicle_weeks
    FROM analytics.weekly_result GROUP BY ALL;
    CREATE OR REPLACE TABLE analytics.inventory_reconciliation AS
    SELECT b.*,d.inventory_detail_state,e.ecu_fuel_l,e.ecu_distance_km,e.valid_seconds,
      e.ecu_fuel_l-b.balance_consumption_l AS ecu_minus_inventory_l,
      CASE WHEN b.inventory_quality_state<>'uncertainty_known' THEN d.inventory_detail_state
        WHEN e.ecu_fuel_l IS NULL THEN 'no_eligible_ecu_intervals'
        WHEN abs(e.ecu_fuel_l-b.balance_consumption_l)<=b.uncertainty_l+0.01 THEN 'within_measurement_uncertainty'
        ELSE 'investigate_coverage_or_balance' END AS reconciliation_status
    FROM normalized.fuel_inventory_balance b
    JOIN analytics.inventory_result d USING(balance_id)
    LEFT JOIN LATERAL (
      SELECT sum(fuel_delta) FILTER(WHERE pair_accepted) AS ecu_fuel_l,
        sum(distance_delta) FILTER(WHERE pair_accepted) AS ecu_distance_km,
        sum(elapsed_seconds) FILTER(WHERE pair_accepted) AS valid_seconds
      FROM analytics.interval_candidates i
      WHERE i.tenant_id=b.tenant_id AND i.assigned_vehicle=b.vehicle_id AND i.report_view='retrospective'
        AND i.prior_fuel_at>=b.period_start_at AND i.fuel_measured_at<=b.period_end_at
    ) e ON true;
    CREATE OR REPLACE TABLE analytics.interval_exclusions AS
    SELECT report_view,exclusion_reason,count(*) AS interval_count,
      sum(elapsed_seconds) AS interval_seconds,
      count(DISTINCT assigned_vehicle) AS vehicle_count
    FROM analytics.interval_candidates GROUP BY ALL;
    CREATE OR REPLACE TABLE analytics.report_revisions AS
    SELECT i.tenant_id,i.vehicle_id,i.report_week_start,
      i.fuel_used_l AS initial_fuel_l,r.fuel_used_l AS revised_fuel_l,
      r.fuel_used_l-i.fuel_used_l AS revision_fuel_l,
      i.measurement_coverage AS initial_coverage,r.measurement_coverage AS revised_coverage,
      i.comparable_fuel_amount AS initial_purchase_amount,r.comparable_fuel_amount AS revised_purchase_amount
    FROM analytics.weekly_result i
    JOIN analytics.weekly_result r ON i.tenant_id=r.tenant_id AND i.vehicle_id=r.vehicle_id
      AND i.report_week_start=r.report_week_start AND r.report_view='revised'
    WHERE i.report_view='initial';
    CREATE OR REPLACE TABLE analytics.coverage_sensitivity AS
    WITH thresholds AS (SELECT * FROM (VALUES (0.0),(0.90),(0.95),(0.99)) t(minimum_coverage))
    SELECT t.minimum_coverage,count(*) AS included_vehicle_weeks,
      sum(w.fuel_used_l) AS fuel_used_l,sum(w.distance_travelled_km) AS distance_km,
      fuel_mpg(sum(w.distance_travelled_km),sum(w.fuel_used_l)) AS mpg
    FROM analytics.weekly_result w CROSS JOIN thresholds t
    WHERE w.report_view='retrospective' AND w.measurement_coverage>=t.minimum_coverage
    GROUP BY t.minimum_coverage ORDER BY t.minimum_coverage;
    """)


def _create_efficiency_comparison(connection) -> None:
    """Compare task-specific observed efficiency, with explicit peer coverage."""
    connection.execute("""
    CREATE OR REPLACE TABLE analytics.task_efficiency AS
    WITH exposure AS (
      SELECT r.output_id,t.vehicle_id,t.task_type,
        sum(epoch(least(t.task_end_at,r.report_week_end)-greatest(t.task_start_at,r.report_week_start))) AS expected_seconds
      FROM analytics.report_context r
      JOIN normalized.fuel_task_assignment t ON t.tenant_id=r.tenant_id
        AND t.task_start_at<r.report_week_end AND t.task_end_at>r.report_week_start
      JOIN normalized.provenance_record p ON p.provenance_id=t.provenance_id AND p.available_time<=r.as_of_time
      GROUP BY ALL
    ), observed AS (
      SELECT output_id,assigned_vehicle AS vehicle_id,task_type,
        sum(fuel_delta) FILTER(WHERE pair_accepted) AS fuel_l,
        sum(distance_delta) FILTER(WHERE pair_accepted) AS distance_km,
        coalesce(sum(elapsed_seconds) FILTER(WHERE pair_accepted),0) AS valid_seconds
      FROM analytics.interval_candidates GROUP BY ALL
    )
    SELECT r.tenant_id,e.output_id,e.vehicle_id,v.vehicle_class,r.report_week_start,r.report_view,e.task_type,
      o.fuel_l,o.distance_km,coalesce(o.valid_seconds,0) AS valid_seconds,e.expected_seconds,
      coalesce(o.valid_seconds,0)/nullif(e.expected_seconds,0) AS measurement_coverage,
      o.fuel_l/nullif(o.distance_km,0)*100 AS l_per_100km
    FROM exposure e JOIN analytics.report_context r USING(output_id)
    JOIN normalized.core_vehicle v ON v.tenant_id=r.tenant_id AND v.vehicle_id=e.vehicle_id
    LEFT JOIN observed o ON o.output_id=e.output_id AND o.vehicle_id=e.vehicle_id AND o.task_type=e.task_type;

    CREATE OR REPLACE TABLE analytics.efficiency_comparison AS
    WITH history AS (
      SELECT *,lag(l_per_100km) OVER w AS previous_value,lag(measurement_coverage) OVER w AS previous_coverage,
        lag(report_week_start) OVER w AS previous_week
      FROM analytics.task_efficiency
      WINDOW w AS (PARTITION BY tenant_id,vehicle_id,task_type,report_view ORDER BY report_week_start)
    ), compared AS (
      SELECT h.* EXCLUDE(previous_value,previous_coverage,previous_week),
        CASE WHEN previous_week AT TIME ZONE 'America/Los_Angeles'=report_week_start AT TIME ZONE 'America/Los_Angeles'-INTERVAL 7 DAY
          AND previous_coverage>=0.95 THEN previous_value END AS prior_l_per_100km,
        previous_coverage AS prior_coverage,p.peer_count,p.peer_median_l_per_100km
      FROM history h LEFT JOIN LATERAL (
        SELECT count(*) AS peer_count,median(p.l_per_100km) AS peer_median_l_per_100km
        FROM analytics.task_efficiency p
        WHERE p.tenant_id=h.tenant_id AND p.vehicle_class=h.vehicle_class AND p.task_type=h.task_type
          AND p.report_week_start=h.report_week_start AND p.report_view=h.report_view
          AND p.vehicle_id<>h.vehicle_id AND p.measurement_coverage>=0.95
          AND p.distance_km>0 AND p.fuel_l>0
      ) p ON true
    ), assessed AS (
      SELECT *,l_per_100km/nullif(prior_l_per_100km,0)-1 AS relative_to_prior,
        CASE WHEN peer_count>=3 THEN l_per_100km/nullif(peer_median_l_per_100km,0)-1 END AS relative_to_peer,
        CASE WHEN measurement_coverage<0.95 THEN 'insufficient_coverage'
          WHEN distance_km IS NULL OR distance_km<=0 OR fuel_l IS NULL OR fuel_l<=0 THEN 'no_positive_paired_exposure'
          WHEN peer_count<3 THEN 'insufficient_peers' ELSE 'descriptive_peer_comparison' END AS comparison_status
      FROM compared
    )
    SELECT *,fuel_efficiency_review(measurement_coverage,peer_count,relative_to_peer) AS review_flag,
      'Observed task-specific difference; load, PTO and route require review before causal attribution.' AS interpretation_limit
    FROM assessed;
    """)


def _summary(connection, root: Path) -> dict:
    totals = _records(connection, """SELECT sum(fuel_used_l) AS fuel_used_l,
      sum(distance_travelled_km) AS distance_km,fuel_mpg(sum(distance_travelled_km),sum(fuel_used_l)) AS fleet_mpg,
      sum(valid_paired_seconds)/nullif(sum(expected_observation_seconds),0) AS measurement_coverage,
      sum(comparable_fuel_amount) AS purchase_amount_usd,sum(purchase_quantity_l) AS purchased_l,
      sum(benchmark_amount_gap) AS market_background_gap_usd
      FROM analytics.fleet_weekly WHERE report_view='retrospective'""")[0]
    return {"project_id": "DA-E01", "metric_version": METRIC_VERSION,
            "data_origin": "synthetic_fleet_with_separately_identified_public_price_background",
            "totals": totals,
            "canonical_rows": {name: connection.execute(f'SELECT count(*) FROM normalized."{name}"').fetchone()[0]
                               for name in ["fuel_report_run", "fuel_paired_interval", "fuel_weekly_metric", "fuel_inventory_balance"]},
            "financial_exclusions": _records(connection, """SELECT financial_status,count(*) AS rows
              FROM analytics.purchase_detail WHERE report_view='retrospective' GROUP BY financial_status"""),
            "market_sources": _records(connection, """SELECT report_view,benchmark_view,count(*) AS rows,
              sum(effective_quantity_l) AS purchase_l FROM analytics.purchase_detail
              WHERE financial_status='comparable' GROUP BY ALL"""),
            "followup_statuses": _records(connection, """SELECT comparison_status,count(*) AS cases
              FROM analytics.followup_evaluation GROUP BY comparison_status"""),
            "inventory_statuses": _records(connection, """SELECT reconciliation_status,count(*) AS periods
              FROM analytics.inventory_reconciliation GROUP BY reconciliation_status"""),
            "limits": ["All fleet operations and actions are synthetic.",
                       "Market gaps are background comparisons, not realizable savings.",
                       "Initial/revised views use information available by their cutoff.",
                       "Retrospective public prices do not establish historical availability.",
                       "Follow-up changes are descriptive, not causal effects."],
            "exports": sorted(path.name for path in (root / "outputs").glob("*.csv"))}


def analyze(root: Path | str) -> dict:
    """Build O01/O02/O03 from an already-ingested normalized database."""
    import duckdb

    root = Path(root).resolve()
    (root / "outputs").mkdir(parents=True, exist_ok=True)
    contract = json.loads((root / "contracts/da_e01_contract.json").read_text())
    config = json.loads((root / "config/project.json").read_text())
    database = root / "data/DA-E01.duckdb"
    if not database.exists():
        raise FileNotFoundError(f"Build the normalized database before analysis: {database}")
    connection = duckdb.connect(str(database))
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET threads=2")
    connection.execute("SET preserve_insertion_order=false")
    try:
        input_policy=validate_analysis_inputs(connection,contract)
        _create_reports(connection, root, config)
        _canonical(connection, contract, "fuel_report_run", "SELECT * FROM analytics.report_context")
        execute_analysis_sql(connection,(root / "sql/analytics.sql").read_text())
        for name, source in [("fuel_paired_interval", "paired_result"),
                             ("fuel_weekly_metric", "weekly_result"),
                             ("fuel_inventory_balance", "inventory_result")]:
            _canonical(connection, contract, name, f"SELECT * FROM analytics.{source}")
        _create_followup(connection)
        _create_output_views(connection)
        _create_efficiency_comparison(connection)
        exports = {
            "vehicle_weekly": "SELECT * EXCLUDE(input_provenance_ids) FROM analytics.weekly_result ORDER BY tenant_id,vehicle_id,report_week_start,report_view",
            "fleet_weekly": "SELECT * FROM analytics.fleet_weekly ORDER BY tenant_id,report_week_start,report_view",
            "purchase_detail": "SELECT * FROM analytics.purchase_detail ORDER BY tenant_id,attributed_purchase_time,purchase_line_id,report_view",
            "inventory_reconciliation": "SELECT * FROM analytics.inventory_reconciliation ORDER BY tenant_id,vehicle_id,period_start_at",
            "followup_evaluation": "SELECT * FROM analytics.followup_evaluation ORDER BY tenant_id,review_case_id",
            "followup_task_comparison": "SELECT * FROM analytics.followup_task_comparison ORDER BY tenant_id,review_case_id,task_type",
            "interval_exclusions": "SELECT * FROM analytics.interval_exclusions ORDER BY report_view,exclusion_reason",
            "report_revisions": "SELECT * FROM analytics.report_revisions ORDER BY tenant_id,vehicle_id,report_week_start",
            "coverage_sensitivity": "SELECT * FROM analytics.coverage_sensitivity ORDER BY minimum_coverage",
            "report_runs": "SELECT * EXCLUDE(input_snapshot) FROM analytics.report_context ORDER BY tenant_id,report_week_start,report_view",
            "efficiency_comparison": "SELECT * FROM analytics.efficiency_comparison ORDER BY tenant_id,vehicle_id,report_week_start,task_type,report_view",
        }
        for name, query in exports.items():
            _export(connection, root, name, query)
        derived_dir = root / "data/derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        for name in ["fuel_report_run", "fuel_paired_interval", "fuel_weekly_metric", "fuel_inventory_balance"]:
            connection.execute(f'COPY normalized."{name}" TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',
                               [str(derived_dir / f"{name}.parquet")])
        summary = _summary(connection, root)
        summary['input_policy']=input_policy
        (root / "outputs/analytics_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default) + "\n")
        connection.execute("CHECKPOINT")
        return summary
    finally:
        connection.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    print(json.dumps(analyze(parser.parse_args().root), default=_json_default, indent=2))
