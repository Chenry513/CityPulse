# CityPulse

A runnable Vancouver urban intelligence MVP: an interactive geographic dashboard, reproducible data pipeline, trained statistical models, and a FastAPI service.

**The included activity, weather, transit and event observations are synthetic.** The 22 neighbourhood geometries are official City of Vancouver boundaries. The hosted site is a static export of a completed demo run; it does not run Python or continuously ingest live feeds.

## Run locally

Python 3.12 recommended. From this directory:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-lock.txt
python -m pipelines.run
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API. The included exported snapshot works before a pipeline run. The pipeline regenerates 90 days × 24 hours × 22 neighbourhoods, validates sources, executes dbt models and tests, trains models, and writes a new snapshot atomically.

Alternatively:

```sh
docker compose up --build
```

The pipeline finishes before the API starts. Docker uses named data and dashboard volumes and binds the API to localhost. To refresh an existing volume, rerun the pipeline service. Docker configuration is supplied; see VALIDATION.md for what was actually executed in this build.

## Explore

- **Overview:** official interactive boundaries, switchable activity/transit/anomaly layers, daily rhythm and anomaly drilldowns.
- **Neighbourhoods:** search, sort, keyboard-accessible rows and forecast explanations.
- **Forecasts:** 24-hour city and neighbourhood forecasts.
- **Anomalies:** severity filtering and feature evidence.
- **Historical patterns:** five distinct dates with nearest numerical city-state vectors.
- **Data sources / model performance:** provenance and measured holdout evaluation.
- **Export snapshot:** download the dataset, predictions and provenance as JSON.

## Architecture

```text
CSV / public adapters / deterministic demo
  → Polars validation and Parquet
  → DuckDB raw tables
  → dbt staging + hourly feature tables + data tests
  → standardized Ridge / Isolation Forest / K-Means
  → JSON snapshot + metrics + serialized model
  → FastAPI endpoints / static dashboard export
```

`ingestion/` contains deterministic sources plus Open-Meteo and GTFS adapters. `features/` validates numeric ranges, nulls, duplicates, timestamps and joined coverage. `dbt/` owns analytical SQL. `models/` owns fit/evaluation/explanation. `pipelines/` coordinates the full run. `api/` serves read-only results. `dist/` is the dependency-light dashboard. `tests/` covers data failure paths, forecasts, GTFS service exceptions and API contracts.

## Models and honest interpretation

The baseline is the training-period neighbourhood × weekday × hour mean. The forecast model is standardized Ridge regression with lagged activity, transit supply, event intensity, weather, cyclical hour, weekend and neighbourhood features. The last seven days are held out by timestamp; preprocessing is fitted on earlier observations only. A missing hourly lag is excluded.

MAE and RMSE measure **one-step conditional predictions using observed exogenous inputs**. Tomorrow's recursive forecasts instead use training-period hourly profiles for future transit, events and weather. Their full-horizon accuracy has not been separately validated. Do not interpret one-step MAE as a calibrated prediction interval or production accuracy.

Isolation Forest is fitted on training data only. The displayed anomaly score rescales the upper half of the training score percentile distribution to 0–1; it is **not a probability**. The 0.70 display threshold is a configurable screening convention. K-Means groups standardized city-hour vectors into five states. Historical retrieval uses cosine similarity on standardized numerical vectors, excludes the last seven days, and selects distinct dates. This is numerical similarity, not semantic text embedding search.

Explanations use exact additive linear-model contributions before clipping the result to 0–100. They are grounded deterministic text, not LLM responses, causal estimates, or SHAP values. Full per-feature contributions and the intercept are included in the snapshot.

## Use supplied data

Prepare hourly UTC files in a private input directory (timestamps use `YYYY-MM-DDTHH:00:00`, with no offset, or explicit UTC offsets):

