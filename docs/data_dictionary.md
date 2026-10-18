# Data dictionary

All tables are synthetic. Raw tables come from `src/generate_nitrogen_plant_data.py`; processed tables from notebooks 04 and 05.

## Instrument tags

Tag numbers follow the ISA-5.1 letter convention. The first digit is the package: 1 for NGU-A, 2 for NGU-B, 3 for NGU-C. So FI-101, FI-201 and FI-301 are the feed air flow meters on the three packages.

| Column | Tag (NGU-A) | Description | Unit | L | LL | H | HH |
|---|---|---|---|---|---|---|---|
| feed_air_flow_nm3h | FI-101 | Feed air flow to cold box | Nm3/h |  |  |  |  |
| feed_air_discharge_pressure_barg | PI-102 | Feed air compressor discharge pressure | barg | 8.8 |  | 10.2 |  |
| feed_air_discharge_temp_degC | TI-103 | Aftercooler outlet air temperature | degC |  |  | 46 | 52 |
| feed_air_compressor_power_kw | JI-104 | Feed air compressor motor power | kW |  |  |  |  |
| compressor_vibration_mm_s | VI-105 | Feed air compressor bearing housing vibration | mm/s |  |  | 7.1 | 11 |
| cooling_water_supply_temp_degC | TI-106 | Cooling water supply temperature | degC |  |  | 35 |  |
| ppu_outlet_co2_ppm | AI-107 | PPU outlet CO2 | ppm |  |  | 1 | 2 |
| ppu_outlet_dewpoint_degC | AI-108 | PPU outlet dew point | degC |  |  | -60 | -50 |
| coldbox_temp_degC | TI-109 | Main exchanger cold end temperature | degC |  |  | -168 |  |
| coldbox_dp_kpa | PDI-110 | Main exchanger pressure drop | kPa |  |  | 13.5 | 15 |
| expander_speed_rpm | SI-111 | Turbo-expander speed | rpm | 25500 |  | 28500 |  |
| expander_bearing_temp_degC | TI-112 | Turbo-expander bearing temperature | degC |  |  | 72 | 82 |
| expander_vibration_um | VI-113 | Turbo-expander shaft vibration | um |  |  | 40 | 60 |
| product_n2_flow_nm3h | FIC-114 | Product N2 to plant header | Nm3/h |  |  |  |  |
| n2_vented_nm3h | FI-117 | Off-spec N2 vented to atmosphere | Nm3/h |  |  |  |  |
| product_n2_pressure_barg | PIC-115 | Product N2 pressure | barg | 6.3 | 6 |  |  |
| o2_content_ppm | AI-116 | O2 in product N2 | ppm |  |  | 5 | 10 |
| lin_tank_level_pct | LI-901 | LIN storage tank level | % |  |  |  |  |
| lin_vaporised_nm3h | FI-902 | LIN vaporiser outlet to header | Nm3/h |  |  |  |  |
| n2_demand_nm3h | FI-903 | N2 header flow to ammonia and urea plants | Nm3/h |  |  |  |  |

## Raw tables (data/raw)

### hourly_process_data

One row per package per hour, 52,560 rows. Columns are the tags above plus timestamp, package_id, operating_state and ambient_temp_degC. About 0.3% of rows have historian gaps (blank values). The O2 analyser reads exactly 0.00 then 8.00 ppm for an hour each during the monthly calibration.

### hourly_plant_data

One row per hour for the N2 header and LIN tank.

| Column | Description |
|---|---|
| timestamp | Hour start (historian hourly average) |
| n2_demand_nm3h | N2 drawn by ammonia and urea plants |
| n2_from_packages_nm3h | On-spec N2 from all packages |
| lin_vaporised_nm3h | LIN vaporised into the header |
| lin_tank_level_pct | LIN storage tank level |
| lin_tanker_delivered_nm3 | LIN road tanker delivery, gas equivalent |
| n2_shortfall_nm3h | Demand not met by packages or LIN |

### downtime_events

Maintenance log, one row per stop.

| Column | Description |
|---|---|
| event_id | Maintenance log ID |
| package_id | NGU-A, NGU-B or NGU-C |
| trip_time | Hour the package stopped |
| restart_time | Hour the package restarted (startup begins) |
| downtime_h | Hours stopped |
| startup_h | Hours from restart to steady running |
| event_type | Planned or Unplanned |
| cause_category | Mechanical, Process, Electrical, Utility or Planned |
| failure_mode | Specific failure mode |
| description | Plain-language description |

### process_alarms

One row per alarm activation (the hour a signal first crosses into an alarm band while running).

