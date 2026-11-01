#!/usr/bin/env node
import {readFile,mkdir,writeFile} from 'node:fs/promises';
const boundary=JSON.parse(await readFile('data/boundary.geojson','utf8')).features[0].geometry;
const polys=boundary.type==='Polygon'?[boundary.coordinates]:boundary.coordinates;
const vertices=polys.flat(2);
const xs=vertices.map(v=>v[0]),ys=vertices.map(v=>v[1]);
const bbox=[Math.min(...ys),Math.min(...xs),Math.max(...ys),Math.max(...xs)].join(',');
function inRing(p,ring){let ok=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])ok=!ok;}return ok;}
function inside(p){return polys.some(rings=>inRing(p,rings[0])&&!rings.slice(1).some(r=>inRing(p,r)));}
const q='[out:json][timeout:90];node["addr:housenumber"]('+bbox+');out body;';
const endpoints=['https://overpass.kumi.systems/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter'];
let elements=null;
for(const endpoint of endpoints){try{
 console.log('Trying',endpoint);
 const r=await fetch(endpoint,{method:'POST',body:new URLSearchParams({data:q}),headers:{'User-Agent':'borodianka-map/0.3 educational importer'},signal:AbortSignal.timeout(115000)});
 if(!r.ok)throw Error('HTTP '+r.status);
 const json=await r.json();
 if(!Array.isArray(json.elements))throw Error('Invalid JSON data');
 elements=json.elements;break;
}catch(e){console.error('Failed:',e.message);}}
if(!elements)throw Error('Could not retrieve address points; existing files untouched.');
const features=elements.filter(v=>v.type==='node'&&Number.isFinite(v.lat)&&Number.isFinite(v.lon)&&inside([v.lon,v.lat])).map(v=>({type:'Feature',properties:{id:v.id,street:v.tags?.['addr:street']||'',housenumber:v.tags?.['addr:housenumber']||'',unit:v.tags?.['addr:unit']||''},geometry:{type:'Point',coordinates:[v.lon,v.lat]}}));
console.log('Retrieved',elements.length,'OSM address nodes; inside Borodianka:',features.length);
await mkdir('data',{recursive:true});
await writeFile('data/address-points.geojson',JSON.stringify({type:'FeatureCollection',features})+'\n');
