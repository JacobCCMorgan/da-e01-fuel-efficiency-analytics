-- Generated from contracts/da_e01_contract.json. Do not edit this export.
-- Key existence is checked by quality.py; temporal resolution uses analytical scenario tests.
CREATE SCHEMA IF NOT EXISTS normalized;

CREATE TABLE IF NOT EXISTS normalized."core_tenant" (
  "tenant_id" VARCHAR NOT NULL,
  "tenant_name" VARCHAR NOT NULL,
  "report_timezone" VARCHAR NOT NULL,
  "base_currency" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."core_vehicle" (
  "tenant_id" VARCHAR NOT NULL,
  "vehicle_id" VARCHAR NOT NULL,
  "vin_raw" VARCHAR,
  "vin" VARCHAR,
  "vehicle_class" VARCHAR NOT NULL,
  "fuel_type" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."core_device" (
  "tenant_id" VARCHAR NOT NULL,
  "device_id" VARCHAR NOT NULL,
  "device_model" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."core_vehicle_device_assignment" (
  "tenant_id" VARCHAR NOT NULL,
  "assignment_id" VARCHAR NOT NULL,
  "vehicle_id" VARCHAR NOT NULL,
  "device_id" VARCHAR NOT NULL,
  "valid_from" TIMESTAMPTZ NOT NULL,
  "valid_to" TIMESTAMPTZ,
  "known_from" TIMESTAMPTZ NOT NULL,
  "known_to" TIMESTAMPTZ,
  "valid_to_state" VARCHAR NOT NULL,
  "known_to_state" VARCHAR NOT NULL,
  "resolution_status" VARCHAR NOT NULL,
  "provenance_id" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."provenance_record" (
  "provenance_id" VARCHAR NOT NULL,
  "source_system_id" VARCHAR NOT NULL,
  "source_record_id" VARCHAR NOT NULL,
  "record_version" VARCHAR NOT NULL,
  "record_state" VARCHAR NOT NULL,
  "event_time" TIMESTAMPTZ,
  "available_time" TIMESTAMPTZ,
  "retrieved_at" TIMESTAMPTZ NOT NULL,
  "extract_as_of" TIMESTAMPTZ NOT NULL,
  "raw_record_reference" VARCHAR NOT NULL,
  "origin_type" VARCHAR NOT NULL,
  "source_dataset_id" VARCHAR NOT NULL,
  "synthetic_scenario_id" VARCHAR,
  "value_states" JSON NOT NULL,
  "source_timezone" VARCHAR,
  "source_utc_offset_minutes" INTEGER,
  "tenant_id" VARCHAR,
  "field_origins" JSON NOT NULL,
  "availability_basis" VARCHAR NOT NULL,
  "availability_evidence" VARCHAR,
  "canonical_table" VARCHAR NOT NULL,
  "canonical_record_key" JSON NOT NULL,
  "parent_provenance_ids" JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_vehicle_context" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "vehicle_context_id" VARCHAR NOT NULL,
  "vehicle_source_id" VARCHAR,
  "vehicle_active_from" TIMESTAMPTZ,
  "vehicle_active_to" TIMESTAMPTZ,
  "operating_timezone" VARCHAR,
  "day_boundary_local" VARCHAR,
  "vehicle_id" VARCHAR
);

CREATE TABLE IF NOT EXISTS normalized."fuel_task_assignment" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "task_assignment_id" VARCHAR NOT NULL,
  "task_id" VARCHAR,
  "task_type" VARCHAR,
  "task_assignment_from" TIMESTAMPTZ,
  "task_assignment_to" TIMESTAMPTZ,
  "task_start_at" TIMESTAMPTZ,
  "task_end_at" TIMESTAMPTZ,
  "vehicle_id" VARCHAR
);

CREATE TABLE IF NOT EXISTS normalized."fuel_signal_definition" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "signal_definition_id" VARCHAR NOT NULL,
  "source_ecu_id" VARCHAR,
  "signal_definition_version" VARCHAR,
  "signal_kind" VARCHAR,
  "signal_unit" VARCHAR,
  "signal_resolution" DECIMAL(20,6),
  "counter_modulus" DECIMAL(20,6),
  "firmware_version" VARCHAR,
  "ecu_configuration" VARCHAR,
  "signal_protocol" VARCHAR,
  "source_signal_locator" VARCHAR,
  "valid_from" TIMESTAMPTZ NOT NULL,
  "valid_to" TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS normalized."fuel_counter_observation" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "counter_observation_id" VARCHAR NOT NULL,
  "fuel_total_l" DECIMAL(20,6),
  "odometer_km" DECIMAL(20,6),
  "signal_validity" VARCHAR,
  "fuel_measured_at" TIMESTAMPTZ,
  "fuel_raw_unit" VARCHAR,
  "fuel_validity" VARCHAR,
  "distance_measured_at" TIMESTAMPTZ,
  "distance_raw_unit" VARCHAR,
  "vehicle_id" VARCHAR,
  "device_id" VARCHAR NOT NULL,
  "signal_definition_id" VARCHAR NOT NULL,
  "fuel_total_raw" DECIMAL(20,6),
  "odometer_raw" DECIMAL(20,6),
  "distance_validity" VARCHAR,
  "distance_definition_id" VARCHAR
);

CREATE TABLE IF NOT EXISTS normalized."fuel_counter_change" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "counter_change_id" VARCHAR NOT NULL,
  "counter_change_at" TIMESTAMPTZ,
  "counter_change_type" VARCHAR,
  "counter_change_evidence" VARCHAR,
  "vehicle_id" VARCHAR,
  "device_id" VARCHAR NOT NULL,
  "signal_definition_id" VARCHAR NOT NULL,
  "signal_kind" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_purchase_line" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "purchase_line_id" VARCHAR NOT NULL,
  "line_version" VARCHAR NOT NULL,
  "purchase_id" VARCHAR,
  "purchase_time" TIMESTAMPTZ,
  "posted_at" TIMESTAMPTZ,
  "purchase_quantity_l" DECIMAL(20,6),
  "purchase_quantity_unit" VARCHAR,
  "purchase_amount" DECIMAL(20,6),
  "purchase_fuel_type" VARCHAR,
  "currency" VARCHAR,
  "fuel_subtotal" DECIMAL(20,6),
  "fuel_tax_amount" DECIMAL(20,6),
  "fuel_discount_amount" DECIMAL(20,6),
  "extra_fee_amount" DECIMAL(20,6),
  "nonfuel_amount" DECIMAL(20,6),
  "transaction_status" VARCHAR,
  "adjustment_type" VARCHAR,
  "original_purchase_line_id" VARCHAR,
  "fuel_card_id" VARCHAR,
  "station_id" VARCHAR,
  "statement_id" VARCHAR,
  "source_amount_basis" VARCHAR,
  "vehicle_id" VARCHAR,
  "quantity_raw" DECIMAL(20,6),
  "record_state" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_card_assignment" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "card_assignment_id" VARCHAR NOT NULL,
  "card_vehicle_from" TIMESTAMPTZ,
  "card_vehicle_to" TIMESTAMPTZ,
  "vehicle_id" VARCHAR,
  "fuel_card_id" VARCHAR NOT NULL,
  "known_from" TIMESTAMPTZ NOT NULL,
  "known_to" TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS normalized."fuel_station" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "station_version_id" VARCHAR NOT NULL,
  "station_country" VARCHAR,
  "station_state" VARCHAR,
  "station_id" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_market_price" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "market_price_version_id" VARCHAR NOT NULL,
  "market_week_price" DECIMAL(20,6),
  "market_region" VARCHAR,
  "eia_series_id" VARCHAR,
  "price_observation_date" DATE,
  "price_published_at" TIMESTAMPTZ,
  "price_retrieved_at" TIMESTAMPTZ,
  "price_snapshot_ref" VARCHAR,
  "price_method_version" VARCHAR,
  "origin_label" VARCHAR NOT NULL,
  "publication_precision" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_region_mapping" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "region_mapping_id" VARCHAR NOT NULL,
  "region_mapping_version" VARCHAR,
  "country_code" VARCHAR NOT NULL,
  "state_code" VARCHAR NOT NULL,
  "market_region" VARCHAR NOT NULL,
  "valid_from" DATE NOT NULL,
  "valid_to" DATE
);

CREATE TABLE IF NOT EXISTS normalized."fuel_tank_scope" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "tank_scope_version_id" VARCHAR NOT NULL,
  "inventory_tank_scope_id" VARCHAR,
  "tank_capacity_l" DECIMAL(20,6),
  "vehicle_id" VARCHAR
);

