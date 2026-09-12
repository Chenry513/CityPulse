"""Add empirical reference ranges and hourly neighbourhood history to demo UI."""
import json
from pathlib import Path
import polars as pl
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
def enrich():
    path=ROOT/'dist/snapshot.json';snapshot=json.loads(path.read_text(encoding='utf-8'))
    frame=pl.read_parquet(ROOT/'data/analytics/features.parquet').to_pandas().sort_values('timestamp')
    training=frame[frame.timestamp<=snapshot['metrics']['train_end']]
    for n in snapshot['neighbourhoods']:
        area=frame[frame.neighbourhood==n['name']];now=area.iloc[-1];fit=training[training.neighbourhood==n['name']];reference=fit[(fit.weekday==now.weekday)&(fit.hour==now.hour)].activity
        n['typical']=round(float(reference.mean()),1);n['typical_range']=[round(float(reference.quantile(q)),1) for q in [.1,.9]]
        n['hourly']=area.tail(24).activity.round().astype(int).tolist();n['hourly_reference']=[round(float(fit[(fit.weekday==r.weekday)&(fit.hour==r.hour)].activity.mean())) for r in area.tail(24).itertuples()]
    snapshot['metrics']['train_start']=str(training.timestamp.min());snapshot['metrics']['model_version']='ridge-demo-v1';snapshot['metrics']['trained_at']=snapshot['generated_at']
    snapshot['metrics']['validation']='Last seven days by timestamp; preprocessing fit on training data only; one-step conditional predictions.'
    for p in [path,ROOT/'data/snapshot.json']:p.write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
if __name__=='__main__':enrich()
