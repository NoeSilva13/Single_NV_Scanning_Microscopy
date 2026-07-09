"""
plot_scan.py
------------
Publication-quality heatmap for live confocal scan results.

Thread-safe: uses Figure + FigureCanvasAgg only — no pyplot global state,
safe to call from a background acquisition thread.
"""

import numpy as np
import matplotlib
import matplotlib.ticker as ticker
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import Normalize
from pathlib import Path

from utils import calculate_scale

# ── Style (mirrors nv_style.py) ───────────────────────────────────────────────
matplotlib.rcParams.update({
    "font.family":          "serif",
    "font.size":            8,
    "axes.labelsize":       8,
    "axes.titlesize":       8,
    "xtick.labelsize":      7,
    "ytick.labelsize":      7,
    "legend.fontsize":      7,
    "axes.linewidth":       0.8,
    "xtick.direction":      "in",
    "ytick.direction":      "in",
    "xtick.major.width":    0.8,
    "ytick.major.width":    0.8,
    "xtick.minor.width":    0.5,
    "ytick.minor.width":    0.5,
    "xtick.major.size":     3.0,
    "ytick.major.size":     3.0,
    "xtick.minor.size":     1.5,
    "ytick.minor.size":     1.5,
    "lines.linewidth":      1.2,
    "savefig.dpi":          300,
    "savefig.bbox":         "tight",
    "savefig.pad_inches":   0.02,
})

# Figure dimensions: single-column width (inches) and aspect ratio for images
_W1     = 3.5
_ASPECT = 1.1   # height = width × aspect

# ── Display range ─────────────────────────────────────────────────────────────
VMIN_PCT = 1    # lower percentile for color clipping (robust vs. hot pixels)
VMAX_PCT = 99   # upper percentile

# ── Colorbar label ────────────────────────────────────────────────────────────
CBLABEL = "SPD counts"


def plot_scan_results(scan_data: dict, save_path: str | Path, *,
                      title: str = "Confocal scan",
                      show_title: bool = False,
                      show_scalebar: bool = True) -> Path:
    """
    Save a 2D confocal scan as a publication-quality PNG.

    Thread-safe: uses Figure + FigureCanvasAgg — no pyplot global state.

    Args:
        scan_data:      dict with keys ``x_points``, ``y_points``, ``image``
                        x_points / y_points : 1D arrays of galvo voltages (V)
                        image               : 2D array (ny, nx) in raw counts.
                        Row 0 of image must correspond to the smallest y value.
        save_path:      output path — extension is replaced with .png / .pdf
        title:          figure title (shown only when show_title is True)
        show_title:     set to False for publication panels
        show_scalebar:  draw a white scale bar on the image

    Returns:
        Path to the saved PNG.
    """
    save_path = Path(save_path)

    x_grid = np.asarray(scan_data["x_points"])   # 1D, volts
    y_grid = np.asarray(scan_data["y_points"])   # 1D, volts
    image  = np.asarray(scan_data["image"])       # 2D (ny, nx), counts

    # ── Galvo voltage → physical coordinates (µm) ─────────────────────────────
    # calculate_scale(v_start, v_end, 1) returns the total FOV in µm.
    scan_width_um  = float(calculate_scale(x_grid[0], x_grid[-1], 1))
    scan_height_um = float(calculate_scale(y_grid[0], y_grid[-1], 1))
    x_range = (0.0, scan_width_um)
    y_range = (0.0, scan_height_um)

    print(f"[scan] image {image.shape}  "
          f"FOV: {scan_width_um:.2f} × {scan_height_um:.2f} µm  "
          f"counts: {image.min():.0f} – {image.max():.0f}")

    # ── Color range (percentile clip) ─────────────────────────────────────────
    vmin = float(np.percentile(image, VMIN_PCT))
    vmax = float(np.percentile(image, VMAX_PCT))
    print(f"[display] {VMIN_PCT}th={vmin:.3g} – {VMAX_PCT}th={vmax:.3g} counts")

    # ── Figure ────────────────────────────────────────────────────────────────
    fig = Figure(figsize=(_W1, _W1 * _ASPECT))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    extent = [x_range[0], x_range[1], y_range[0], y_range[1]]
    im = ax.imshow(
        image,
        extent=extent,
        origin="lower",
        cmap="inferno",
        norm=Normalize(vmin=vmin, vmax=vmax),
        aspect="equal",
        interpolation="nearest",
        rasterized=True,
    )

    # ── Colorbar ──────────────────────────────────────────────────────────────
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(CBLABEL, fontsize=7)
    cb.ax.tick_params(labelsize=6)

    # ── Axes style ────────────────────────────────────────────────────────────
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    ax.tick_params(which="both", direction="out", top=False, right=False)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())

    ax.set_xlabel(r"$x$ ($\mu$m)")
    ax.set_ylabel(r"$y$ ($\mu$m)")
    if show_title:
        ax.set_title(title)

    # ── Scale bar (~20 % of FOV, bottom-left corner) ──────────────────────────
    if show_scalebar:
        scale_len = round(scan_width_um / 5)
        pad       = scan_width_um * 0.08
        x0 = x_range[0] + pad
        y0 = y_range[0] + pad
        ax.plot([x0, x0 + scale_len], [y0, y0],
                "-", color="white", linewidth=1.8, solid_capstyle="butt")
        ax.text(x0 + scale_len / 2, y0 + scan_width_um * 0.04,
                fr"${scale_len}\,\mu$m",
                ha="center", va="bottom", color="white", fontsize=6)

    # ── Save ──────────────────────────────────────────────────────────────────
    save_path.parent.mkdir(parents=True, exist_ok=True)
    png_path = save_path.with_suffix(".png")
    # pdf_path = save_path.with_suffix(".pdf")
    fig.savefig(png_path, format="png", dpi=300, bbox_inches="tight", pad_inches=0.02)
    # fig.savefig(pdf_path, format="pdf",          bbox_inches="tight", pad_inches=0.02)
    print(f"[saved] {png_path.name}")
    return png_path
