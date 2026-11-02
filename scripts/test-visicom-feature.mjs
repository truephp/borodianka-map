#!/usr/bin/env node
// Diagnostic: inspect geometry types only; never publish Visicom response data.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
import {randomBytes,pbkdf2Sync,createCipheriv} from 'node:crypto';
const key=process.env.VISICOM_API_KEY;
if(!key)throw Error('VISICOM_API_KEY missing');
const features=JSON.parse(await readFile('data/buildings.geojson','utf8')).features;
const selected=features.filter(f=>f.properties.street&&f.properties.housenumber).slice(0,30);
const exported=new Map();
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
  const item=response[0];
  const type=item?.geometry?.type||'none';
  if(['Polygon','MultiPolygon'].includes(type))exported.set(String(id),{type:'Feature',geometry:item.geometry,properties:{visicomId:String(id),street:String(geo[0]?.properties?.street||''),name:String(geo[0]?.properties?.name||''),geometryType:type}});
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

if(process.env.VISICOM_EXPORT_PATH){
 const password=process.env.VISICOM_EXPORT_PASSWORD;
 if(!password||password.length<12)throw Error('VISICOM_EXPORT_PASSWORD secret missing or too short');
 const salt=randomBytes(16),iv=randomBytes(12),keyBytes=pbkdf2Sync(password,salt,210000,32,'sha256');
 const cipher=createCipheriv('aes-256-gcm',keyBytes,iv);
 const plain=Buffer.from(JSON.stringify({type:'FeatureCollection',features:[...exported.values()]}));
 const encrypted=Buffer.concat([cipher.update(plain),cipher.final()]);
 const envelope={version:1,kdf:'PBKDF2-SHA256',iterations:210000,salt:salt.toString('base64'),iv:iv.toString('base64'),data:Buffer.concat([encrypted,cipher.getAuthTag()]).toString('base64')};
 await mkdir(dirname(process.env.VISICOM_EXPORT_PATH),{recursive:true});
 await writeFile(process.env.VISICOM_EXPORT_PATH,JSON.stringify(envelope)+'\n',{mode:0o600});
 console.log('Encrypted feature collection: '+exported.size+' unique polygons');
}
