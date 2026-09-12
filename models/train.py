"""Time-based evaluation, interpretable forecast, anomaly and city-state models."""
from __future__ import annotations
from datetime import timedelta
import json
import pickle
from pathlib import Path
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.metrics.pairwise import cosine_similarity

NUMERIC = ['lag_1','departures','event_intensity','temperature','precipitation','wind','hour_sin','hour_cos','weekend']
VECTOR = ['activity','departures','event_intensity','temperature','precipitation']

def train(frame, directory: Path, track=False):
    df = frame.to_pandas().sort_values(['timestamp','neighbourhood'])
    df = df[df['lag_1'].notna() & ((df.timestamp-df.previous_timestamp).dt.total_seconds()==3600)].copy()
    cutoff = df.timestamp.max() - timedelta(days=7)
    fit, holdout = df[df.timestamp<=cutoff], df[df.timestamp>cutoff]
    if len(fit)<200 or len(holdout)<50:
        raise ValueError('At least several weeks of hourly observations are required')
    transform = ColumnTransformer([('numeric',StandardScaler(),NUMERIC),('area',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['neighbourhood'])])
    model = make_pipeline(transform, Ridge(alpha=8))
    model.fit(fit,fit.activity)
    predicted = np.clip(model.predict(holdout),0,100)
    averages = fit.groupby(['neighbourhood','weekday','hour']).activity.mean()
    fallback = float(fit.activity.mean())
    baseline = [averages.get((r.neighbourhood,r.weekday,r.hour),fallback) for r in holdout.itertuples()]
    metrics = {'mae':round(float(mean_absolute_error(holdout.activity,predicted)),3), 'rmse':round(float(np.sqrt(mean_squared_error(holdout.activity,predicted))),3), 'baseline_mae':round(float(mean_absolute_error(holdout.activity,baseline)),3), 'model':'Standardized Ridge regression', 'train_rows':len(fit), 'test_rows':len(holdout), 'train_end':str(cutoff), 'provenance':'synthetic unless a supplied-data run is explicitly requested'}
    # Scale on training data only; anomaly values are training-score percentiles.
    anomaly_scale = StandardScaler().fit(fit[VECTOR])
    isolation = IsolationForest(n_estimators=100, contamination=.03, random_state=42).fit(anomaly_scale.transform(fit[VECTOR]))
    reference = np.sort(-isolation.score_samples(anomaly_scale.transform(fit[VECTOR])))
    city = df.groupby('timestamp')[VECTOR].mean()
    historical = city.loc[city.index<=cutoff]
    city_scale = StandardScaler().fit(historical)
    states = KMeans(n_clusters=5,n_init=10,random_state=42).fit(city_scale.transform(historical))
    directory.mkdir(parents=True,exist_ok=True)
    bundle = {'forecast':model,'isolation':isolation,'anomaly_scale':anomaly_scale,'anomaly_reference':reference,'city_scale':city_scale,'states':states,'baseline':averages,'metrics':metrics}
    with (directory/'model.pkl').open('wb') as f: pickle.dump(bundle,f)
    (directory/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    if track:
        import mlflow
        mlflow.set_experiment('citypulse_activity_forecasting')
        with mlflow.start_run():
            mlflow.log_params({'model':'Ridge','alpha':8,'split':'last 7 days','seed':42})
            mlflow.log_metrics({k:metrics[k] for k in ['mae','rmse','baseline_mae']})
            mlflow.log_artifact(str(directory/'metrics.json'))
            mlflow.log_artifact(str(directory/'model.pkl'))
    return bundle, df, city

def explain(bundle, row):
    """Exact additive contributions on the model's un-clipped linear scale."""
    model=bundle['forecast']
    contribution=model[0].transform(row)[0]*model[1].coef_
    names={'lag_1':'Previous activity','departures':'Transit service','event_intensity':'Event intensity','temperature':'Temperature','precipitation':'Precipitation','wind':'Wind','hour_sin':'Time of day (sin)','hour_cos':'Time of day (cos)','weekend':'Weekend'}
    drivers=[{'label':names[n],'value':round(float(v),1)} for n,v in zip(NUMERIC,contribution[:len(NUMERIC)])]
    drivers.append({'label':'Neighbourhood','value':round(float(contribution[len(NUMERIC):].sum()),1)})
    drivers.sort(key=lambda d:abs(d['value']),reverse=True)
    return drivers, float(model[1].intercept_)

def similar_hours(bundle, city):
    current=city.iloc[[-1]]
    # Exclude the last week to retrieve distinct historical situations.
    past=city.loc[city.index<city.index.max()-timedelta(days=7)]
    scores=cosine_similarity(bundle['city_scale'].transform(current),bundle['city_scale'].transform(past))[0]
    chosen=[]; dates=set()
    for i in np.argsort(scores)[::-1]:
        ts=past.index[i]
        if ts.date() in dates: continue
        dates.add(ts.date()); chosen.append((ts,float(scores[i]),past.iloc[i]))
        if len(chosen)==5: break
    return chosen
