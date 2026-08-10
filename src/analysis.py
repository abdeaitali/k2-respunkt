"""Canonical case-study metrics built from the derived on-board tables."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .constants import (
    MOVEMENT_KEYS,
    STATIONS_SOUTH_TO_NORTH,
    TIME_PERIODS_MINUTES,
    TRAIN_KEYS,
)
from .utils import (
    assign_time_period,
    clock_minutes,
    expected_waiting_time,
    ratio_confidence_interval_by_day,
    weighted_quantile,
)


DATETIME_COLUMNS = [
    "Datum",
    "Ankomsttid",
    "Avgangstid",
    "Planerad_ankomsttid",
    "Planerad_avgangstid",
]


def parse_onboard_datetimes(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    for column in DATETIME_COLUMNS:
        if column in result:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    result["Datum"] = result["Datum"].dt.normalize()
    return result


def weekdays(data: pd.DataFrame) -> pd.DataFrame:
    parsed = parse_onboard_datetimes(data)
    return parsed.loc[parsed["Datum"].dt.dayofweek.lt(5)].copy()


def add_service_period(
    data: pd.DataFrame,
    periods: Mapping[str, tuple[float, float]] = TIME_PERIODS_MINUTES,
) -> pd.DataFrame:
    """Attach the period of a train's first scheduled departure to every movement."""

    result = parse_onboard_datetimes(data)
    first_departures = (
        result.sort_values("Delstrackanummer")
        .groupby(TRAIN_KEYS, as_index=False, sort=False)
        .first()[TRAIN_KEYS + ["Planerad_avgangstid"]]
        .rename(columns={"Planerad_avgangstid": "service_start_scheduled"})
    )
    result = result.merge(first_departures, on=TRAIN_KEYS, how="left", validate="many_to_one")
    result["service_start_minutes"] = clock_minutes(result["service_start_scheduled"])
    result["period"] = assign_time_period(result["service_start_minutes"], periods)
    return result


def _observed_arrival(data: pd.DataFrame) -> pd.Series:
    observed = data["Ankomsttid"].notna()
    if "arrival_time_imputed" in data:
        observed &= ~data["arrival_time_imputed"].fillna(False).astype(bool)
    return observed


def _period_subsets(data: pd.DataFrame) -> Iterable[tuple[str, pd.DataFrame]]:
    yield "All day", data
    for label in TIME_PERIODS_MINUTES:
        yield label, data.loc[data["period"].eq(label)]


def _ratio_row(
    data: pd.DataFrame,
    *,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    weights: pd.Series | None,
    metric: str,
    period: str,
) -> dict[str, float | str | int]:
    if weights is None:
        weight = pd.Series(1.0, index=data.index)
    else:
        weight = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    daily = pd.DataFrame(
        {
            "date": data["Datum"],
            "numerator": weight.where(numerator_mask, 0.0),
            "denominator": weight.where(denominator_mask, 0.0),
        }
    ).groupby("date", as_index=False)[["numerator", "denominator"]].sum()
    estimate, lower, upper = ratio_confidence_interval_by_day(
        daily,
        numerator="numerator",
        denominator="denominator",
    )
    return {
        "metric": metric,
        "period": period,
        "score": 100.0 * estimate,
        "ci_lower": 100.0 * lower,
        "ci_upper": 100.0 * upper,
        "denominator": float(daily["denominator"].sum()),
        "days": int((daily["denominator"] > 0).sum()),
    }


def punctuality_summary(
    actual: pd.DataFrame,
    planned: pd.DataFrame,
    *,
    threshold_minutes: float = 3.0,
) -> pd.DataFrame:
    """Calculate comparable train/passenger metrics for the declared workday cohort.

    ``OTP`` and ``PP2`` use observed completed services. ``CPM`` and ``PP2-C``
    retain the planned denominator, so cancellations and missing completions are
    treated as failures.  The latter is a conservative cancellation-sensitive
    passenger measure, not a model of passengers' eventual re-routing.
    """

    actual_input = actual
    planned_input = planned
    actual = add_service_period(weekdays(actual_input))
    planned = add_service_period(weekdays(planned_input))
    actual_journeys = build_passenger_journeys(actual_input)
    planned_journeys = build_passenger_journeys(planned_input)
    rows: list[dict[str, float | str | int]] = []

    actual_final = actual.loc[actual["UppehallstypAnkomst"].eq("Sista")].copy()
    planned_final = planned.loc[planned["UppehallstypAnkomst"].eq("Sista")].copy()

    for label, subset in _period_subsets(actual_final):
        observed = _observed_arrival(subset)
        rows.append(
            _ratio_row(
                subset,
                numerator_mask=observed & subset["arr_delay_minutes"].le(threshold_minutes),
                denominator_mask=observed,
                weights=None,
                metric="OTP",
                period=label,
            )
        )

    for label, subset in _period_subsets(actual_journeys):
        observed = subset["observed_arrival"]
        rows.append(
            _ratio_row(
                subset,
                numerator_mask=observed & subset["arrival_delay_minutes"].le(threshold_minutes),
                denominator_mask=observed,
                weights=subset["passengers"],
                metric="PP2",
                period=label,
            )
        )

    for label, subset in _period_subsets(planned_final):
        completed_on_time = (
            subset["Ankomsttid"].notna()
            & subset["arr_delay_minutes"].le(threshold_minutes)
        )
        rows.append(
            _ratio_row(
                subset,
                numerator_mask=completed_on_time,
                denominator_mask=pd.Series(True, index=subset.index),
                weights=None,
                metric="CPM",
                period=label,
            )
        )

    for label, subset in _period_subsets(planned_journeys):
        completed_on_time = (
            subset["actual_arrival"].notna()
            & subset["arrival_delay_minutes"].le(threshold_minutes)
        )
        rows.append(
            _ratio_row(
                subset,
                numerator_mask=completed_on_time,
                denominator_mask=pd.Series(True, index=subset.index),
                weights=subset["passengers"],
                metric="PP2-C",
                period=label,
            )
        )
    return pd.DataFrame(rows)


