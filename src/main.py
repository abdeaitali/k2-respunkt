"""Command-line entry point for rebuilding and summarising the case study."""

from __future__ import annotations

import argparse
from pathlib import Path

from .analysis import punctuality_summary
from .processing import build_onboard_dataset, write_onboard_dataset
from .reading_data import (
    VISUALISATION_DIR,
    get_demand_data,
    get_onboard_data,
    get_traffic_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild-onboard",
        action="store_true",
        help="Regenerate actual and planned passenger assignment CSVs first.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional CSV path for the corrected 3-minute metric summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rebuild_onboard:
        traffic = get_traffic_data()
        demand = get_demand_data()
        for mode in ["planned", "actual"]:
            onboard = build_onboard_dataset(
                traffic,
                demand,
                mode=mode,
                weekdays_only=True,
            )
            write_onboard_dataset(
                onboard,
                VISUALISATION_DIR / f"df_onboard_{mode}.csv",
            )

    summary = punctuality_summary(
        get_onboard_data("actual"),
        get_onboard_data("planned"),
    )
    print(summary.to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    if args.summary_output:
        output = args.summary_output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(output, index=False)


if __name__ == "__main__":
    main()
