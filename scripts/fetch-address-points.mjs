#!/usr/bin/env node
import {readFile,mkdir,writeFile} from 'node:fs/promises';
const boundary=JSON.parse(await readFile('data/boundary.geojson','utf8')).features[0].geometry;
const polys=boundary.type==='Polygon'?[boundary.coordinates]:boundary.coordinates;
const vertices=polys.flat(2);
const xs=vertices.map(v=>v[0]),ys=vertices.map(v=>v[1]);
const bbox=[Math.min(...ys),Math.min(...xs),Math.max(...ys),Math.max(...xs)].join(',');
function inRing(p,ring){let ok=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])ok=!ok;}return ok;}
function inside(p){return polys.some(rings=>inRing(p,rings[0])&&!rings.slice(1).some(r=>inRing(p,r)));}
const endpoints=[...(process.env.OVERPASS_URL?[process.env.OVERPASS_URL]:[]),'https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter'];
async function queryBox(box){
 const q='[out:json][timeout:70];node["addr:housenumber"]('+box.join(',')+');out body;';
 let lastError;
 for(const endpoint of endpoints){
  for(let attempt=1;attempt<=2;attempt++){
   try{
    console.log('Trying',endpoint,'attempt',attempt,'bbox',box.join(','));
    const r=await fetch(endpoint,{method:'POST',body:new URLSearchParams({data:q}),headers:{'User-Agent':'borodianka-map/0.4 educational importer'},signal:AbortSignal.timeout(90000)});
    if(!r.ok)throw Error('HTTP '+r.status);
    const json=await r.json();
    if(!Array.isArray(json.elements))throw Error('Invalid Overpass response');
    console.log('Received',json.elements.length,'nodes');
    return json.elements;
   }catch(e){lastError=e;console.error('Failed:',e.message);if(attempt===1)await new Promise(resolve=>setTimeout(resolve,3000));}
  }
 }
 throw Error('No Overpass endpoint succeeded for bbox '+box.join(',')+': '+lastError?.message);
}
const box=bbox.split(',').map(Number);
let elements;
try{
 elements=await queryBox(box);
}catch(error){
 console.warn('Whole area failed:',error.message,'Retrying as 4 smaller areas');
 const [south,west,north,east]=box,midLat=(south+north)/2,midLon=(west+east)/2;
 const boxes=[[south,west,midLat,midLon],[south,midLon,midLat,east],[midLat,west,north,midLon],[midLat,midLon,north,east]];
 const all=[];
 for(const b of boxes)all.push(...await queryBox(b));
 elements=[...new Map(all.map(x=>[x.id,x])).values()];
}
const features=elements.filter(v=>v.type==='node'&&Number.isFinite(v.lat)&&Number.isFinite(v.lon)&&inside([v.lon,v.lat])).map(v=>({type:'Feature',properties:{id:v.id,street:v.tags?.['addr:street']||'',housenumber:v.tags?.['addr:housenumber']||'',unit:v.tags?.['addr:unit']||''},geometry:{type:'Point',coordinates:[v.lon,v.lat]}}));
console.log('Retrieved',elements.length,'OSM address nodes; inside Borodianka:',features.length);
await mkdir('data',{recursive:true});
await writeFile('data/address-points.geojson',JSON.stringify({type:'FeatureCollection',features})+'\n');
