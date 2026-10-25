-- Fuel metrics 1.0.0. All windows are left-closed and right-open.
CREATE OR REPLACE MACRO fuel_mpg(km, litres) AS
  CASE WHEN litres > 0 AND km >= 0 THEN (km / 1.609344) / (litres / 3.785411784) END;
CREATE OR REPLACE MACRO fuel_comparable_amount(basis, amount, subtotal, tax, discount, fees, nonfuel) AS
  CASE WHEN basis = 'pretax_gross' THEN subtotal + tax - discount
       WHEN basis IN ('tax_inclusive_net_fuel', 'inclusive_net_fuel') THEN amount
       WHEN basis = 'tax_inclusive_before_discount' THEN subtotal - discount
       WHEN basis = 'transaction_total' AND fees IS NOT NULL AND nonfuel IS NOT NULL
         THEN amount - fees - nonfuel END;
CREATE OR REPLACE MACRO fuel_price_effect(p0, q0, p1) AS (p1-p0)*q0;
CREATE OR REPLACE MACRO fuel_quantity_effect(q0, p1, q1) AS p1*(q1-q0);
CREATE OR REPLACE MACRO fuel_balance(opening, added, incoming, closing, removed) AS
  opening + added + incoming - closing - removed;
CREATE OR REPLACE MACRO fuel_efficiency_review(coverage, peers, relative_difference) AS
  CASE WHEN coverage < 0.95 OR coverage IS NULL THEN 'insufficient_coverage'
       WHEN peers < 3 OR peers IS NULL THEN 'insufficient_peers'
       WHEN relative_difference >= 0.20 THEN 'review_load_pto_route'
       ELSE 'within_review_threshold' END;
-- END MACROS

-- The temporary report table is populated by analysis.py with zoned Monday
-- boundaries. Initial/revised snapshots never gain retrospective public data.
CREATE OR REPLACE TABLE analytics.observations_asof AS
WITH versions AS (
 SELECT o.*, p.source_record_id, p.record_version, p.record_state AS provenance_state,
        p.available_time, r.output_id, r.as_of_time, r.report_week_start,
        r.report_week_end, r.report_view,
        row_number() OVER (
          PARTITION BY r.output_id, p.source_system_id, p.source_record_id
          ORDER BY try_cast(p.record_version AS BIGINT) DESC NULLS LAST,
                   p.available_time DESC, o.counter_observation_id DESC) AS version_rank
 FROM normalized.fuel_counter_observation o
 JOIN normalized.provenance_record p ON p.provenance_id=o.provenance_id
 JOIN analytics.report_context r ON r.tenant_id=o.tenant_id
   AND o.fuel_measured_at >= r.report_week_start - INTERVAL 1 DAY
   AND o.fuel_measured_at <= r.report_week_end
   AND p.available_time <= r.as_of_time
)
SELECT * EXCLUDE(version_rank)
FROM versions WHERE version_rank=1
 AND coalesce(provenance_state,'active') NOT IN ('withdrawn','deleted','cancelled');

CREATE OR REPLACE TABLE analytics.observation_context AS
SELECT o.*, coalesce(a.assignment_count,0) AS assignment_count,
       a.assigned_vehicle, a.assignments_resolved, a.assignment_ids, a.assignment_provenance,
       sf.counter_modulus AS fuel_modulus, sd.counter_modulus AS distance_modulus,
       sf.provenance_id AS fuel_definition_provenance,sd.provenance_id AS distance_definition_provenance,
       sf.source_ecu_id AS fuel_ecu, sd.source_ecu_id AS distance_ecu,
       sf.signal_unit AS fuel_definition_unit, sd.signal_unit AS distance_definition_unit,
       coalesce(sf.valid_from <= o.fuel_measured_at AND
          (sf.valid_to IS NULL OR o.fuel_measured_at < sf.valid_to)
          AND sfp.available_time<=o.as_of_time,false) AS fuel_definition_valid,
       coalesce(sd.valid_from <= o.distance_measured_at AND
          (sd.valid_to IS NULL OR o.distance_measured_at < sd.valid_to)
          AND sdp.available_time<=o.as_of_time,false) AS distance_definition_valid
