# Power BI build guide

The report reads the eight tables in `data/processed/`. Build time is about one evening once the data is loaded.

## 1. Load the data

Option A, CSV: Home > Get data > Text/CSV, one file at a time from `data/processed/`. In Power Query, check that `date`, `trip_time`, `restart_time`, `start` and `end` come in as Date or Date/Time, and package IDs as Text.

Option B, BigQuery: run notebook 05 with `LOAD_TO_BIGQUERY = True`, then Home > Get data > Google BigQuery, sign in, and pick the `nitrochem_ngu` dataset.

Load these and skip the rest:

| Table | Use |
|---|---|
| dim_date | date slicer, month axis |
| dim_package | package slicer and colours |
| fact_daily_package | production, OEE, energy |
| fact_downtime_events | downtime pages |
| fact_daily_plant | LIN tank and N2 shortfall |
| fact_anomaly_daily | risk by day |
| fact_alert_episodes | alert list |

`fact_monthly_package` is for the SQL views and for anyone not using DAX. In Power BI, compute monthly figures from the daily table with the measures below, so they stay right under any filter.

## 2. Model

Mark `dim_date` as the date table (Table tools > Mark as date table, column `date`).

Relationships, all single direction, one to many:

| From (one side) | To (many side) |
|---|---|
| dim_date[date] | fact_daily_package[date] |
| dim_date[date] | fact_downtime_events[date] |
| dim_date[date] | fact_daily_plant[date] |
| dim_date[date] | fact_anomaly_daily[date] |
| dim_date[date] | fact_alert_episodes[date] |
| dim_package[package_id] | fact_daily_package[package_id] |
| dim_package[package_id] | fact_downtime_events[package_id] |
| dim_package[package_id] | fact_anomaly_daily[package_id] |
| dim_package[package_id] | fact_alert_episodes[package_id] |

`fact_daily_plant` is plant level and has no package column, so package slicers do not filter it. That is correct.

Sort `dim_date[month_name]` by `dim_date[month_sort]` (Column tools > Sort by column).

## 3. Theme

View > Themes > Browse for themes > `docs/powerbi_theme.json`. It sets the package colours used in the notebooks (NGU-A blue, NGU-B orange, NGU-C aqua), which stay distinguishable for colour-blind readers.

## 4. Measures

Create a blank table called `_Measures` (Enter data, one empty column) and put every measure in it.

```DAX
N2 Production (MNm3) = DIVIDE ( SUM ( fact_daily_package[n2_production_nm3] ), 1e6 )

N2 Vented (kNm3) = DIVIDE ( SUM ( fact_daily_package[n2_vented_nm3] ), 1e3 )

Running Hours = SUM ( fact_daily_package[running_hours] )

Planned Downtime (h) = SUM ( fact_daily_package[planned_downtime_hrs] )

Unplanned Downtime (h) = SUM ( fact_daily_package[unplanned_downtime_hrs] )

Available Hours = COUNTROWS ( fact_daily_package ) * 24 - [Planned Downtime (h)]

Availability % = DIVIDE ( [Running Hours], [Available Hours] )

Performance % =
DIVIDE (
    SUM ( fact_daily_package[n2_production_nm3] ) + SUM ( fact_daily_package[n2_vented_nm3] ),
    1000 * [Running Hours]
)

Quality % =
DIVIDE (
    SUM ( fact_daily_package[n2_production_nm3] ),
    SUM ( fact_daily_package[n2_production_nm3] ) + SUM ( fact_daily_package[n2_vented_nm3] )
)

OEE % = [Availability %] * [Performance %] * [Quality %]

Energy Intensity (kWh/Nm3) =
DIVIDE ( SUM ( fact_daily_package[power_consumption_kwh] ), SUM ( fact_daily_package[n2_production_nm3] ) )

Energy Intensity NGU-A =
CALCULATE ( [Energy Intensity (kWh/Nm3)], dim_package[package_id] = "NGU-A" )

Energy Gap vs NGU-A % = DIVIDE ( [Energy Intensity (kWh/Nm3)], [Energy Intensity NGU-A] ) - 1

Unplanned Trips =
CALCULATE ( COUNTROWS ( fact_downtime_events ), fact_downtime_events[event_type] = "Unplanned" )

MTBF (h) = DIVIDE ( [Running Hours], [Unplanned Trips] )

MTTR (h) =
CALCULATE ( AVERAGE ( fact_downtime_events[downtime_h] ), fact_downtime_events[event_type] = "Unplanned" )

Event Downtime (h) = SUM ( fact_downtime_events[downtime_h] )

N2 Shortfall (h) = SUM ( fact_daily_plant[n2_shortfall_hours] )

Lowest LIN Level % = MIN ( fact_daily_plant[lin_tank_level_min_pct] ) / 100

High Risk Days =
CALCULATE ( COUNTROWS ( fact_anomaly_daily ), fact_anomaly_daily[risk_level] = "High" )

Alerts = COUNTROWS ( fact_alert_episodes )

Alerts Before Trip =
CALCULATE ( COUNTROWS ( fact_alert_episodes ), fact_alert_episodes[outcome] = "Warned before trip" )

False Alarms =
CALCULATE ( COUNTROWS ( fact_alert_episodes ), fact_alert_episodes[outcome] = "False alarm" )
```

