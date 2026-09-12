import io
import zipfile
from pathlib import Path
from datetime import datetime
import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient
from api.main import app, snapshot
from ingestion.sources import demo, gtfs_departures
from features.validation import validate

def test_invalid_values_and_duplicates_are_rejected():
    frames=demo(days=1)
    validate(frames)
    broken=dict(frames)
    broken['weather']=frames['weather'].with_columns(pl.lit(-1).alias('precipitation'))
    with pytest.raises(ValueError,match='precipitation'): validate(broken)
    broken=dict(frames);broken['events']=pl.concat([frames['events'],frames['events'].head(1)])
    with pytest.raises(ValueError,match='duplicate'): validate(broken)

def test_missing_source_coverage_is_rejected():
    frames=demo(days=1);frames['transit']=frames['transit'].slice(1)
    with pytest.raises(ValueError,match='coverage'): validate(frames)

def test_api_contract_and_invalid_inputs():
    client=TestClient(app)
    for path in ['/health','/activity/current','/activity/neighbourhood/Downtown','/forecast','/anomalies','/similar-days','/explanation','/metrics','/']:
        assert client.get(path).status_code==200,path
    assert client.get('/activity/neighbourhood/unknown').status_code==404
    assert client.get('/anomalies?threshold=2').status_code==422
    assert client.get('/similar-days?limit=0').status_code==422
    assert client.get('/forecast?neighbourhood=unknown').status_code==404
    assert client.get('/activity/current').json()['provenance']=='synthetic'

def test_forecasts_are_finite_and_complete():
    s=snapshot()
    assert len(s['neighbourhoods'])==22
    for n in s['neighbourhoods']:
        assert len(n['forecast'])==24
        assert all(np.isfinite(x) and 0<=x<=100 for x in n['forecast'])
        assert 0<=n['anomaly_score']<=1
    assert s['metrics']['train_rows']>s['metrics']['test_rows']
    assert s['metrics']['mae']<10

def test_gtfs_calendar_exceptions_and_after_midnight(tmp_path):
    archive=tmp_path/'gtfs.zip';mapping=tmp_path/'mapping.csv'
    mapping.write_text('stop_id,neighbourhood\na,Downtown\n')
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('calendar.txt','service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nregular,1,1,1,1,1,0,0,20260101,20261231\n')
        z.writestr('calendar_dates.txt','service_id,date,exception_type\nregular,20260911,2\nspecial,20260911,1\n')
        z.writestr('trips.txt','route_id,service_id,trip_id\n1,regular,no\n2,special,yes\n')
        z.writestr('stop_times.txt','trip_id,stop_id,departure_time\nno,a,10:00:00\nyes,a,25:15:00\n')
    frame=gtfs_departures(archive,'2026-09-11',mapping)
    assert frame.height==1
    row=frame.row(0,named=True)
    assert row['timestamp']==datetime(2026,9,12,8)
    assert row['departures']==1