FROM analytics.observations_asof o
LEFT JOIN LATERAL (
 SELECT count(*) AS assignment_count, min(a.vehicle_id) AS assigned_vehicle,
        bool_and(a.resolution_status='resolved') AS assignments_resolved,
        list(a.assignment_id) AS assignment_ids,
        list(a.provenance_id) AS assignment_provenance
 FROM normalized.core_vehicle_device_assignment a
 JOIN normalized.provenance_record ap ON ap.provenance_id=a.provenance_id
 WHERE a.tenant_id=o.tenant_id AND a.device_id=o.device_id
   AND a.valid_from <= o.fuel_measured_at
   AND (a.valid_to IS NULL OR o.fuel_measured_at<a.valid_to)
   AND a.known_from <= o.as_of_time
   AND ap.available_time <= o.as_of_time
   AND (a.known_to IS NULL OR o.as_of_time<a.known_to)
   AND a.resolution_status IN ('resolved','ambiguous','unknown')
   AND a.valid_to_state IN ('known','open') AND a.known_to_state IN ('known','open')
) a ON true
LEFT JOIN normalized.fuel_signal_definition sf ON
 sf.tenant_id=o.tenant_id AND sf.signal_definition_id=o.signal_definition_id
LEFT JOIN normalized.fuel_signal_definition sd ON
 sd.tenant_id=o.tenant_id AND sd.signal_definition_id=o.distance_definition_id
LEFT JOIN normalized.provenance_record sfp ON sfp.provenance_id=sf.provenance_id
LEFT JOIN normalized.provenance_record sdp ON sdp.provenance_id=sd.provenance_id;

