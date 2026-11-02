#!/usr/bin/env node
// Decrypt a spatial ID index from a previous run, fetch a slice, re-encrypt features.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
import {randomBytes,createDecipheriv,createCipheriv,pbkdf2Sync} from 'node:crypto';
const pass=process.env.VISICOM_EXPORT_PASSWORD,key=process.env.VISICOM_API_KEY;
if(!pass||!key)throw Error('Missing Visicom secrets');
const env=JSON.parse(await readFile(process.env.VISICOM_INDEX_FILE,'utf8'));
if(env.version!==1||env.kdf!=='PBKDF2-SHA256')throw Error('Unsupported encrypted index');
const oldKey=pbkdf2Sync(pass,Buffer.from(env.salt,'base64'),env.iterations,32,'sha256');
const cipherBytes=Buffer.from(env.data,'base64'),dec=createDecipheriv('aes-256-gcm',oldKey,Buffer.from(env.iv,'base64'));
dec.setAuthTag(cipherBytes.subarray(-16));
const index=JSON.parse(Buffer.concat([dec.update(cipherBytes.subarray(0,-16)),dec.final()]).toString());
if(index.type!=='VisicomAddressIndex'||!Array.isArray(index.entries))throw Error('Not an address index');
if(index.metadata?.completeDiscovery!==true)throw Error('Index discovery incomplete; run discovery again');
const offset=Math.max(0,Number(process.env.VISICOM_OFFSET||0));
const limit=Math.min(250,Math.max(1,Number(process.env.VISICOM_BATCH_SIZE||100)));
const entries=index.entries.slice(offset,offset+limit),features=[],failures=[];
for(const [n,p] of entries.entries()){
 try{
  if(!/^[a-z0-9_-]+$/i.test(p.id))throw Error('Invalid ID');
  const url=new URL('https://api.visicom.ua/data-api/5.0/uk/feature/'+encodeURIComponent(p.id)+'.json');url.searchParams.set('key',key);
  const r=await fetch(url,{signal:AbortSignal.timeout(25000)});
  if(!r.ok)throw Error('HTTP '+r.status);
  const obj=await r.json(),item=Array.isArray(obj?.features)?obj.features[0]:obj;
  if(['Polygon','MultiPolygon'].includes(item?.geometry?.type))
   features.push({type:'Feature',geometry:item.geometry,properties:{visicomId:p.id,street:p.street,name:p.name,geometryType:item.geometry.type}});
 }catch(e){failures.push(p.id);console.log('Feature '+(offset+n)+': '+(/^HTTP \d+$/.test(e.message)?e.message:'request failure'));}
 await new Promise(r=>setTimeout(r,400));
}
const payload={type:'FeatureCollection',features,metadata:{offset,requested:entries.length,total:index.entries.length,failed:failures.length,completeDiscovery:true}};
const salt=randomBytes(16),iv=randomBytes(12),k=pbkdf2Sync(pass,salt,210000,32,'sha256'),enc=createCipheriv('aes-256-gcm',k,iv);
const encrypted=Buffer.concat([enc.update(JSON.stringify(payload),'utf8'),enc.final(),enc.getAuthTag()]);
const out={version:1,kdf:'PBKDF2-SHA256',iterations:210000,salt:salt.toString('base64'),iv:iv.toString('base64'),data:encrypted.toString('base64')};
await mkdir(dirname(process.env.VISICOM_EXPORT_PATH),{recursive:true});
await writeFile(process.env.VISICOM_EXPORT_PATH,JSON.stringify(out)+'\n',{mode:0o600});
console.log('FEATURE_BATCH '+JSON.stringify({offset,requested:entries.length,polygons:features.length,failed:failures.length,total:index.entries.length,nextOffset:offset+entries.length}));
if(failures.length)process.exitCode=2;
