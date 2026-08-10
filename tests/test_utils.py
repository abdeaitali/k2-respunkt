from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils import (
    assign_time_period,
    expected_waiting_time,
    on_time_curve,
    weighted_quantile,
)


def test_time_periods_are_half_open() -> None:
    minutes = pd.Series([359.9, 360.0, 539.9, 540.0, 899.9, 900.0, 1079.9, 1080.0])
    result = assign_time_period(minutes)
    assert result.tolist() == [
        pd.NA,
        "Morning peak",
        "Morning peak",
        "Midday off-peak",
        "Midday off-peak",
        "Afternoon peak",
        "Afternoon peak",
        pd.NA,
    ]


def test_on_time_curve_uses_eligible_denominator_and_weights() -> None:
    scores = on_time_curve(
        pd.Series([1.0, 4.0, np.nan]),
        [1.0, 3.0, 5.0],
        weights=pd.Series([3.0, 1.0, 20.0]),
        eligible=pd.Series([True, True, False]),
    )
    np.testing.assert_allclose(scores, [0.75, 0.75, 1.0])


def test_weighted_quantile_respects_passenger_volume() -> None:
    result = weighted_quantile([1.0, 10.0], [0.5, 0.95], [9.0, 1.0])
    np.testing.assert_allclose(result, [1.0, 10.0])


def test_expected_waiting_time_counts_each_departure_once() -> None:
    departures = pd.DataFrame({"headway": [10.0, 20.0], "n_boarding": [10.0, 30.0]})
    assert expected_waiting_time(departures) == 8.75
