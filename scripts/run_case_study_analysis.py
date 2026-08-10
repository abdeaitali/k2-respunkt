"""Reproduce, correct, and extend the report's Stockholm case-study analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr

from src.analysis import (
    add_service_period,
    build_passenger_journeys,
    cancellation_adjusted_od_metrics,
    expected_wait_table,
    journey_period_summary,
    od_metrics,
    period_definition_sensitivity,
    punctuality_curves,
    punctuality_summary,
)
from src.constants import STATIONS_SOUTH_TO_NORTH, TIME_PERIODS_MINUTES, TRAIN_KEYS
from src.reading_data import PROJECT_ROOT, get_onboard_data, get_traffic_data
from src.utils import assign_time_period, clock_minutes, weighted_quantile


PERIOD_ORDER = list(TIME_PERIODS_MINUTES)
METRIC_ORDER = ["OTP", "PP2", "CPM", "PP2-C"]
COLORS = {
    "OTP": "#0072B2",
    "PP2": "#009E73",
    "CPM": "#D55E00",
    "PP2-C": "#CC79A7",
    "Morning peak": "#D55E00",
    "Midday off-peak": "#009E73",
    "Afternoon peak": "#0072B2",
}


def _style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 180,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
        }
    )


def _save(fig: plt.Figure, output: Path) -> None:
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def data_quality_table(
    raw: pd.DataFrame,
    actual: pd.DataFrame,
    planned: pd.DataFrame,
) -> pd.DataFrame:
    raw_dates = pd.to_datetime(raw["Datum (PAU)"], errors="coerce")
    final_planned = planned.loc[planned["UppehallstypAnkomst"].eq("Sista")]
    final_actual = actual.loc[actual["UppehallstypAnkomst"].eq("Sista")]
    cancelled = final_planned["Planeringsstatus"].eq("I")
    observations = [
        ("Raw calendar days", raw_dates.dt.normalize().nunique(), "days"),
        ("Raw weekend days", raw_dates.loc[raw_dates.dt.dayofweek.ge(5)].dt.normalize().nunique(), "days"),
        ("Corrected workday cohort", actual["Datum"].nunique(), "days"),
        ("Planned terminal services", len(final_planned), "services"),
        ("Cancelled terminal services", int(cancelled.sum()), "services"),
        ("Terminal cancellation rate", 100.0 * cancelled.mean(), "percent"),
        ("Actual movements", len(actual), "movements"),
        ("Imputed movement arrivals", int(actual["arrival_time_imputed"].sum()), "movements"),
        (
            "Imputed movement-arrival rate",
            100.0 * actual["arrival_time_imputed"].mean(),
            "percent",
        ),
        ("Imputed terminal arrivals", int(final_actual["arrival_time_imputed"].sum()), "services"),
        ("Suspect arrivals (>10 min early)", int(actual["arrival_time_suspect"].sum()), "movements"),
        ("Assigned actual passengers", actual["n_alighting_next"].sum(), "passenger trips"),
        ("Assigned planned passengers", planned["n_alighting_next"].sum(), "passenger trips"),
    ]
    return pd.DataFrame(observations, columns=["measure", "value", "unit"])


def plot_data_quality(actual: pd.DataFrame, planned: pd.DataFrame) -> plt.Figure:
    final = planned.loc[planned["UppehallstypAnkomst"].eq("Sista")].copy()
    daily = final.groupby("Datum").agg(
        services=("Planeringsstatus", "size"),
        cancellations=("Planeringsstatus", lambda status: status.eq("I").sum()),
    )
    daily["cancellation_rate"] = 100.0 * daily["cancellations"] / daily["services"]
    imputation = (
        actual.groupby("Fran_platssignatur")["arrival_time_imputed"]
        .mean()
        .reindex(STATIONS_SOUTH_TO_NORTH)
        .mul(100.0)
    )

    fig, axes = plt.subplots(1, 2, figsize=(17, 6))
    axes[0].plot(daily.index, daily["cancellation_rate"], marker="o", color="#D55E00")
    axes[0].axhline(daily["cancellations"].sum() / daily["services"].sum() * 100, color="black", linestyle="--", linewidth=1.5)
    axes[0].set(title="Terminal-service cancellations by workday", ylabel="Cancelled services (%)", xlabel="Date")
    axes[0].tick_params(axis="x", rotation=45)

    axes[1].bar(np.arange(len(imputation)), imputation, color="#56B4E9")
    axes[1].set_xticks(np.arange(len(imputation)), imputation.index, rotation=60, ha="right")
    axes[1].set(title="Operational arrivals imputed for assignment", ylabel="Imputed movement arrivals (%)", xlabel="Departure station")
    fig.suptitle("Data coverage and preprocessing provenance", y=1.03)
    fig.tight_layout()
    return fig


def plot_curves(curves: pd.DataFrame) -> plt.Figure:
    panels = ["All day", *PERIOD_ORDER]
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharex=True, sharey=True)
    for ax, period in zip(axes.flat, panels, strict=True):
        selected = curves.loc[curves["period"].eq(period)]
        for metric in METRIC_ORDER:
            group = selected.loc[selected["metric"].eq(metric)]
            ax.plot(
                group["threshold_minutes"],
                group["score"],
                label=metric,
                color=COLORS[metric],
                linestyle="--" if metric in {"CPM", "PP2-C"} else "-",
                linewidth=2.2,
            )
        ax.axvline(3, color="0.35", linestyle=":", linewidth=1.5)
        ax.set_title(period)
        ax.set_xlim(0, 15)
        ax.set_ylim(55, 101)
        ax.set_xlabel("Delay threshold (minutes)")
        ax.set_ylabel("Punctuality score (%)")
    axes[0, 0].legend(ncol=2, loc="lower right")
    fig.suptitle("Corrected train and passenger punctuality curves", y=1.01)
    fig.tight_layout()
    return fig


def plot_metric_summary(summary: pd.DataFrame) -> plt.Figure:
    selected = summary.loc[summary["period"].isin(PERIOD_ORDER)].copy()
    fig, ax = plt.subplots(figsize=(14, 7))
    x = np.arange(len(PERIOD_ORDER))
    width = 0.19
    for position, metric in enumerate(METRIC_ORDER):
        group = selected.loc[selected["metric"].eq(metric)].set_index("period").reindex(PERIOD_ORDER)
        offset = (position - 1.5) * width
        errors = np.vstack(
            [group["score"] - group["ci_lower"], group["ci_upper"] - group["score"]]
        )
        bars = ax.bar(
            x + offset,
            group["score"],
            width,
            label=metric,
            color=COLORS[metric],
            yerr=errors,
            capsize=3,
        )
        ax.bar_label(bars, fmt="%.1f", fontsize=9, padding=3)
    ax.set_xticks(x, PERIOD_ORDER)
    ax.set_ylim(60, 101)
    ax.set_ylabel("3-minute punctuality score (%)")
    ax.set_title("Corrected workday punctuality with day-cluster bootstrap intervals")
    ax.legend(ncol=4, loc="lower center")
    fig.tight_layout()
    return fig


def plot_sensitivity(sensitivity: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(18, 7), sharey=True)
    markers = ["o", "s", "D", "^"]
    for ax, metric in zip(axes, ["OTP", "PP2"], strict=True):
        metric_data = sensitivity.loc[sensitivity["metric"].eq(metric)]
        for marker, (variant, group) in zip(markers, metric_data.groupby("variant", sort=False), strict=False):
            values = group.set_index("period").reindex(PERIOD_ORDER)
            ax.plot(PERIOD_ORDER, values["score"], marker=marker, linewidth=2, label=variant)
        ax.set(title=metric, ylabel="3-minute score (%)", ylim=(78, 98))
        ax.tick_params(axis="x", rotation=15)
    axes[1].legend(fontsize=9, loc="lower left")
    fig.suptitle("Sensitivity to weekends, legacy hour bins, and period cohort", y=1.02)
    fig.tight_layout()
    return fig


def plot_weighted_quantiles(journeys: pd.DataFrame) -> plt.Figure:
    quantiles = np.linspace(0, 1, 101)
    fig, axes = plt.subplots(1, 3, figsize=(19, 6), sharex=True, sharey=True)
    for ax, period in zip(axes, PERIOD_ORDER, strict=True):
        group = journeys.loc[
            journeys["period"].eq(period)
            & journeys["observed_arrival"]
            & journeys["passengers"].gt(0)
        ]
        weights = group["passengers"]
        actual = weighted_quantile(group["actual_travel_minutes"], quantiles, weights)
        scheduled = weighted_quantile(group["scheduled_travel_minutes"], quantiles, weights)
        ax.plot(100 * quantiles, actual, label="Actual", color="#0072B2", linewidth=2)
        ax.plot(100 * quantiles, scheduled, label="Scheduled", color="#D55E00", linestyle="--", linewidth=2)
        ax.set(title=period, xlabel="Passenger-trip percentile", ylabel="Journey time (minutes)", xlim=(0, 100))
        ax.annotate(
            f"P50 actual: {weighted_quantile(group['actual_travel_minutes'], [0.5], weights)[0]:.0f} min\n"
            f"P90 actual: {weighted_quantile(group['actual_travel_minutes'], [0.9], weights)[0]:.0f} min",
            xy=(0.04, 0.78),
            xycoords="axes fraction",
            fontsize=10,
        )
    axes[0].legend()
    fig.suptitle("Passenger-weighted journey-time distributions", y=1.02)
    fig.tight_layout()
    return fig


def _matrix(data: pd.DataFrame, value: str, period: str) -> pd.DataFrame:
    return (
        data.loc[data["period"].eq(period)]
        .pivot(index="origin", columns="destination", values=value)
        .reindex(index=STATIONS_SOUTH_TO_NORTH, columns=STATIONS_SOUTH_TO_NORTH)
    )


def plot_od_heatmaps(actual_od: pd.DataFrame, planned_od: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(2, 3, figsize=(21, 13))
    ejt_vmax = actual_od["EJT_minutes"].quantile(0.98)
    for column, period in enumerate(PERIOD_ORDER):
        pp2c = _matrix(planned_od, "PP2_C", period)
        ejt = _matrix(actual_od, "EJT_minutes", period)
        sns.heatmap(
            pp2c,
            ax=axes[0, column],
            cmap="RdYlGn",
            vmin=60,
            vmax=100,
            square=True,
            cbar=column == 2,
            cbar_kws={"label": "PP2-C (%)"},
        )
        sns.heatmap(
            ejt,
            ax=axes[1, column],
            cmap="YlOrRd",
            vmin=0,
            vmax=ejt_vmax,
            square=True,
            cbar=column == 2,
            cbar_kws={"label": "Passenger-weighted EJT (min)"},
        )
        axes[0, column].set_title(period)
        axes[1, column].set_title(period)
        for ax in axes[:, column]:
            ax.set_xlabel("Destination")
            ax.set_ylabel("Origin" if column == 0 else "")
            ax.tick_params(axis="x", labelrotation=60, labelsize=7)
            ax.tick_params(axis="y", labelrotation=0, labelsize=7)
    fig.text(0.01, 0.73, "Cancellation-sensitive\npassenger punctuality", rotation=90, va="center", fontsize=15)
    fig.text(0.01, 0.27, "Excess journey time", rotation=90, va="center", fontsize=15)
    fig.suptitle("OD-level passenger reliability: volume-weighted, workdays only", y=1.01)
    fig.tight_layout(rect=(0.035, 0, 1, 0.98))
    return fig


def plot_expected_wait(ew: pd.DataFrame) -> plt.Figure:
    pivot = ew.pivot(index="station", columns="period", values="EW_minutes").reindex(STATIONS_SOUTH_TO_NORTH)
    fig, ax = plt.subplots(figsize=(17, 7))
    x = np.arange(len(pivot))
    width = 0.25
    for position, period in enumerate(PERIOD_ORDER):
        ax.bar(
            x + (position - 1) * width,
            pivot[period],
            width,
            label=period,
            color=COLORS[period],
        )
    ax.set_xticks(x, pivot.index, rotation=55, ha="right")
    ax.set(ylabel="Expected waiting time (minutes)", xlabel="Departure station", title="Corrected EW: one observation per departure")
    ax.legend(ncol=3)
    fig.tight_layout()
    return fig


def combine_od_metrics(actual_od: pd.DataFrame, planned_od: pd.DataFrame) -> pd.DataFrame:
    combined = actual_od.merge(
        planned_od,
        on=["period", "origin", "destination"],
        how="outer",
        validate="one_to_one",
    )
    combined["affected_planned_passengers"] = (
        combined["planned_passengers"] - combined["on_time_passengers_y"]
    )
    return combined


def plot_od_risk(combined: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 3, figsize=(20, 6), sharex=True, sharey=True)
    for ax, period in zip(axes, PERIOD_ORDER, strict=True):
        group = combined.loc[
            combined["period"].eq(period)
            & combined["EJT_minutes"].notna()
            & combined["PP2_C"].notna()
        ].copy()
        sizes = 12 + 70 * np.sqrt(group["planned_passengers"] / group["planned_passengers"].max())
        ax.scatter(group["EJT_minutes"], group["PP2_C"], s=sizes, alpha=0.45, color=COLORS[period], edgecolor="none")
        top = group.nlargest(4, "affected_planned_passengers")
        for row in top.itertuples():
            ax.annotate(f"{row.origin}-{row.destination}", (row.EJT_minutes, row.PP2_C), fontsize=8)
        rho = spearmanr(group["EJT_minutes"], group["PP2_C"], nan_policy="omit").statistic
        ax.set(title=f"{period}\nSpearman ρ = {rho:.2f}", xlabel="Passenger-weighted EJT (minutes)", ylabel="PP2-C (%)", ylim=(55, 101))
    fig.suptitle("EJT and PP2-C identify related but non-identical OD risks", y=1.03)
    fig.tight_layout()
    return fig


def train_volume_delay(actual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, plt.Figure]:
    data = add_service_period(actual)
    totals = (
        data.groupby(TRAIN_KEYS, as_index=False)["n_boarding"]
        .sum()
        .rename(columns={"n_boarding": "passengers"})
    )
    final = data.loc[
        data["UppehallstypAnkomst"].eq("Sista")
        & ~data["arrival_time_imputed"].astype(bool)
    ].merge(totals, on=TRAIN_KEYS, how="left", validate="one_to_one")
    rows = []
    for period in PERIOD_ORDER:
        group = final.loc[final["period"].eq(period)]
        rho, p_value = spearmanr(group["passengers"], group["arr_delay_minutes"], nan_policy="omit")
        rows.append({"period": period, "spearman_rho": rho, "p_value": p_value, "trains": len(group)})
    correlations = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(12, 7))
    for period in PERIOD_ORDER:
        group = final.loc[final["period"].eq(period)]
        ax.scatter(group["passengers"], group["arr_delay_minutes"], s=18, alpha=0.45, label=period, color=COLORS[period])
    ax.axhline(3, color="black", linestyle="--", linewidth=1.5, label="3-minute threshold")
    ax.set(xlabel="Estimated passengers on train", ylabel="Terminal arrival delay (minutes)", title="Passenger exposure is concentrated in a subset of delayed trains", ylim=(-6, 35))
    ax.legend(ncol=2)
    fig.tight_layout()
    return final, correlations, fig


def station_period_ridership_figure(
    actual: pd.DataFrame,
) -> tuple[pd.DataFrame, plt.Figure]:
    """Compare unweighted and alighting-passenger-weighted station delay."""

    data = actual.loc[
        actual["Ankomsttid"].notna()
        & ~actual["arrival_time_imputed"].fillna(False).astype(bool)
    ].copy()
    data["period"] = assign_time_period(
        clock_minutes(data["Planerad_ankomsttid"])
    )
    data = data.loc[
        data["period"].isin(PERIOD_ORDER)
        & data["Till_platssignatur"].notna()
    ].copy()
    # Early arrivals are treated as zero delay, as they impose no lateness.
    data["nonnegative_arrival_delay_minutes"] = data[
        "arr_delay_minutes"
    ].clip(lower=0.0)
    data["weighted_delay_minutes"] = (
        data["n_alighting_next"]
        * data["nonnegative_arrival_delay_minutes"]
    )

    impact = data.groupby(
        ["period", "Till_platssignatur"],
        as_index=False,
        observed=True,
    ).agg(
        train_arrivals=("nonnegative_arrival_delay_minutes", "size"),
        accumulated_station_arrival_delay_minutes=(
            "nonnegative_arrival_delay_minutes",
            "sum",
        ),
        mean_station_arrival_delay_minutes=(
            "nonnegative_arrival_delay_minutes",
            "mean",
        ),
        total_alighting_passengers=("n_alighting_next", "sum"),
        passenger_delay_minutes=("weighted_delay_minutes", "sum"),
    )
    impact = impact.rename(columns={"Till_platssignatur": "station"})
    impact["passenger_weighted_arrival_delay_minutes"] = (
        impact["passenger_delay_minutes"]
        / impact["total_alighting_passengers"]
    )
    impact["passenger_delay_hours"] = impact["passenger_delay_minutes"] / 60.0
    impact["accumulated_station_arrival_delay_hours"] = (
        impact["accumulated_station_arrival_delay_minutes"] / 60.0
    )
    impact["weighting_difference_minutes"] = (
        impact["passenger_weighted_arrival_delay_minutes"]
        - impact["mean_station_arrival_delay_minutes"]
    )

    period_markers = {
        "Morning peak": "o",
        "Midday off-peak": "s",
        "Afternoon peak": "^",
    }
    short_period = {
        "Morning peak": "AM",
        "Midday off-peak": "Midday",
        "Afternoon peak": "PM",
    }
    max_passengers = impact["total_alighting_passengers"].max()
    marker_sizes = 35 + 155 * np.sqrt(
        impact["total_alighting_passengers"] / max_passengers
    )

    fig, axes = plt.subplots(1, 2, figsize=(18, 7.5))
    for period in PERIOD_ORDER:
        group = impact.loc[impact["period"].eq(period)]
        sizes = marker_sizes.loc[group.index]
        common = {
            "s": sizes,
            "alpha": 0.72,
            "color": COLORS[period],
            "marker": period_markers[period],
            "edgecolors": "white",
            "linewidths": 0.7,
            "label": period,
        }
        axes[0].scatter(
            group["mean_station_arrival_delay_minutes"],
            group["total_alighting_passengers"] / 1000.0,
            **common,
        )
        axes[1].scatter(
            group["mean_station_arrival_delay_minutes"],
            group["passenger_weighted_arrival_delay_minutes"],
            **common,
        )

    x_max = 1.08 * impact["mean_station_arrival_delay_minutes"].max()
    y_max = 1.08 * impact["passenger_weighted_arrival_delay_minutes"].max()
    diagonal_max = max(x_max, y_max)
    axes[0].set(
        title="A. Similar station delays affect very different passenger volumes",
        xlabel="Mean station arrival delay (minutes)",
        ylabel="Passengers alighting over the period (thousands, log scale)",
        xlim=(0, x_max),
    )
    axes[0].set_yscale("log")
    axes[1].plot(
        [0, diagonal_max],
        [0, diagonal_max],
        color="black",
        linestyle="--",
        linewidth=1.3,
        label="Equal weighted and unweighted delay",
    )
    axes[1].set(
        title="B. Alighting-passenger weights change the measured delay",
        xlabel="Mean station arrival delay (minutes)",
        ylabel="Alighting-passenger-weighted delay (minutes)",
        xlim=(0, diagonal_max),
        ylim=(0, diagonal_max),
    )

    top_flows = impact.groupby("period", observed=True).apply(
        lambda group: group.nlargest(1, "total_alighting_passengers"),
        include_groups=False,
    ).reset_index()
    for row in top_flows.itertuples():
        axes[0].annotate(
            f"{row.station} ({short_period[row.period]})",
            (
                row.mean_station_arrival_delay_minutes,
                row.total_alighting_passengers / 1000.0,
            ),
            xytext=(7, 5),
            textcoords="offset points",
            fontsize=9,
        )

    largest_shifts = impact.groupby("period", observed=True).apply(
        lambda group: group.nlargest(1, "weighting_difference_minutes"),
        include_groups=False,
    ).reset_index()
    shift_offsets = {
        "Morning peak": (-28, 12),
        "Midday off-peak": (8, -18),
        "Afternoon peak": (8, 7),
    }
    for row in largest_shifts.itertuples():
        axes[1].annotate(
            f"{row.station} ({short_period[row.period]})",
            (
                row.mean_station_arrival_delay_minutes,
                row.passenger_weighted_arrival_delay_minutes,
            ),
            xytext=shift_offsets[row.period],
            textcoords="offset points",
            fontsize=9,
        )

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.925),
        ncol=3,
        fontsize=10,
    )
    axes[1].text(
        0.97,
        0.07,
        "Dashed line: weighting makes no difference",
        transform=axes[1].transAxes,
        ha="right",
        fontsize=9,
    )
    fig.suptitle(
        "Ridership weighting changes how station arrival delay is interpreted",
        y=0.99,
        fontsize=22,
    )
    fig.text(
        0.5,
        0.015,
        "Each point is one arrival station aggregated over all 25 weekdays in a period. "
        "Early arrivals are set to zero; marker area scales with alighting volume.",
        ha="center",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 0.87))
    return impact, fig


def station_period_accumulated_delay_figure(
    impact: pd.DataFrame,
) -> plt.Figure:
    """Relate accumulated station delay to ridership and passenger delay."""

    data = impact.loc[
        impact["accumulated_station_arrival_delay_hours"].gt(0)
        & impact["passenger_delay_hours"].gt(0)
    ].copy()
    period_markers = {
        "Morning peak": "o",
        "Midday off-peak": "s",
        "Afternoon peak": "^",
    }
    short_period = {
        "Morning peak": "AM",
        "Midday off-peak": "Midday",
        "Afternoon peak": "PM",
    }
    max_passengers = data["total_alighting_passengers"].max()
    marker_sizes = 40 + 175 * np.sqrt(
        data["total_alighting_passengers"] / max_passengers
    )

    fig, axes = plt.subplots(1, 2, figsize=(18, 7.5))
    for period in PERIOD_ORDER:
        group = data.loc[data["period"].eq(period)]
        common = {
            "s": marker_sizes.loc[group.index],
            "alpha": 0.75,
            "color": COLORS[period],
            "marker": period_markers[period],
            "edgecolors": "white",
            "linewidths": 0.8,
            "label": period,
        }
        axes[0].scatter(
            group["accumulated_station_arrival_delay_hours"],
            group["total_alighting_passengers"] / 1000.0,
            **common,
        )
        axes[1].scatter(
            group["accumulated_station_arrival_delay_hours"],
            group["passenger_delay_hours"],
            **common,
        )

    top_flows = data.groupby("period", observed=True).apply(
        lambda group: group.nlargest(1, "total_alighting_passengers"),
        include_groups=False,
    ).reset_index()
    flow_label_offsets = {
        "Morning peak": (8, 5),
        "Midday off-peak": (-96, -18),
        "Afternoon peak": (8, -22),
    }
    for row in top_flows.itertuples():
        axes[0].annotate(
            f"{row.station} ({short_period[row.period]})",
            (
                row.accumulated_station_arrival_delay_hours,
                row.total_alighting_passengers / 1000.0,
            ),
            xytext=flow_label_offsets[row.period],
            textcoords="offset points",
            fontsize=9,
        )

    top_burden = data.groupby("period", observed=True).apply(
        lambda group: group.nlargest(1, "passenger_delay_hours"),
        include_groups=False,
    ).reset_index()
    label_offsets = {
        "Morning peak": (8, 7),
        "Midday off-peak": (-120, 10),
        "Afternoon peak": (10, -27),
    }
    for row in top_burden.itertuples():
        axes[1].annotate(
            f"{row.station} ({short_period[row.period]}): "
            f"{row.passenger_delay_hours:,.0f} passenger-hours",
            (
                row.accumulated_station_arrival_delay_hours,
                row.passenger_delay_hours,
            ),
            xytext=label_offsets[row.period],
            textcoords="offset points",
            fontsize=10,
        )

    for ax in axes:
        ax.set_xscale("log")
        ax.set_yscale("log")
    axes[0].set(
        title="A. Passenger exposure differs at similar accumulated train delay",
        xlabel="Accumulated train-arrival delay (train-hours, log scale)",
        ylabel="Alighting passengers (thousands, log scale)",
    )
    axes[1].set(
        title="B. Ridership converts train delay into passenger delay",
        xlabel="Accumulated train-arrival delay (train-hours, log scale)",
        ylabel="Accumulated passenger delay (passenger-hours, log scale)",
    )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.925),
        ncol=3,
        fontsize=10,
    )
    fig.suptitle(
        "Accumulated delay reveals the scale of passenger exposure",
        y=0.99,
        fontsize=22,
    )
    fig.text(
        0.5,
        0.015,
        "Each point is one arrival station aggregated over all 25 weekdays in a period. "
        "Early arrivals are set to zero; marker area scales with total alighting volume.",
        ha="center",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 0.87))
    return fig


def write_report(
    output: Path,
    quality: pd.DataFrame,
    summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
    journey_summary: pd.DataFrame,
    ew: pd.DataFrame,
    hotspots: pd.DataFrame,
    station_impact: pd.DataFrame,
) -> None:
    metric = summary.set_index(["metric", "period"])["score"]
    cancellation_rate = quality.set_index("measure").loc["Terminal cancellation rate", "value"]
    ew_means = ew.groupby("period")["EW_minutes"].mean()
    legacy = sensitivity.loc[
        sensitivity["variant"].eq("Report code: all days, legacy arrival-hour bins")
    ].set_index(["metric", "period"])["score"]
    corrected_arrival = sensitivity.loc[
        sensitivity["variant"].eq("Weekdays, corrected arrival-time bins")
    ].set_index(["metric", "period"])["score"]
    weighting_increases = station_impact["weighting_difference_minutes"].gt(0).sum()
    central_morning = station_impact.loc[
        station_impact["period"].eq("Morning peak")
        & station_impact["station"].eq("Cst")
    ].iloc[0]
    lines = [
        "# Corrected case-study analysis",
        "",
        "## Main findings",
        "",
        f"- The weekday terminal-service cancellation rate is **{cancellation_rate:.1f}%**.",
        f"- At the 3-minute threshold, morning OTP is **{metric['OTP', 'Morning peak']:.1f}%** while passenger PP2 is **{metric['PP2', 'Morning peak']:.1f}%**. Afternoon scores are **{metric['OTP', 'Afternoon peak']:.1f}%** and **{metric['PP2', 'Afternoon peak']:.1f}%**, respectively.",
        f"- Keeping planned passengers exposed to cancellations in the denominator reduces PP2 to **{metric['PP2-C', 'Morning peak']:.1f}%** in the morning and **{metric['PP2-C', 'Afternoon peak']:.1f}%** in the afternoon.",
        f"- The original all-days/legacy-bin calculation gives morning PP2 **{legacy['PP2', 'Morning peak']:.1f}%**; selecting weekdays and corrected arrival-time bins gives **{corrected_arrival['PP2', 'Morning peak']:.1f}%**.",
        f"- Passenger-weighted median journey time is **{journey_summary.set_index('period').loc['Morning peak', 'actual_p50_minutes']:.0f} min** in the morning, not the unweighted train-OD median of 28 min reported by the legacy notebook.",
        f"- Corrected mean station EW is **{ew_means['Morning peak']:.1f} min** in the morning and **{ew_means['Afternoon peak']:.1f} min** in the afternoon; the legacy OD-expanded calculation was 13.0 and 12.7 min.",
        f"- Alighting-passenger weighting increases the measured delay in **{weighting_increases} of {len(station_impact)} station-period cells**. At Cst in the morning peak, the unweighted station-arrival mean is **{central_morning['mean_station_arrival_delay_minutes']:.2f} min**, compared with **{central_morning['passenger_weighted_arrival_delay_minutes']:.2f} min** after weighting {central_morning['total_alighting_passengers']:,.0f} alighting passengers.",
        f"- Accumulated over the 25 weekdays, morning-peak arrivals at Cst account for **{central_morning['accumulated_station_arrival_delay_hours']:,.1f} train-hours** of nonnegative station delay but **{central_morning['passenger_delay_hours']:,.0f} passenger-hours** after weighting passengers who alight there.",
        "",
        "## Interpretation safeguards",
        "",
        "- PP2 is calculated for observed completed journeys. PP2-C is a conservative cancellation-sensitive extension: planned passengers on a cancelled or unobserved completion are counted as not on time.",
        "- PP2-C is not an individual re-routing model. Eventual arrival after a cancellation needs linked AFC journeys or explicit route-choice assumptions.",
        "- EJT and PP2 share delay information, so their strong negative correlation is partly structural. OD rankings should also consider passenger volume and affected-passenger burden.",
        "- Confidence intervals resample workdays, reflecting day-to-day operational variation rather than treating every train or synthetic passenger estimate as independent.",
        "",
        "## Highest affected-passenger OD-period cells",
        "",
        hotspots.head(10).to_markdown(index=False),
        "",
        "## Promising extensions",
        "",
        "- Link individual AFC journeys, or simulate explicit passenger re-routing, so cancellation delay measures eventual arrival rather than treating every cancelled journey as a failure.",
        "- Repeat the analysis across lines, seasons, and years with a hierarchical day/line model; one five-week corridor extract cannot establish generality.",
        "- Use multiple imputation or scenario bounds for missing arrival/departure timestamps, especially at Ts and Ngd where the imputed share is unusually high.",
        "- Add crowding or capacity data and test whether passenger exposure predicts delay after controlling for direction, time of day, stopping pattern, and service length.",
        "- Stabilise low-volume OD rankings with empirical-Bayes shrinkage and publish both rate-based and affected-passenger priority lists.",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def run(output_root: Path, legacy_actual_path: Path | None) -> None:
    _style()
    figures = output_root / "figures"
    tables = output_root / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    raw = get_traffic_data()
    actual = get_onboard_data("actual")
    planned = get_onboard_data("planned")
    quality = data_quality_table(raw, actual, planned)
    summary = punctuality_summary(actual, planned, threshold_minutes=3.0)
    curves = punctuality_curves(actual, planned, thresholds_minutes=range(16))

    sensitivity_source = actual
    if legacy_actual_path is not None and legacy_actual_path.is_file():
        sensitivity_source = get_onboard_data("actual", legacy_actual_path)
    sensitivity = period_definition_sensitivity(sensitivity_source)

    actual_journeys = build_passenger_journeys(actual)
    planned_journeys = build_passenger_journeys(planned)
    journeys = journey_period_summary(actual_journeys)
    actual_od = od_metrics(actual_journeys)
    planned_od = cancellation_adjusted_od_metrics(planned_journeys)
    combined_od = combine_od_metrics(actual_od, planned_od)
    ew = expected_wait_table(actual)
    station_impact, weighting_figure = station_period_ridership_figure(actual)
    accumulated_figure = station_period_accumulated_delay_figure(station_impact)

    hotspots = combined_od.loc[
        combined_od["planned_passengers"].ge(500)
    ].nlargest(30, "affected_planned_passengers")[
        [
            "period",
            "origin",
            "destination",
            "planned_passengers",
            "PP2_C",
            "EJT_minutes",
            "affected_planned_passengers",
            "passenger_delay_minutes",
        ]
    ]

    outputs = {
        "data_quality.csv": quality,
        "corrected_metric_summary.csv": summary,
        "punctuality_curves.csv": curves,
        "period_definition_sensitivity.csv": sensitivity,
        "journey_time_summary.csv": journeys,
        "expected_wait_by_station.csv": ew,
        "od_metrics.csv": combined_od,
        "top_reliability_hotspots.csv": hotspots,
        "station_period_ridership_impact.csv": station_impact,
    }
    for name, frame in outputs.items():
        frame.to_csv(tables / name, index=False)

    _save(plot_data_quality(actual, planned), figures / "01_data_quality.png")
    _save(plot_curves(curves), figures / "02_punctuality_curves.png")
    _save(plot_metric_summary(summary), figures / "03_metric_summary.png")
    _save(plot_sensitivity(sensitivity), figures / "04_period_sensitivity.png")
    _save(plot_weighted_quantiles(actual_journeys), figures / "05_weighted_journey_quantiles.png")
    _save(plot_od_heatmaps(actual_od, planned_od), figures / "06_od_reliability.png")
    _save(plot_expected_wait(ew), figures / "07_expected_wait.png")
    _save(plot_od_risk(combined_od), figures / "08_od_risk_comparison.png")
    _save(weighting_figure, figures / "09_station_ridership_weighting.png")
    _save(accumulated_figure, figures / "10_station_accumulated_delay.png")
    write_report(
        output_root / "analysis_report.md",
        quality,
        summary,
        sensitivity,
        journeys,
        ew,
        hotspots,
        station_impact,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "output",
    )
    parser.add_argument(
        "--legacy-actual",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "legacy_derived" / "df_onboard_actual.csv",
        help="Optional pre-correction table used to reproduce report-code sensitivity.",
    )
    args = parser.parse_args()
    run(args.output_root.resolve(), args.legacy_actual.resolve())


if __name__ == "__main__":
    main()