CREATE OR REPLACE TABLE analytics.interval_candidates AS
WITH lagged AS (
 SELECT *,
   lag(counter_observation_id) OVER w AS prior_id,
   lag(provenance_id) OVER w AS prior_provenance_id,
   lag(fuel_measured_at) OVER w AS prior_fuel_at,
   lag(distance_measured_at) OVER w AS prior_distance_at,
   lag(fuel_total_l) OVER w AS prior_fuel,
   lag(odometer_km) OVER w AS prior_distance,
   lag(fuel_validity) OVER w AS prior_fuel_validity,
   lag(distance_validity) OVER w AS prior_distance_validity,
   lag(fuel_raw_unit) OVER w AS prior_fuel_unit,
   lag(distance_raw_unit) OVER w AS prior_distance_unit,
   lag(assignment_count) OVER w AS prior_assignment_count,
   lag(assignments_resolved) OVER w AS prior_assignments_resolved,
   lag(assigned_vehicle) OVER w AS prior_assigned_vehicle,
   lag(signal_definition_id) OVER w AS prior_fuel_definition,
   lag(distance_definition_id) OVER w AS prior_distance_definition,
   lag(fuel_ecu) OVER w AS prior_fuel_ecu,
   lag(distance_ecu) OVER w AS prior_distance_ecu
   ,lag(fuel_definition_valid) OVER w AS prior_fuel_definition_valid
   ,lag(distance_definition_valid) OVER w AS prior_distance_definition_valid
   ,lag(assignment_provenance) OVER w AS prior_assignment_provenance
 FROM analytics.observation_context
 WINDOW w AS (PARTITION BY output_id, tenant_id, device_id
   ORDER BY fuel_measured_at, counter_observation_id)
), boundary AS (
 SELECT l.*, epoch(fuel_measured_at-prior_fuel_at) AS elapsed_seconds,
   coalesce(c.fuel_reset,false) AS fuel_reset,
   coalesce(c.distance_reset,false) AS distance_reset,
   coalesce(c.fuel_wrap,false) AS fuel_wrap,
   coalesce(c.distance_wrap,false) AS distance_wrap,
   t.task_id, t.task_type,
   t.task_count,
   c.change_provenance,t.task_provenance,
   CASE WHEN lower(fuel_raw_unit) IN ('us_gal','us gal','gal','gallon')
     THEN fuel_modulus*3.785411784 ELSE fuel_modulus END AS fuel_modulus_l,
   CASE WHEN lower(distance_raw_unit) IN ('mile','mi','miles')
     THEN distance_modulus*1.609344 ELSE distance_modulus END AS distance_modulus_km
 FROM lagged l
 LEFT JOIN LATERAL (
   SELECT bool_or(c.signal_kind IN ('fuel','fuel_total','fuel_total_l','cumulative_fuel')
               AND c.counter_change_type NOT IN ('wrap','confirmed_wrap','rollover','confirmed_rollover')) AS fuel_reset,
          bool_or(c.signal_kind IN ('distance','odometer','odometer_km','cumulative_distance')
               AND c.counter_change_type NOT IN ('wrap','confirmed_wrap','rollover','confirmed_rollover')) AS distance_reset,
          bool_or(c.signal_kind IN ('fuel','fuel_total','fuel_total_l','cumulative_fuel')
               AND c.counter_change_type IN ('wrap','confirmed_wrap','rollover','confirmed_rollover')) AS fuel_wrap,
          bool_or(c.signal_kind IN ('distance','odometer','odometer_km','cumulative_distance')
               AND c.counter_change_type IN ('wrap','confirmed_wrap','rollover','confirmed_rollover')) AS distance_wrap,
          list(c.provenance_id) AS change_provenance
   FROM normalized.fuel_counter_change c
   JOIN normalized.provenance_record cp ON cp.provenance_id=c.provenance_id
   WHERE c.tenant_id=l.tenant_id AND c.device_id=l.device_id
     AND c.counter_change_at>l.prior_fuel_at AND c.counter_change_at<=l.fuel_measured_at
     AND cp.available_time<=l.as_of_time
 ) c ON true
 LEFT JOIN LATERAL (
   SELECT count(*) AS task_count, min(t.task_id) AS task_id, min(t.task_type) AS task_type,
     list(t.provenance_id) AS task_provenance
   FROM normalized.fuel_task_assignment t
   JOIN normalized.provenance_record tp ON tp.provenance_id=t.provenance_id
   WHERE t.tenant_id=l.tenant_id AND t.vehicle_id=l.assigned_vehicle
     AND l.prior_fuel_at>=t.task_start_at AND l.fuel_measured_at<=t.task_end_at
     AND t.task_assignment_from<=l.prior_fuel_at
     AND (t.task_assignment_to IS NULL OR l.fuel_measured_at<=t.task_assignment_to)
     AND tp.available_time<=l.as_of_time
 ) t ON true
 WHERE l.prior_id IS NOT NULL AND l.fuel_measured_at>l.report_week_start
), differences AS (
 SELECT *,
   CASE WHEN fuel_total_l-prior_fuel>=0 THEN fuel_total_l-prior_fuel
        WHEN fuel_wrap AND fuel_modulus_l>0 THEN fuel_modulus_l-prior_fuel+fuel_total_l END AS fuel_delta,
   CASE WHEN odometer_km-prior_distance>=0 THEN odometer_km-prior_distance
        WHEN distance_wrap AND distance_modulus_km>0 THEN distance_modulus_km-prior_distance+odometer_km END AS distance_delta,
   assignment_count=1 AND prior_assignment_count=1 AND assignments_resolved AND prior_assignments_resolved
     AND assigned_vehicle=prior_assigned_vehicle
     AND (vehicle_id IS NULL OR vehicle_id=assigned_vehicle) AS assignment_ok,
   prior_fuel_at=prior_distance_at AND fuel_measured_at=distance_measured_at AS aligned,
   lower(fuel_raw_unit) IN ('l','liter','litre','us_gal','us gal','gal','gallon')
     AND lower(prior_fuel_unit) IN ('l','liter','litre','us_gal','us gal','gal','gallon') AS fuel_unit_ok,
   lower(distance_raw_unit) IN ('km','kilometer','kilometre','mile','mi','miles')
     AND lower(prior_distance_unit) IN ('km','kilometer','kilometre','mile','mi','miles') AS distance_unit_ok,
   lower(coalesce(fuel_validity,'')) IN ('valid','observed')
     AND lower(coalesce(prior_fuel_validity,'')) IN ('valid','observed')
     AND fuel_total_l IS NOT NULL AND prior_fuel IS NOT NULL AS fuel_valid,
   lower(coalesce(distance_validity,'')) IN ('valid','observed')
     AND lower(coalesce(prior_distance_validity,'')) IN ('valid','observed')
     AND odometer_km IS NOT NULL AND prior_distance IS NOT NULL AS distance_valid,
   prior_fuel_at>=report_week_start AND fuel_measured_at<=report_week_end
     AND cast(prior_fuel_at AT TIME ZONE 'America/Los_Angeles' AS DATE)
       =cast((fuel_measured_at-INTERVAL 1 MICROSECOND) AT TIME ZONE 'America/Los_Angeles' AS DATE)
       AS period_ok
 FROM boundary
), reasons AS (
 SELECT *,
  CASE WHEN NOT assignment_ok THEN 'ambiguous_assignment'
       WHEN NOT fuel_unit_ok OR NOT distance_unit_ok THEN 'unknown_unit'
       WHEN NOT fuel_valid OR NOT distance_valid OR NOT fuel_definition_valid OR NOT distance_definition_valid
         OR NOT prior_fuel_definition_valid OR NOT prior_distance_definition_valid THEN 'invalid_reading'
       WHEN fuel_reset OR distance_reset OR fuel_delta IS NULL OR distance_delta IS NULL
         OR signal_definition_id<>prior_fuel_definition OR distance_definition_id<>prior_distance_definition
         OR fuel_ecu IS DISTINCT FROM prior_fuel_ecu OR distance_ecu IS DISTINCT FROM prior_distance_ecu THEN 'counter_break'
       WHEN NOT aligned OR elapsed_seconds<=0 THEN 'unaligned_boundary'
       WHEN NOT period_ok THEN 'cross_period_unallocatable'
       WHEN task_count<>1 THEN 'outside_or_ambiguous_task'
       ELSE 'none' END AS exclusion_reason,
  coalesce(assignment_ok AND distance_unit_ok AND distance_valid AND distance_definition_valid AND prior_distance_definition_valid
    AND aligned AND period_ok AND elapsed_seconds>0 AND task_count=1
    AND NOT distance_reset AND distance_delta IS NOT NULL
    AND distance_definition_id=prior_distance_definition
    AND distance_ecu IS NOT DISTINCT FROM prior_distance_ecu,false) AS distance_accepted
 FROM differences
)
SELECT *,coalesce(exclusion_reason='none',false) AS pair_accepted,
 list_distinct(list_concat([prior_provenance_id,provenance_id,fuel_definition_provenance,distance_definition_provenance],
   coalesce(assignment_provenance,[]),coalesce(prior_assignment_provenance,[]),
   coalesce(change_provenance,[]),coalesce(task_provenance,[]))) AS input_provenance_list
