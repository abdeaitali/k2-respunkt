from __future__ import annotations

import numpy as np
import pandas as pd

from src.processing import _integrate_demand, process_traffic_data


def _raw_row(date: str) -> dict[str, object]:
    timestamp = pd.Timestamp(date) + pd.Timedelta(hours=7)
    return {
        "Tåguppdrag": 1,
        "Tågnr": 1,
        "Datum (PAU)": date,
        "UppehållstypAvgång": "Första",
        "UppehållstypAnkomst": "Sista",
        "Delsträckanummer": 1,
        "Första platssignatur": "BÅL",
        "Sista platssignatur": "NYH",
        "Från platssignatur": "Bål",
        "Till platssignatur": "Bro",
        "Sträcka med riktning": "Bål-Bro",
        "Ankomsttid": timestamp + pd.Timedelta(minutes=5),
        "Avgångstid": timestamp,
        "Planerad ankomsttid": timestamp + pd.Timedelta(minutes=5),
        "Planerad avgångstid": timestamp,
        "Inställtflagga": "N",
        "Planeringsstatus": "P",
    }


def test_process_traffic_data_returns_weekdays_and_signed_delays() -> None:
    traffic = pd.DataFrame([_raw_row("2015-09-18"), _raw_row("2015-09-19")])
    result = process_traffic_data(traffic)
    assert len(result) == 1
    assert result.iloc[0]["Datum"].dayofweek == 4
    assert result.iloc[0]["arr_delay_minutes"] == 0.0
    assert result.iloc[0]["direction"] == 1


def test_integrate_demand_handles_fractional_intervals() -> None:
    rates = np.tile(np.array([[10.0, 20.0]]), (96, 1))
    np.testing.assert_allclose(_integrate_demand(rates, 0.0, 7.5), [5.0, 10.0])
    np.testing.assert_allclose(_integrate_demand(rates, 7.5, 22.5), [10.0, 20.0])
