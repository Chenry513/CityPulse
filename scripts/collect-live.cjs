const fs=require('node:fs'),path=require('node:path');const {collect}=require('../dist/live.js');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'dist');
const read=(name,fallback)=>{try{return JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'))}catch{return fallback}};
(async()=>{const geo=read('neighbourhoods.geojson',null);if(!geo)throw Error('Missing neighbourhood geometry');const previous=read('live-snapshot.json',null),history=read('live-history.json',[]),schedule=read('transit-schedule.json',null);const result=await collect(geo,{previous,history,schedule});
  if(result.sources.every(s=>s.status!=='healthy'))throw Error('All sources failed; retaining last good snapshot');
  if(result.sources[1].status==='healthy'){const timestamp=new Date().toISOString().slice(0,13)+':00:00Z';const row={timestamp,observed_at:result.sources[1].updated_at,neighbourhoods:Object.fromEntries(result.neighbourhoods.map(n=>[n.name,n.closures]))};const i=history.findIndex(h=>h.timestamp===timestamp);if(i>=0)history[i]=row;else history.push(row)}
  // Keep 8 weeks of hourly aggregates, enough for weekday/hour comparisons.
  const cutoff=Date.now()-56*86400000,trimmed=history.filter(h=>Date.parse(h.timestamp)>cutoff).sort((a,b)=>a.timestamp.localeCompare(b.timestamp));
  for(const [name,value] of [['live-snapshot.json',result],['live-history.json',trimmed]]){fs.writeFileSync(path.join(dir,name+'.tmp'),JSON.stringify(value));fs.renameSync(path.join(dir,name+'.tmp'),path.join(dir,name))}
  console.log(JSON.stringify({collected_at:result.collected_at,sources:result.sources.map(({name,status,records,updated_at})=>({name,status,records,updated_at})),history_hours:trimmed.length}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
