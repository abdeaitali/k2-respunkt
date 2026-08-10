"""Shared constants for the Stockholm commuter-rail case study."""

from __future__ import annotations


STATIONS_SOUTH_TO_NORTH = [
    "Bål",
    "Bro",
    "Kän",
    "Khä",
    "Jkb",
    "Bkb",
    "Spå",
    "Sub",
    "Ke",
    "Cst",
    "Sst",
    "Åbe",
    "Äs",
    "Fas",
    "Tåd",
    "Skg",
    "Hnd",
    "Jbo",
    "Vhe",
    "Kda",
    "Ts",
    "Hfa",
    "Ssä",
    "Öso",
    "Ngd",
    "Gdv",
    "Nyh",
]

STATIONS_NORTH_TO_SOUTH = list(reversed(STATIONS_SOUTH_TO_NORTH))
TRAIN_KEYS = ["Datum", "Taguppdrag", "Tagnr"]
MOVEMENT_KEYS = TRAIN_KEYS + ["Delstrackanummer"]

# Half-open intervals avoid double counting services on period boundaries.
TIME_PERIODS_MINUTES = {
    "Morning peak": (6 * 60, 9 * 60),
    "Midday off-peak": (9 * 60, 15 * 60),
    "Afternoon peak": (15 * 60, 18 * 60),
}
