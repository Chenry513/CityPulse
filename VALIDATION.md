# Validation record

## Live console update — September 12, 2026

- Seven Node tests passed: geometry holes/exterior, neighbourhood mapping and publication timestamps, stale preservation, unknown counts on failure, invalid weather isolation, four-week reference requirement, expired transit handling, and complete exported data contracts. The local Windows sandbox used Node's `--test-isolation=none`; CI uses normal process isolation.
- All five existing Python/API tests passed again.
- Browser checks verified live refresh, inline neighbourhood selection, separate technical details, switching live/demo modes, and the live weather/service outlook. No browser errors were reported during these interactions.
- Actual municipal/weather collection at 17:20 UTC returned 21 road closures, 40 construction projects, and weather published at 17:15 UTC. Counts change with the upstream data.
- Parsed the actual TransLink GTFS feed (1,847,219 stop-time rows; 1,761 stops within Vancouver neighbourhoods) into a seven-day service schedule.
- Live historical baselines are still collecting. Models remain demonstrations trained only on synthetic observations.

## Original model pipeline

Completed on September 11, 2026 (Vancouver time).

- Generated 90 days of deterministic hourly sources for 22 neighbourhoods.
- Wrote raw Parquet, DuckDB tables and analytical Parquet.
- Executed all 4 dbt models and all 7 dbt data tests successfully.
- Trained Ridge regression, Isolation Forest and 5-cluster K-Means; generated 24-hour recursive forecasts and 5 historical matches.
- Time holdout: 43,802 training rows and 3,696 test rows. MAE 2.365, RMSE 3.050, baseline MAE 2.196. The baseline currently outperforms Ridge; no superiority claim is made.
- All 5 pytest tests passed: invalid values/duplicates, missing source coverage, API success/error contracts, finite complete forecasts, and GTFS exceptions/after-midnight handling.
- JavaScript syntax passed `node --check`.
- Browser inspection verified the loaded official boundary map and basemap, route navigation, neighbourhood search, detail dialog, forecast selector, and rendered model-derived snapshot.
- WebMCP `inspect_neighbourhood` registered and returned the selected area after opening the shared detail panel. Unknown-area input was rejected without replacing the valid panel.

The Windows sandbox required an external validation-only adapter replacing dbt's named-pipe ThreadPool with Python's ThreadPoolExecutor. The actual dbt SQL, model execution, and data tests were unchanged. This adapter is not required by an ordinary local Python or Docker installation and is not part of application code.

Docker and the optional Prefect/MLflow extras were not run locally. Live observations were not used to train the model run. Production activity accuracy and 24-hour backtesting remain unverified. GitHub workflow results are available in the repository's Actions tab.
