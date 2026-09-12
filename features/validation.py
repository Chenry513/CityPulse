"""Small explicit validation contract, shared by all ingestion paths."""
import polars as pl

CONTRACT = {'weather': {'temperature':(-50,60), 'precipitation':(0,500), 'wind':(0,400)}, 'transit':{'departures':(0,100000)}, 'events':{'event_intensity':(0,10)}, 'observed':{'activity':(0,100)}}

def validate(frames):
    for name, limits in CONTRACT.items():
        df = frames[name]
        keys = ['timestamp'] if name == 'weather' else ['timestamp', 'neighbourhood']
        missing = set(keys + list(limits)) - set(df.columns)
        if missing:
            raise ValueError(f'{name}: missing columns {sorted(missing)}')
        if not df.height or df.select(pl.any_horizontal(pl.all().is_null()).any()).item():
            raise ValueError(f'{name}: empty data or null values')
        if df.select(keys).is_duplicated().any():
            raise ValueError(f'{name}: duplicate hourly keys')
        if not isinstance(df.schema['timestamp'], pl.Datetime):
            raise ValueError(f'{name}: timestamp must be an hourly UTC datetime')
        if df.filter((pl.col('timestamp').dt.minute()!=0)|(pl.col('timestamp').dt.second()!=0)).height:
            raise ValueError(f'{name}: timestamp is not hourly')
        for column, (lo, hi) in limits.items():
            if df.filter(~pl.col(column).is_finite() | ~pl.col(column).is_between(lo, hi)).height:
                raise ValueError(f'{name}: invalid {column}; expected {lo}..{hi}')
    expected = frames['observed'].select('timestamp','neighbourhood')
    for name in ['transit','events']:
        if expected.join(frames[name].select('timestamp','neighbourhood'), on=['timestamp','neighbourhood'], how='anti').height:
            raise ValueError(f'{name}: missing coverage for observed activity')
    if expected.select('timestamp').unique().join(frames['weather'].select('timestamp'), on='timestamp', how='anti').height:
        raise ValueError('weather: missing coverage for observed activity')
