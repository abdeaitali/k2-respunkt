from __future__ import annotations

import pandas as pd

from src.analysis import build_passenger_journeys, journey_period_summary


def test_passenger_journeys_are_volume_weighted() -> None:
    date = pd.Timestamp("2015-09-18")
    rows = [
        {
            "Datum": date,
            "Taguppdrag": 1,
            "Tagnr": 1,
            "Delstrackanummer": 1,
            "Fran_platssignatur": "Bål",
            "Till_platssignatur": "Bro",
            "Avgangstid": date + pd.Timedelta(hours=7),
            "Ankomsttid": date + pd.Timedelta(hours=7, minutes=5),
            "Planerad_avgangstid": date + pd.Timedelta(hours=7),
            "Planerad_ankomsttid": date + pd.Timedelta(hours=7, minutes=5),
            "Planeringsstatus": "P",
            "headway": 15.0,
            "direction": 1,
            "Bål": 0.0,
            "Bro": 2.0,
            "Kän": 8.0,
        },
        {
            "Datum": date,
            "Taguppdrag": 1,
            "Tagnr": 1,
            "Delstrackanummer": 2,
            "Fran_platssignatur": "Bro",
            "Till_platssignatur": "Kän",
            "Avgangstid": date + pd.Timedelta(hours=7, minutes=6),
            "Ankomsttid": date + pd.Timedelta(hours=7, minutes=12),
            "Planerad_avgangstid": date + pd.Timedelta(hours=7, minutes=6),
            "Planerad_ankomsttid": date + pd.Timedelta(hours=7, minutes=11),
            "Planeringsstatus": "P",
            "headway": 15.0,
            "direction": 1,
            "Bål": 0.0,
            "Bro": 0.0,
            "Kän": 1.0,
        },
    ]
    journeys = build_passenger_journeys(pd.DataFrame(rows))
    assert len(journeys) == 3
    assert journeys["passengers"].sum() == 11.0
    summary = journey_period_summary(journeys)
    morning = summary.loc[summary["period"].eq("Morning peak")].iloc[0]
    assert morning["passengers"] == 11.0
    assert morning["actual_p50_minutes"] == 12.0
