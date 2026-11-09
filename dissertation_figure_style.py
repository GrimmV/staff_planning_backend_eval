"""Shared typography, configuration encoding and exports for Figures 8.7–8.9."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter

MODE_ORDER = ("full", "simple", "simple_direct")
MODE_LABELS = dict(zip(MODE_ORDER, ("Full evidence", "Condensed evidence", "Direct summary")))
MODE_COLORS = dict(zip(MODE_ORDER, ("#0072B2", "#E69F00", "#009E73")))
MODE_MARKERS = dict(zip(MODE_ORDER, ("o", "s", "^")))
WIDTH = 152 / 25.4


def apply_style():
    font = Path(__file__).parent / "assets/fonts/NotoSans-Regular.ttf"
    if font.exists():
        font_manager.fontManager.addfont(str(font))
    font_manager.findfont("Noto Sans", fallback_to_default=False)
    plt.rcParams.update({
        "font.family": "Noto Sans", "font.size": 9,
        "axes.labelsize": 9, "axes.titlesize": 10,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
        "text.color": "#333333", "axes.labelcolor": "#333333",
        "xtick.color": "#333333", "ytick.color": "#333333",
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "axes.facecolor": "white",
        "pdf.fonttype": 42, "svg.fonttype": "path",
    })


def percentage_axis(ax):
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.grid(axis="x", color="#dddddd", linewidth=0.5)
    ax.set_axisbelow(True)


def export_figure(fig, output_path, short_caption, caption, dpi=300):
    """Keep an exact 152 mm canvas; tight cropping would change final font sizes."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for extension in ("png", "pdf", "svg"):
        target = path.with_suffix("." + extension)
        fig.savefig(target, dpi=dpi, facecolor="white")
        artifacts["plot_" + extension] = target.as_posix()
    target = path.with_suffix(".caption.txt")
    target.write_text(f"List of Figures: {short_caption}\n\n{caption}\n", encoding="utf-8")
    artifacts["caption"] = target.as_posix()
    return artifacts
