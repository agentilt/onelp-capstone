"""Shared matplotlib styling so every figure across the three deliverables
matches the OneLP brand register (deep slate + teal accent)."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager  # noqa: F401

# OneLP palette
INK = "#0f172a"        # slate-900
SLATE = "#334155"      # slate-700
TEAL = "#0d9488"       # teal-600
TEAL_LT = "#5eead4"    # teal-300
AMBER = "#d97706"      # amber-600
RED = "#dc2626"        # red-600
GREEN = "#16a34a"      # green-600
GRID = "#e2e8f0"       # slate-200
MUTED = "#64748b"      # slate-500


def apply_style():
    plt.rcParams.update({
        "text.parse_math": False,   # treat '$' literally (dollar amounts in titles)
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": SLATE,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 13,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": SLATE,
        "ytick.color": SLATE,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.frameon": False,
        "legend.fontsize": 11,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "figure.dpi": 130,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })


def savefig(fig, path):
    fig.savefig(path)
    plt.close(fig)
    return path