FROM reasons;

CREATE OR REPLACE TABLE analytics.paired_result AS
SELECT tenant_id,
 output_id||':'||prior_id||':'||counter_observation_id AS paired_interval_id,
 device_id||':'||signal_definition_id||':'||cast(sum(CASE WHEN fuel_reset OR fuel_delta IS NULL THEN 1 ELSE 0 END)
   OVER (PARTITION BY output_id,device_id ORDER BY fuel_measured_at,counter_observation_id) AS VARCHAR) AS fuel_segment_id,
 device_id||':'||distance_definition_id||':'||cast(sum(CASE WHEN distance_reset OR distance_delta IS NULL THEN 1 ELSE 0 END)
   OVER (PARTITION BY output_id,device_id ORDER BY fuel_measured_at,counter_observation_id) AS VARCHAR) AS distance_segment_id,
 prior_fuel_at AS paired_interval_start, fuel_measured_at AS paired_interval_end,
 CASE WHEN pair_accepted THEN fuel_delta END AS paired_fuel_l,
 CASE WHEN pair_accepted THEN distance_delta END AS paired_distance_km,
 exclusion_reason AS excluded_interval_reason,
 assigned_vehicle AS vehicle_id, as_of_time, 'fuel-metrics-1.0.0' AS calculation_version,
 to_json(input_provenance_list) AS input_provenance_ids,
 prior_id AS fuel_start_observation_id,counter_observation_id AS fuel_end_observation_id,
 prior_id AS distance_start_observation_id,counter_observation_id AS distance_end_observation_id,
 pair_accepted AS accepted
FROM analytics.interval_candidates
WHERE elapsed_seconds>0;

