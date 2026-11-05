#!/usr/bin/env node
// One full encrypted export. The checkpoint is encrypted too; no proprietary plaintext artifacts.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
import {randomBytes,pbkdf2Sync,createCipheriv,createDecipheriv} from 'node:crypto';
const pass=process.env.VISICOM_EXPORT_PASSWORD,key=process.env.VISICOM_API_KEY;
if(!pass||!key)throw Error('Missing Visicom credentials');
function decrypt(v){if(v.version!==1||v.kdf!=='PBKDF2-SHA256')throw Error('Unsupported encrypted file');const k=pbkdf2Sync(pass,Buffer.from(v.salt,'base64'),v.iterations,32,'sha256'),all=Buffer.from(v.data,'base64'),c=createDecipheriv('aes-256-gcm',k,Buffer.from(v.iv,'base64'));c.setAuthTag(all.subarray(-16));return JSON.parse(Buffer.concat([c.update(all.subarray(0,-16)),c.final()]).toString());}
function encrypt(data){const salt=randomBytes(16),iv=randomBytes(12),k=pbkdf2Sync(pass,salt,210000,32,'sha256'),c=createCipheriv('aes-256-gcm',k,iv),bytes=Buffer.concat([c.update(JSON.stringify(data),'utf8'),c.final(),c.getAuthTag()]);return {version:1,kdf:'PBKDF2-SHA256',iterations:210000,salt:salt.toString('base64'),iv:iv.toString('base64'),data:bytes.toString('base64')};}
async function save(file,data){await mkdir(dirname(file),{recursive:true});await writeFile(file,JSON.stringify(encrypt(data))+'\n',{mode:0o600});}
const index=decrypt(JSON.parse(await readFile(process.env.VISICOM_INDEX_FILE,'utf8')));
if(index.type!=='VisicomAddressIndex'||!index.metadata?.completeDiscovery||!Array.isArray(index.entries))throw Error('Incomplete or invalid address index');
const output=process.env.VISICOM_EXPORT_PATH,checkpoint=process.env.VISICOM_CHECKPOINT_PATH;
let state={done:{},features:[],nonPolygons:[],failures:[]};
if(process.env.VISICOM_RESUME_FILE){state=decrypt(JSON.parse(await readFile(process.env.VISICOM_RESUME_FILE,'utf8')));if(!state.done||!Array.isArray(state.features))throw Error('Invalid checkpoint');state.failures=[];}
const seen=new Set(state.features.map(x=>String(x.properties?.visicomId)));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let processed=0;
for(const [n,p] of index.entries.entries()){
 const id=String(p.id);
 if(state.done[id])continue;
 if(!/^[a-z0-9_-]+$/i.test(id)){state.failures.push(id);continue;}
 let item=null,reason='';
 for(let attempt=0;attempt<4;attempt++){
  try{
   const url=new URL('https://api.visicom.ua/data-api/5.0/uk/feature/'+encodeURIComponent(id)+'.json');url.searchParams.set('key',key);
   const r=await fetch(url,{signal:AbortSignal.timeout(30000)});
   if(!r.ok)throw Error('HTTP '+r.status);
   const response=await r.json();item=Array.isArray(response?.features)?response.features[0]:response;break;
  }catch(e){reason=/^HTTP \d+$/.test(e.message)?e.message:'network-error';if(attempt<3)await sleep(1500*2**attempt);}
 }
 if(item){
  if(['Polygon','MultiPolygon'].includes(item.geometry?.type)){if(!seen.has(id)){state.features.push({type:'Feature',geometry:item.geometry,properties:{visicomId:id,street:String(item.properties?.street||p.street||''),name:String(item.properties?.name||p.name||''),street_type:item.properties?.street_type||null,street_id:item.properties?.street_id||null,geometryType:item.geometry.type}});seen.add(id);}}
  else state.nonPolygons.push(id);
  state.done[id]=true;
 }else{state.failures.push(id);console.log('Feature request unresolved at index '+n+': '+reason);}
 processed++;
 if(processed%100===0){await save(checkpoint,state);console.log('CHECKPOINT '+JSON.stringify({processed,finished:Object.keys(state.done).length,polygons:state.features.length,failures:state.failures.length}));}
 await sleep(400);
}
await save(checkpoint,state);
const incomplete=state.failures.length>0;
const payload={type:'FeatureCollection',features:state.features,metadata:{total:index.entries.length,completed:Object.keys(state.done).length,failed:state.failures.length,nonPolygons:state.nonPolygons.length,complete:!incomplete&&Object.keys(state.done).length===index.entries.length}};
await save(output,payload);
console.log('FULL_FEATURE_EXPORT '+JSON.stringify({total:payload.metadata.total,polygons:state.features.length,failed:state.failures.length,complete:payload.metadata.complete}));
if(!payload.metadata.complete)process.exitCode=2;
