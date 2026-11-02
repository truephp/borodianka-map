#!/usr/bin/env node
// Small diagnostic only: no Visicom results written to tracked files or artifacts.
import {readFile} from 'node:fs/promises';
const key=process.env.VISICOM_API_KEY;
if(!key)throw Error('Missing VISICOM_API_KEY GitHub Actions secret');
const buildings=JSON.parse(await readFile('data/buildings.geojson','utf8')).features;
const withAddress=buildings.filter(f=>f.properties.street&&f.properties.housenumber);
const withoutAddress=buildings.filter(f=>!f.properties.street&&!f.properties.housenumber);
function sample(items,n){return Array.from({length:Math.min(n,items.length)},(_,i)=>items[Math.floor((i+.5)*items.length/Math.min(n,items.length))]);}
function center(f){const pts=f.geometry.coordinates[0],lon=pts.reduce((a,p)=>a+p[0],0)/pts.length,lat=pts.reduce((a,p)=>a+p[1],0)/pts.length;return [lon,lat];}
const samples=[...sample(withAddress,10),...sample(withoutAddress,10)];
let success=0,empty=0,failed=0;
for(const [i,f] of samples.entries()){
 const [lon,lat]=center(f);
 const url=new URL('https://api.visicom.ua/data-api/5.0/uk/geocode.json');
 url.searchParams.set('categories','adr_address');url.searchParams.set('near',lon+','+lat);url.searchParams.set('radius','40');url.searchParams.set('limit','5');url.searchParams.set('order','distance');url.searchParams.set('key',key);
 try{
  const response=await fetch(url,{signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw Error('HTTP '+response.status);
  const data=await response.json();
  const arr=Array.isArray(data)?data:Array.isArray(data.features)?data.features:Array.isArray(data.results)?data.results:null;
  if(!arr){console.log('Sample '+(i+1)+': unexpected response shape, top-level keys: '+Object.keys(data).join(', '));failed++;continue;}
  if(arr.length)success++;else empty++;
  console.log('Sample '+(i+1)+' ['+(f.properties.housenumber?'tagged':'untagged')+']: '+arr.length+' candidate(s); result categories '+[...new Set(arr.map(x=>x.properties?.categories?.[0]||x.properties?.category||x.category||'unknown'))].join(','));
 }catch(e){failed++;console.log('Sample '+(i+1)+': '+e.message);}
 await new Promise(r=>setTimeout(r,250));
}
console.log('SUMMARY: checked='+samples.length+' candidatesFound='+success+' none='+empty+' errors='+failed);
if(failed===samples.length)process.exitCode=1;