-- Version selection is applied before financial filtering: corrected historical
-- records remain usable until a replacement is actually available.
CREATE OR REPLACE TABLE analytics.purchase_versions AS
SELECT * EXCLUDE(version_rank) FROM (
 SELECT f.*,p.available_time,p.record_state AS provenance_state,
   r.output_id,r.as_of_time,r.report_week_start,r.report_week_end,r.report_view,
   row_number() OVER (PARTITION BY r.output_id,f.tenant_id,f.purchase_line_id
    ORDER BY try_cast(f.line_version AS BIGINT) DESC NULLS LAST,p.available_time DESC) AS version_rank
 FROM normalized.fuel_purchase_line f
 JOIN normalized.provenance_record p ON p.provenance_id=f.provenance_id
 JOIN analytics.report_context r ON r.tenant_id=f.tenant_id AND p.available_time<=r.as_of_time
  AND (f.posted_at IS NULL OR f.posted_at<=r.as_of_time)
) WHERE version_rank=1;

CREATE OR REPLACE TABLE analytics.purchase_detail AS
WITH effective AS (
 SELECT f.*,coalesce(o.purchase_time,f.purchase_time) AS attributed_purchase_time,
  coalesce(o.vehicle_id,f.vehicle_id) AS attributed_vehicle_id,
  coalesce(o.station_id,f.station_id) AS attributed_station_id,
  CASE WHEN f.adjustment_type IN ('amount_refund','pure_amount_refund','discount_adjustment') THEN 0
    ELSE f.purchase_quantity_l END AS effective_quantity_l,
  fuel_comparable_amount(f.source_amount_basis,f.purchase_amount,f.fuel_subtotal,
   f.fuel_tax_amount,f.fuel_discount_amount,f.extra_fee_amount,f.nonfuel_amount) AS comparable_amount
 FROM analytics.purchase_versions f
 LEFT JOIN analytics.purchase_versions o ON o.output_id=f.output_id AND o.tenant_id=f.tenant_id
  AND o.purchase_line_id=f.original_purchase_line_id
), scoped AS (
 SELECT e.*,s.station_state,m.market_region,s.station_provenance_id,m.region_mapping_provenance_id,
  ca.card_assignment_provenance,
  CASE WHEN provenance_state IN ('withdrawn','deleted','cancelled') OR record_state IN ('withdrawn','deleted','cancelled')
      OR lower(coalesce(transaction_status,'')) IN ('cancelled','pending','void') THEN 'inactive'
    WHEN upper(coalesce(currency,''))<>'USD' THEN 'currency_not_comparable'
    WHEN lower(coalesce(purchase_fuel_type,'')) NOT IN ('diesel','diesel_ulsd','ulsd') THEN 'nonfuel_or_product'
    WHEN comparable_amount IS NULL THEN 'unknown_amount_basis'
    WHEN effective_quantity_l IS NULL THEN 'unknown_quantity'
    WHEN ca.assignment_count<>1 OR ca.assigned_vehicle IS DISTINCT FROM attributed_vehicle_id THEN 'ambiguous_card_assignment'
    ELSE 'comparable' END AS financial_status
 FROM effective e
 LEFT JOIN LATERAL (
  SELECT s.station_state,s.provenance_id AS station_provenance_id FROM normalized.fuel_station s
  JOIN normalized.provenance_record sp ON sp.provenance_id=s.provenance_id
  WHERE s.tenant_id=e.tenant_id AND s.station_id=e.attributed_station_id AND sp.available_time<=e.as_of_time
  ORDER BY sp.available_time DESC LIMIT 1
 ) s ON true
 LEFT JOIN LATERAL (
  SELECT m.market_region,m.provenance_id AS region_mapping_provenance_id FROM normalized.fuel_region_mapping m
  JOIN normalized.provenance_record mp ON mp.provenance_id=m.provenance_id
  WHERE m.tenant_id=e.tenant_id AND m.state_code=s.station_state
   AND m.valid_from<=e.attributed_purchase_time AND (m.valid_to IS NULL OR e.attributed_purchase_time<m.valid_to)
   AND mp.available_time<=e.as_of_time ORDER BY mp.available_time DESC LIMIT 1
 ) m ON true
 LEFT JOIN LATERAL (
  SELECT count(*) AS assignment_count,min(c.vehicle_id) AS assigned_vehicle,
    list(c.provenance_id) AS card_assignment_provenance
  FROM normalized.fuel_card_assignment c
  JOIN normalized.provenance_record cp ON cp.provenance_id=c.provenance_id
  WHERE c.tenant_id=e.tenant_id AND c.fuel_card_id=e.fuel_card_id
   AND c.card_vehicle_from<=e.attributed_purchase_time AND (c.card_vehicle_to IS NULL OR e.attributed_purchase_time<c.card_vehicle_to)
   AND c.known_from<=e.as_of_time AND (c.known_to IS NULL OR e.as_of_time<c.known_to)
   AND cp.available_time<=e.as_of_time
 ) ca ON true
 WHERE e.attributed_purchase_time>=e.report_week_start AND e.attributed_purchase_time<e.report_week_end
)
SELECT s.*,market.market_week_price,market.origin_label AS market_origin,
 market.provenance_id AS market_provenance_id,
 market.price_observation_date,market.price_snapshot_ref,
 CASE WHEN financial_status='comparable' AND effective_quantity_l>=0 AND market.market_week_price>0
   THEN effective_quantity_l/3.785411784*market.market_week_price END AS reference_amount,
 CASE WHEN market.origin_label='public' THEN 'retrospective_public_background'
      WHEN market.origin_label='synthetic' THEN 'simulated_asof_background' ELSE 'unmatched' END AS benchmark_view
