"""Traffic cleaning and passenger-assignment pipeline.

The original implementation lived in one long notebook and silently mixed
weekends, cancellations, and imputed observations.  These functions keep the
same case-study assumptions while making each policy explicit and testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    MOVEMENT_KEYS,
    STATIONS_NORTH_TO_SOUTH,
    STATIONS_SOUTH_TO_NORTH,
    TRAIN_KEYS,
)
from .utils import get_direction


DROP_COLUMNS = [
    "Tågordning uppdrag",
    "Tågslag",
    "Avgångsplats",
    "Ankomstplats",
    "Första platssignatur för uppdrag",
    "Sista platssignatur för uppdrag",
    "Inställelseorsakskod",
    "Inställelseorsak",
    "Dragfordonsid",
    "Framförda tågkm",
    "Rapporterad tågvikt",
    "Rapporterad tåglängd",
    "Antal rapporterade hjulaxlar",
    "Antal rapporterade vagnar",
]

RENAME_COLUMNS = {
    "Tåguppdrag": "Taguppdrag",
    "Tågnr": "Tagnr",
    "Datum (PAU)": "Datum",
    "UppehållstypAvgång": "UppehallstypAvgang",
    "UppehållstypAnkomst": "UppehallstypAnkomst",
    "Delsträckanummer": "Delstrackanummer",
    "Första platssignatur": "Forsta_platssignatur",
    "Sista platssignatur": "Sista_platssignatur",
    "Från platssignatur": "Fran_platssignatur",
    "Till platssignatur": "Till_platssignatur",
    "Sträcka med riktning": "Stracka_med_riktning",
    "Avgångstid": "Avgangstid",
    "Planerad ankomsttid": "Planerad_ankomsttid",
    "Planerad avgångstid": "Planerad_avgangstid",
}

DATETIME_COLUMNS = [
    "Datum",
    "Ankomsttid",
    "Avgangstid",
    "Planerad_ankomsttid",
    "Planerad_avgangstid",
]


def normalise_traffic_data(
    traffic: pd.DataFrame,
    *,
    weekdays_only: bool = True,
) -> pd.DataFrame:
    """Rename columns, parse timestamps, and select the declared study cohort."""

    data = traffic.drop(columns=[c for c in DROP_COLUMNS if c in traffic], errors="ignore")
    data = data.rename(columns=RENAME_COLUMNS).copy()
    required = {
        "Taguppdrag",
        "Tagnr",
        "Datum",
        "UppehallstypAvgang",
        "UppehallstypAnkomst",
        "Delstrackanummer",
        "Fran_platssignatur",
        "Till_platssignatur",
        "Ankomsttid",
        "Avgangstid",
        "Planerad_ankomsttid",
        "Planerad_avgangstid",
        "Planeringsstatus",
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Traffic data is missing columns: {sorted(missing)}")

    for column in DATETIME_COLUMNS:
        data[column] = pd.to_datetime(data[column], errors="coerce")
    data["Datum"] = data["Datum"].dt.normalize()
    if weekdays_only:
        data = data.loc[data["Datum"].dt.dayofweek.lt(5)].copy()
    return data


def merge_passage_movements(traffic: pd.DataFrame) -> pd.DataFrame:
    """Collapse the two movements surrounding every non-stopping station."""

    data = traffic.loc[
        ~(
            traffic["UppehallstypAvgang"].eq("Passage")
            & traffic["UppehallstypAnkomst"].eq("Passage")
        )
    ].copy()
    passage_departure = data.loc[data["UppehallstypAvgang"].eq("Passage")]
    passage_arrival = data.loc[data["UppehallstypAnkomst"].eq("Passage")]

    departure_groups = {
        key: group.sort_values("Delstrackanummer")
        for key, group in passage_departure.groupby(TRAIN_KEYS, sort=False)
    }
    arrival_groups = {
        key: group.sort_values("Delstrackanummer")
        for key, group in passage_arrival.groupby(TRAIN_KEYS, sort=False)
    }
    if departure_groups.keys() != arrival_groups.keys():
        raise ValueError("Passage arrival/departure train groups do not match")

    merged_groups: list[pd.DataFrame] = []
    fields_from_departure_side = [
        "UppehallstypAvgang",
        "Delstrackanummer",
        "Fran_platssignatur",
        "Avgangstid",
        "Planerad_avgangstid",
    ]
    fields_from_arrival_side = [
        "UppehallstypAnkomst",
        "Till_platssignatur",
        "Ankomsttid",
        "Planerad_ankomsttid",
    ]
    for key, arrivals in arrival_groups.items():
        departures = departure_groups[key]
        if len(arrivals) != len(departures):
            raise ValueError(
                f"Unequal passage observations for train {key}: "
                f"{len(arrivals)} arrivals and {len(departures)} departures"
            )
        merged = departures.copy().reset_index(drop=True)
        arrivals = arrivals.reset_index(drop=True)
        for column in fields_from_departure_side:
            merged[column] = arrivals[column]
        for column in fields_from_arrival_side:
            merged[column] = departures.reset_index(drop=True)[column]
        merged_groups.append(merged)

    stopping = data.loc[
        ~(
            data["UppehallstypAvgang"].eq("Passage")
            | data["UppehallstypAnkomst"].eq("Passage")
        )
    ].copy()
    result = pd.concat([stopping, *merged_groups], ignore_index=True)
    result = result.sort_values(TRAIN_KEYS + ["Delstrackanummer"]).reset_index(drop=True)
    result["Delstrackanummer"] = result.groupby(TRAIN_KEYS, sort=False).cumcount() + 1

    first_date = result["Datum"].min()
    incomplete_previous_service = (
        result["Planerad_avgangstid"].dt.normalize().eq(first_date)
        & result["Planerad_avgangstid"].dt.hour.lt(2)
    )
    return result.loc[~incomplete_previous_service].reset_index(drop=True)


def _apply_cancellation_policy(traffic: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == "planned":
        return traffic.copy()
    if mode != "actual":
        raise ValueError("mode must be 'actual' or 'planned'")

    retained: list[pd.DataFrame] = []
    for _, group in traffic.groupby(TRAIN_KEYS, sort=False):
        group = group.sort_values("Delstrackanummer")
        first = group.loc[group["UppehallstypAvgang"].eq("Första")]
        if not first.empty and first.iloc[0]["Planeringsstatus"] == "I":
            continue
        cancelled = group.loc[group["Planeringsstatus"].eq("I"), "Delstrackanummer"]
        if not cancelled.empty:
            group = group.loc[group["Delstrackanummer"].lt(cancelled.min())]
        if not group.empty:
            retained.append(group)
    if not retained:
        return traffic.iloc[0:0].copy()
    return pd.concat(retained, ignore_index=True)


def _impute_non_cancelled_times(traffic: pd.DataFrame) -> pd.DataFrame:
    """Impute operational times needed for assignment and retain provenance flags."""

    data = traffic.copy()
    runtime = data["Planerad_ankomsttid"] - data["Planerad_avgangstid"]
    data["arrival_time_imputed"] = False
    data["departure_time_imputed"] = False

    missing_arrival = data["Ankomsttid"].isna() & data["Avgangstid"].notna()
    data.loc[missing_arrival, "Ankomsttid"] = data.loc[missing_arrival, "Avgangstid"] + runtime
    data.loc[missing_arrival, "arrival_time_imputed"] = True

    missing_departure = data["Avgangstid"].isna() & data["Ankomsttid"].notna()
    data.loc[missing_departure, "Avgangstid"] = data.loc[missing_departure, "Ankomsttid"] - runtime
    data.loc[missing_departure, "departure_time_imputed"] = True

    both_missing = data["Avgangstid"].isna() & data["Ankomsttid"].isna()
    data.loc[both_missing, "Avgangstid"] = data.loc[both_missing, "Planerad_avgangstid"]
    data.loc[both_missing, "Ankomsttid"] = data.loc[both_missing, "Planerad_ankomsttid"]
    data.loc[both_missing, ["arrival_time_imputed", "departure_time_imputed"]] = True

    data["arrival_time_suspect"] = (
        (data["Ankomsttid"] - data["Planerad_ankomsttid"]).dt.total_seconds() / 60.0
    ).lt(-10)
    return data


def _service_minutes(values: pd.Series, service_date: pd.Series) -> pd.Series:
    return (pd.to_datetime(values) - pd.to_datetime(service_date)).dt.total_seconds() / 60.0


def add_operational_columns(traffic: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Add signed delays, directions, clock positions, and date-aware headways."""

    data = traffic.copy()
    if mode == "actual":
        data = _impute_non_cancelled_times(data)
        departure = "Avgangstid"
        arrival = "Ankomsttid"
    elif mode == "planned":
        data["arrival_time_imputed"] = False
        data["departure_time_imputed"] = False
        data["arrival_time_suspect"] = False
        departure = "Planerad_avgangstid"
        arrival = "Planerad_ankomsttid"
    else:
        raise ValueError("mode must be 'actual' or 'planned'")

    data["dep_delay_minutes"] = (
        data["Avgangstid"] - data["Planerad_avgangstid"]
    ).dt.total_seconds() / 60.0
    data["arr_delay_minutes"] = (
        data["Ankomsttid"] - data["Planerad_ankomsttid"]
    ).dt.total_seconds() / 60.0
    data["dep_delay"] = data["Avgangstid"] - data["Planerad_avgangstid"]
    data["arr_delay"] = data["Ankomsttid"] - data["Planerad_ankomsttid"]
    data["dep_service_minutes"] = _service_minutes(data[departure], data["Datum"])
    data["arr_service_minutes"] = _service_minutes(data[arrival], data["Datum"])
    data["dep_t_float"] = data["dep_service_minutes"] / 15.0
    data["arr_t_float"] = data["arr_service_minutes"] / 15.0
    data["direction"] = [
        get_direction(origin, destination)
        for origin, destination in zip(
            data["Fran_platssignatur"], data["Till_platssignatur"], strict=True
        )
    ]
    data = data.sort_values(
        ["Datum", "direction", "Fran_platssignatur", departure]
    ).copy()
    data["previous_departure"] = data.groupby(
        ["Datum", "direction", "Fran_platssignatur"], sort=False
    )[departure].shift()
    data["prev_dep_t_float"] = _service_minutes(
        data["previous_departure"], data["Datum"]
    ) / 15.0
    data["headway"] = (
        data[departure] - data["previous_departure"]
    ).dt.total_seconds() / 60.0
    return data.sort_values(TRAIN_KEYS + ["Delstrackanummer"]).reset_index(drop=True)


