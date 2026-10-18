-- Pareto of unplanned downtime by failure mode, with cumulative share.
WITH by_mode AS (
  SELECT
    cause_category,
    failure_mode,
    COUNT(*)        AS trips,
    SUM(downtime_h) AS downtime_h,
    AVG(downtime_h) AS mttr_h
  FROM `your-gcp-project-id.nitrochem_ngu.fact_downtime_events`
  WHERE event_type = 'Unplanned'
  GROUP BY cause_category, failure_mode
)
SELECT
  cause_category,
  failure_mode,
  trips,
  downtime_h,
  ROUND(mttr_h, 1) AS mttr_h,
  ROUND(100 * downtime_h / SUM(downtime_h) OVER (), 1) AS share_pct,
  ROUND(100 * SUM(downtime_h) OVER (ORDER BY downtime_h DESC ROWS UNBOUNDED PRECEDING)
        / SUM(downtime_h) OVER (), 1) AS cumulative_share_pct
FROM by_mode
ORDER BY downtime_h DESC;
