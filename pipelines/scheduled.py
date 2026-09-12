"""Optional Prefect orchestration; an explicit source path is required for imports."""
import os
from pathlib import Path
from prefect import flow, task
from pipelines.run import run

@task(retries=2,retry_delay_seconds=30)
def refresh():
    source=os.environ.get('CITYPULSE_SOURCE_DIR')
    return run(Path(source) if source else None,track=os.environ.get('CITYPULSE_MLFLOW')=='1')['timestamp']

@flow(name='citypulse-hourly')
def citypulse_flow():
    return refresh()

if __name__=='__main__':
    citypulse_flow.serve(name='citypulse-hourly',cron='0 * * * *')
