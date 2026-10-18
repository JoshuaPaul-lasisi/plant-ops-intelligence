"""Shared paths, colours and chart style for the notebooks."""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"

# Colour follows the package everywhere. The first three slots of the palette
# stay distinguishable for colour-blind readers in every pairing.
PACKAGE_COLOURS = {"NGU-A": "#2a78d6", "NGU-B": "#eb6834", "NGU-C": "#1baf7a"}
CAUSE_COLOURS = {"Mechanical": "#2a78d6", "Process": "#eb6834", "Electrical": "#1baf7a",
                 "Utility": "#eda100", "Planned": "#a3a29c"}
ALERT = "#d03b3b"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"

SPLIT_VALID = pd.Timestamp("2025-10-01")
SPLIT_TEST = pd.Timestamp("2026-02-01")


def apply_style():
    mpl.rcParams.update({
        "figure.figsize": (10, 4.2),
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": INK_2,
        "axes.edgecolor": GRID,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "lines.linewidth": 1.6,
        "legend.frameon": False,
        "text.color": INK,
    })


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png")


def load(name, **kw):
    """Read a raw table, parsing any time columns."""
    df = pd.read_csv(RAW / f"{name}.csv", **kw)
    for c in df.columns:
        if c in ("timestamp", "date") or c.endswith("_time") or c.startswith("fault_"):
            df[c] = pd.to_datetime(df[c])
    return df

MODE_NAMES = {
    "compressor_vibration": "Compressor vibration",
    "ppu_breakthrough": "PPU breakthrough",
    "expander_bearing": "Expander bearing",
    "grid_dip": "Grid power dip",
    "motor_trip": "Motor relay trip",
    "cw_loss": "Cooling water loss",
    "coupling_failure": "Coupling failure",
    "valve_failure": "PPU valve failure",
}
