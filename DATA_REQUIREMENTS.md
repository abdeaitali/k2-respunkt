# Data requirements

The large passenger-on-board tables are intentionally not stored in Git. They are deterministic derived data and can be rebuilt from the two case-study source files described below.

## Data inventory

| Expected path | Purpose | Git status | How to obtain it |
|---|---|---|---|
| `data/RST_2015_v38_42.csv` | Filtered Trafikverket AVL/train-movement records for 14 September–18 October 2015 | Included | Case-study source data supplied with the project |
| `data/OD_data_dynamic.xlsx` | Typical-workday OD demand matrices in 96 15-minute sheets, plus the `Static` station-label sheet | Included | Case-study source data supplied with the project |
| `vizualisation/df_onboard_actual.csv` | Passenger assignment using observed train movements | Not included; generated locally | Run the rebuild command below |
| `vizualisation/df_onboard_planned.csv` | Passenger assignment using the planned timetable, including cancellation exposure | Not included; generated locally | Run the rebuild command below |
| `tmp/legacy_derived/df_onboard_actual.csv` | Pre-correction derived table used only for exact legacy-period sensitivity comparisons | Optional and not included | Preserve or supply the original legacy output if exact comparison is needed |
| `data/filter_traffic_data_pendeltag_Bal_Nyh_2015.csv` | Full, unfiltered Trafikverket export used only to recreate the filtered AVL input | Optional and not included | Obtain from the original data provider, subject to its access terms |

The source files may be subject to provider or project data-sharing conditions. Do not commit replacements unless redistribution is permitted.

## Generate the excluded onboard tables

Create the environment and install the dependencies as described in the README, then run:

```powershell
.venv\Scripts\python.exe -m src.main --rebuild-onboard --summary-output output\corrected_metric_summary.csv
```

This writes both excluded CSVs under `vizualisation/`. The current analysis uses only weekdays, clips no delay values during passenger assignment, and records whether operational timestamps were imputed.

After generating them, reproduce the report, tables, and figures with:

```powershell
.venv\Scripts\python.exe -m scripts.run_case_study_analysis
```

If the optional legacy table is absent, the analysis still runs; only the exact pre-correction sensitivity baseline is unavailable and the script uses the corrected actual table as its fallback.
