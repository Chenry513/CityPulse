"""Read-only inference snapshot API. Serve the dashboard from the same origin."""
from functools import lru_cache
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

ROOT=Path(__file__).resolve().parents[1]
app=FastAPI(title='CityPulse API',version='1.0.0',description='Reproducible urban analytics. Inspect provenance on every response.')

def snapshot():
    path=ROOT/'data/snapshot.json'
    if not path.exists(): path=ROOT/'dist/snapshot.json'
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): raise HTTPException(503,'No valid snapshot available; run the pipeline')

def envelope(value):
    s=snapshot();return {'provenance':s['provenance'],'timestamp':s['timestamp'],'data':value}

@app.get('/health')
def health():
    s=snapshot();return {'status':'ok','provenance':s['provenance'],'timestamp':s['timestamp']}

@app.get('/activity/current')
def current():
    s=snapshot();return envelope({'activity':round(sum(n['activity'] for n in s['neighbourhoods'])/len(s['neighbourhoods'])),'neighbourhoods':s['neighbourhoods']})

def find(name):
    for n in snapshot()['neighbourhoods']:
        if n['name'].casefold()==name.casefold(): return n
    raise HTTPException(404,'Unknown neighbourhood')

@app.get('/activity/neighbourhood/{name}')
def neighbourhood(name:str): return envelope(find(name))

@app.get('/forecast')
def forecast(neighbourhood:str|None=None):
    s=snapshot();return envelope({'values':find(neighbourhood)['forecast'] if neighbourhood else s['forecast'],'hours':list(range(24)),'timezone':'America/Vancouver','assumption':'Future exogenous values use training-period hourly profiles','evaluation_mae':s.get('metrics',{}).get('mae')})

@app.get('/anomalies')
def anomalies(threshold:float=Query(.7,ge=0,le=1)):
    return envelope(sorted([n for n in snapshot()['neighbourhoods'] if n['anomaly_score']>=threshold],key=lambda n:n['anomaly_score'],reverse=True))

@app.get('/similar-days')
def similar(limit:int=Query(5,ge=1,le=5)): return envelope(snapshot()['similar'][:limit])

@app.get('/explanation')
def explanation(neighbourhood:str='Downtown'):
    n=find(neighbourhood);return envelope({'text':n['explanation'],'drivers':n['drivers'],'method':snapshot()['explanation_method'],'llm_connected':False})

@app.get('/metrics')
def metrics(): return envelope(snapshot().get('metrics',{}))

app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='dashboard')
