"""One command: validated sources → Parquet → DuckDB/dbt → ML → API snapshot."""
from __future__ import annotations
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import numpy as np
import duckdb
import polars as pl
from ingestion.sources import ROOT, demo, import_csv
from features.validation import validate
from models.train import train, explain, similar_hours, VECTOR

def run(source: Path|None=None, days=90, track=False):
    os.chdir(ROOT)
    directory=ROOT/'data'; raw=directory/'raw'; raw.mkdir(parents=True,exist_ok=True)
    frames=import_csv(source) if source else demo(days)
    validate(frames)
    database=directory/'citypulse.duckdb'
    with duckdb.connect(str(database)) as con:
        for name,frame in frames.items():
            path=raw/f'{name}.parquet';frame.write_parquet(path)
            con.execute(f"create or replace table raw_{name} as select * from read_parquet(?)",[str(path)])
    # Close DuckDB before dbt acquires the file.
    from dbt.cli.main import dbtRunner
    result=dbtRunner().invoke(['build','--project-dir',str(ROOT/'dbt'),'--profiles-dir',str(ROOT/'dbt')])
    if not result.success: raise RuntimeError(f'dbt build failed: {result.exception}')
    with duckdb.connect(str(database)) as con:
        frame=pl.from_pandas(con.execute('select * from feature_neighbourhood_activity order by timestamp, neighbourhood').df())
    (directory/'analytics').mkdir(exist_ok=True)
    frame.write_parquet(directory/'analytics/features.parquet')
    bundle,df,city=train(frame,directory/'models',track)
    current=df[df.timestamp==df.timestamp.max()].copy()
    now=current.timestamp.max(); local_now=now-timedelta(hours=7)
    forecasts={}; districts=[]
    # Forecast the next calendar day recursively. Future exogenous variables use
    # train-period hour/day profiles, never future observations from the holdout.
    training=df[df.timestamp<=bundle['metrics']['train_end']]
    profile=training.groupby(['neighbourhood','weekday','hour'])[['departures','event_intensity','temperature','precipitation','wind']].mean()
    for _,r in current.iterrows():
        name=r.neighbourhood;future=r.to_frame().T.copy();predictions=[];previous=float(r.activity)
        target_day=(local_now+timedelta(days=1)).date()
        for offset in range(1,31):
            ts=now+timedelta(hours=offset);local=ts-timedelta(hours=7)
            hour=local.hour;weekday=local.weekday()
            values=profile.loc[(name,weekday,hour)] if (name,weekday,hour) in profile.index else training[training.neighbourhood==name][['departures','event_intensity','temperature','precipitation','wind']].mean()
            for key in values.index: future[key]=float(values[key])
            future['lag_1']=previous;future['hour_sin']=np.sin(2*np.pi*hour/24);future['hour_cos']=np.cos(2*np.pi*hour/24);future['weekend']=int(weekday>=5)
            previous=float(np.clip(bundle['forecast'].predict(future)[0],0,100))
            if local.date()==target_day: predictions.append(round(previous))
        forecasts[name]=predictions
        if len(predictions)!=24: raise ValueError('Snapshot must be at 18:00 Vancouver time for this 30-hour export')
        base=float(bundle['baseline'].get((name,r.weekday,r.hour),training.activity.mean()))
        change=round((float(r.activity)-base)/max(1,base)*100)
        raw_score=-bundle['isolation'].score_samples(bundle['anomaly_scale'].transform(current[current.neighbourhood==name][VECTOR]))[0]
        # Upper-tail anomaly score: 0 at the training median, 1 at the maximum.
        rank=np.searchsorted(bundle['anomaly_reference'],raw_score)/len(bundle['anomaly_reference'])
        anomaly=round(float(np.clip((rank-.5)*2,0,1)),3)
        drivers,intercept=explain(bundle,current[current.neighbourhood==name])
        top=', '.join(d['label'].lower() for d in drivers[:3])
        summary='Elevated evening event activity' if r.event_intensity>.8 else 'Outside the typical activity pattern' if anomaly>=.7 else 'Within the usual activity range'
        districts.append({'name':name,'activity':round(float(r.activity)),'change':change,'anomaly_score':anomaly,'transit':round(min(100,float(r.departures)*1.5)),'summary':summary,'tags':['Events' if r.event_intensity>.5 else 'Neighbourhood activity','Transit'],'explanation':f'{name} activity is {abs(change)}% {"above" if change>=0 else "below"} its training-period weekday/hour baseline. The largest model contributions are {top}. This describes associations in synthetic data, not causal effects.','drivers':drivers,'intercept':round(intercept,3),'forecast':predictions})
    daily=city.tail(24).activity
    baseline=training[training.weekday==local_now.weekday()].groupby('hour').activity.mean().sort_index()
    cityforecast=np.mean(list(forecasts.values()),axis=0)
    w=frames['weather'].sort('timestamp').row(-1,named=True)
    state_id=int(bundle['states'].predict(bundle['city_scale'].transform(city.iloc[[-1]]))[0])
    label='Friday evening upswing' if local_now.weekday()==4 and local_now.hour>=17 else f'Urban activity state {state_id+1}'
    snapshot={'schema_version':1,'provenance':'supplied' if source else 'synthetic','timestamp':str(now)+'Z','generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'city_change':round((current.activity.mean()/float(baseline.loc[local_now.hour])-1)*100),'transit_index':round(np.mean([n['transit'] for n in districts])),'weather':{'temperature':round(w['temperature']),'precipitation':w['precipitation'],'wind':round(w['wind']),'label':'Dry' if w['precipitation']==0 else 'Rain'},'neighbourhoods':districts,'hourly':[round(float(x)) for x in daily],'baseline':[round(float(x)) for x in baseline],'forecast':[round(float(x)) for x in cityforecast],'metrics':bundle['metrics'],'state':label,'cluster_id':state_id,'state_description':'The nearest learned city-state cluster combines elevated transit service and evening activity.','explanation_method':'Exact additive Ridge contributions relative to training means (before 0–100 clipping)','similar':[{'label':(ts-timedelta(hours=7)).strftime('%A, %B %d · %H:%M'),'description':f'Activity {row.activity:.0f}/100 · {row.temperature:.0f}°C · event intensity {row.event_intensity:.2f}','similarity':round(score*100,1)} for ts,score,row in similar_hours(bundle,city)]}
    snapshot['rhythm_baseline']=[round(float(baseline.loc[(ts-timedelta(hours=7)).hour])) for ts in daily.index]
    # Supplied data must never be published into the hard-coded demo workspace.
    output=directory/'snapshot.json'
    temp=output.with_suffix('.tmp');temp.write_text(json.dumps(snapshot,indent=2),encoding='utf-8');temp.replace(output)
    if not source:
        target=ROOT/'dist/snapshot.json';temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(snapshot,indent=2),encoding='utf-8');temporary.replace(target)
    if not source:
        import runpy
        runpy.run_path(str(ROOT/'scripts/enrich-demo.py'))['enrich']()
    print(json.dumps({'snapshot':str(output),'metrics':bundle['metrics'],'neighbourhoods':len(districts)},indent=2))
    return snapshot

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--days',type=int,default=90);p.add_argument('--mlflow',action='store_true');a=p.parse_args()
    run(a.source.resolve() if a.source else None,a.days,a.mlflow)