FROM scoped s
LEFT JOIN LATERAL (
 SELECT m.* FROM normalized.fuel_market_price m
 JOIN normalized.provenance_record mp ON mp.provenance_id=m.provenance_id
 WHERE m.tenant_id=s.tenant_id AND m.market_region=s.market_region
  AND m.price_observation_date<=cast(s.attributed_purchase_time AT TIME ZONE 'America/Los_Angeles' AS DATE)
  AND m.price_observation_date>cast(s.attributed_purchase_time AT TIME ZONE 'America/Los_Angeles' AS DATE)-INTERVAL 8 DAY
  AND mp.available_time<=s.as_of_time
  AND (s.report_view='retrospective' OR m.origin_label='synthetic'
       OR (m.price_published_at IS NOT NULL AND m.price_published_at<=s.as_of_time
           AND mp.availability_basis<>'retrieved_only'))
 ORDER BY CASE WHEN m.origin_label='public' THEN 0 ELSE 1 END,
  m.price_observation_date DESC,mp.available_time DESC LIMIT 1
) market ON true;

CREATE OR REPLACE TABLE analytics.weekly_result AS
WITH operating AS (
 SELECT r.output_id,t.vehicle_id,
  sum(epoch(least(t.task_end_at,r.report_week_end)-greatest(t.task_start_at,r.report_week_start))) AS expected_seconds,
  CASE WHEN count(DISTINCT t.task_type)=1 THEN min(t.task_type) ELSE 'mixed' END AS task_group
 FROM analytics.report_context r
 JOIN normalized.fuel_task_assignment t ON t.tenant_id=r.tenant_id
  AND t.task_start_at<r.report_week_end AND t.task_end_at>r.report_week_start
 JOIN normalized.provenance_record tp ON tp.provenance_id=t.provenance_id AND tp.available_time<=r.as_of_time
 GROUP BY r.output_id,t.vehicle_id
), driving AS (
 SELECT output_id,assigned_vehicle AS vehicle_id,
  sum(fuel_delta) FILTER (WHERE pair_accepted) AS fuel_l,
  sum(distance_delta) FILTER (WHERE pair_accepted) AS distance_km,
  coalesce(sum(elapsed_seconds) FILTER (WHERE pair_accepted),0) AS paired_seconds,
  coalesce(sum(elapsed_seconds) FILTER (WHERE distance_accepted),0) AS distance_seconds,
  sum(distance_delta) FILTER (WHERE distance_accepted) AS all_distance_km,
  list_distinct(flatten(list(input_provenance_list))) AS source_provenance_ids
 FROM analytics.interval_candidates GROUP BY output_id,assigned_vehicle
), purchases AS (
 SELECT output_id,attributed_vehicle_id AS vehicle_id,
  sum(comparable_amount) FILTER (WHERE financial_status='comparable') AS comparable_amount,
  sum(effective_quantity_l) FILTER (WHERE financial_status='comparable') AS purchase_l,
  sum(reference_amount) FILTER (WHERE financial_status='comparable') AS benchmark_amount,
  sum(comparable_amount) FILTER (WHERE financial_status='comparable' AND reference_amount IS NOT NULL) AS matched_amount,
  sum(effective_quantity_l) FILTER (WHERE financial_status='comparable' AND reference_amount IS NOT NULL) AS matched_l,
  sum(effective_quantity_l) FILTER (WHERE financial_status='comparable' AND effective_quantity_l>0) AS eligible_l,
  list_distinct(flatten(list(list_concat([provenance_id,market_provenance_id,station_provenance_id,region_mapping_provenance_id],
    coalesce(card_assignment_provenance,[]))))) AS source_provenance_ids
 FROM analytics.purchase_detail GROUP BY output_id,attributed_vehicle_id
), joined AS (
 SELECT r.tenant_id,r.output_id||':'||v.vehicle_id AS weekly_metric_id,
  d.fuel_l AS fuel_used_l,d.distance_km AS distance_travelled_km,
  d.paired_seconds/nullif(o.expected_seconds,0) AS measurement_coverage,
  'ecu_difference' AS consumption_method,fuel_mpg(d.distance_km,d.fuel_l) AS mpg,
  p.comparable_amount AS comparable_fuel_amount,
  CASE WHEN p.purchase_l>0 THEN p.comparable_amount/p.purchase_l END AS weighted_purchase_price_usd_per_l,
  CASE WHEN d.distance_seconds>=o.expected_seconds-0.001 AND d.all_distance_km>0
   THEN p.comparable_amount/d.all_distance_km END AS purchase_spend_usd_per_km,
  p.benchmark_amount,p.matched_amount-p.benchmark_amount AS benchmark_amount_gap,
  p.matched_l/nullif(p.eligible_l,0) AS benchmark_match_coverage,
  CASE WHEN d.distance_seconds>=o.expected_seconds-0.001 THEN d.all_distance_km END AS weekly_valid_distance_km,
  v.vehicle_id,r.as_of_time,'fuel-metrics-1.0.0' AS calculation_version,
  to_json(list_distinct(list_concat(coalesce(d.source_provenance_ids,[]),coalesce(p.source_provenance_ids,[])))) AS input_provenance_ids,
  r.output_id,coalesce(o.task_group,'unknown') AS task_comparison_group,
  coalesce(d.paired_seconds,0) AS valid_paired_seconds,coalesce(o.expected_seconds,0) AS expected_observation_seconds,
  coalesce(p.matched_l,0) AS benchmark_matched_quantity_l,coalesce(p.eligible_l,0) AS benchmark_eligible_quantity_l,
  p.purchase_l,r.report_view,r.report_week_start,r.report_week_end
 FROM analytics.report_context r JOIN normalized.core_vehicle v ON v.tenant_id=r.tenant_id
 LEFT JOIN operating o ON o.output_id=r.output_id AND o.vehicle_id=v.vehicle_id
 LEFT JOIN driving d ON d.output_id=r.output_id AND d.vehicle_id=v.vehicle_id
 LEFT JOIN purchases p ON p.output_id=r.output_id AND p.vehicle_id=v.vehicle_id
), previous AS (
 SELECT *,lag(weighted_purchase_price_usd_per_l) OVER w AS prior_price,
  lag(purchase_l) OVER w AS prior_quantity,
  lag(task_comparison_group) OVER w AS prior_group
 FROM joined WINDOW w AS (PARTITION BY tenant_id,vehicle_id,report_view ORDER BY report_week_start)
)
SELECT *,
 fuel_price_effect(prior_price,prior_quantity,weighted_purchase_price_usd_per_l) AS purchase_price_effect,
 fuel_quantity_effect(prior_quantity,weighted_purchase_price_usd_per_l,purchase_l) AS purchase_quantity_effect,
 CASE WHEN prior_price IS NULL OR weighted_purchase_price_usd_per_l IS NULL OR prior_quantity IS NULL OR purchase_l IS NULL
    THEN 'missing_purchase_baseline' ELSE 'same_vehicle_usd_diesel_monetary_bridge' END AS decomposition_status,
 CASE WHEN prior_group=task_comparison_group AND task_comparison_group NOT IN ('mixed','unknown')
    THEN 'same_single_task' ELSE 'duty_mix_requires_separate_review' END AS decomposition_task_context