| Column | Description |
|---|---|
| alarm_id | Alarm ID |
| timestamp | Hour start (historian hourly average) |
| package_id | NGU-A, NGU-B or NGU-C |
| tag | ISA-style instrument tag |
| parameter | Column name of the alarmed signal |
| description | Plain-language description |
| alarm_type | H, HH, L or LL |
| value | Value when the alarm activated |
| alarm_limit | Alarm setpoint |
| unit | Engineering unit |
| hours_to_next_unplanned_trip | Hours until the next unplanned trip on the same package |
| preceding_downtime_event | True if an unplanned trip followed within 48 h |

### operator_log

Shift log entries where the crew caught a developing fault before it tripped the package.

| Column | Description |
|---|---|
| log_id | Shift log ID |
| timestamp | Hour start (historian hourly average) |
| package_id | NGU-A, NGU-B or NGU-C |
| system | Equipment group |
| failure_mode | Specific failure mode |
| entry | Shift log text |
| fault_start | When the fault began to develop |
| fault_cleared | When signals were back to normal |

### daily_package_summary

One row per package per day.

| Column | Description |
|---|---|
| date | Calendar day |
| package_id | NGU-A, NGU-B or NGU-C |
| running_hours | Hours in RUN or STARTUP |
| producing_hours | Hours with on-spec N2 to header |
| planned_downtime_hrs | Hours in planned stop |
| unplanned_downtime_hrs | Hours in unplanned stop |
| n2_production_nm3 | On-spec N2 to header |
| n2_vented_nm3 | Off-spec N2 vented |
| power_consumption_kwh | Feed air compressor energy |
| avg_o2_ppm | Mean product O2 while running |
| max_o2_ppm | Max product O2 while running |
| avg_cooling_water_temp_degC | Mean cooling water supply temperature |
| downtime_cause | Cause category of unplanned downtime that day, or None |
| failure_mode | Specific failure mode |
| availability_pct | Running hours / (24 - planned hours) |
| performance_pct | Total N2 made / (1,000 Nm3/h x running hours) |
| quality_pct | On-spec N2 / total N2 made |
| oee_pct | Availability x performance x quality |
| energy_intensity_kwh_per_nm3 | Compressor kWh per Nm3 on-spec N2 |

### daily_plant_summary

One row per day for the whole unit.

| Column | Description |
|---|---|
| date | Calendar day |
| total_n2_production_nm3 | On-spec N2, all packages |
| total_power_kwh | Compressor energy, all packages |
| total_unplanned_downtime_hrs | Unplanned hours, all packages |
| total_planned_downtime_hrs | Planned hours, all packages |
| packages_with_unplanned_downtime | Packages with any unplanned downtime that day |
| energy_intensity_kwh_per_nm3 | Compressor kWh per Nm3 on-spec N2 |
| n2_demand_nm3 | Daily N2 demand |
| lin_vaporised_nm3 | Daily LIN vaporised |
| lin_tank_level_min_pct | Lowest LIN tank level that day |
| lin_tanker_deliveries | Tanker deliveries that day |
| n2_shortfall_nm3 | Daily N2 not delivered |
| n2_shortfall_hours | Hours with any shortfall |

### instrument_tags

Tag list with alarm limits for all three packages.

| Column | Description |
|---|---|
| tag | ISA-style instrument tag |
| package_id | NGU-A, NGU-B or NGU-C |
| column | Column name in hourly_process_data |
| description | Plain-language description |
| unit | Engineering unit |
| alarm_l | Low alarm |
| alarm_ll | Low-low alarm |
| alarm_h | High alarm |
| alarm_hh | High-high alarm |

## Processed tables (data/processed)

| Table | Grain | Notes |
|---|---|---|
| dim_date | day | year, quarter, month_start, month_name, month_sort, season (Dry Nov to Mar, Rainy Apr to Oct), dataset_period (Train, Validation, Test) |
| dim_package | package | tag series, design rate, turnaround month |
| fact_daily_package | package x day | daily_package_summary plus max_risk_ratio, alert_hours, risk_level, n2_production_knm3, power_consumption_mwh |
| fact_monthly_package | package x month | sums plus availability, performance, quality, OEE, energy intensity, unplanned_trips |
| fact_downtime_events | stop | downtime_events plus date and onset (Gradual, Sudden, Planned) |
| fact_daily_plant | day | same as daily_plant_summary |
| fact_anomaly_daily | package x day | max_risk_ratio (above 1.0 is anomalous), alert_hours, flagged_system, risk_level (High: alert fired; Medium: score crossed 1.0 without persisting; Low), period |
| fact_alert_episodes | alert | start, end, package, system flagged, peak_ratio, outcome (Warned before trip, Fault caught by crew, False alarm), duration_h |
| test_trip_evaluation | trip | test-period trips with caught flag, model lead time and first DCS alarm lead time |
