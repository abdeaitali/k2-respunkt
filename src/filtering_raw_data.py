"""Filter a full Trafikverket traffic export to the Bål-Nyh case-study line."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .constants import STATIONS_SOUTH_TO_NORTH


def filter_raw_traffic(
    input_file: str | Path,
    output_file: str | Path,
    *,
    start_date: str = "2015-09-14",
    end_date: str = "2015-10-18",
    chunksize: int = 1_000_000,
) -> Path:
    """Stream-filter passenger trains whose task endpoints are on the line."""

    source = Path(input_file).expanduser().resolve()
    target = Path(output_file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)

    station_codes = {station.upper() for station in STATIONS_SOUTH_TO_NORTH}
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    wrote_header = False
    for chunk in pd.read_csv(source, sep=";", chunksize=chunksize, low_memory=False):
        required = {
            "Datum (PAU)",
            "Tågslag",
            "Första platssignatur",
            "Sista platssignatur",
        }
        missing = required.difference(chunk.columns)
        if missing:
            raise ValueError(f"Raw export is missing columns: {sorted(missing)}")
        dates = pd.to_datetime(chunk["Datum (PAU)"], errors="coerce")
        selected = chunk.loc[
            dates.between(start, end, inclusive="both")
            & chunk["Tågslag"].eq("RST")
            & chunk["Första platssignatur"].str.upper().isin(station_codes)
            & chunk["Sista platssignatur"].str.upper().isin(station_codes)
        ]
        if selected.empty:
            continue
        selected.to_csv(
            target,
            sep=";",
            mode="a" if wrote_header else "w",
            header=not wrote_header,
            index=False,
        )
        wrote_header = True
    if not wrote_header:
        raise ValueError("No rows matched the requested filters")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--start-date", default="2015-09-14")
    parser.add_argument("--end-date", default="2015-10-18")
    args = parser.parse_args()
    print(
        filter_raw_traffic(
            args.input_file,
            args.output_file,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    )


if __name__ == "__main__":
    main()