def punctuality_curves(
    actual: pd.DataFrame,
    planned: pd.DataFrame,
    thresholds_minutes: Sequence[float] = tuple(range(16)),
) -> pd.DataFrame:
    """Return exact-threshold curves for OTP, PP2, CPM, and PP2-C."""

    actual_input = actual
    planned_input = planned
    actual = add_service_period(weekdays(actual_input))
    planned = add_service_period(weekdays(planned_input))
    actual_journeys = build_passenger_journeys(actual_input)
    planned_journeys = build_passenger_journeys(planned_input)
    actual_final = actual.loc[actual["UppehallstypAnkomst"].eq("Sista")]
    planned_final = planned.loc[planned["UppehallstypAnkomst"].eq("Sista")]
    rows: list[dict[str, float | str]] = []

    for period in ["All day", *TIME_PERIODS_MINUTES]:
        a = (
            actual_journeys
            if period == "All day"
            else actual_journeys.loc[actual_journeys["period"].eq(period)]
        )
        af = actual_final if period == "All day" else actual_final.loc[actual_final["period"].eq(period)]
        p = (
            planned_journeys
            if period == "All day"
            else planned_journeys.loc[planned_journeys["period"].eq(period)]
        )
        pf = planned_final if period == "All day" else planned_final.loc[planned_final["period"].eq(period)]
        definitions = [
            ("OTP", af, pd.Series(1.0, index=af.index), _observed_arrival(af)),
            ("PP2", a, a["passengers"], a["observed_arrival"]),
            ("CPM", pf, pd.Series(1.0, index=pf.index), pd.Series(True, index=pf.index)),
            ("PP2-C", p, p["passengers"], pd.Series(True, index=p.index)),
        ]
        for metric, data, weights, denominator in definitions:
            denominator_weight = weights.where(denominator, 0.0).sum()
            for threshold in thresholds_minutes:
                if metric in {"PP2", "PP2-C"}:
                    completed = data["actual_arrival"].notna()
                    if metric == "PP2":
                        completed &= data["observed_arrival"]
                    delay = data["arrival_delay_minutes"]
                else:
                    completed = data["Ankomsttid"].notna()
                    if metric == "OTP":
                        completed &= _observed_arrival(data)
                    delay = data["arr_delay_minutes"]
                numerator = completed & delay.le(threshold)
                score = (
                    100.0 * weights.where(numerator, 0.0).sum() / denominator_weight
                    if denominator_weight > 0
                    else np.nan
                )
                rows.append(
                    {
                        "metric": metric,
                        "period": period,
                        "threshold_minutes": float(threshold),
                        "score": float(score),
                    }
                )
    return pd.DataFrame(rows)