def prepare_traffic_data(
    traffic: pd.DataFrame,
    *,
    mode: str,
    weekdays_only: bool = True,
) -> pd.DataFrame:
    """Run the complete traffic preprocessing policy for one time basis."""

    normalised = normalise_traffic_data(traffic, weekdays_only=weekdays_only)
    movements = merge_passage_movements(normalised)
    movements = _apply_cancellation_policy(movements, mode)
    return add_operational_columns(movements, mode)


def _demand_cube(
    demand: Mapping[int, pd.DataFrame],
) -> tuple[np.ndarray, dict[str, int]]:
    missing = set(range(96)).difference(demand)
    if missing:
        raise ValueError(f"Demand matrices are missing periods: {sorted(missing)}")
    template = demand[0]
    stations = [
        station
        for station in STATIONS_NORTH_TO_SOUTH
        if station in template.index and station in template.columns
    ]
    if len(stations) != len(STATIONS_NORTH_TO_SOUTH):
        missing_stations = set(STATIONS_NORTH_TO_SOUTH).difference(stations)
        raise ValueError(f"Demand matrices are missing case-study stations: {sorted(missing_stations)}")
    cube = np.stack(
        [demand[period].reindex(index=stations, columns=stations).to_numpy(float) for period in range(96)]
    )
    return cube, {station: i for i, station in enumerate(stations)}