| File | Required columns |
|---|---|
| weather.csv | timestamp, temperature, precipitation, wind |
| transit.csv | timestamp, neighbourhood, departures |
| events.csv | timestamp, neighbourhood, event_intensity |
| observed.csv | timestamp, neighbourhood, activity |

Weather has one row per hour; other files have one row per hour and neighbourhood. Use the official names from the boundary dataset. Supply at least several weeks of complete overlapping coverage. For this Vancouver demonstration exporter, the latest observation must be at 18:00 local daylight time. Data outside the demo summer period requires timezone-aware exporter adjustments before production use.

```sh
python -m pipelines.run --source /absolute/path/to/input
```

This writes `data/snapshot.json` for the API and deliberately **does not overwrite the labelled demo in `dist/`**. Do not relabel the demo as live. A production rollout needs an observed activity target, source-specific licensing/rate-limit review, missing-data and late-arrival handling, real backtesting, and an explicit deployment connection between the API and dashboard.

The source adapters are explicit; they raise on failed requests rather than silently substituting sample observations:

```sh
python -m ingestion.sources weather --start 2026-06-01 --end 2026-09-01 --output input/weather.csv
python -m ingestion.sources gtfs --archive transit.zip --date 2026-09-11 --mapping stop-neighbourhoods.csv --output input/transit.csv
```

GTFS requires a supplied `stop_id,neighbourhood` mapping and respects calendar exceptions and times beyond 24:00. It counts scheduled stop departures, not passengers. Frequency-based feeds, ambiguous DST times, unmapped stops, and complete zero-filling need explicit treatment for a particular production feed. Event and observed-activity imports use the normalized CSV contract; this project does not invent a universal municipal events API.

## API

`GET /activity/current`, `/activity/neighbourhood/{name}`, `/forecast?neighbourhood=Downtown`, `/anomalies?threshold=0.7`, `/similar-days?limit=5`, `/explanation?neighbourhood=Downtown`, `/metrics`, `/health`. Analytical responses include provenance and the snapshot timestamp. No authentication or mutation endpoints are added; keep the local service private until a production security design exists.

## Optional orchestration and tracking

```sh
pip install -r requirements-mlops.txt
python -m pipelines.run --mlflow
python -m pipelines.scheduled
```

The first command enables MLflow logging. The second registers a persistent Prefect runner with an hourly cron schedule; the process must stay running. `CITYPULSE_SOURCE_DIR` selects a normalized input directory; without it, scheduled runs regenerate the same deterministic demo. This scheduler does not download GTFS or curate event data automatically. `CITYPULSE_MLFLOW=1` enables tracking inside scheduled runs. No automation has been scheduled on your computer by this build.

## Validation and extensions

Run `pytest -q`. CI regenerates a shorter dataset, executes the dbt tests and API/data tests, syntax-checks JavaScript, then builds the Docker image. The optional MLflow/Prefect integrations and container workflow are not claims that those services have already been deployed.

The broader brief's boosted/deep models, H3/PostGIS, vector database, LLM, streaming, multi-city support, and live production MLOps remain extensions. This version intentionally uses a compact, inspectable implementation of the end-to-end MVP.

## Data and library attribution

- [City of Vancouver local area boundaries](https://opendata.vancouver.ca/explore/dataset/local-area-boundary/) — Open Government Licence – Vancouver; geometry downloaded for this build. The City does not endorse the app or its analysis.
- [Open-Meteo historical weather API](https://open-meteo.com/en/docs/historical-weather-api) — optional adapter; consult provider terms for use beyond the demo.
- [TransLink developer resources](https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources) — GTFS acquisition and terms.
- [Leaflet 1.9.4](https://leafletjs.com/) — BSD-2-Clause, vendored with license.
- [OpenStreetMap](https://www.openstreetmap.org/copyright) — external basemap tiles, credited on the map. If tiles are unavailable, local neighbourhood geometry remains interactive.

Font delivery and basemap tiles require an internet connection. The numerical snapshot, Leaflet code and neighbourhood boundaries are bundled locally.
