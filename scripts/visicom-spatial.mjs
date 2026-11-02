#!/usr/bin/env node
// Visicom spatial discovery: bounded pilot independent of OSM building locations.
// Output stays encrypted in GitHub Actions. No Visicom data goes into git or Pages.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
import {randomBytes,pbkdf2Sync,createCipheriv} from 'node:crypto';
const key=process.env.VISICOM_API_KEY,password=process.env.VISICOM_EXPORT_PASSWORD;
if(!key||!password||password.length<12)throw Error('Missing VISICOM_API_KEY or VISICOM_EXPORT_PASSWORD');
const polygons=JSON.parse(await readFile('data/boundary.geojson','utf8')).features[0].geometry;
const pieces=polygons.type==='Polygon'?[polygons.coordinates]:polygons.coordinates;
const pts=pieces.flat(2),lon=pts.map(x=>x[0]),lat=pts.map(x=>x[1]);
const bbox=[Math.min(...lon),Math.min(...lat),Math.max(...lon),Math.max(...lat)];
const MAX_CELLS=Math.min(5000,Math.max(1,Number(process.env.VISICOM_MAX_CELLS||1500)));
const MAX_FEATURES=Math.min(100,Math.max(1,Number(process.env.VISICOM_MAX_FEATURES||30)));
function normalize(data){return Array.isArray(data)?data:Array.isArray(data?.features)?data.features:data?.id?[data]:[];}
async function request(url){const r=await fetch(url,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
function wkt(b){return 'POLYGON(('+[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[b[0],b[1]]].map(x=>x.join(' ')).join(',')+'))';}
const queue=[bbox],ids=new Map();let cells=0,capped=0,failed=0,unresolved=0;
while(queue.length&&cells<MAX_CELLS){
 const b=queue.shift(),url=new URL('https://api.visicom.ua/data-api/5.0/uk/geocode.json');
 url.searchParams.set('key',key);url.searchParams.set('categories','adr_address');
 url.searchParams.set('intersect',wkt(b));url.searchParams.set('limit','250');
 try{
  const items=normalize(await request(url));cells++;
  for(const x of items){if(x?.id&&typeof x.id==='string')ids.set(x.id,{street:x.properties?.street||'',name:x.properties?.name||''});}
  console.log('Cell '+cells+': returned '+items.length+' objects');
  // A full page may hide more data. Divide into 4; do not call saturated cells complete.
  if(items.length>=250){capped++;const [w,s,e,n]=b,mx=(w+e)/2,my=(s+n)/2;
   if(Math.abs(e-w)>0.0002&&Math.abs(n-s)>0.0002)queue.push([w,s,mx,my],[mx,s,e,my],[w,my,mx,n],[mx,my,e,n]);else unresolved++;
  }
 }catch(err){cells++;failed++;console.log('Cell '+cells+': '+(/^HTTP \d+$/.test(err.message)?err.message:'network error'));}
 await new Promise(r=>setTimeout(r,300));
}
const complete=queue.length===0&&failed===0&&unresolved===0;
console.log('DISCOVERY '+JSON.stringify({cells,uniqueAddresses:ids.size,capped,unresolved,remainingCells:queue.length,failed,complete}));
const features=[],known=new Set();let attempts=0;
for(const [id,p] of (process.env.VISICOM_IDS_ONLY==='1'?[]:ids)){
 if(features.length>=MAX_FEATURES)break;
 if(!/^[a-z0-9_-]+$/i.test(id))continue;
 attempts++;
 try{
  const u=new URL('https://api.visicom.ua/data-api/5.0/uk/feature/'+encodeURIComponent(id)+'.json');u.searchParams.set('key',key);
  const item=normalize(await request(u))[0];
  if(item&&['Polygon','MultiPolygon'].includes(item.geometry?.type)&&!known.has(id)){known.add(id);features.push({type:'Feature',geometry:item.geometry,properties:{visicomId:id,street:String(p.street).slice(0,100),name:String(p.name).slice(0,40),geometryType:item.geometry.type}});}
 }catch(e){console.log('Feature request failed: '+(/^HTTP \d+$/.test(e.message)?e.message:'network error'));}
 await new Promise(r=>setTimeout(r,250));
}
const payload=process.env.VISICOM_IDS_ONLY==='1'?{type:'VisicomAddressIndex',entries:[...ids].map(([id,p])=>({id,...p})),metadata:{completeDiscovery:complete,uniqueAddresses:ids.size,queriedCells:cells,unresolved,failed,remainingCells:queue.length}}:{type:'FeatureCollection',features,metadata:{completeDiscovery:complete,uniqueAddresses:ids.size,queriedCells:cells}};
const salt=randomBytes(16),iv=randomBytes(12),k=pbkdf2Sync(password,salt,210000,32,'sha256'),cipher=createCipheriv('aes-256-gcm',k,iv);
const ct=Buffer.concat([cipher.update(JSON.stringify(payload),'utf8'),cipher.final(),cipher.getAuthTag()]);
const out={version:1,kdf:'PBKDF2-SHA256',iterations:210000,salt:salt.toString('base64'),iv:iv.toString('base64'),data:ct.toString('base64')};
const target=process.env.VISICOM_EXPORT_PATH;if(!target)throw Error('VISICOM_EXPORT_PATH missing');
await mkdir(dirname(target),{recursive:true});await writeFile(target,JSON.stringify(out)+'\n',{mode:0o600});
console.log('ENCRYPTED_SPATIAL_EXPORT '+JSON.stringify({polygons:features.length,featureRequests:attempts,completeDiscovery:complete}));

if(process.env.VISICOM_IDS_ONLY==='1'&&!complete){console.error('Incomplete address discovery. Encrypted diagnostic still uploaded; do not treat as complete.');process.exitCode=2;}