def _integrate_demand(
    rates_per_interval: np.ndarray,
    start_minute: float,
    end_minute: float,
) -> np.ndarray:
    """Integrate 15-minute OD totals over a possibly fractional interval."""

    start = float(np.clip(start_minute, 0.0, 24.0 * 60.0))
    end = float(np.clip(end_minute, 0.0, 24.0 * 60.0))
    if not np.isfinite(start) or not np.isfinite(end) or end <= start:
        return np.zeros(rates_per_interval.shape[1], dtype=float)
    first = int(np.floor(start / 15.0))
    last = int(np.ceil(end / 15.0))
    total = np.zeros(rates_per_interval.shape[1], dtype=float)
    for period in range(first, min(last, 96)):
        overlap = max(
            0.0,
            min(end, (period + 1) * 15.0) - max(start, period * 15.0),
        )
        total += rates_per_interval[period] * (overlap / 15.0)
    return total


def assign_passengers(
    traffic: pd.DataFrame,
    demand: Mapping[int, pd.DataFrame],
    *,
    mode: str,
) -> pd.DataFrame:
    """Assign time-dependent OD demand to departures and propagate on-board loads."""

    cube, station_positions = _demand_cube(demand)
    station_columns = list(STATIONS_NORTH_TO_SOUTH)
    output = traffic.reset_index(drop=True).copy()
    passenger_matrix = np.zeros((len(output), len(station_columns)), dtype=float)
    departure_minutes = "dep_service_minutes"
    origins = output["Fran_platssignatur"].to_numpy()
    current_departures = output[departure_minutes].to_numpy(dtype=float)
    previous_departures = output["prev_dep_t_float"].to_numpy(dtype=float) * 15.0
    for position in range(len(output)):
        origin = origins[position]
        origin_position = station_positions.get(origin)
        if origin_position is None:
            continue
        current = current_departures[position]
        previous = previous_departures[position]
        if not np.isfinite(previous):
            previous = 0.0
        passenger_matrix[position] = _integrate_demand(
            cube[:, origin_position, :], previous, current
        )

    n_boarding = np.zeros(len(output), dtype=float)
    n_alighting = np.zeros(len(output), dtype=float)
    n_alighting_next = np.zeros(len(output), dtype=float)
    n_onboard = np.zeros(len(output), dtype=float)
    destinations = output["Till_platssignatur"].to_numpy()
    station_set = set(station_columns)
    for indices in output.groupby(TRAIN_KEYS, sort=False).groups.values():
        positions = np.asarray(list(indices), dtype=int)
        order = np.argsort(output.loc[positions, "Delstrackanummer"].to_numpy())
        positions = positions[order]
        route_destinations = destinations[positions]
        for route_position, row_position in enumerate(positions):
            future = station_set.intersection(route_destinations[route_position:])
            keep_positions = [station_positions[station] for station in future]
            invalid_positions = [
                station_positions[station] for station in station_set.difference(future)
            ]
            passenger_matrix[row_position, invalid_positions] = 0.0
            boarding = passenger_matrix[row_position, keep_positions].sum()
            n_boarding[row_position] = boarding
            if route_position == 0:
                alighting = 0.0
                onboard = boarding
            else:
                origin_position = station_positions[origins[row_position]]
                alighting = passenger_matrix[positions[:route_position], origin_position].sum()
                onboard = n_onboard[positions[route_position - 1]] + boarding - alighting
            destination_position = station_positions[destinations[row_position]]
            alighting_next = passenger_matrix[
                positions[: route_position + 1], destination_position
            ].sum()
            n_alighting[row_position] = alighting
            n_onboard[row_position] = max(float(onboard), 0.0)
            n_alighting_next[row_position] = alighting_next

    output[station_columns] = passenger_matrix
    output["n_boarding"] = n_boarding
    output["n_alighting"] = n_alighting
    output["n_alighting_next"] = n_alighting_next
    output["n_onboard"] = n_onboard
    return output.sort_values(TRAIN_KEYS + ["Delstrackanummer"]).reset_index(drop=True)


def build_onboard_dataset(
    traffic: pd.DataFrame,
    demand: Mapping[int, pd.DataFrame],
    *,
    mode: str,
    weekdays_only: bool = True,
) -> pd.DataFrame:
    """Build the canonical actual- or planned-departure passenger table."""

    prepared = prepare_traffic_data(
        traffic,
        mode=mode,
        weekdays_only=weekdays_only,
    )
    return assign_passengers(prepared, demand, mode=mode)


def write_onboard_dataset(data: pd.DataFrame, output_file: str | Path) -> Path:
    """Write a derived table, creating only its immediate output directory."""

    path = Path(output_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False)
    return path


# Backward-compatible name used by the original source module.
def process_traffic_data(df: pd.DataFrame) -> pd.DataFrame:
    return prepare_traffic_data(df, mode="actual", weekdays_only=True)
