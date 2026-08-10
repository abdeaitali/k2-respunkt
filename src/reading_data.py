"""Portable, validated readers for the project data files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
VISUALISATION_DIR = PROJECT_ROOT / "vizualisation"


def _existing_path(path: str | Path | None, default: Path) -> Path:
    resolved = Path(path) if path is not None else default
    resolved = resolved.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Data file not found: {resolved}")
    return resolved


def get_traffic_data(
    input_file: str | Path | None = None,
    *,
    parse_dates: bool = False,
) -> pd.DataFrame:
    """Read the filtered 2015 AVL extract without relying on a user path."""

    path = _existing_path(input_file, DATA_DIR / "RST_2015_v38_42.csv")
    data = pd.read_csv(path, sep=";", low_memory=False)
    if parse_dates:
        for column in [
            "Datum (PAU)",
            "Ankomsttid",
            "Avgångstid",
            "Planerad ankomsttid",
            "Planerad avgångstid",
        ]:
            data[column] = pd.to_datetime(data[column], errors="coerce")
    return data

def get_demand_data(
    input_file: str | Path | None = None,
    *,
    periods: Iterable[int] = range(96),
) -> dict[int, pd.DataFrame]:
    """Read the 15-minute OD matrices and restore their station labels."""

    path = _existing_path(input_file, DATA_DIR / "OD_data_dynamic.xlsx")
    requested = list(periods)
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        static = pd.read_excel(workbook, sheet_name="Static", index_col=0, header=0)
        sheets: dict[int, pd.DataFrame] = {}
        for period in requested:
            sheet_name = f"Sheet{period + 1}"
            if sheet_name not in workbook.sheet_names:
                raise ValueError(f"Missing demand sheet {sheet_name!r} in {path.name}")
            matrix = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
            matrix = matrix.iloc[: len(static.index), : len(static.columns)].copy()
            if matrix.shape != static.shape:
                raise ValueError(
                    f"{sheet_name} has shape {matrix.shape}; expected {static.shape}"
                )
            matrix.index = static.index
            matrix.columns = static.columns
            sheets[period] = matrix.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return sheets


def get_onboard_data(
    kind: str = "actual",
    input_file: str | Path | None = None,
) -> pd.DataFrame:
    """Read a derived passenger-on-board table with datetime columns parsed."""

    if kind not in {"actual", "planned"}:
        raise ValueError("kind must be 'actual' or 'planned'")
    path = _existing_path(
        input_file,
        VISUALISATION_DIR / f"df_onboard_{kind}.csv",
    )
    data = pd.read_csv(path, low_memory=False)
    for column in [
        "Datum",
        "Ankomsttid",
        "Avgangstid",
        "Planerad_ankomsttid",
        "Planerad_avgangstid",
    ]:
        if column in data:
            data[column] = pd.to_datetime(data[column], errors="coerce")
    return data
