"""Explicit demo data and public-data adapters; no silent synthetic fallback."""
from __future__ import annotations
import csv
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import polars as pl
import httpx

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = datetime(2026, 9, 12, 1)  # UTC; Sep 11, 18:00 in Vancouver

def names():
    geo = json.loads((ROOT / 'dist/neighbourhoods.geojson').read_text(encoding='utf-8'))
    return sorted(f['properties']['name'] for f in geo['features'])

def demo(days=90, seed=42):
    """Three explanatory sources plus a synthetic observed activity target."""
    rng = np.random.default_rng(seed)
    weather, transit, events, observed = [], [], [], []
    districts = names()
    for step in range(days * 24):
        ts = SNAPSHOT - timedelta(hours=days * 24 - step - 1)
        local = ts - timedelta(hours=7)
        hour, weekday = local.hour, local.weekday()
        temperature = 19 + 4 * np.sin((hour - 9) * np.pi / 12) + rng.normal(0, 1.8)
        rain = max(0, rng.normal(-.6, 1.3))
        if ts == SNAPSHOT:
            temperature, rain = 19.0, 0.0
        weather.append({'timestamp': ts, 'temperature': round(temperature, 2), 'precipitation': round(rain, 2), 'wind': round(max(0, rng.normal(11, 3)), 2)})
        for idx, name in enumerate(districts):
            central = name in ['Downtown', 'West End', 'Mount Pleasant', 'Fairview', 'Kitsilano', 'Grandview-Woodland']
            commute = np.exp(-((hour - 8) / 2) ** 2) + np.exp(-((hour - 17) / 3) ** 2)
            departures = max(0, 10 + 19 * commute + central * 12 + rng.normal(0, 2))
            event = (float(rng.uniform(.2, .7)) if central and hour in range(17, 23) and weekday >= 4 else float(rng.uniform(0, .12)))
            if ts == SNAPSHOT and name in ['Downtown', 'Mount Pleasant', 'Grandview-Woodland']:
                event = {'Downtown': 1.8, 'Mount Pleasant': 1.5, 'Grandview-Woodland': 1.25}[name]
                departures += 20
            awake = 1 / (1 + np.exp(-(hour - 7))) - .7 / (1 + np.exp(-(hour - 22)))
            activity = float(np.clip(12 + idx % 8 + 25 * awake + central * 8 + .4 * departures + 18 * event - 2.2 * rain + rng.normal(0, 2), 0, 100))
            transit.append({'timestamp': ts, 'neighbourhood': name, 'departures': round(float(departures), 2)})
            events.append({'timestamp': ts, 'neighbourhood': name, 'event_intensity': round(event, 3)})
            observed.append({'timestamp': ts, 'neighbourhood': name, 'activity': round(activity, 2)})
    return {k: pl.DataFrame(v) for k, v in [('weather', weather), ('transit', transit), ('events', events), ('observed', observed)]}

def import_csv(directory: Path):
    """Import normalized hourly UTC data; fail rather than mix demo and real rows."""
    result = {}
    for name in ['weather', 'transit', 'events', 'observed']:
        df = pl.read_csv(directory / f'{name}.csv', try_parse_dates=True)
        if df.schema['timestamp'] == pl.String:
            df = df.with_columns(pl.col('timestamp').str.to_datetime(time_zone='UTC').dt.replace_time_zone(None))
        elif isinstance(df.schema['timestamp'], pl.Datetime) and df.schema['timestamp'].time_zone:
            df = df.with_columns(pl.col('timestamp').dt.convert_time_zone('UTC').dt.replace_time_zone(None))
        result[name] = df
    return result

def weather_archive(start: str, end: str) -> pl.DataFrame:
    """Fetch Open-Meteo hourly historical weather in UTC, raising on failure."""
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        r = client.get('https://archive-api.open-meteo.com/v1/archive', params={'latitude':49.2827, 'longitude':-123.1207, 'start_date':start, 'end_date':end, 'hourly':'temperature_2m,precipitation,wind_speed_10m', 'timezone':'UTC'})
        r.raise_for_status()
    h = r.json()['hourly']
    return pl.DataFrame({'timestamp': [datetime.fromisoformat(t) for t in h['time']], 'temperature':h['temperature_2m'], 'precipitation':h['precipitation'], 'wind':h['wind_speed_10m']})

def gtfs_departures(archive: Path, service_date: str, stop_neighbourhoods: Path) -> pl.DataFrame:
    """Expand a day's GTFS service, respecting exceptions and >24h times.

    stop_neighbourhoods CSV: stop_id,neighbourhood. Unknown/outside-city stops
    are omitted. Schedules are service supply, never passenger counts.
    """
    from zoneinfo import ZoneInfo
    day = datetime.fromisoformat(service_date)
    stamp = day.strftime('%Y%m%d')
    mapping = {r['stop_id']: r['neighbourhood'] for r in csv.DictReader(stop_neighbourhoods.open(encoding='utf-8-sig'))}
    with zipfile.ZipFile(archive) as z:
        def rows(name):
            return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig')))) if name in z.namelist() else []
        active = {r['service_id'] for r in rows('calendar.txt') if r['start_date'] <= stamp <= r['end_date'] and r[day.strftime('%A').lower()] == '1'}
        for r in rows('calendar_dates.txt'):
            if r['date'] == stamp:
                (active.add if r['exception_type'] == '1' else active.discard)(r['service_id'])
        trips = {r['trip_id'] for r in rows('trips.txt') if r['service_id'] in active}
        counts = {}
        for r in rows('stop_times.txt'):
            if r['trip_id'] not in trips or r['stop_id'] not in mapping or not r.get('departure_time'):
                continue
            hour, minute, second = map(int, r['departure_time'].split(':'))
            local = (day + timedelta(hours=hour, minutes=minute, seconds=second)).replace(tzinfo=ZoneInfo('America/Vancouver'))
            ts = local.astimezone(timezone.utc).replace(tzinfo=None, minute=0, second=0)
            key = (ts, mapping[r['stop_id']])
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        raise ValueError('No matching service; check date and stop mapping')
    return pl.DataFrame([{'timestamp': ts, 'neighbourhood': area, 'departures': n} for (ts, area), n in sorted(counts.items())])

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='source', required=True)
    w = sub.add_parser('weather'); w.add_argument('--start', required=True); w.add_argument('--end', required=True); w.add_argument('--output', type=Path, required=True)
    g = sub.add_parser('gtfs'); g.add_argument('--archive', type=Path, required=True); g.add_argument('--date', required=True); g.add_argument('--mapping', type=Path, required=True); g.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    frame = weather_archive(args.start, args.end) if args.source == 'weather' else gtfs_departures(args.archive, args.date, args.mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(args.output)
    print(f'Wrote {frame.height} rows to {args.output}')
