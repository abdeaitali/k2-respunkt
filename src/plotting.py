"""Plot helpers that return Matplotlib objects and do not mutate input data."""

from __future__ import annotations

from collections.abc import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .utils import assign_time_period, clock_minutes, on_time_curve


def plot_OTP(
    otp: pd.DataFrame,
    periodicity: str = "all",
    *,
    thresholds_minutes: Sequence[float] = tuple(range(31)),
) -> tuple[plt.Figure, plt.Axes]:
    """Plot train OTP curves and return the figure for saving or further edits."""

    data = otp.copy()
    delay_column = "OTP_minutes" if "OTP_minutes" in data else "OTP_seconds"
    delays = data[delay_column] if delay_column == "OTP_minutes" else data[delay_column] / 60.0

    fig, ax = plt.subplots(figsize=(10, 6))
    if periodicity == "all":
        groups = {"All observed trains": data.index}
    elif periodicity == "day":
        date_column = "Datum (PAU)" if "Datum (PAU)" in data else "Datum"
        weekday = pd.to_datetime(data[date_column]).dt.day_name()
        groups = {
            label: data.index[weekday.eq(label)]
            for label in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }
    elif periodicity == "hour":
        periods = assign_time_period(clock_minutes(data["Ankomsttid"]))
        groups = {
            label: data.index[periods.eq(label)]
            for label in periods.dropna().drop_duplicates()
        }
    else:
        raise ValueError("periodicity must be 'all', 'day', or 'hour'")

    for label, index in groups.items():
        if len(index) == 0:
            continue
        scores = 100.0 * on_time_curve(delays.loc[index], thresholds_minutes)
        ax.plot(thresholds_minutes, scores, label=str(label))
    ax.set(
        xlabel="Delay threshold (minutes)",
        ylabel="On-time trains (%)",
        title="Train on-time performance",
        xlim=(min(thresholds_minutes), max(thresholds_minutes)),
        ylim=(0, 100.5),
    )
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig, ax


def plot_punctuality_curves(
    curves: pd.DataFrame,
    *,
    period: str = "All day",
) -> tuple[plt.Figure, plt.Axes]:
    """Plot the canonical OTP/PP2/CPM/PP2-C comparison."""

    selected = curves.loc[curves["period"].eq(period)]
    fig, ax = plt.subplots(figsize=(10, 6))
    styles = {
        "OTP": ("#0072B2", "-"),
        "PP2": ("#009E73", "-"),
        "CPM": ("#D55E00", "--"),
        "PP2-C": ("#CC79A7", "--"),
    }
    for metric, group in selected.groupby("metric", sort=False):
        color, linestyle = styles.get(metric, (None, "-"))
        ax.plot(
            group["threshold_minutes"],
            group["score"],
            label=metric,
            color=color,
            linestyle=linestyle,
            linewidth=2.2,
        )
    ax.set(
        xlabel="Delay threshold (minutes)",
        ylabel="Punctuality score (%)",
        title=f"Train and passenger punctuality - {period}",
        ylim=(0, 100.5),
    )
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig, ax


def plot_PP2(*_: object, **__: object) -> None:
    raise NotImplementedError(
        "Use plot_punctuality_curves with src.analysis.punctuality_curves."
    )