def build_passenger_journeys(onboard: pd.DataFrame) -> pd.DataFrame:
    """Expand movement-level destination columns into passenger OD journeys."""

    data = weekdays(onboard)
    station_columns = [station for station in STATIONS_SOUTH_TO_NORTH if station in data]
    demand = data[station_columns].to_numpy(dtype=float)
    row_positions, destination_positions = np.nonzero(demand > 1e-10)
    source = data.iloc[row_positions]
    journeys = pd.DataFrame(
        {
            "Datum": source["Datum"].to_numpy(),
            "Taguppdrag": source["Taguppdrag"].to_numpy(),
            "Tagnr": source["Tagnr"].to_numpy(),
            "origin": source["Fran_platssignatur"].to_numpy(),
            "destination": np.asarray(station_columns, dtype=object)[destination_positions],
            "passengers": demand[row_positions, destination_positions],
            "actual_departure": source["Avgangstid"].to_numpy(),
            "scheduled_departure": source["Planerad_avgangstid"].to_numpy(),
            "departure_imputed": source.get(
                "departure_time_imputed", pd.Series(False, index=source.index)
            ).to_numpy(),
            "headway": source.get(
                "headway", pd.Series(np.nan, index=source.index)
            ).to_numpy(),
            "direction": source["direction"].to_numpy(),
        }
    )

    arrival_columns = TRAIN_KEYS + [
        "Till_platssignatur",
        "Ankomsttid",
        "Planerad_ankomsttid",
        "Planeringsstatus",
    ]
    if "arrival_time_imputed" in data:
        arrival_columns.append("arrival_time_imputed")
    arrivals = data[arrival_columns].drop_duplicates(TRAIN_KEYS + ["Till_platssignatur"])
    arrivals = arrivals.rename(
        columns={
            "Till_platssignatur": "destination",
            "Ankomsttid": "actual_arrival",
            "Planerad_ankomsttid": "scheduled_arrival",
            "arrival_time_imputed": "arrival_imputed",
        }
    )
    journeys = journeys.merge(
        arrivals,
        on=TRAIN_KEYS + ["destination"],
        how="left",
        validate="many_to_one",
    )
    if "arrival_imputed" not in journeys:
        journeys["arrival_imputed"] = False
    journeys["actual_departure"] = pd.to_datetime(journeys["actual_departure"])
    journeys["scheduled_departure"] = pd.to_datetime(journeys["scheduled_departure"])
    journeys["actual_arrival"] = pd.to_datetime(journeys["actual_arrival"])
    journeys["scheduled_arrival"] = pd.to_datetime(journeys["scheduled_arrival"])
    journeys["actual_travel_minutes"] = (
        journeys["actual_arrival"] - journeys["actual_departure"]
    ).dt.total_seconds() / 60.0
    journeys["scheduled_travel_minutes"] = (
        journeys["scheduled_arrival"] - journeys["scheduled_departure"]
    ).dt.total_seconds() / 60.0
    journeys["arrival_delay_minutes"] = (
        journeys["actual_arrival"] - journeys["scheduled_arrival"]
    ).dt.total_seconds() / 60.0
    journeys["EJT_minutes"] = (
        journeys["actual_travel_minutes"] - journeys["scheduled_travel_minutes"]
    ).clip(lower=0.0)
    journeys["observed_arrival"] = (
        journeys["actual_arrival"].notna()
        & ~journeys["arrival_imputed"].fillna(False).astype(bool)
    )
    journeys["period"] = assign_time_period(clock_minutes(journeys["scheduled_departure"]))
    return journeys


def journey_period_summary(journeys: pd.DataFrame) -> pd.DataFrame:
    """Passenger-weighted travel-time and EJT summaries by departure period."""

    rows: list[dict[str, float | str]] = []
    for period in TIME_PERIODS_MINUTES:
        group = journeys.loc[
            journeys["period"].eq(period)
            & journeys["observed_arrival"]
            & journeys["passengers"].gt(0)
        ]
        if group.empty:
            continue
        weights = group["passengers"]
        actual_q = weighted_quantile(
            group["actual_travel_minutes"], [0.5, 0.9, 0.95], weights
        )
        scheduled_q = weighted_quantile(
            group["scheduled_travel_minutes"], [0.5, 0.9, 0.95], weights
        )
        rows.append(
            {
                "period": period,
                "passengers": float(weights.sum()),
                "actual_mean_minutes": float(np.average(group["actual_travel_minutes"], weights=weights)),
                "scheduled_mean_minutes": float(
                    np.average(group["scheduled_travel_minutes"], weights=weights)
                ),
                "actual_p50_minutes": actual_q[0],
                "actual_p90_minutes": actual_q[1],
                "actual_p95_minutes": actual_q[2],
                "scheduled_p50_minutes": scheduled_q[0],
                "scheduled_p90_minutes": scheduled_q[1],
                "scheduled_p95_minutes": scheduled_q[2],
                "EJT_seconds_per_passenger": float(
                    60.0 * np.average(group["EJT_minutes"], weights=weights)
                ),
            }
        )
    return pd.DataFrame(rows)


