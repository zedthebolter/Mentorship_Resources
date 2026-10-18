#!/usr/bin/env python3
"""Plot group profiles and model estimates from saved result tables."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


COLORS = {
    "topic_continuity": "#D84B5B",
    "network_consistency": "#2B82A4",
    "direct_percent": "#737E84",
    "log_PeerCount": "#8756B3",
}
LABELS = {
    "topic_continuity": "TC",
    "network_consistency": "NC",
    "direct_percent": "DP",
    "log_PeerCount": "PC",
}
LEGEND_LABELS = {
    "topic_continuity": "Topic_Continuity",
    "network_consistency": "Net_Consistency",
    "direct_percent": "Direct_Percent",
    "log_PeerCount": "PeerCount_log",
}
GROUPS = ["G1a", "G1b", "G2a", "G2b"]
GROUP_COLORS = {
    "G1a": "#A61C00",
    "G1b": "#F49D83",
    "G2a": "#1F4E79",
    "G2b": "#6FA8DC",
}
GROUP_LABELS = {
    "G1a": "G1a  Improved after graduation",
    "G1b": "G1b  Late bloomer",
    "G2a": "G2a  No increase after graduation",
    "G2b": "G2b  No citation-elite output in either period",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-dir", type=Path, default=root / "Results"
    )
    parser.add_argument("--figure2-dir", type=Path, default=root / "Results")
    parser.add_argument("--output-dir", type=Path, default=root / "Figure")
    return parser.parse_args()


def configure() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )


def save(fig: plt.Figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(output.with_suffix(".png").name)
    print(output.with_suffix(".pdf").name)


def make_group_figure(data_dir: Path, output: Path) -> None:
    summary = pd.read_csv(data_dir / "group_distribution_summary.csv")
    density = pd.read_csv(data_dir / "kde_density_curves.csv")
    variables = [
        ("Topic_Continuity", "Topic continuity\n(TC)"),
        ("Net_Consistency", "Network consistency\n(NC)"),
        ("Direct_Percent", "Direct mentor collaboration\n(DP)"),
        ("PeerCount_log", "Peer environment\n(PC)"),
    ]

    fig = plt.figure(figsize=(13.8, 8.6))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.08, 1], hspace=0.36, wspace=0.22)
    ax_bar = fig.add_subplot(grid[0, :])
    x = np.arange(len(variables))
    width = 0.18
    offsets = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]

    for group, offset in zip(GROUPS, offsets):
        means: list[float] = []
        errors: list[float] = []
        for variable, _ in variables:
            block = summary[summary["Variable"].eq(variable)].set_index("Group").reindex(GROUPS)
            scale = float(block["Mean"].std(ddof=1))
            means.append(float((block.loc[group, "Mean"] - block["Mean"].mean()) / scale))
            errors.append(float(1.96 * block.loc[group, "Std"] / math.sqrt(block.loc[group, "N"]) / scale))
        ax_bar.bar(
            x + offset,
            means,
            width=width * 0.9,
            yerr=errors,
            capsize=2.2,
            color=GROUP_COLORS[group],
            edgecolor="white",
            linewidth=0.5,
            label=GROUP_LABELS[group],
        )
    ax_bar.axhline(0, color="#555555", linewidth=1)
    ax_bar.grid(axis="y", linestyle="--", alpha=0.28)
    ax_bar.set_xticks(x, [label for _, label in variables])
    ax_bar.set_ylabel("Standardized group mean (z-score; 95% CI)")
    ax_bar.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.18), fontsize=11)
    ax_bar.text(-0.05, 1.06, "A", transform=ax_bar.transAxes, fontweight="bold", fontsize=15)

    for ax, panel, letter, xlabel in (
        (fig.add_subplot(grid[1, 0]), "network", "B", "log10(Network size + 1)"),
        (fig.add_subplot(grid[1, 1]), "hindex", "C", "log10(h-index + 1)"),
    ):
        curves = density[(density["Panel"].eq(panel)) & (density["Kind"].eq("curve"))]
        medians = density[(density["Panel"].eq(panel)) & (density["Kind"].eq("median"))]
        for group in GROUPS:
            curve = curves[curves["Group"].eq(group)].sort_values("Order")
            ax.plot(curve["X"], curve["Y"], color=GROUP_COLORS[group], linewidth=1.8)
            median = medians[medians["Group"].eq(group)]
            if not median.empty:
                ax.axvline(float(median.iloc[0]["X"]), color=GROUP_COLORS[group], linestyle="--", linewidth=1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Density")
        ax.grid(alpha=0.18)
        ax.text(-0.10, 1.04, letter, transform=ax.transAxes, fontweight="bold", fontsize=15)
    save(fig, output)


