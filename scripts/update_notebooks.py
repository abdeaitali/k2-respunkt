"""Replace legacy analysis notebooks with portable, reproducible workflows.

The demand notebook contains useful bespoke plots and has local user edits, so it
is patched in place instead of being regenerated.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
VIS = ROOT / "vizualisation"
TESTS = ROOT / "tests"

SETUP = """from pathlib import Path
import sys
import pandas as pd
from IPython.display import Image, Markdown, display

ROOT = Path.cwd().resolve()
while not (ROOT / 'src').is_dir() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / 'output'
pd.set_option('display.max_columns', 100)
pd.set_option('display.float_format', lambda value: f'{value:,.2f}')
"""


def markdown(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def write_notebook(path: Path, title: str, purpose: str, cells: list) -> None:
    notebook = nbf.v4.new_notebook()
    notebook["cells"] = [
        markdown(f"# {title}\n\n{purpose}"),
        code(SETUP),
        *cells,
    ]
    notebook["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, path)


def patch_demand_notebook() -> None:
    """Make paths portable while preserving the user's chart formatting edits."""

    path = TESTS / "viz_demand.ipynb"
    notebook = nbf.read(path, as_version=4)
    notebook.nbformat_minor = 5
    marker = "# Portable project-root discovery (added during the reproducibility review)"
    if not notebook.cells or marker not in notebook.cells[0].source:
        notebook.cells.insert(0, code(f"{marker}\n" + SETUP))

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source
        source = source.replace(
            "'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/OD_data_dynamic.xlsx'",
            "str(ROOT / 'data' / 'OD_data_dynamic.xlsx')",
        )
        source = source.replace(
            "ax.set_yticks(index, fontsize=12)",
            "ax.set_yticks(index)\nax.tick_params(axis='y', labelsize=12)",
        )
        source = source.replace(
            "ax.set_yticks(index, fontsize=f_size_ticks)",
            "ax.set_yticks(index)\nax.tick_params(axis='y', labelsize=f_size_ticks)",
        )
        source = source.replace("freq='15T'", "freq='15min'")
        # Remove only immediately repeated show calls; keep every intended plot.
        lines = source.splitlines()
        cleaned: list[str] = []
        for line in lines:
            if line.strip() == "plt.show()" and cleaned and cleaned[-1].strip() == "plt.show()":
                continue
            cleaned.append(line)
        cell.source = "\n".join(cleaned)
    nbf.write(notebook, path)


