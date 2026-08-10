# Code and methods review

## Material corrections implemented

- Replaced user-specific absolute paths with project-relative `pathlib` readers and explicit file validation.
- Moved top-level preprocessing side effects behind command-line entry points.
- Normalised raw column names once and made planned/actual processing use the same tested pipeline.
- Restricted the synthetic workday demand assignment to Monday–Friday and made period intervals half-open.
- Added date to train/headway keys so services on different days cannot be linked accidentally.
- Preserved signed delays in minutes instead of silently truncating or converting early arrivals.
- Added provenance flags for imputed arrival/departure times and suspect arrival observations.
- Replaced row-order origin–destination alignment with validated key-based joins.
- Calculated expected waiting from one departure sequence per station rather than repeating headways for every destination.
- Replaced unweighted train–OD journey percentiles with passenger-weighted quantiles.
- Added planned-denominator CPM and PP2-C so cancellations remain visible.
- Added day-cluster bootstrap intervals, data-quality summaries, OD burden rankings, and passenger-volume/delay exploration.

## Remaining limitations

- Demand is an aggregate typical-workday matrix and cannot identify actual passenger reactions to disruption.
- PP2-C counts planned passengers without an observed on-time completion as failures. It is deliberately conservative and should not be described as passengers' eventual punctuality.
- Timestamp imputation is deterministic. Scenario bounds or multiple imputation would better represent uncertainty, particularly at stations with high missingness.
- The case study covers one corridor and five weeks in 2015. External validity needs more lines, dates, and operating conditions.
- OD hotspot rates can be unstable for small flows; production ranking should use a minimum exposure rule or hierarchical shrinkage.

## Verification performed

- Passenger conservation is exact for every regenerated service.
- Seven unit tests cover time periods, cancellation handling, passenger assignment, weighted quantiles, and metric denominators.
- All nine project notebooks execute from a clean kernel with project-relative paths.
- All generated PNGs were inspected for clipping, illegible labels, and inconsistent units.
