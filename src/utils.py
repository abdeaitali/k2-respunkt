"""Metric and statistical utilities used by the case-study notebooks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from .constants import STATIONS_SOUTH_TO_NORTH, TIME_PERIODS_MINUTES


def get_direction(
    from_station: str,
    to_station: str,
    stations_south_to_north: Sequence[str] = STATIONS_SOUTH_TO_NORTH,
) -> int:
    """Return +1 northbound, -1 southbound, and 0 for a zero-length movement."""

    positions = {station: position for position, station in enumerate(stations_south_to_north)}
    try:
        difference = positions[to_station] - positions[from_station]
    except KeyError as exc:
        raise ValueError(f"Unknown station code: {exc.args[0]!r}") from exc
    return int(np.sign(difference))


def get_OTP(
    df_traffic: pd.DataFrame,
    *,
    include_cancellations: bool = False,
) -> pd.DataFrame:
    """Return destination-arrival delays while retaining cancellation provenance."""

    arrival_type = (
        "UppehållstypAnkomst"
        if "UppehållstypAnkomst" in df_traffic
        else "UppehallstypAnkomst"
    )
    actual_arrival = "Ankomsttid"
    planned_arrival = (
        "Planerad ankomsttid"
        if "Planerad ankomsttid" in df_traffic
        else "Planerad_ankomsttid"
    )
    date_column = "Datum (PAU)" if "Datum (PAU)" in df_traffic else "Datum"

    result = df_traffic.loc[df_traffic[arrival_type] == "Sista"].copy()
    if not include_cancellations and "Inställtflagga" in result:
        result = result.loc[result["Inställtflagga"] == "N"].copy()

    result[actual_arrival] = pd.to_datetime(result[actual_arrival], errors="coerce")
    result[planned_arrival] = pd.to_datetime(result[planned_arrival], errors="coerce")
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    result["OTP_seconds"] = (
        result[actual_arrival] - result[planned_arrival]
    ).dt.total_seconds()
    result["OTP_minutes"] = result["OTP_seconds"] / 60.0

    if not include_cancellations:
        result = result.dropna(subset=[actual_arrival, planned_arrival])
    return result


def clock_minutes(values: pd.Series) -> pd.Series:
    """Convert datetimes to minutes after midnight, preserving missing values."""

    datetimes = pd.to_datetime(values, errors="coerce")
    return (
        datetimes.dt.hour * 60
        + datetimes.dt.minute
        + datetimes.dt.second / 60.0
    )


def assign_time_period(
    minutes: pd.Series,
    periods: Mapping[str, tuple[float, float]] = TIME_PERIODS_MINUTES,
) -> pd.Series:
    """Assign half-open time periods such as 06:00 <= t < 09:00."""

    result = pd.Series(pd.NA, index=minutes.index, dtype="string")
    for label, (start, end) in periods.items():
        result.loc[minutes.ge(start) & minutes.lt(end)] = label
    return result


def on_time_curve(
    delays_minutes: pd.Series,
    thresholds_minutes: Sequence[float],
    *,
    weights: pd.Series | None = None,
    eligible: pd.Series | None = None,
) -> np.ndarray:
    """Compute a weighted empirical CDF of delays for exact thresholds."""

    delay = pd.to_numeric(delays_minutes, errors="coerce")
    valid = delay.notna() if eligible is None else eligible.fillna(False)
    if weights is None:
        weight = pd.Series(1.0, index=delay.index)
    else:
        weight = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    denominator = weight.loc[valid].sum()
    if denominator <= 0:
        return np.full(len(thresholds_minutes), np.nan)
    return np.asarray(
        [weight.loc[valid & delay.le(threshold)].sum() / denominator for threshold in thresholds_minutes],
        dtype=float,
    )


def weighted_quantile(
    values: Sequence[float] | pd.Series,
    quantiles: Sequence[float],
    sample_weight: Sequence[float] | pd.Series,
) -> np.ndarray:
    """Calculate weighted empirical quantiles for non-negative observation weights."""

    value = np.asarray(values, dtype=float)
    weight = np.asarray(sample_weight, dtype=float)
    q = np.asarray(quantiles, dtype=float)
    valid = np.isfinite(value) & np.isfinite(weight) & (weight > 0)
    if not valid.any():
        return np.full(q.shape, np.nan)
    value = value[valid]
    weight = weight[valid]
    order = np.argsort(value, kind="mergesort")
    value = value[order]
    weight = weight[order]
    cumulative = np.cumsum(weight) / weight.sum()
    positions = np.searchsorted(cumulative, q, side="left")
    positions = np.clip(positions, 0, len(value) - 1)
    return value[positions]


def ratio_confidence_interval_by_day(
    daily: pd.DataFrame,
    *,
    numerator: str,
    denominator: str,
    draws: int = 2_000,
    seed: int = 2024,
) -> tuple[float, float, float]:
    """Return estimate and a day-cluster bootstrap 95% interval for a ratio."""

    data = daily[[numerator, denominator]].dropna()
    data = data.loc[data[denominator] > 0]
    if data.empty:
        return np.nan, np.nan, np.nan
    estimate = data[numerator].sum() / data[denominator].sum()
    generator = np.random.default_rng(seed)
    positions = generator.integers(0, len(data), size=(draws, len(data)))
    numerator_samples = data[numerator].to_numpy()[positions].sum(axis=1)
    denominator_samples = data[denominator].to_numpy()[positions].sum(axis=1)
    samples = np.divide(
        numerator_samples,
        denominator_samples,
        out=np.full(draws, np.nan),
        where=denominator_samples > 0,
    )
    lower, upper = np.nanquantile(samples, [0.025, 0.975])
    return float(estimate), float(lower), float(upper)


def expected_waiting_time(
    departures: pd.DataFrame,
    *,
    headway_column: str = "headway",
    boarding_column: str = "n_boarding",
) -> float:
    """Passenger-weighted expected wait using one observation per departure.

    With a piecewise-constant passenger arrival rate, this is
    0.5 * sum(boardings_i * headway_i) / sum(boardings_i).
    """

    headway = pd.to_numeric(departures[headway_column], errors="coerce")
    boardings = pd.to_numeric(departures[boarding_column], errors="coerce")
    valid = headway.gt(0) & headway.notna() & boardings.gt(0) & boardings.notna()
    if not valid.any():
        return np.nan
    return float(
        0.5
        * np.average(
            headway.loc[valid].to_numpy(),
            weights=boardings.loc[valid].to_numpy(),
        )
    )


def get_PP2_A_to_B(
    station_A: str,
    station_B: str,
    journeys: pd.DataFrame,
    delay_threshold: float = 5.0,
    period: str | None = None,
) -> float:
    """Calculate PP2 for an OD pair from the canonical passenger-journey table."""

    required = {"origin", "destination", "passengers", "arrival_delay_minutes"}
    missing = required.difference(journeys.columns)
    if missing:
        raise ValueError(
            "get_PP2_A_to_B now expects the canonical journey table; "
            f"missing columns: {sorted(missing)}"
        )
    selection = journeys.loc[
        journeys["origin"].eq(station_A) & journeys["destination"].eq(station_B)
    ]
    if period is not None:
        selection = selection.loc[selection["period"].eq(period)]
    weight = selection["passengers"].clip(lower=0.0)
    if weight.sum() <= 0:
        return np.nan
    return float(
        weight.loc[selection["arrival_delay_minutes"].le(delay_threshold)].sum()
        / weight.sum()
    )
