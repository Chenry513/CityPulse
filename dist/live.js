/* Shared browser / scheduled collector. No credentials and no synthetic fallback. */
(function(root){
  'use strict';
  const BASE='https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/';
  const WEATHER='https://api.open-meteo.com/v1/forecast?latitude=49.2827&longitude=-123.1207&current=temperature_2m,precipitation,wind_speed_10m,weather_code&hourly=temperature_2m,precipitation_probability&timezone=UTC&forecast_days=2';
  function insideRing(p,ring){let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if(((a[1]>p[1])!==(b[1]>p[1]))&&(p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]))yes=!yes}return yes}
  function inside(p,g){const polys=g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];return polys.some(r=>insideRing(p,r[0])&&!r.slice(1).some(h=>insideRing(p,h)))}
  async function json(url,fetcher=fetch){const r=await fetcher(url,{headers:{Accept:'application/json'},signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error(`Source returned ${r.status}`);return r.json()}
  function weatherName(code){return code===0?'Clear':code<=3?'Cloudy':code<=48?'Fog':code<=67?'Rain':code<=77?'Snow':code<=82?'Showers':code<=86?'Snow showers':'Thunderstorm'}
  async function municipal(id,name,fetcher){const [meta,rows]=await Promise.all([json(BASE+id,fetcher),json(BASE+id+'/records?limit=100',fetcher)]);if(!Array.isArray(rows.results)||rows.total_count>100)throw Error('Municipal result was incomplete; pagination required');return {name,id,status:'healthy',checked_at:new Date().toISOString(),updated_at:meta.metas?.default?.data_processed||null,records:rows.total_count,cadence:'Daily municipal extract',url:'https://opendata.vancouver.ca/explore/dataset/'+id+'/',rows:rows.results}}
  function project(r,type){return {id:r.url_link||JSON.stringify(r.geo_point_2d),title:r.project||r.location||r.street||'Road construction project',type,completion:r.comp_date||null,url:r.url_link||null,point:r.geo_point_2d? [r.geo_point_2d.lon,r.geo_point_2d.lat]:null,geometry:r.geom?.geometry||null}}
  function sourceFailure(name,previous,message){return {name,status:previous?'stale':'unavailable',checked_at:new Date().toISOString(),updated_at:previous?.updated_at||null,records:previous?.records??null,cadence:previous?.cadence||'Unavailable',url:previous?.url||null,rows:previous?.rows||null,error:message}}
  function localParts(value){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Vancouver',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23',weekday:'short'}).formatToParts(new Date(value));return Object.fromEntries(parts.map(p=>[p.type,p.value]))}
  function enrich(snapshot,history=[],schedule=null){
    const now=new Date(),hour=now.toISOString().slice(0,13)+':00:00Z';
    for(const n of snapshot.neighbourhoods){
      n.service=(schedule?.hours||[]).filter(h=>h.timestamp>=hour).slice(0,25).map(h=>({timestamp:h.timestamp,departures:h.neighbourhoods[n.name]??0}));
      const valid=schedule&&Date.parse(schedule.valid_until)>now.getTime()&&n.service.length>=1;
      n.departures=valid?n.service[0].departures:null;if(!valid)n.service=[];
      n.history=history.filter(h=>h.neighbourhoods?.[n.name]!==undefined).slice(-24).map(h=>({timestamp:h.timestamp,value:h.neighbourhoods[n.name]}));
      const current=localParts(now),baselineRows=history.filter(h=>{const p=localParts(h.timestamp);return p.weekday===current.weekday&&p.hour===current.hour&&Date.parse(h.timestamp)<now.getTime()-86400000&&h.neighbourhoods?.[n.name]!==undefined});
      const unique=new Map(baselineRows.map(h=>[h.timestamp.slice(0,10),h.neighbourhoods[n.name]]));const values=[...unique.values()].sort((a,b)=>a-b);
      n.typical=null;n.range=null;n.change=null;n.unusual=false;
      if(values.length>=4&&n.closures!==null){const median=values[Math.floor(values.length/2)],low=values[Math.floor((values.length-1)*.1)],high=values[Math.ceil((values.length-1)*.9)];n.typical=median;n.range=[low,high];n.change=median>0?Math.round((n.closures/median-1)*100):null;n.unusual=n.closures>Math.max(high,median+2)}
    }
    snapshot.schedule=schedule?{...schedule,hours:undefined}:null;
    snapshot.history_hours=history.length;
    return snapshot;
  }
  async function collect(geo,{previous=null,fetcher=fetch,history=[],schedule=null}={}){
    const results=await Promise.allSettled([json(WEATHER,fetcher),municipal('road-ahead-current-road-closures','Road closures',fetcher),municipal('road-ahead-projects-under-construction','Construction projects',fetcher)]);
    if(results[0].status==='fulfilled'&&(!results[0].value.current||!Number.isFinite(results[0].value.current.temperature_2m)))results[0]={status:'rejected',reason:Error('Invalid weather response')};
    let weather=null;let ws;
    if(results[0].status==='fulfilled'){const w=results[0].value;if(!w.current||!Number.isFinite(w.current.temperature_2m))throw Error('Invalid weather response');weather={temperature:w.current.temperature_2m,precipitation:w.current.precipitation,wind:w.current.wind_speed_10m,label:weatherName(w.current.weather_code),timestamp:w.current.time+'Z',forecast:(w.hourly?.time||[]).map((t,i)=>({timestamp:t+'Z',temperature:w.hourly.temperature_2m[i],rain_probability:w.hourly.precipitation_probability[i]})).filter(h=>Date.parse(h.timestamp)>=Date.now()).slice(0,24)};ws={name:'Weather',status:'healthy',checked_at:new Date().toISOString(),updated_at:weather.timestamp,records:1+weather.forecast.length,cadence:'15-minute model conditions',url:'https://open-meteo.com/en/docs'};}else{weather=previous?.weather||null;ws=sourceFailure('Weather',previous?.sources?.[0],String(results[0].reason));}
    const roads=results[1].status==='fulfilled'?results[1].value:sourceFailure('Road closures',previous?.sources?.[1],String(results[1].reason));
    const works=results[2].status==='fulfilled'?results[2].value:sourceFailure('Construction projects',previous?.sources?.[2],String(results[2].reason));
    const districts=geo.features.map(f=>({name:f.properties.name,closures:roads.rows?0:null,construction:works.rows?0:null,projects:[]}));let unmapped=0;
    for(const [source,type] of [[roads,'closure'],[works,'construction']])for(const row of source.rows||[]){const p=project(row,type);const match=p.point?geo.features.find(f=>inside(p.point,f.geometry)):null;if(!match){unmapped++;continue}const n=districts.find(n=>n.name===match.properties.name);n.projects.push(p);if(type==='closure')n.closures++;else n.construction++}
    const snapshot={schema_version:2,mode:'live',collected_at:new Date().toISOString(),weather,sources:[ws,roads,works],neighbourhoods:districts,unmapped,totals:{closures:roads.rows?.length??null,construction:works.rows?.length??null},refresh_seconds:300};
    return enrich(snapshot,history,schedule);
  }
  const api={collect,enrich,inside,localParts,weatherName};root.CityPulseLive=api;if(typeof module==='object')module.exports=api;
})(globalThis);
