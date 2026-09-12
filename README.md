# CityPulse

[Open CityPulse](https://citypulse-vancouver-henry.jobanwrld.chatgpt.site) · [Source](https://github.com/Chenry513/CityPulse)

A Vancouver urban intelligence console with an interactive neighbourhood map, live source observations, historical collection, and a separate reproducible modelling demo.

## Live sources

- Official Vancouver road closures and construction reports, assigned to the city's 22 neighbourhoods by their reported location.
- Open-Meteo current modelled weather and hourly weather forecast.
- TransLink GTFS scheduled stop departures by neighbourhood and hour. These are scheduled services, not vehicle positions or passenger counts.

The open dashboard checks sources every **five minutes** and refreshes when returning to the tab. GitHub Actions checks municipal/weather sources every **15 minutes** even without visitors, retains up to 56 days of hourly road observations, and refreshes the seven-day transit schedule daily. GitHub scheduling is best effort and can be delayed. Source publication times are shown separately from retrieval times: municipal extracts generally update daily, and weather conditions have a 15-minute model cadence. This is continuously refreshed public data, not a second-by-second sensor network.

History and schedules are read from this repository's main branch, so scheduled data updates appear without republishing the website. Failed feeds retain their last observation with a stale/unavailable status. Expired transit schedules are not shown as current. A same-weekday/hour reference requires four distinct historical dates; until then, comparisons say **Baseline building**. Road reports are not a measure of traffic volume.

## Run the dashboard

Serve the dist directory using any static HTTP server, for example:

```sh
python -m http.server 5173 --directory dist
```

Open http://localhost:5173. Set dist/config.json data_base to an empty string to use local history and schedules. No API keys are required for the connected sources.

## Collect and validate

```sh
python scripts/collect-transit.py
node scripts/collect-live.cjs
node --test tests/live.test.cjs
```

Python 3.12 and Node 22 are used by the workflows. On Windows, Python needs timezone data (pip install tzdata). The live-data workflow supports manual dispatch from Actions. Full Python pipeline checks run on source changes; scheduled data commits do not retrigger them.

## Model demonstration

Choose **Model demo** to explore synthetic activity forecasts, anomaly detection and historical similarity. Its observations are explicitly separate from live sources. Ridge's holdout MAE is 2.365 versus 2.196 for the weekday/hour baseline; the baseline performs better. No production activity forecasting claim is made. Technical details are behind View analysis details and Model performance.

See [demo pipeline documentation](docs/DEMO.md) for Polars, DuckDB/dbt, Ridge, Isolation Forest, K-Means, FastAPI, Docker, and optional Prefect/MLflow. See [validation](VALIDATION.md) for executed checks.

## Sources and attribution

- [City of Vancouver road closures](https://opendata.vancouver.ca/explore/dataset/road-ahead-current-road-closures/) and [construction](https://opendata.vancouver.ca/explore/dataset/road-ahead-projects-under-construction/), under the City of Vancouver Open Government Licence.
- [Vancouver local area boundaries](https://opendata.vancouver.ca/explore/dataset/local-area-boundary/).
- [Open-Meteo](https://open-meteo.com/) weather data, CC BY 4.0. Review service terms before commercial use.
- [TransLink GTFS](https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs/gtfs-data). Route and arrival data used in this product or service is provided by permission of TransLink. TransLink assumes no responsibility for the accuracy or currency of the Data used in this product or service.
- [OpenStreetMap](https://www.openstreetmap.org/copyright) basemap and Leaflet (BSD-2-Clause, vendored licence included).