CREATE TABLE IF NOT EXISTS normalized."fuel_inventory_measurement" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "inventory_measurement_id" VARCHAR NOT NULL,
  "inventory_measurement_method" VARCHAR,
  "inventory_uncertainty" DECIMAL(20,6),
  "raw_level_percent" DECIMAL(20,6),
  "calibration_curve_ref" VARCHAR,
  "vehicle_id" VARCHAR,
  "inventory_tank_scope_id" VARCHAR NOT NULL,
  "measured_at" TIMESTAMPTZ NOT NULL,
  "quantity_l" DECIMAL(20,6),
  "raw_quantity" DECIMAL(20,6),
  "raw_quantity_unit" VARCHAR NOT NULL,
  "measurement_role" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_movement" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "fuel_movement_id" VARCHAR NOT NULL,
  "fuel_movement_at" TIMESTAMPTZ,
  "fuel_movement_type" VARCHAR,
  "fuel_movement_quantity_l" DECIMAL(20,6),
  "fuel_movement_reference" VARCHAR,
  "movement_source_scope" VARCHAR,
  "movement_destination_scope" VARCHAR,
  "vehicle_id" VARCHAR
);

CREATE TABLE IF NOT EXISTS normalized."fuel_inventory_balance" (
  "tenant_id" VARCHAR NOT NULL,
  "balance_id" VARCHAR NOT NULL,
  "opening_volume_l" DECIMAL(20,6),
  "closing_volume_l" DECIMAL(20,6),
  "period_start_at" TIMESTAMPTZ,
  "period_end_at" TIMESTAMPTZ,
  "inventory_quality_state" VARCHAR,
  "refuel_volume_l" DECIMAL(20,6),
  "transfer_in_l" DECIMAL(20,6),
  "removed_l" DECIMAL(20,6),
  "balance_consumption_l" DECIMAL(20,6),
  "net_transfer_l" DECIMAL(20,6),
  "vehicle_id" VARCHAR,
  "opening_measurement_id" VARCHAR NOT NULL,
  "closing_measurement_id" VARCHAR NOT NULL,
  "inventory_tank_scope_id" VARCHAR NOT NULL,
  "as_of_time" TIMESTAMPTZ NOT NULL,
  "uncertainty_l" DECIMAL(20,6)
);

