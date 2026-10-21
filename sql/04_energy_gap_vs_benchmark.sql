-- Monthly energy intensity of each package against NGU-A, and the cost of the gap.
-- The naira rate is an assumption; change it to your own power cost.
DECLARE ngn_per_kwh FLOAT64 DEFAULT 150;

WITH m AS (
  SELECT
    month_start,
    package_id,
    n2_production_nm3,
    SAFE_DIVIDE(power_consumption_kwh, n2_production_nm3) AS ei
  FROM `nitrogen-plant-operations.nitrochem_ngu.fact_monthly_package`
),
benchmark AS (
  SELECT month_start, ei AS ei_benchmark FROM m WHERE package_id = 'NGU-A'
)
SELECT
  m.month_start,
  m.package_id,
  ROUND(m.ei, 4)                                         AS energy_intensity_kwh_per_nm3,
  ROUND(100 * (m.ei / b.ei_benchmark - 1), 1)            AS gap_vs_ngu_a_pct,
  ROUND((m.ei - b.ei_benchmark) * m.n2_production_nm3)   AS excess_kwh,
  ROUND((m.ei - b.ei_benchmark) * m.n2_production_nm3 * ngn_per_kwh) AS excess_cost_ngn
FROM m
JOIN benchmark b USING (month_start)
WHERE m.package_id <> 'NGU-A'
ORDER BY m.month_start, m.package_id;