def od_metrics(
    journeys: pd.DataFrame,
    *,
    threshold_minutes: float = 3.0,
) -> pd.DataFrame:
    """Aggregate PP2, EJT, passenger volume, and delay burden by OD and period."""

    valid = journeys.loc[
        journeys["period"].notna()
        & journeys["observed_arrival"]
        & journeys["passengers"].gt(0)
    ].copy()
    valid["on_time_passengers"] = valid["passengers"].where(
        valid["arrival_delay_minutes"].le(threshold_minutes), 0.0
    )
    valid["weighted_ejt"] = valid["passengers"] * valid["EJT_minutes"]
    valid["passenger_delay_minutes"] = (
        valid["passengers"] * valid["arrival_delay_minutes"].clip(lower=0.0)
    )
    result = valid.groupby(
        ["period", "origin", "destination"], as_index=False, observed=True
    ).agg(
        passengers=("passengers", "sum"),
        on_time_passengers=("on_time_passengers", "sum"),
        weighted_ejt=("weighted_ejt", "sum"),
        passenger_delay_minutes=("passenger_delay_minutes", "sum"),
        observations=("passengers", "size"),
    )
    result["PP2"] = 100.0 * result["on_time_passengers"] / result["passengers"]
    result["EJT_minutes"] = result["weighted_ejt"] / result["passengers"]
    return result


def cancellation_adjusted_od_metrics(
    planned_journeys: pd.DataFrame,
    *,
    threshold_minutes: float = 3.0,
) -> pd.DataFrame:
    """OD-level PP2-C using all planned passenger journeys as denominator."""

    data = planned_journeys.loc[
        planned_journeys["period"].notna() & planned_journeys["passengers"].gt(0)
    ].copy()
    on_time = (
        data["actual_arrival"].notna()
        & data["arrival_delay_minutes"].le(threshold_minutes)
    )
    data["on_time_passengers"] = data["passengers"].where(on_time, 0.0)
    result = data.groupby(
        ["period", "origin", "destination"], as_index=False, observed=True
    ).agg(
        planned_passengers=("passengers", "sum"),
        on_time_passengers=("on_time_passengers", "sum"),
    )
    result["PP2_C"] = (
        100.0 * result["on_time_passengers"] / result["planned_passengers"]
    )
    return result


def expected_wait_table(actual: pd.DataFrame) -> pd.DataFrame:
    """Calculate EW once per train departure, station, and period."""

    data = weekdays(actual)
    data["period"] = assign_time_period(clock_minutes(data["Planerad_avgangstid"]))
    departures = data.drop_duplicates(MOVEMENT_KEYS).copy()
    rows: list[dict[str, float | str | int]] = []
    for (period, station), group in departures.loc[departures["period"].notna()].groupby(
        ["period", "Fran_platssignatur"], observed=True
    ):
        rows.append(
            {
                "period": str(period),
                "station": station,
                "EW_minutes": expected_waiting_time(group),
                "passengers": float(group["n_boarding"].sum()),
                "departures": int(group["headway"].gt(0).sum()),
            }
        )
    return pd.DataFrame(rows)


def period_definition_sensitivity(
    actual: pd.DataFrame,
    *,
    threshold_minutes: float = 3.0,
) -> pd.DataFrame:
    """Quantify the effects of weekends, legacy hour bins, and cohort definition."""

    data = parse_onboard_datetimes(actual)
    variants: list[tuple[str, pd.DataFrame]] = []

    legacy = data.copy()
    legacy["legacy_hour"] = legacy["Ankomsttid"].dt.hour
    legacy["period"] = pd.cut(
        legacy["legacy_hour"],
        bins=[6, 9, 15, 18],
        labels=list(TIME_PERIODS_MINUTES),
        ordered=False,
    ).astype("string")
    variants.append(("Report code: all days, legacy arrival-hour bins", legacy))

    arrival_all = data.copy()
    arrival_all["period"] = assign_time_period(clock_minutes(arrival_all["Ankomsttid"]))
    variants.append(("All days, corrected arrival-time bins", arrival_all))

    arrival_weekday = weekdays(data)
    arrival_weekday["period"] = assign_time_period(
        clock_minutes(arrival_weekday["Ankomsttid"])
    )
    variants.append(("Weekdays, corrected arrival-time bins", arrival_weekday))

    service_weekday = add_service_period(weekdays(data))
    variants.append(("Weekdays, scheduled service-start cohort", service_weekday))

    rows: list[dict[str, float | str]] = []
    for variant, frame in variants:
        for period in TIME_PERIODS_MINUTES:
            subset = frame.loc[frame["period"].eq(period)]
            final = subset.loc[subset["UppehallstypAnkomst"].eq("Sista")]
            otp = 100.0 * final["arr_delay_minutes"].le(threshold_minutes).mean()
            denominator = subset["n_alighting_next"].sum()
            pp2 = (
                100.0
                * subset.loc[
                    subset["arr_delay_minutes"].le(threshold_minutes),
                    "n_alighting_next",
                ].sum()
                / denominator
                if denominator > 0
                else np.nan
            )
            rows.extend(
                [
                    {"variant": variant, "period": period, "metric": "OTP", "score": otp},
                    {"variant": variant, "period": period, "metric": "PP2", "score": pp2},
                ]
            )
    return pd.DataFrame(rows)