CREATE TABLE IF NOT EXISTS normalized."fuel_statement_control" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "statement_control_id" VARCHAR NOT NULL,
  "statement_period_start" TIMESTAMPTZ,
  "statement_period_end" TIMESTAMPTZ,
  "statement_control_amount" DECIMAL(20,6),
  "statement_control_quantity" DECIMAL(20,6),
  "statement_id" VARCHAR NOT NULL,
  "category_code" VARCHAR NOT NULL,
  "currency" VARCHAR NOT NULL,
  "fuel_type" VARCHAR NOT NULL,
  "quantity_unit" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_reference_case" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "reference_case_id" VARCHAR NOT NULL,
  "reference_metric" VARCHAR NOT NULL,
  "expected_value" JSON,
  "reference_reviewer_role" VARCHAR,
  "reference_reviewed_at" TIMESTAMPTZ,
  "reference_evidence_ref" VARCHAR,
  "reference_review_status" VARCHAR,
  "scenario_id" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_output_review" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "review_case_id" VARCHAR NOT NULL,
  "output_received_at" TIMESTAMPTZ,
  "adoption_status" VARCHAR,
  "review_reason" VARCHAR,
  "review_outcome" VARCHAR,
  "vehicle_id" VARCHAR,
  "project_id" VARCHAR NOT NULL,
  "output_id" VARCHAR NOT NULL,
  "evidence_origin" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_action_followup" (
  "provenance_id" VARCHAR NOT NULL,
  "tenant_id" VARCHAR NOT NULL,
  "action_followup_id" VARCHAR NOT NULL,
  "action_id" VARCHAR,
  "action_type" VARCHAR,
  "action_time" TIMESTAMPTZ,
  "active_review_seconds" BIGINT,
  "baseline_review_seconds" BIGINT,
  "baseline_window_start" TIMESTAMPTZ,
  "baseline_window_end" TIMESTAMPTZ,
  "followup_start" TIMESTAMPTZ,
  "outcome_observation_end" TIMESTAMPTZ,
  "observed_fuel_l" DECIMAL(20,6),
  "action_evidence" VARCHAR,
  "planned_followup_end" TIMESTAMPTZ,
  "followup_distance_km" DECIMAL(20,6),
  "followup_task_mix" JSON,
  "investigation_seconds" BIGINT,
  "vehicle_id" VARCHAR,
  "project_id" VARCHAR NOT NULL,
  "output_id" VARCHAR NOT NULL,
  "evidence_origin" VARCHAR NOT NULL,
  "review_case_id" VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_report_run" (
  "tenant_id" VARCHAR NOT NULL,
  "output_id" VARCHAR NOT NULL,
  "metric_version" VARCHAR,
  "metric_owner" VARCHAR,
  "report_week_start" TIMESTAMPTZ,
  "report_week_end" TIMESTAMPTZ,
  "as_of_time" TIMESTAMPTZ,
  "input_snapshot" JSON
);