FROM previous;

CREATE OR REPLACE TABLE analytics.inventory_result AS
WITH boundaries AS (
 SELECT i.*,lead(inventory_measurement_id) OVER w AS closing_id,
  lead(measured_at) OVER w AS closing_at,lead(quantity_l) OVER w AS closing_l,
  lead(inventory_uncertainty) OVER w AS closing_uncertainty,
  lead(inventory_measurement_method) OVER w AS closing_method
 FROM normalized.fuel_inventory_measurement i
 WHERE measurement_role='period_boundary'
 WINDOW w AS (PARTITION BY tenant_id,vehicle_id,inventory_tank_scope_id ORDER BY measured_at)
), sums AS (
 SELECT b.*,m.refuel,m.incoming,m.removed,m.unknown_count,m.in_count,m.out_count,m.available_at,
  (SELECT max(available_time) FROM normalized.provenance_record) AS cutoff
 FROM boundaries b
 LEFT JOIN LATERAL (
  SELECT sum(CASE WHEN fuel_movement_type='refuel' AND movement_destination_scope=b.inventory_tank_scope_id THEN fuel_movement_quantity_l ELSE 0 END) AS refuel,
   sum(CASE WHEN fuel_movement_type='transfer_in' AND movement_destination_scope=b.inventory_tank_scope_id THEN fuel_movement_quantity_l ELSE 0 END) AS incoming,
   sum(CASE WHEN fuel_movement_type IN ('transfer_out','maintenance_drain','other_verified') AND movement_source_scope=b.inventory_tank_scope_id THEN fuel_movement_quantity_l ELSE 0 END) AS removed,
   count(*) FILTER (WHERE fuel_movement_quantity_l IS NULL) AS unknown_count,
   count(*) FILTER (WHERE fuel_movement_type='transfer_in') AS in_count,
   count(*) FILTER (WHERE fuel_movement_type IN ('transfer_out','maintenance_drain','other_verified')) AS out_count,
   max(p.available_time) AS available_at
  FROM normalized.fuel_movement m
  JOIN normalized.provenance_record p ON p.provenance_id=m.provenance_id
  WHERE m.tenant_id=b.tenant_id AND m.vehicle_id=b.vehicle_id
   AND m.fuel_movement_at>=b.measured_at AND m.fuel_movement_at<b.closing_at
   AND (m.movement_source_scope=b.inventory_tank_scope_id OR m.movement_destination_scope=b.inventory_tank_scope_id)
 ) m ON true
 WHERE b.closing_id IS NOT NULL
), checked AS (
 SELECT *,CASE
  WHEN quantity_l IS NULL OR closing_l IS NULL OR inventory_measurement_method='unknown' OR closing_method='unknown' THEN 'uncalibrated_boundary'
  WHEN unknown_count>0 THEN 'incomplete_movements'
  WHEN in_count=0 OR out_count=0 THEN 'unconfirmed_movements'
  WHEN inventory_uncertainty IS NULL OR closing_uncertainty IS NULL THEN 'unknown_uncertainty'
  ELSE 'verified_synthetic_ledger' END AS quality_state
 FROM sums
)
SELECT tenant_id,inventory_measurement_id||':'||closing_id AS balance_id,
 quantity_l AS opening_volume_l,closing_l AS closing_volume_l,measured_at AS period_start_at,closing_at AS period_end_at,
 CASE WHEN quality_state='verified_synthetic_ledger' THEN 'uncertainty_known'
   WHEN quality_state IN ('incomplete_movements','unconfirmed_movements') THEN 'incomplete_movements'
   ELSE 'boundary_mismatch' END AS inventory_quality_state,
 quality_state AS inventory_detail_state,refuel AS refuel_volume_l,
 CASE WHEN unknown_count=0 AND in_count>0 THEN incoming END AS transfer_in_l,
 CASE WHEN unknown_count=0 AND out_count>0 THEN removed END AS removed_l,
 CASE WHEN quality_state='verified_synthetic_ledger' THEN fuel_balance(quantity_l,refuel,incoming,closing_l,removed) END AS balance_consumption_l,
 CASE WHEN unknown_count=0 AND in_count>0 AND out_count>0 THEN incoming-removed END AS net_transfer_l,
 vehicle_id,inventory_measurement_id AS opening_measurement_id,closing_id AS closing_measurement_id,
 inventory_tank_scope_id,cutoff AS as_of_time,
 CASE WHEN inventory_uncertainty IS NOT NULL AND closing_uncertainty IS NOT NULL
  THEN inventory_uncertainty+closing_uncertainty END AS uncertainty_l
FROM checked;
