# Passenger-centric punctuality on Stockholm commuter rail

This repository reproduces and extends the Bål–Nynäshamn case study from *Exploring measures to monitor passenger-centric punctuality*. It combines five weeks of train movement records with 15-minute origin–destination demand matrices, assigns passenger demand to services, and compares operational punctuality with passenger-weighted reliability.

The 2026 reproducibility review replaced hard-coded paths and notebook-only calculations with tested library functions, regenerated the weekday passenger-assignment tables, and reran every notebook.

## Corrected headline results

At the 3-minute threshold:

| Period | OTP | PP2 | CPM | PP2-C |
|---|---:|---:|---:|---:|
| Morning peak | 88.8% | 83.2% | 72.1% | 72.1% |
| Midday off-peak | 94.7% | 94.1% | 90.6% | 88.4% |
| Afternoon peak | 87.2% | 83.3% | 73.6% | 75.7% |

- **OTP**: observed terminal arrivals within 3 minutes, excluding imputed terminal arrivals.
- **PP2**: observed completed passenger journeys arriving within 3 minutes, weighted by estimated passengers.
- **CPM**: planned services completed within 3 minutes; cancellations and missing completions fail.
- **PP2-C**: planned passenger journeys completed within 3 minutes; this is a conservative cancellation-sensitive measure, not an eventual-arrival re-routing model.

The review found three material reasons the original report-code figures were optimistic or hard to interpret:

1. The report described workdays, but the derived tables included all 35 calendar days and repeated a typical-workday demand matrix on 10 weekend days.
2. `pd.cut([6, 9, 15, 18])` used right-closed integer-hour bins, excluding 06:00–06:59 and assigning boundary hours to the preceding period.
3. Journey-time percentiles treated every train–OD cell equally. The corrected passenger-weighted morning median is 17 minutes, versus 28 minutes in the legacy unweighted calculation.

See [the full analysis report](output/analysis_report.md), [all result tables](output/tables), [the updated figures](output/figures), and [the data requirements](DATA_REQUIREMENTS.md).

## Reproduce

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest
```

Rebuild the passenger-on-board datasets from the raw traffic and OD files:

```powershell
.venv\Scripts\python.exe -m src.main --rebuild-onboard --summary-output output\corrected_metric_summary.csv
```

Regenerate all analysis tables and figures:

```powershell
.venv\Scripts\python.exe -m scripts.run_case_study_analysis
```

The canonical executable notebook is [case_study_reanalysis.ipynb](vizualisation/case_study_reanalysis.ipynb). The other notebooks are focused views of data quality, metric sensitivity, peak/off-peak journey reliability, and passenger exposure. Run `scripts/update_notebooks.py` only when intentionally regenerating those notebook templates.

## Data and modelling assumptions

- Time periods are half-open and based on scheduled passenger departure: morning `[06:00, 09:00)`, midday `[09:00, 15:00)`, afternoon `[15:00, 18:00)`.
- The analysis uses Monday–Friday records only. The OD workbook represents a typical workday and is repeated over the 25 observed weekdays.
- Missing movement timestamps are imputed from their scheduled counterparts and flagged. Imputed terminal arrivals do not count as observed completions.
- Confidence intervals use a workday-cluster bootstrap to preserve within-day dependence.
- Passenger counts are model estimates from aggregate OD matrices, not linked smart-card journeys. Results should therefore be interpreted as passenger exposure estimates.

## Repository structure

- `src/`: portable readers, passenger assignment, metrics, and plotting helpers.
- `scripts/run_case_study_analysis.py`: one-command generation of the report, figures, and tables.
- `tests/`: unit tests plus demand/traffic exploratory notebooks.
- `vizualisation/`: executable case-study notebooks; the large onboard tables are generated locally and excluded from Git.
- `output/`: corrected report, figures, and CSV tables.

Further extensions are listed in the generated analysis report. The most important is an explicit passenger re-routing model for cancelled trains, ideally calibrated with linked AFC journeys.