CREATE TABLE IF NOT EXISTS normalized."fuel_paired_interval" (
  "tenant_id" VARCHAR NOT NULL,
  "paired_interval_id" VARCHAR NOT NULL,
  "fuel_segment_id" VARCHAR,
  "distance_segment_id" VARCHAR,
  "paired_interval_start" TIMESTAMPTZ,
  "paired_interval_end" TIMESTAMPTZ,
  "paired_fuel_l" DECIMAL(20,6),
  "paired_distance_km" DECIMAL(20,6),
  "excluded_interval_reason" VARCHAR,
  "vehicle_id" VARCHAR,
  "as_of_time" TIMESTAMPTZ NOT NULL,
  "calculation_version" VARCHAR NOT NULL,
  "input_provenance_ids" JSON NOT NULL,
  "fuel_start_observation_id" VARCHAR NOT NULL,
  "fuel_end_observation_id" VARCHAR NOT NULL,
  "distance_start_observation_id" VARCHAR NOT NULL,
  "distance_end_observation_id" VARCHAR NOT NULL,
  "accepted" BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized."fuel_weekly_metric" (
  "tenant_id" VARCHAR NOT NULL,
  "weekly_metric_id" VARCHAR NOT NULL,
  "fuel_used_l" DECIMAL(20,6),
  "distance_travelled_km" DECIMAL(20,6),
  "measurement_coverage" DECIMAL(20,6),
  "consumption_method" VARCHAR,
  "mpg" DECIMAL(20,6),
  "comparable_fuel_amount" DECIMAL(20,6),
  "weighted_purchase_price_usd_per_l" DECIMAL(20,6),
  "purchase_spend_usd_per_km" DECIMAL(20,6),
  "benchmark_amount" DECIMAL(20,6),
  "benchmark_amount_gap" DECIMAL(20,6),
  "benchmark_match_coverage" DECIMAL(20,6),
  "purchase_price_effect" DECIMAL(20,6),
  "purchase_quantity_effect" DECIMAL(20,6),
  "weekly_valid_distance_km" DECIMAL(20,6),
  "vehicle_id" VARCHAR,
  "as_of_time" TIMESTAMPTZ NOT NULL,
  "calculation_version" VARCHAR NOT NULL,
  "input_provenance_ids" JSON NOT NULL,
  "output_id" VARCHAR NOT NULL,
  "task_comparison_group" VARCHAR NOT NULL,
  "valid_paired_seconds" DECIMAL(20,6),
  "expected_observation_seconds" DECIMAL(20,6),
  "benchmark_matched_quantity_l" DECIMAL(20,6),
  "benchmark_eligible_quantity_l" DECIMAL(20,6)
);

