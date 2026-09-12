"""Aggregate official GTFS stop departures for Vancouver over the next 7 days.

Schedule supply only. Never described as actual ridership or vehicle positions.
"""
import csv, io, json, sys, zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
URL='https://gtfs-static.translink.ca/gtfs/google_transit.zip'
TZ=ZoneInfo('America/Vancouver')

def in_ring(p,ring):
    yes=False;j=len(ring)-1
    for i,a in enumerate(ring):
        b=ring[j]
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:yes=not yes
        j=i
    return yes

def contains(p,g):
    polygons=[g['coordinates']] if g['type']=='Polygon' else g['coordinates']
    return any(in_ring(p,r[0]) and not any(in_ring(p,h) for h in r[1:]) for r in polygons)

def run(archive=None):
    now=datetime.now(timezone.utc);today=now.astimezone(TZ).date()
    if archive:payload=Path(archive).read_bytes();modified=None
    else:
        with urlopen(Request(URL,headers={'User-Agent':'CityPulse/2.0 public urban analytics'}),timeout=120) as response:
            payload=response.read();modified=response.headers.get('Last-Modified')
    geo=json.loads((ROOT/'dist/neighbourhoods.geojson').read_text(encoding='utf-8'))
    by_stop={};areas=[f['properties']['name'] for f in geo['features']]
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig'))
        for s in rows('stops.txt'):
            if not s.get('stop_lon') or not s.get('stop_lat'):continue
            p=(float(s['stop_lon']),float(s['stop_lat']))
            if not (-123.25<p[0]<-123.0 and 49.18<p[1]<49.31):continue
            for f in geo['features']:
                if contains(p,f['geometry']):by_stop[s['stop_id']]=f['properties']['name'];break
        calendars=list(rows('calendar.txt')) if 'calendar.txt' in z.namelist() else []
        exceptions=list(rows('calendar_dates.txt')) if 'calendar_dates.txt' in z.namelist() else []
        trip_service={r['trip_id']:r['service_id'] for r in rows('trips.txt')}
        # Frequency feeds need expansion rather than one departure per template.
        if 'frequencies.txt' in z.namelist() and any(rows('frequencies.txt')):
            raise ValueError('Frequency-based GTFS detected; explicit expansion required')
        # Aggregate once per service_id/hour/area, not millions of rows per day.
        template=defaultdict(int);raw_rows=0
        for r in rows('stop_times.txt'):
            raw_rows+=1
            if r.get('pickup_type')=='1' or r['stop_id'] not in by_stop or not r.get('departure_time'):continue
            h=int(r['departure_time'].split(':')[0]);service=trip_service.get(r['trip_id'])
            if service:template[(service,h,by_stop[r['stop_id']])]+=1
        hours={};first=now.replace(minute=0,second=0,microsecond=0);end=datetime.combine(today+timedelta(days=7),datetime.min.time(),TZ).astimezone(timezone.utc)
        cursor=first
        while cursor<end:hours[cursor.isoformat().replace('+00:00','Z')]={n:0 for n in areas};cursor+=timedelta(hours=1)
        active_days=0
        for offset in range(-1,7):
            day=today+timedelta(days=offset);stamp=day.strftime('%Y%m%d');weekday=day.strftime('%A').lower()
            active={r['service_id'] for r in calendars if r['start_date']<=stamp<=r['end_date'] and r[weekday]=='1'}
            for r in exceptions:
                if r['date']==stamp:(active.add if r['exception_type']=='1' else active.discard)(r['service_id'])
            if active and offset>=0:active_days+=1
            # GTFS seconds since local noon minus 12 hours handles DST service days.
            service_start=(datetime.combine(day,datetime.min.time(),TZ)+timedelta(hours=12)).astimezone(timezone.utc)-timedelta(hours=12)
            for (service,h,area),count in template.items():
                if service not in active:continue
                ts=(service_start+timedelta(hours=h)).isoformat().replace('+00:00','Z')
                if ts in hours:hours[ts][area]+=count
        if active_days<7:raise ValueError(f'GTFS covers only {active_days}/7 requested service days; retaining previous schedule')
    result={'kind':'scheduled_stop_departures','name':'TransLink GTFS','fetched_at':now.isoformat(),'updated_at':modified,'valid_until':end.isoformat(),'records':raw_rows,'mapped_stops':len(by_stop),'hours':[{'timestamp':ts,'neighbourhoods':counts} for ts,counts in sorted(hours.items())],'attribution':'Route and arrival data used in this product or service is provided by permission of TransLink. TransLink assumes no responsibility for the accuracy or currency of the Data used in this product or service.'}
    out=ROOT/'dist/transit-schedule.json';tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(result),encoding='utf-8');tmp.replace(out)
    print(json.dumps({k:v for k,v in result.items() if k not in ['hours','attribution']}))

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else None)
