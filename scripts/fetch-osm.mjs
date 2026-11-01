#!/usr/bin/env node
import {mkdir,writeFile} from 'node:fs/promises';

const relationId=18281347;
const overpass=['https://overpass.kumi.systems/api/interpreter','https://overpass.nchc.org.tw/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter'];

async function boundary(){
  const url='https://nominatim.openstreetmap.org/lookup?'+new URLSearchParams({osm_ids:'R'+relationId,format:'json',polygon_geojson:'1',addressdetails:'0'});
  const response=await fetch(url,{headers:{'User-Agent':'BorodiankaMap/0.2 (educational demo; https://github.com/truephp/borodianka-map)','Accept-Language':'uk'},signal:AbortSignal.timeout(45000)});
  if(!response.ok)throw Error('Nominatim HTTP '+response.status);
  const entry=(await response.json())[0];
  if(!entry || !/Бородян|Borodiank/i.test(entry.display_name||''))throw Error('OSM relation does not match Borodianka');
  const geometry=entry.geojson;
  if(!['Polygon','MultiPolygon'].includes(geometry?.type))throw Error('OSM boundary is not a polygon');
  return {type:'Feature',properties:{id:relationId,name:entry.display_name,source:'OpenStreetMap'},geometry};
}
function rings(g){return g.type==='Polygon'?[g.coordinates]:g.coordinates}
function bbox(g){let xs=[],ys=[];for(const polygon of rings(g))for(const ring of polygon)for(const p of ring){xs.push(p[0]);ys.push(p[1])}return [Math.min(...ys),Math.min(...xs),Math.max(...ys),Math.max(...xs)]}
function withinRing(point,ring){let odd=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){let a=ring[i],b=ring[j];if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])odd=!odd}return odd}
function inside(point,g){return rings(g).some(poly=>withinRing(point,poly[0])&&!poly.slice(1).some(hole=>withinRing(point,hole)))}
async function queryOSM(query){
let error;
for(const server of overpass){try{console.log('Overpass',server);const r=await fetch(server,{method:'POST',body:new URLSearchParams({data:query}),headers:{'User-Agent':'BorodiankaMap/0.2 educational OSM geometry'},signal:AbortSignal.timeout(135000)});if(!r.ok)throw Error('HTTP '+r.status);const json=await r.json();if(!Array.isArray(json.elements))throw Error('Invalid Overpass response');return json.elements}catch(e){error=e;console.error(server,e.message)}}
throw Error('Every Overpass server failed: '+error?.message);
}
const featureCollection=features=>({type:'FeatureCollection',features});
function geometryOfWay(el){const coordinates=el.geometry?.map(p=>[p.lon,p.lat])||[];if(coordinates.length<3)return null;return coordinates[0][0]===coordinates.at(-1)[0]&&coordinates[0][1]===coordinates.at(-1)[1]?{type:'Polygon',coordinates:[coordinates]}:null}
function centroid(poly){const ring=poly.coordinates[0];let x=0,y=0;for(const p of ring){x+=p[0];y+=p[1]}return [x/ring.length,y/ring.length]}

const border=await boundary(),area=border.geometry;const [s,w,n,e]=bbox(area);
console.log('Boundary bbox',s,w,n,e);
if((n-s)*(e-w)>.1)throw Error('Boundary appears too large for Borodianka settlement');
const areaQuery='('+[s,w,n,e].join(',')+')';
const roadQ='[out:json][timeout:120];way["highway"~"^(residential|living_street|tertiary|secondary|primary|unclassified|service|pedestrian)$"]'+areaQuery+';out geom;';
const buildingsQ='[out:json][timeout:120];way["building"]'+areaQuery+';out geom;';
const roads=(await queryOSM(roadQ)).filter(el=>el.type==='way'&&el.geometry?.length>=2).map(el=>({type:'Feature',properties:{id:el.id,name:el.tags?.name||'',highway:el.tags?.highway||''},geometry:{type:'LineString',coordinates:el.geometry.map(p=>[p.lon,p.lat])}})).filter(f=>f.geometry.coordinates.some(p=>inside(p,area)));
if(roads.length<30)throw Error('Suspiciously few roads: '+roads.length);
const buildings=(await queryOSM(buildingsQ)).filter(el=>el.type==='way').map(el=>{const geometry=geometryOfWay(el);if(!geometry||!inside(centroid(geometry),area))return null;return {type:'Feature',properties:{id:el.id,building:el.tags?.building||'yes',street:el.tags?.['addr:street']||'',housenumber:el.tags?.['addr:housenumber']||''},geometry}}).filter(Boolean);
if(buildings.length<100)throw Error('Suspiciously few buildings: '+buildings.length);
const addressQ='[out:json][timeout:120];node["addr:housenumber"]'+areaQuery+';out body;';
const addressNodes=(await queryOSM(addressQ)).filter(el=>el.type==='node'&&Number.isFinite(el.lat)&&Number.isFinite(el.lon)&&inside([el.lon,el.lat],area)).map(el=>({type:'Feature',properties:{id:el.id,street:el.tags?.['addr:street']||'',housenumber:el.tags?.['addr:housenumber']||'',unit:el.tags?.['addr:unit']||''},geometry:{type:'Point',coordinates:[el.lon,el.lat]}}));
console.log('Found',addressNodes.length,'standalone address nodes');
await mkdir('data',{recursive:true});
await Promise.all([writeFile('data/boundary.geojson',JSON.stringify(featureCollection([border]))+'\n'),writeFile('data/roads.geojson',JSON.stringify(featureCollection(roads))+'\n'),writeFile('data/buildings.geojson',JSON.stringify(featureCollection(buildings))+'\n'),writeFile('data/address-points.geojson',JSON.stringify(featureCollection(addressNodes))+'\n')]);
console.log('Saved',roads.length,'roads and',buildings.length,'buildings,',addressNodes.length,'address points');