def main() -> None:
    write_notebook(
        VIS / "case_study_reanalysis.ipynb",
        "Passenger-centric punctuality: corrected case-study reanalysis",
        "Canonical notebook. It regenerates every corrected table and figure from the tested library code.",
        [
            code("""from scripts.run_case_study_analysis import run

legacy = ROOT / 'tmp' / 'legacy_derived' / 'df_onboard_actual.csv'
run(OUTPUT, legacy if legacy.exists() else None)
display(Markdown((OUTPUT / 'analysis_report.md').read_text(encoding='utf-8')))"""),
            code("""for figure in sorted((OUTPUT / 'figures').glob('*.png')):
    display(Markdown(f'### {figure.stem.replace("_", " ").title()}'))
    display(Image(filename=str(figure)))"""),
        ],
    )

    write_notebook(
        VIS / "viz_main_merge.ipynb",
        "Passenger assignment and data validation",
        "Audits the regenerated weekday onboard tables, provenance flags, and passenger conservation.",
        [
            code("""from src.constants import TRAIN_KEYS
from src.reading_data import get_onboard_data

actual = get_onboard_data('actual')
planned = get_onboard_data('planned')

def maximum_service_residual(data):
    totals = data.groupby(TRAIN_KEYS)[['n_boarding', 'n_alighting']].sum()
    return (totals['n_boarding'] - totals['n_alighting']).abs().max()

validation = pd.DataFrame({
    'dataset': ['actual', 'planned'],
    'rows': [len(actual), len(planned)],
    'services': [actual[TRAIN_KEYS].drop_duplicates().shape[0], planned[TRAIN_KEYS].drop_duplicates().shape[0]],
    'dates': [actual['Datum'].dt.normalize().nunique(), planned['Datum'].dt.normalize().nunique()],
    'maximum_service_passenger_residual': [maximum_service_residual(actual), maximum_service_residual(planned)],
})
display(validation)"""),
            code("""flags = [column for column in actual.columns if column.endswith('_imputed')]
pd.DataFrame({
    'flag': flags,
    'rows': [int(actual[column].sum()) for column in flags],
    'share_percent': [100 * actual[column].mean() for column in flags],
})"""),
            code("display(Image(filename=str(OUTPUT / 'figures' / '01_data_quality.png')))")
        ],
    )

    write_notebook(
        VIS / "viz_main_OTP_CPM.ipynb",
        "Operational and completed-passenger punctuality",
        "Reports corrected weekday OTP and CPM using half-open service periods and date-aware services.",
        [
            code("""summary = pd.read_csv(OUTPUT / 'tables' / 'corrected_metric_summary.csv')
display(summary.loc[summary.metric.isin(['OTP', 'CPM'])])"""),
            code("display(Image(filename=str(OUTPUT / 'figures' / '02_punctuality_curves.png')))")
        ],
    )

    write_notebook(
        VIS / "viz_main_PP2_OTP.ipynb",
        "OTP, PP2, CPM, and cancellation-adjusted PP2",
        "Compares train and passenger metrics and quantifies sensitivity to the original period/weekend choices.",
        [
            code("""summary = pd.read_csv(OUTPUT / 'tables' / 'corrected_metric_summary.csv')
sensitivity = pd.read_csv(OUTPUT / 'tables' / 'period_definition_sensitivity.csv')
display(summary)
display(sensitivity)"""),
            code("""display(Image(filename=str(OUTPUT / 'figures' / '03_metric_summary.png')))
display(Image(filename=str(OUTPUT / 'figures' / '04_period_sensitivity.png')))"""),
        ],
    )

    write_notebook(
        VIS / "viz_main_off_peak.ipynb",
        "Off-peak passenger journey reliability",
        "Uses passenger-weighted journey distributions and keyed origin–destination metrics.",
        [
            code("""journeys = pd.read_csv(OUTPUT / 'tables' / 'journey_time_summary.csv')
od = pd.read_csv(OUTPUT / 'tables' / 'od_metrics.csv')
display(journeys.loc[journeys.period.eq('midday')])
display(od.loc[od.period.eq('midday')].nlargest(15, 'affected_planned_passengers'))"""),
            code("""display(Image(filename=str(OUTPUT / 'figures' / '05_weighted_journey_quantiles.png')))
display(Image(filename=str(OUTPUT / 'figures' / '06_od_reliability.png')))"""),
        ],
    )

    write_notebook(
        VIS / "viz_main_peak.ipynb",
        "Peak-period journey time and expected waiting",
        "Applies one service definition throughout and computes expected waiting once per station departure sequence.",
        [
            code("""journeys = pd.read_csv(OUTPUT / 'tables' / 'journey_time_summary.csv')
waiting = pd.read_csv(OUTPUT / 'tables' / 'expected_wait_by_station.csv')
display(journeys.loc[journeys.period.isin(['morning', 'afternoon'])])
display(waiting.groupby('period', as_index=False).agg(mean_EW_minutes=('EW_minutes', 'mean')))"""),
            code("""display(Image(filename=str(OUTPUT / 'figures' / '07_expected_wait.png')))
display(Image(filename=str(OUTPUT / 'figures' / '08_od_risk_comparison.png')))"""),
        ],
    )

    write_notebook(
        VIS / "viz_main_pax_delay.ipynb",
        "Station arrival delay and alighting-passenger weighting",
        "Aggregates each arrival station over the morning, midday, and afternoon periods and contrasts unweighted with alighting-passenger-weighted delay.",
        [
            code("""impact = pd.read_csv(OUTPUT / 'tables' / 'station_period_ridership_impact.csv')
display(impact.nlargest(12, 'weighting_difference_minutes')[
    ['period', 'station', 'train_arrivals', 'total_alighting_passengers',
     'mean_station_arrival_delay_minutes', 'passenger_weighted_arrival_delay_minutes',
     'accumulated_station_arrival_delay_hours', 'passenger_delay_hours']
])"""),
            code("""display(Image(filename=str(OUTPUT / 'figures' / '09_station_ridership_weighting.png')))
display(Image(filename=str(OUTPUT / 'figures' / '10_station_accumulated_delay.png')))"""),
        ],
    )

    write_notebook(
        TESTS / "viz_traffic.ipynb",
        "Traffic data exploratory audit",
        "Checks coverage, cancellation codes, temporal scope, and missing timestamps in the raw AVL extract.",
        [
            code("""from src.reading_data import get_traffic_data

raw = get_traffic_data(parse_dates=True)
train_column = next(column for column in raw if column.endswith('gnr'))
task_column = next(column for column in raw if column.endswith('guppdrag'))
departure_column = next(
    column for column in raw
    if column.lower().startswith('avg') and 'planerad' not in column.lower()
)
cancelled_column = next(column for column in raw if column.endswith('lltflagga'))
audit = pd.Series({
    'rows': len(raw),
    'services': raw[['Datum (PAU)', task_column, train_column]].drop_duplicates().shape[0],
    'dates': raw['Datum (PAU)'].dt.normalize().nunique(),
    'weekday_rows_percent': 100 * raw['Datum (PAU)'].dt.dayofweek.lt(5).mean(),
    'missing_actual_arrival_percent': 100 * raw['Ankomsttid'].isna().mean(),
    'missing_actual_departure_percent': 100 * raw[departure_column].isna().mean(),
})
display(audit.to_frame('value'))
display(raw[['Planeringsstatus', cancelled_column]].value_counts(dropna=False).to_frame('rows'))"""),
            code("""daily = (raw.assign(date=raw['Datum (PAU)'].dt.normalize())
         .groupby('date')
         .agg(rows=(train_column, 'size'), services=(task_column, 'nunique')))
display(daily.describe())
display(Image(filename=str(OUTPUT / 'figures' / '01_data_quality.png')))"""),
        ],
    )

    patch_demand_notebook()


if __name__ == "__main__":
    main()
