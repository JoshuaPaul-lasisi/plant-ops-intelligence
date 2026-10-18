"""
Synthetic process data for the nitrogen generation unit (NGU) of a fertiliser complex.

Fictional operator: NitroChem Process Industries Limited, Port Harcourt.

DATA DISCLAIMER
All data produced by this script is synthetic. No proprietary or confidential
operational data from any employer or facility was used. Operating ranges are
typical published values for small cryogenic nitrogen generators, instrument
tags follow the generic ISA-5.1 letter convention, and the fault scenarios are
modelled on failure modes described in open process engineering literature.
The fault-injection approach follows the idea behind the Tennessee Eastman
Process benchmark (Downs and Vogel, 1993): a known fault with a known start
time, so that a detection method can be scored against ground truth.

The unit has three identical cryogenic packages (NGU-A, NGU-B, NGU-C). Each one
has a feed air compressor, a pre-purification unit (PPU) with molecular sieve
adsorbers, a cold box with main heat exchanger and distillation column, and a
turbo-expander for refrigeration. A liquid nitrogen (LIN) storage tank with
vaporisers backs up the plant header when packages are down.

Outputs (written to --out, default data/raw):
    hourly_process_data.csv    one row per package per hour (historian averages)
    hourly_plant_data.csv      one row per hour: demand, LIN tank, shortfall
    downtime_events.csv        maintenance log: planned and unplanned stops
    process_alarms.csv         alarm activations (rising edge into H/HH or L/LL)
    operator_log.csv           shift log: faults caught by operators before a trip
    daily_package_summary.csv  one row per package per day, with OEE
    daily_plant_summary.csv    one row per day for the whole unit
    instrument_tags.csv        tag list and alarm limits

Usage:
    python src/generate_nitrogen_plant_data.py --seed 42 --out data/raw
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

COMPANY = "NitroChem Process Industries Limited, Port Harcourt (fictional)"
START = pd.Timestamp("2024-10-01 00:00")
DAYS = 730
N_HOURS = DAYS * 24

DESIGN_N2_NM3H = 1000.0        # design product rate per package
AIR_TO_N2_RATIO = 1.96         # feed air per unit of product N2
SPECIFIC_AIR_POWER = 0.158     # kWh per Nm3 of feed air at design conditions
PLANT_DEMAND_NM3H = 2700.0     # ammonia and urea plants: purge, blanketing, seal gas
LIN_CAPACITY_NM3 = 138_000.0   # 200 m3 LIN tank, expressed as gas equivalent
LIN_MAKE_NM3H = 20.0           # liquid make per running package
TANKER_NM3 = 17_200.0          # one 20 t LIN road tanker
O2_PRODUCT_SPEC_PPM = 10.0     # above this the product is vented, not sent to header

PACKAGES = {
    # NGU-C is the oldest package: worse compressor efficiency, faster
    # intercooler fouling, more mechanical trips.
    "NGU-A": dict(tag_no=1, trips_per_year=8.0, efficiency_penalty=0.000, fouling_per_year=0.030,
                  comp_vib_base=2.3, exp_vib_base=14.0, bearing_base=54.0, turnaround="2025-01-13",
                  mode_weights=dict(expander_bearing=0.22, compressor_vibration=0.18, ppu_breakthrough=0.22,
                                    cw_loss=0.08, motor_trip=0.14, coupling_failure=0.06, valve_failure=0.10)),
    "NGU-B": dict(tag_no=2, trips_per_year=8.0, efficiency_penalty=0.010, fouling_per_year=0.035,
                  comp_vib_base=2.5, exp_vib_base=15.0, bearing_base=55.0, turnaround="2025-04-07",
                  mode_weights=dict(expander_bearing=0.22, compressor_vibration=0.18, ppu_breakthrough=0.22,
                                    cw_loss=0.08, motor_trip=0.14, coupling_failure=0.06, valve_failure=0.10)),
    "NGU-C": dict(tag_no=3, trips_per_year=12.0, efficiency_penalty=0.055, fouling_per_year=0.085,
                  comp_vib_base=3.1, exp_vib_base=18.0, bearing_base=57.5, turnaround="2025-07-07",
                  mode_weights=dict(expander_bearing=0.22, compressor_vibration=0.26, ppu_breakthrough=0.18,
                                    cw_loss=0.06, motor_trip=0.10, coupling_failure=0.08, valve_failure=0.10)),
}

FAILURE_MODES = {
    "expander_bearing": dict(category="Mechanical", description="Turbo-expander bearing degradation, trip on high shaft vibration",
                             precursor_h=(10, 96), repair_h=(14, 40), exponent=2.2),
    "compressor_vibration": dict(category="Mechanical", description="Feed air compressor high vibration trip",
                                 precursor_h=(6, 96), repair_h=(18, 60), exponent=2.0),
    "ppu_breakthrough": dict(category="Process", description="PPU molecular sieve CO2 breakthrough, product off-spec on O2",
                             precursor_h=(4, 20), repair_h=(16, 40), exponent=2.0),
    "cw_loss": dict(category="Utility", description="Cooling water flow loss to aftercooler, trip on high air temperature",
                    precursor_h=(3, 8), repair_h=(3, 10), exponent=1.5),
    "coupling_failure": dict(category="Mechanical", description="Compressor coupling failure, sudden",
                             precursor_h=(0, 0), repair_h=(24, 72), exponent=1.0),
    "valve_failure": dict(category="Process", description="PPU switching valve failed to stroke, feed air pressure dip",
                          precursor_h=(0, 0), repair_h=(4, 12), exponent=1.0),
    "motor_trip": dict(category="Electrical", description="Compressor motor protection relay trip",
                       precursor_h=(0, 0), repair_h=(2, 8), exponent=1.0),
    "grid_dip": dict(category="Electrical", description="Plant power supply dip, all running packages tripped",
                     precursor_h=(0, 0), repair_h=(3, 8), exponent=1.0),
}

# column: (tag pattern, description, unit, low alarm, low-low, high alarm, high-high)
TAGS = {
    "feed_air_flow_nm3h": ("FI-{n}01", "Feed air flow to cold box", "Nm3/h", None, None, None, None),
    "feed_air_discharge_pressure_barg": ("PI-{n}02", "Feed air compressor discharge pressure", "barg", 8.8, None, 10.2, None),
    "feed_air_discharge_temp_degC": ("TI-{n}03", "Aftercooler outlet air temperature", "degC", None, None, 46.0, 52.0),
    "feed_air_compressor_power_kw": ("JI-{n}04", "Feed air compressor motor power", "kW", None, None, None, None),
    "compressor_vibration_mm_s": ("VI-{n}05", "Feed air compressor bearing housing vibration", "mm/s", None, None, 7.1, 11.0),
    "cooling_water_supply_temp_degC": ("TI-{n}06", "Cooling water supply temperature", "degC", None, None, 35.0, None),
    "ppu_outlet_co2_ppm": ("AI-{n}07", "PPU outlet CO2", "ppm", None, None, 1.0, 2.0),
    "ppu_outlet_dewpoint_degC": ("AI-{n}08", "PPU outlet dew point", "degC", None, None, -60.0, -50.0),
    "coldbox_temp_degC": ("TI-{n}09", "Main exchanger cold end temperature", "degC", None, None, -168.0, None),
    "coldbox_dp_kpa": ("PDI-{n}10", "Main exchanger pressure drop", "kPa", None, None, 13.5, 15.0),
    "expander_speed_rpm": ("SI-{n}11", "Turbo-expander speed", "rpm", 25500.0, None, 28500.0, None),
    "expander_bearing_temp_degC": ("TI-{n}12", "Turbo-expander bearing temperature", "degC", None, None, 72.0, 82.0),
    "expander_vibration_um": ("VI-{n}13", "Turbo-expander shaft vibration", "um", None, None, 40.0, 60.0),
    "product_n2_flow_nm3h": ("FIC-{n}14", "Product N2 to plant header", "Nm3/h", None, None, None, None),
    "n2_vented_nm3h": ("FI-{n}17", "Off-spec N2 vented to atmosphere", "Nm3/h", None, None, None, None),
    "product_n2_pressure_barg": ("PIC-{n}15", "Product N2 pressure", "barg", 6.3, 6.0, None, None),
    "o2_content_ppm": ("AI-{n}16", "O2 in product N2", "ppm", None, None, 5.0, 10.0),
}
PLANT_TAGS = {
    "lin_tank_level_pct": ("LI-901", "LIN storage tank level", "%"),
    "lin_vaporised_nm3h": ("FI-902", "LIN vaporiser outlet to header", "Nm3/h"),
    "n2_demand_nm3h": ("FI-903", "N2 header flow to ammonia and urea plants", "Nm3/h"),
}


def ar1(n, phi, sigma, rng):
    """AR(1) noise with stationary standard deviation sigma."""
    e = rng.normal(0.0, sigma * np.sqrt(1 - phi ** 2), n)
    x = np.empty(n)
    x[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def hour_index(ts):
    return int((pd.Timestamp(ts) - START) / pd.Timedelta(hours=1))


def weather(rng, hours):
    """Port Harcourt ambient and cooling water supply temperatures.

    Dry season (Nov to Mar) runs hotter, the rains (Jun to Sep) run cooler.
    """
    doy = hours.dayofyear.to_numpy()
    hod = hours.hour.to_numpy()
    seasonal = 1.6 * np.cos(2 * np.pi * (doy - 60) / 365.25)
    diurnal = 3.8 * np.sin(2 * np.pi * (hod - 9) / 24)
    ambient = 27.0 + seasonal + diurnal + ar1(len(hours), 0.97, 0.9, rng)
    cw = 29.5 + 0.55 * (ambient - 27.0) + ar1(len(hours), 0.995, 0.5, rng)
    return ambient, cw


def schedule_events(rng):
    """Build the maintenance log: planned stops, package trips, plant-wide dips, near misses."""
    blocked = {p: np.zeros(N_HOURS, dtype=bool) for p in PACKAGES}
    events = []

    def block(pkg, a, b):
        blocked[pkg][max(a, 0):min(b, N_HOURS)] = True

    def free(pkg, a, b):
        return a >= 0 and b <= N_HOURS and not blocked[pkg][a:b].any()

    # Planned: 5-day annual turnaround (intercooler clean, cold box derime) and
    # a 10-hour quarterly expander inspection.
    for pkg, cfg in PACKAGES.items():
        for year_shift in (0, 1):
            t = hour_index(pd.Timestamp(cfg["turnaround"]) + pd.DateOffset(years=year_shift)) + 8
            events.append(dict(package_id=pkg, start_h=t, down_h=120, kind="Planned", mode="turnaround",
                               precursor_h=0))
            block(pkg, t - 24 * 5, t + 120 + 24 * 6)
        for q in range(8):
            t = hour_index(pd.Timestamp(cfg["turnaround"])) + (q - 1) * 91 * 24 + 45 * 24 + 8
            if 0 < t < N_HOURS - 24 and free(pkg, t - 48, t + 36):
                events.append(dict(package_id=pkg, start_h=t, down_h=10, kind="Planned",
                                   mode="expander_inspection", precursor_h=0))
                block(pkg, t - 48, t + 36)

    # Plant-wide power dips, about 1.5 per year. Operators restart one package
    # at a time, so B and C come back 2 and 4 hours after A.
    n_dips = rng.poisson(1.5 * DAYS / 365)
    for _ in range(n_dips):
        for _attempt in range(500):
            t = int(rng.integers(300, N_HOURS - 100))
            if all(free(p, t - 24, t + 48) for p in PACKAGES):
                base = int(rng.integers(*FAILURE_MODES["grid_dip"]["repair_h"]))
                for k, pkg in enumerate(PACKAGES):
                    events.append(dict(package_id=pkg, start_h=t, down_h=base + 2 * k, kind="Unplanned",
                                       mode="grid_dip", precursor_h=0))
                    block(pkg, t - 72, t + 96)
                break

    # Package trips.
    for pkg, cfg in PACKAGES.items():
        modes = list(cfg["mode_weights"])
        weights = np.array([cfg["mode_weights"][m] for m in modes])
        n_trips = rng.poisson(cfg["trips_per_year"] * DAYS / 365)
        for _ in range(n_trips):
            mode = modes[rng.choice(len(modes), p=weights / weights.sum())]
            fm = FAILURE_MODES[mode]
            for _attempt in range(1000):
                pre = int(rng.integers(fm["precursor_h"][0], fm["precursor_h"][1] + 1))
                down = int(rng.integers(fm["repair_h"][0], fm["repair_h"][1] + 1))
                t = int(rng.integers(200, N_HOURS - 120))
                if free(pkg, t - pre - 72, t + down + 120):
                    events.append(dict(package_id=pkg, start_h=t, down_h=down, kind="Unplanned", mode=mode,
                                       precursor_h=pre))
                    block(pkg, t - pre - 72, t + down + 120)
                    break

    # Near misses: a fault starts to develop and operators catch it (early PPU
    # switchover, compressor unloaded, expander changed over to standby).
    # Nothing goes in the maintenance log, but the signals move.
    near_misses = []
    for pkg in PACKAGES:
        for _ in range(rng.poisson(3.0 * DAYS / 365)):
            mode = ["expander_bearing", "compressor_vibration", "ppu_breakthrough"][int(rng.integers(0, 3))]
            fm = FAILURE_MODES[mode]
            for _attempt in range(1000):
                up = int(rng.integers(fm["precursor_h"][0], fm["precursor_h"][1] + 1))
                recover = int(rng.integers(6, 24))
                t = int(rng.integers(200, N_HOURS - 200))
                if free(pkg, t, t + up + recover + 48):
                    near_misses.append(dict(package_id=pkg, start_h=t, up_h=up, recover_h=recover, mode=mode,
                                            peak=float(rng.uniform(0.35, 0.6))))
                    block(pkg, t, t + up + recover + 48)
                    break

    return events, near_misses


class Package:
    """Holds the hourly signal arrays for one package."""

    def __init__(self, pkg, cfg, ambient, cw, rng):
        n = N_HOURS
        self.pkg, self.cfg, self.rng = pkg, cfg, rng
        self.ambient = ambient
        self.state = np.array(["RUN"] * n, dtype=object)
        self.startup_progress = np.full(n, np.nan)
        self.cw = cw + rng.normal(0.0, 0.15) + ar1(n, 0.9, 0.12, rng)
        self.fouling = np.zeros(n)
        self.days_since_ta = np.zeros(n)
        self.sig = {}
        # severity overlays per mode, combined into the signals later
        self.sev = {m: np.zeros(n) for m in ("expander_bearing", "compressor_vibration", "ppu_breakthrough",
                                             "cw_loss")}

    def set_fouling(self, turnaround_hours):
        """Intercooler fouling and exchanger CO2 build-up, reset at each turnaround."""
        last = -365 * 24  # previous turnaround a year before the first one in range
        ta = sorted(turnaround_hours)
        k = 0
        for i in range(N_HOURS):
            while k < len(ta) and i >= ta[k]:
                last = ta[k]
                k += 1
            self.days_since_ta[i] = (i - last) / 24.0
        self.fouling = self.cfg["fouling_per_year"] * self.days_since_ta / 365.0


def build(seed=42):
    rng = np.random.default_rng(seed)
    hours = pd.date_range(START, periods=N_HOURS, freq="h")
    ambient, cw_plant = weather(rng, hours)
    events, near_misses = schedule_events(rng)

    pkgs = {p: Package(p, cfg, ambient, cw_plant, rng) for p, cfg in PACKAGES.items()}

    # Operating states.
    for ev in sorted(events, key=lambda e: e["start_h"]):
        pk = pkgs[ev["package_id"]]
        a, b = ev["start_h"], min(ev["start_h"] + ev["down_h"], N_HOURS)
        pk.state[a:b] = "DOWN_PLANNED" if ev["kind"] == "Planned" else "DOWN_UNPLANNED"
        # Cold box warms while down: slowly after a trip, faster during a
        # turnaround because it is deliberately derimed.
        tau = 30.0 if ev["mode"] == "turnaround" else 140.0
        warm = (27.0 + 172.5) * (1 - np.exp(-ev["down_h"] / tau))
        startup = int(np.clip(round(3 + 0.12 * warm), 3, 30))
        ev["startup_h"] = startup
        c = min(b + startup, N_HOURS)
        pk.state[b:c] = "STARTUP"
        pk.startup_progress[b:c] = (np.arange(c - b) + 1) / startup
        ev["coldbox_warm_by"] = warm
        if ev["precursor_h"] > 0:
            fm = FAILURE_MODES[ev["mode"]]
            pre = ev["precursor_h"]
            p = (np.arange(pre) + 1) / pre
            pk.sev[ev["mode"]][a - pre:a] = np.maximum(pk.sev[ev["mode"]][a - pre:a], p ** fm["exponent"])

    for nm in near_misses:
        pk = pkgs[nm["package_id"]]
        fm = FAILURE_MODES[nm["mode"]]
        up = nm["peak"] * ((np.arange(nm["up_h"]) + 1) / nm["up_h"]) ** fm["exponent"]
        down = nm["peak"] * (1 - (np.arange(nm["recover_h"]) + 1) / nm["recover_h"])
        prof = np.concatenate([up, down])
        a = nm["start_h"]
        pk.sev[nm["mode"]][a:a + len(prof)] = np.maximum(pk.sev[nm["mode"]][a:a + len(prof)], prof)

    for p, pk in pkgs.items():
        pk.set_fouling([e["start_h"] for e in events if e["package_id"] == p and e["mode"] == "turnaround"])

    # Load sharing: when a package is down the others push to their limit.
    running = np.stack([np.isin(pk.state, ["RUN", "STARTUP"]) for pk in pkgs.values()])
    n_running = running.sum(axis=0)
    demand = PLANT_DEMAND_NM3H + 40 * np.sin(2 * np.pi * hours.hour.to_numpy() / 24) + ar1(N_HOURS, 0.98, 35, rng)

    frames = []
    for p, pk in pkgs.items():
        frames.append(package_signals(pk, n_running, rng, hours))
    hourly = pd.concat(frames, ignore_index=True)

    plant = plant_balance(hourly, demand, hours, rng)
    downtime = downtime_log(events, hours)
    alarms = alarm_events(hourly, downtime)
    oplog = operator_log(near_misses, hours)
    daily_pkg = daily_package(hourly, downtime)
    daily_plant = daily_plant_summary(daily_pkg, plant)
    tags = tag_list()
    return dict(hourly_process_data=hourly, hourly_plant_data=plant, downtime_events=downtime,
                process_alarms=alarms, operator_log=oplog, daily_package_summary=daily_pkg, daily_plant_summary=daily_plant,
                instrument_tags=tags)


def package_signals(pk, n_running, rng, hours):
    n = N_HOURS
    cfg = pk.cfg
    s_eb, s_cv = pk.sev["expander_bearing"], pk.sev["compressor_vibration"]
    s_ppu, s_cw = pk.sev["ppu_breakthrough"], pk.sev["cw_loss"]

    load = 0.965 + ar1(n, 0.95, 0.006, rng)
    load = np.where(n_running == 2, 1.03 + ar1(n, 0.9, 0.004, rng), load)
    load = np.where(n_running <= 1, 1.045 + ar1(n, 0.9, 0.003, rng), load)

    # Steady running values.
    product = DESIGN_N2_NM3H * load * (1 + ar1(n, 0.8, 0.004, rng))
    product *= (1 - 0.06 * s_eb) * (1 - 0.02 * s_cv)
    feed_air = product * AIR_TO_N2_RATIO * (1 + ar1(n, 0.8, 0.004, rng)) * (1 + 0.05 * s_eb) * (1 - 0.01 * s_cv)
    pressure = 9.5 + 0.8 * (load - 0.965) + 0.25 * s_eb + ar1(n, 0.9, 0.03, rng)
    cw = pk.cw + 0.6 * s_cw
    power = SPECIFIC_AIR_POWER * feed_air * (1 + cfg["efficiency_penalty"] + pk.fouling + 0.008 * (cw - 30.0))
    power *= (1 + 0.10 * s_eb) * (1 + 0.12 * s_cv) * (1 + 0.05 * s_cw) * (1 + ar1(n, 0.7, 0.005, rng))
    disch_temp = cw + 8.0 + 60.0 * pk.fouling + 7.0 * s_cv + 18.0 * s_cw + ar1(n, 0.8, 0.35, rng)
    comp_vib = cfg["comp_vib_base"] + 9.0 * s_cv + 0.04 * pk.days_since_ta / 30 + np.abs(ar1(n, 0.85, 0.15, rng))

    cycle = (np.arange(n) % 4) / 4.0  # PPU adsorber switchover every 4 hours
    co2 = 0.15 + 0.08 * cycle ** 3 + 7.0 * s_ppu + np.abs(ar1(n, 0.6, 0.03, rng))
    dewpoint = -72.0 + 2.0 * cycle ** 3 + 30.0 * s_ppu + ar1(n, 0.8, 0.8, rng)
    coldbox_dp = 11.0 + 6.0 * (load - 0.965) + 1.0 * pk.days_since_ta / 365 + 4.0 * s_ppu ** 1.5 \
        + ar1(n, 0.9, 0.12, rng)
    coldbox_temp = -172.5 + 3.5 * s_eb + ar1(n, 0.9, 0.3, rng)
    exp_speed = 27000 + 900 * (load - 0.965) - 700 * s_eb + ar1(n, 0.7, 110, rng) * (1 + 3 * s_eb)
    bearing = cfg["bearing_base"] + 0.35 * (pk.ambient - 27.0) + 30.0 * s_eb + ar1(n, 0.85, 0.6, rng)
    exp_vib = cfg["exp_vib_base"] + 58.0 * s_eb + np.abs(ar1(n, 0.8, 1.2, rng))
    o2 = np.exp(np.log(2.0) + ar1(n, 0.9, 0.15, rng)) + 27.0 * np.clip((s_ppu - 0.55) / 0.45, 0, 1) ** 2
    prod_pressure = 6.75 + ar1(n, 0.9, 0.04, rng)

    # Startups: compressor at full load almost at once, product ramps, O2
    # falls from over-range and product is vented until it is on spec.
    st = pk.state == "STARTUP"
    q = np.nan_to_num(pk.startup_progress)
    o2 = np.where(st, 2.0 + 600.0 * np.exp(-7.0 * q), o2)
    product = np.where(st, product * np.clip(1.15 * q, 0.05, 1.0), product)
    feed_air = np.where(st, feed_air * (0.75 + 0.25 * q), feed_air)
    power = np.where(st, power * (0.88 + 0.12 * q), power)
    coldbox_temp = np.where(st, -172.5 + 60.0 * (1 - q) ** 2, coldbox_temp)
    exp_speed = np.where(st, exp_speed * np.clip(0.6 + 0.5 * q, 0, 1), exp_speed)

    # Shutdowns.
    dn = np.isin(pk.state, ["DOWN_PLANNED", "DOWN_UNPLANNED"])
    hrs_down = np.zeros(n)
    for i in range(1, n):
        hrs_down[i] = hrs_down[i - 1] + 1 if dn[i] else 0
    tau = np.where(pk.state == "DOWN_PLANNED", 30.0, 140.0)
    coldbox_temp = np.where(dn, pk.ambient - (pk.ambient + 172.5) * np.exp(-hrs_down / tau), coldbox_temp)
    zero_noise = np.abs(rng.normal(0, 0.3, n))
    for arr in (product, feed_air, power, exp_speed):
        arr[dn] = 0.0
    pressure = np.where(dn, 0.1 + 0.05 * zero_noise, pressure)
    disch_temp = np.where(dn, pk.ambient + 2.0, disch_temp)
    comp_vib = np.where(dn, 0.2 + 0.1 * zero_noise, comp_vib)
    co2 = np.where(dn, 0.0, co2)
    dewpoint = np.where(dn, -20.0 + 2 * zero_noise, dewpoint)
    coldbox_dp = np.where(dn, 0.2 * zero_noise, coldbox_dp)
    bearing = np.where(dn, pk.ambient + 4.0, bearing)
    exp_vib = np.where(dn, 1.0 + zero_noise, exp_vib)
    o2 = np.where(dn, 1000.0, o2)  # analyser over-range, no sample flow
    prod_pressure = np.where(dn, 0.3 + 0.1 * zero_noise, prod_pressure)

    vented = np.where(o2 > O2_PRODUCT_SPEC_PPM, product, 0.0)
    to_header = product - vented

    # Monthly O2 analyser calibration while running: zero gas then 8 ppm span gas.
    o2 = o2.copy()
    for month_start in pd.date_range(START, periods=DAYS // 30, freq="MS"):
        i = hour_index(month_start) + int(rng.integers(3 * 24, 25 * 24)) // 24 * 24 + 10
        if i + 1 < n and pk.state[i] == "RUN" and pk.state[i + 1] == "RUN":
            o2[i], o2[i + 1] = 0.0, 8.0

    df = pd.DataFrame({
        "timestamp": hours,
        "package_id": pk.pkg,
        "operating_state": pk.state,
        "ambient_temp_degC": pk.ambient,
        "cooling_water_supply_temp_degC": cw,
        "feed_air_flow_nm3h": feed_air,
        "feed_air_discharge_pressure_barg": pressure,
        "feed_air_discharge_temp_degC": disch_temp,
        "feed_air_compressor_power_kw": power,
        "compressor_vibration_mm_s": comp_vib,
        "ppu_outlet_co2_ppm": co2,
        "ppu_outlet_dewpoint_degC": dewpoint,
        "coldbox_temp_degC": coldbox_temp,
        "coldbox_dp_kpa": coldbox_dp,
        "expander_speed_rpm": exp_speed,
        "expander_bearing_temp_degC": bearing,
        "expander_vibration_um": exp_vib,
        "product_n2_flow_nm3h": to_header,
        "n2_vented_nm3h": vented,
        "product_n2_pressure_barg": prod_pressure,
        "o2_content_ppm": o2,
    })

    # Historian gaps: short communication losses, values missing.
    value_cols = df.columns[3:]
    n_gaps = int(rng.poisson(0.0015 * n))
    for _ in range(n_gaps):
        i = int(rng.integers(0, n - 3))
        df.loc[i:i + int(rng.integers(0, 3)), value_cols] = np.nan

    rounding = {"feed_air_flow_nm3h": 1, "feed_air_compressor_power_kw": 1, "product_n2_flow_nm3h": 1,
                "n2_vented_nm3h": 1, "expander_speed_rpm": 0, "ppu_outlet_co2_ppm": 3, "o2_content_ppm": 2}
    for c in value_cols:
        df[c] = df[c].round(rounding.get(c, 2))
    return df


def plant_balance(hourly, demand, hours, rng):
    """N2 header balance: packages first, then LIN vaporiser, then shortfall."""
    supply = hourly.pivot(index="timestamp", columns="package_id", values="product_n2_flow_nm3h").fillna(0.0)
    steady = hourly.pivot(index="timestamp", columns="package_id", values="operating_state").eq("RUN")
    gas = supply.sum(axis=1).to_numpy()
    lin_make = steady.sum(axis=1).to_numpy() * LIN_MAKE_NM3H

    level = np.empty(N_HOURS)
    vaporised = np.zeros(N_HOURS)
    shortfall = np.zeros(N_HOURS)
    delivered = np.zeros(N_HOURS)
    stock = 0.8 * LIN_CAPACITY_NM3
    arrivals = []
    for i in range(N_HOURS):
        stock += lin_make[i]
        while arrivals and arrivals[0] <= i:
            arrivals.pop(0)
            stock += TANKER_NM3
            delivered[i] += TANKER_NM3
        gap = demand[i] - gas[i]
        if gap > 0:
            usable = max(stock - 0.05 * LIN_CAPACITY_NM3, 0.0)  # 5% heel kept in the tank
            vaporised[i] = min(gap, usable, 2500.0)              # vaporiser capacity
            shortfall[i] = gap - vaporised[i]
            stock -= vaporised[i]
        stock = min(stock, LIN_CAPACITY_NM3)
        level[i] = 100.0 * stock / LIN_CAPACITY_NM3
        # Order tankers when the tank is below 40%. Road delivery takes 12 to 36 hours.
        if level[i] < 40.0 and len(arrivals) < 2:
            arrivals.append(i + int(rng.integers(12, 37)))
            arrivals.sort()
    return pd.DataFrame({
        "timestamp": hours,
        "n2_demand_nm3h": demand.round(1),
        "n2_from_packages_nm3h": gas.round(1),
        "lin_vaporised_nm3h": vaporised.round(1),
        "lin_tank_level_pct": level.round(2),
        "lin_tanker_delivered_nm3": delivered.round(0),
        "n2_shortfall_nm3h": shortfall.round(1),
    })


def downtime_log(events, hours):
    rows = []
    for ev in sorted(events, key=lambda e: (e["start_h"], e["package_id"])):
        start = hours[ev["start_h"]]
        end_h = min(ev["start_h"] + ev["down_h"], N_HOURS)
        if ev["mode"] in FAILURE_MODES:
            fm = FAILURE_MODES[ev["mode"]]
            cat, desc = fm["category"], fm["description"]
        elif ev["mode"] == "turnaround":
            cat, desc = "Planned", "Annual turnaround: intercooler clean, cold box derime, PPU inspection"
        else:
            cat, desc = "Planned", "Quarterly turbo-expander inspection"
        rows.append(dict(package_id=ev["package_id"], trip_time=start,
                         restart_time=START + pd.Timedelta(hours=end_h),
                         downtime_h=end_h - ev["start_h"], startup_h=ev["startup_h"],
                         event_type=ev["kind"], cause_category=cat, failure_mode=ev["mode"], description=desc))
    df = pd.DataFrame(rows).sort_values(["trip_time", "package_id"]).reset_index(drop=True)
    df.insert(0, "event_id", [f"DT-{i + 1:04d}" for i in range(len(df))])
    return df


INTERVENTIONS = {
    "expander_bearing": ("Expander", "Expander bearing temperature trending up. Changed over to standby expander."),
    "compressor_vibration": ("Compressor", "Compressor vibration rising. Load reduced, lube oil filter changed."),
    "ppu_breakthrough": ("PPU", "PPU outlet CO2 rising. Adsorber switched early, regeneration heater checked."),
}


def operator_log(near_misses, hours):
    """Shift log entries for near misses, written at the hour the crew acted."""
    rows = []
    for nm in near_misses:
        system, text = INTERVENTIONS[nm["mode"]]
        rows.append(dict(timestamp=hours[nm["start_h"] + nm["up_h"] - 1], package_id=nm["package_id"],
                         system=system, failure_mode=nm["mode"], entry=text,
                         fault_start=hours[nm["start_h"]],
                         fault_cleared=hours[min(nm["start_h"] + nm["up_h"] + nm["recover_h"], N_HOURS - 1)]))
    df = pd.DataFrame(rows).sort_values(["timestamp", "package_id"]).reset_index(drop=True)
    df.insert(0, "log_id", [f"OL-{i + 1:04d}" for i in range(len(df))])
    return df


def alarm_events(hourly, downtime):
    """Alarm activations: the hour a value first crosses into an alarm band."""
    trips = downtime[downtime.event_type == "Unplanned"]
    rows = []
    for col, (tag, desc, unit, lo, lolo, hi, hihi) in TAGS.items():
        for pkg, g in hourly.groupby("package_id"):
            run = g["operating_state"].eq("RUN").to_numpy()
            v = g[col].to_numpy()
            tagname = tag.format(n=PACKAGES[pkg]["tag_no"])
            for limit, kind, above in ((hihi, "HH", True), (hi, "H", True), (lolo, "LL", False), (lo, "L", False)):
                if limit is None:
                    continue
                with np.errstate(invalid="ignore"):
                    active = (v > limit) if above else (v < limit)
                active &= run
                rising = active & ~np.concatenate([[False], active[:-1]])
                for i in np.flatnonzero(rising):
                    rows.append(dict(timestamp=g["timestamp"].iloc[i], package_id=pkg, tag=tagname, parameter=col,
                                     description=desc, alarm_type=kind, value=v[i], alarm_limit=limit, unit=unit))
    al = pd.DataFrame(rows).sort_values(["timestamp", "package_id", "tag"]).reset_index(drop=True)

    al["hours_to_next_unplanned_trip"] = np.nan
    for pkg, t in trips.groupby("package_id"):
        tt = np.sort(t["trip_time"].to_numpy().astype("datetime64[h]"))
        m = al.package_id.eq(pkg)
        ts = al.loc[m, "timestamp"].to_numpy().astype("datetime64[h]")
        j = np.searchsorted(tt, ts, side="right")
        nxt = tt[np.minimum(j, len(tt) - 1)]
        hrs = (nxt - ts).astype(float)
        al.loc[m, "hours_to_next_unplanned_trip"] = np.where(j < len(tt), hrs, np.nan)
    al["preceding_downtime_event"] = al["hours_to_next_unplanned_trip"].le(48)
    al.insert(0, "alarm_id", [f"AL-{i + 1:05d}" for i in range(len(al))])
    return al


def daily_package(hourly, downtime):
    h = hourly.copy()
    h["date"] = h["timestamp"].dt.normalize()
    st = h["operating_state"]
    h["run_h"] = st.isin(["RUN", "STARTUP"]).astype(int)
    h["producing_h"] = (h["product_n2_flow_nm3h"].fillna(0) > 0).astype(int)
    h["planned_h"] = st.eq("DOWN_PLANNED").astype(int)
    h["unplanned_h"] = st.eq("DOWN_UNPLANNED").astype(int)
    # Historian gaps: fill flows and power from neighbours so daily totals hold.
    for c in ("product_n2_flow_nm3h", "n2_vented_nm3h", "feed_air_compressor_power_kw"):
        h[c] = h.groupby("package_id")[c].transform(lambda s: s.interpolate(limit_direction="both"))
    d = h.groupby(["date", "package_id"]).agg(
        running_hours=("run_h", "sum"),
        producing_hours=("producing_h", "sum"),
        planned_downtime_hrs=("planned_h", "sum"),
        unplanned_downtime_hrs=("unplanned_h", "sum"),
        n2_production_nm3=("product_n2_flow_nm3h", "sum"),
        n2_vented_nm3=("n2_vented_nm3h", "sum"),
        power_consumption_kwh=("feed_air_compressor_power_kw", "sum"),
        avg_o2_ppm=("o2_content_ppm", lambda s: s[s < 1000].mean()),
        max_o2_ppm=("o2_content_ppm", lambda s: s[s < 1000].max()),
        avg_cooling_water_temp_degC=("cooling_water_supply_temp_degC", "mean"),
    ).reset_index()

    d["downtime_cause"] = "None"
    d["failure_mode"] = "None"
    unpl = downtime[downtime.event_type == "Unplanned"]
    for _, ev in unpl.iterrows():
        days = pd.date_range(ev.trip_time.normalize(), (ev.restart_time - pd.Timedelta(hours=1)).normalize())
        m = d.package_id.eq(ev.package_id) & d.date.isin(days)
        d.loc[m, "downtime_cause"] = ev.cause_category
        d.loc[m, "failure_mode"] = ev.failure_mode

    available = 24 - d["planned_downtime_hrs"]
    d["availability_pct"] = np.where(available > 0, 100 * d["running_hours"] / available, np.nan)
    rated = DESIGN_N2_NM3H * d["running_hours"]
    total = d["n2_production_nm3"] + d["n2_vented_nm3"]
    d["performance_pct"] = np.where(rated > 0, 100 * total / rated, np.nan)
    d["quality_pct"] = np.where(total > 0, 100 * d["n2_production_nm3"] / total, np.nan)
    d["oee_pct"] = d["availability_pct"] * d["performance_pct"] * d["quality_pct"] / 1e4
    d["energy_intensity_kwh_per_nm3"] = np.where(d["n2_production_nm3"] > 0,
                                                 d["power_consumption_kwh"] / d["n2_production_nm3"], np.nan)
    num = d.select_dtypes("number").columns
    d[num] = d[num].round(3)
    return d


def daily_plant_summary(daily_pkg, plant):
    g = daily_pkg.groupby("date").agg(
        total_n2_production_nm3=("n2_production_nm3", "sum"),
        total_power_kwh=("power_consumption_kwh", "sum"),
        total_unplanned_downtime_hrs=("unplanned_downtime_hrs", "sum"),
        total_planned_downtime_hrs=("planned_downtime_hrs", "sum"),
        packages_with_unplanned_downtime=("unplanned_downtime_hrs", lambda s: int((s > 0).sum())),
    )
    g["energy_intensity_kwh_per_nm3"] = g["total_power_kwh"] / g["total_n2_production_nm3"]
    p = plant.copy()
    p["date"] = p["timestamp"].dt.normalize()
    pg = p.groupby("date").agg(
        n2_demand_nm3=("n2_demand_nm3h", "sum"),
        lin_vaporised_nm3=("lin_vaporised_nm3h", "sum"),
        lin_tank_level_min_pct=("lin_tank_level_pct", "min"),
        lin_tanker_deliveries=("lin_tanker_delivered_nm3", lambda s: int((s > 0).sum())),
        n2_shortfall_nm3=("n2_shortfall_nm3h", "sum"),
        n2_shortfall_hours=("n2_shortfall_nm3h", lambda s: int((s > 0).sum())),
    )
    out = g.join(pg).reset_index()
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(3)
    return out


def tag_list():
    rows = []
    for pkg, cfg in PACKAGES.items():
        for col, (tag, desc, unit, lo, lolo, hi, hihi) in TAGS.items():
            rows.append(dict(tag=tag.format(n=cfg["tag_no"]), package_id=pkg, column=col, description=desc,
                             unit=unit, alarm_l=lo, alarm_ll=lolo, alarm_h=hi, alarm_hh=hihi))
    for col, (tag, desc, unit) in PLANT_TAGS.items():
        rows.append(dict(tag=tag, package_id="PLANT", column=col, description=desc, unit=unit))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    tables = build(args.seed)
    for name, df in tables.items():
        df.to_csv(args.out / f"{name}.csv", index=False)
        print(f"{name:26s} {len(df):>7,d} rows")
    print(f"Written to {args.out} ({COMPANY})")


if __name__ == "__main__":
    main()
