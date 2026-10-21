-- Monthly KPIs for the whole nitrogen unit: production, downtime, OEE, energy intensity.
-- Project nitrogen-plant-operations, dataset nitrochem_ngu.
SELECT
  month_start,
  ROUND(SUM(n2_production_nm3) / 1e6, 3)                                   AS n2_production_mnm3,
  SUM(unplanned_trips)                                                      AS unplanned_trips,
  SUM(unplanned_downtime_hrs)                                               AS unplanned_downtime_hrs,
  ROUND(100 * SAFE_DIVIDE(SUM(running_hours),
        SUM(24 * days) - SUM(planned_downtime_hrs)), 2)                     AS availability_pct,
  ROUND(SAFE_DIVIDE(SUM(power_consumption_kwh), SUM(n2_production_nm3)), 4) AS energy_intensity_kwh_per_nm3
FROM `nitrogen-plant-operations.nitrochem_ngu.fact_monthly_package`
GROUP BY month_start
ORDER BY month_start;
