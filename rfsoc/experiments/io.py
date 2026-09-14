"""Versioned persistence and plotting for RFSoC experiment results."""

from __future__ import annotations

import json
import os
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common.utils import experiment_data_root


FORMAT_VERSION = 1


def _next_stem(kind):
    day = time.strftime("%m%d%y")
    folder = os.path.join(experiment_data_root(), day, f"RFSoC_{kind}")
    os.makedirs(folder, exist_ok=True)
    existing = [
        name for name in os.listdir(folder)
        if name.startswith(day) and name.endswith(".npz")
    ]
    return os.path.join(folder, f"{day}{len(existing) + 1:03d}_{kind}")


def save_result(result):
    stem = _next_stem(result.kind)
    metadata = {
        "format_version": FORMAT_VERSION,
        "kind": result.kind,
        "x_name": result.x_name,
        "x_unit": result.x_unit,
        "requested": result.requested,
        "executed": result.executed,
        "fit": result.fit,
    }
    npz_path = stem + ".npz"
    np.savez_compressed(
        npz_path,
        x=result.x,
        signal_counts=result.signal_counts,
        reference_counts=result.reference_counts,
        signal_rate_cps=result.signal_rate_cps,
        reference_rate_cps=result.reference_rate_cps,
        contrast=result.contrast,
        metadata_json=json.dumps(metadata, default=float),
    )
    csv_path = stem + ".csv"
    pd.DataFrame(
        {
            f"{result.x_name}_{result.x_unit}": result.x,
            "Signal_counts": result.signal_counts,
            "Reference_counts": result.reference_counts,
            "Signal_cps": result.signal_rate_cps,
            "Reference_cps": result.reference_rate_cps,
            "Contrast": result.contrast,
        }
    ).to_csv(csv_path, index=False)
    result.saved_files.update(npz=npz_path, csv=csv_path)
    return result


def plot_result(result, save=True, show=True):
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 7))
    axes[0].plot(result.x, result.reference_rate_cps, label="reference")
    axes[0].plot(result.x, result.signal_rate_cps, label="signal")
    axes[0].set_ylabel("Count rate (cps)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(result.x, result.contrast, "o-")
    axes[1].set_xlabel(f"{result.x_name} ({result.x_unit})")
    axes[1].set_ylabel("Signal/reference" if result.kind == "T1" else "Contrast")
    axes[1].grid(True, alpha=0.3)
    fig.suptitle(f"RFSoC4x2 {result.kind}")
    fig.tight_layout()
    if save:
        if not result.saved_files:
            save_result(result)
        pdf_path = os.path.splitext(result.saved_files["npz"])[0] + ".pdf"
        fig.savefig(pdf_path)
        result.saved_files["pdf"] = pdf_path
    if show:
        plt.show()
    else:
        plt.close(fig)
    return result
