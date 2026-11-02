#!/usr/bin/env node
// Diagnostic: inspect geometry types only; never publish Visicom response data.
import {readFile} from 'node:fs/promises';
const key=process.env.VISICOM_API_KEY;
if(!key)throw Error('VISICOM_API_KEY missing');
const features=JSON.parse(await readFile('data/buildings.geojson','utf8')).features;
const selected=features.filter(f=>f.properties.street&&f.properties.housenumber).slice(0,10);
const summary={checked:0,geocoded:0,featureFetched:0,geometryTypes:{},httpErrors:{},missingId:0};
function itemsOf(data){if(Array.isArray(data))return data;if(Array.isArray(data?.features))return data.features;if(data?.id)return [data];return [];}
async function request(url){const r=await fetch(url,{signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
for(const [index,f] of selected.entries()){
 summary.checked++;
 const coordinates=f.geometry.coordinates[0];
 const lng=coordinates.reduce((a,p)=>a+p[0],0)/coordinates.length;
 const lat=coordinates.reduce((a,p)=>a+p[1],0)/coordinates.length;
 const url=new URL('https://api.visicom.ua/data-api/5.0/uk/geocode.json');
 for(const [k,v] of Object.entries({key,categories:'adr_address',near:lng+','+lat,radius:'50',limit:'3',order:'distance'}))url.searchParams.set(k,v);
 try{
  const geo=itemsOf(await request(url));
  if(!geo.length){console.log('Sample '+(index+1)+': no geocode results');continue;}
  summary.geocoded++;
  const id=geo[0]?.id;
  if(!id||!/^[a-z0-9_-]+$/i.test(String(id))){summary.missingId++;console.log('Sample '+(index+1)+': missing usable feature id');continue;}
  const featureUrl=new URL('https://api.visicom.ua/data-api/5.0/uk/feature/'+encodeURIComponent(id)+'.json');
  featureUrl.searchParams.set('key',key);
  const response=itemsOf(await request(featureUrl));
  if(!response.length){console.log('Sample '+(index+1)+': empty feature');continue;}
  const type=response[0]?.geometry?.type||'none';
  summary.featureFetched++;
  summary.geometryTypes[type]=(summary.geometryTypes[type]||0)+1;
  console.log('Sample '+(index+1)+': category='+String(geo[0]?.properties?.categories||'unknown')+' geometry='+type);
 }catch(e){
  const code=/^HTTP \d+$/.test(e.message)?e.message:'network-or-parse-error';
  summary.httpErrors[code]=(summary.httpErrors[code]||0)+1;
  console.log('Sample '+(index+1)+': '+code);
 }
 await new Promise(r=>setTimeout(r,400));
}
console.log('FEATURE_DIAGNOSTIC '+JSON.stringify(summary));
