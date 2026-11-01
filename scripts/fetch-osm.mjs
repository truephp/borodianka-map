#!/usr/bin/env node
import {mkdir,writeFile} from 'node:fs/promises';
const bbox='50.604,29.875,50.690,29.975'; // working area only, not settlement boundary
const query='[out:json][timeout:90];way["highway"~"^(residential|living_street|tertiary|secondary|primary|unclassified|service|pedestrian)$"]('+bbox+');out geom;';
const servers=['https://overpass.kumi.systems/api/interpreter','https://overpass.nchc.org.tw/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter'];
let result;
for(const endpoint of servers){try{console.log('Requesting',endpoint);const response=await fetch(endpoint,{method:'POST',body:new URLSearchParams({data:query}),signal:AbortSignal.timeout(105000),headers:{'User-Agent':'borodianka-map/0.1 (GitHub Actions; educational OSM import)'}});if(!response.ok)throw Error('HTTP '+response.status);const json=await response.json();if(!Array.isArray(json.elements)||json.elements.length<10)throw Error('Empty or incomplete result');result=json;break}catch(e){console.error(endpoint,e.message)}}
if(!result)throw Error('All Overpass endpoints failed. Retry workflow later.');
const features=result.elements.filter(el=>el.type==='way'&&el.geometry?.length>=2).map(el=>({type:'Feature',properties:{id:el.id,name:el.tags?.name||'',highway:el.tags?.highway||''},geometry:{type:'LineString',coordinates:el.geometry.map(p=>[p.lon,p.lat])}}));
if(features.length<10)throw Error('Not enough ways, refusing to publish');
await mkdir('data',{recursive:true});await writeFile('data/roads.geojson',JSON.stringify({type:'FeatureCollection',features})+'\n');
console.log('Saved',features.length,'OSM ways');
