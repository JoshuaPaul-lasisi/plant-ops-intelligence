-- High-risk days from the anomaly model, and whether an unplanned trip followed within 4 days.
WITH high_risk AS (
  SELECT date, package_id, max_risk_ratio, alert_hours, flagged_system
  FROM `nitrogen-plant-operations.nitrochem_ngu.fact_anomaly_daily`
  WHERE risk_level = 'High'
),
trips AS (
  SELECT package_id, date AS trip_date, failure_mode
  FROM `nitrogen-plant-operations.nitrochem_ngu.fact_downtime_events`
  WHERE event_type = 'Unplanned'
)
SELECT
  h.date,
  h.package_id,
  ROUND(h.max_risk_ratio, 2) AS max_risk_ratio,
  h.alert_hours,
  h.flagged_system,
  MIN(t.trip_date)    AS next_trip_date,
  ANY_VALUE(t.failure_mode) AS next_trip_failure_mode
FROM high_risk h
LEFT JOIN trips t
  ON t.package_id = h.package_id
 AND t.trip_date BETWEEN h.date AND DATE_ADD(h.date, INTERVAL 4 DAY)
GROUP BY h.date, h.package_id, h.max_risk_ratio, h.alert_hours, h.flagged_system
ORDER BY h.date DESC, h.package_id;