Power cost is an assumption, so make it a slider. Modeling > New parameter > Numeric range: name `Power Cost NGN per kWh`, 50 to 300, increment 10, default 150. Then:

```DAX
Excess Energy Cost (NGN m) =
VAR gap = [Energy Intensity (kWh/Nm3)] - [Energy Intensity NGU-A]
RETURN
    DIVIDE ( gap * SUM ( fact_daily_package[n2_production_nm3] ) * 'Power Cost NGN per kWh'[Power Cost NGN per kWh Value], 1e6 )
```

Format the % measures as percentage with one decimal, energy intensity with three decimals.

## 5. Pages

Put the same two slicers at the top of every page: `dim_date[month_name]` (dropdown) and `dim_package[package_id]` (buttons). Sync them across pages (View > Sync slicers).

### Page 1: Overview

- Cards: N2 Production (MNm3), Unplanned Downtime (h), Unplanned Trips, OEE %, Energy Intensity (kWh/Nm3), N2 Shortfall (h).
- Line chart: X `dim_date[month_start]`, Y `OEE %`, legend `dim_package[package_id]`.
- Clustered column: X `dim_package[package_id]`, Y `N2 Production (MNm3)`.
- Line chart: X `dim_date[date]`, Y `Lowest LIN Level %` (shows the tank drawing down during trips).

### Page 2: Downtime analysis

- Stacked bar: Y `dim_package[package_id]`, X `Event Downtime (h)`, legend `fact_downtime_events[cause_category]`.
- Line chart: X `dim_date[month_start]`, Y `Unplanned Downtime (h)`, legend `dim_package[package_id]` (the 24-month trend).
- Table (the Pareto): `fact_downtime_events[failure_mode]`, `Unplanned Trips`, `Event Downtime (h)`, `MTTR (h)`; filter `event_type` = Unplanned; sort by downtime.
- Slicer: `fact_downtime_events[onset]` (Gradual, Sudden, Planned). Gradual failures are the ones the anomaly model can catch.
- Cards: MTBF (h), MTTR (h).

### Page 3: Energy efficiency

- Line chart: X `dim_date[month_start]`, Y `Energy Intensity (kWh/Nm3)`, legend `dim_package[package_id]`.
- Scatter: X `fact_daily_package[running_hours]` (Don't summarise), Y `fact_daily_package[power_consumption_mwh]` (Don't summarise), legend `package_id`, details `date`.
- Clustered column: X `dim_package[package_id]`, Y `Energy Gap vs NGU-A %`.
- Card: Excess Energy Cost (NGN m), with the power cost slider beside it.
- Text box: "NGU-C's gap is about two thirds compressor wear and one third intercooler fouling (notebook 03)."

### Page 4: Anomaly alerts

- Page filter: `dim_date[dataset_period]` = Test, so the page shows only months the model never trained on. Remove it to see all two years.
- Line chart: X `dim_date[date]`, Y max of `fact_anomaly_daily[max_risk_ratio]`, legend `package_id`. Add a constant line at 1.0 (Analytics pane) labelled "Alert threshold".
- Table: `fact_anomaly_daily[date]`, `package_id`, `max_risk_ratio`, `alert_hours`, `flagged_system`, `risk_level`; filter `risk_level` = High; conditional formatting on `max_risk_ratio` (background, white to red).
- Table: `fact_alert_episodes[start]`, `end`, `package_id`, `system`, `outcome`, `duration_h`.
- Cards: Alerts Before Trip, False Alarms, High Risk Days.
- Text box: "Catches faults that develop over hours (bearings, compressor vibration, PPU breakthrough, cooling water). Cannot catch sudden failures: power dips, relay trips, coupling and valve failures."

## 6. Publish

File > Publish to Power BI service (free account works for My workspace), or export each page to PDF and PNG for the GitHub README (File > Export > PDF). Save the report as `powerbi/nitrogen_ops_dashboard.pbix` and screenshots in `reports/dashboard/`.
