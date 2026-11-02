#!/usr/bin/env node
// Diagnostic only. No Visicom response data is persisted or published.
import {readFile} from 'node:fs/promises';

const key=process.env.VISICOM_API_KEY;
if(!key)throw Error('Missing VISICOM_API_KEY GitHub Actions secret');
const buildings=JSON.parse(await readFile('data/buildings.geojson','utf8')).features;
const tagged=buildings.filter(f=>f.properties.street&&f.properties.housenumber);
const untagged=buildings.filter(f=>!f.properties.street&&!f.properties.housenumber);
function sample(items,n){
 const count=Math.min(items.length,n);
 return Array.from({length:count},(_,i)=>items[Math.floor((i+.5)*items.length/count)]);
}
function center(f){
 const pts=f.geometry.coordinates[0];
 return [pts.reduce((a,p)=>a+p[0],0)/pts.length,pts.reduce((a,p)=>a+p[1],0)/pts.length];
}
function normalizeResponse(data){
 if(Array.isArray(data))return {kind:'array',items:data};
 if(data===null)return {kind:'null',items:[]};
 if(!data||typeof data!=='object')return {kind:typeof data,items:null};
 for(const field of ['features','results','items','data']){
  if(Array.isArray(data[field]))return {kind:field,items:data[field]};
 }
 // Geocode may return a single GeoJSON-like feature rather than a collection.
 if(data.type==='Feature'||(data.id!=null&&data.properties&&typeof data.properties==='object'))
  return {kind:'single-feature',items:[data]};
 if(Object.keys(data).length===0)return {kind:'empty-object',items:[]};
 return {kind:'unknown-object',items:null};
}
function norm(s){return String(s??'').toLocaleLowerCase('uk').replace(/[’‘\u0027]/g,'').replace(/\b(вул\.?|вулиця|пров\.?|провулок|просп\.?|проспект)\b/g,'').replace(/[.,\s-]+/g,' ').trim();}
function candidateAddress(item){
 const p=item?.properties||item||{};
 // Property field names may differ across Visicom API result types.
 const street=p.street_name??p.street??p['addr:street']??p.address?.street??p.address?.street_name;
 const number=p.housenumber??p.house_number??p.houseNumber??p['addr:housenumber']??p.address?.house_number??p.address?.housenumber;
 return {street,number,name:p.name,categories:p.categories,dist:p.dist_meters,keys:Object.keys(p)};
}
const selected=[...sample(tagged,10),...sample(untagged,10)];
const stats={nameNumberMatches:0,nameNumberMismatches:0,nameNumberUncertain:0,checked:0,candidateLists:0,empty:0,http403:0,httpOther:0,network:0,unrecognized:0,single:0,matches:0,mismatches:0,comparisonUnavailable:0};
for(const [i,f] of selected.entries()){
 const [lon,lat]=center(f);
 const url=new URL('https://api.visicom.ua/data-api/5.0/uk/geocode.json');
 for(const [k,v] of Object.entries({categories:'adr_address',near:lon+','+lat,radius:'40',limit:'5',order:'distance',key}))
  url.searchParams.set(k,v);
 const tag=f.properties.street&&f.properties.housenumber?'tagged':'untagged';
 stats.checked++;
 try{
  const r=await fetch(url,{signal:AbortSignal.timeout(20000)});
  if(!r.ok){
   const code=r.status;
   if(code===403)stats.http403++;else stats.httpOther++;
   // Do not dump body: may echo request URL (including key).
   console.log('Sample '+(i+1)+' ['+tag+']: HTTP '+code+'; content-type='+String(r.headers.get('content-type')||'unknown').split(';')[0]);
   continue;
  }
  const data=await r.json();
  const {kind,items}=normalizeResponse(data);
  if(!items){
   stats.unrecognized++;
   console.log('Sample '+(i+1)+' ['+tag+']: unexpected schema '+kind+'; root field names '+Object.keys(data).join(','));
   continue;
  }
  if(kind==='single-feature')stats.single++;
  if(!items.length){stats.empty++;console.log('Sample '+(i+1)+' ['+tag+']: empty ('+kind+')');continue;}
  stats.candidateLists++;
  let matchStatus='not-comparable';
  if(tag==='tagged'){
   const candidates=items.map(candidateAddress);
   const comparable=candidates.filter(c=>c.street&&c.number);
   if(!comparable.length)stats.comparisonUnavailable++;
   else if(comparable.some(c=>norm(c.street)===norm(f.properties.street)&&norm(c.number)===norm(f.properties.housenumber))){matchStatus='exact-street-and-number';stats.matches++;}
   else{matchStatus='no-exact-match';stats.mismatches++;}
   if(!comparable.length)
    console.log('Sample '+(i+1)+' ['+tag+']: available candidate property names '+[...new Set(candidates.flatMap(c=>c.keys))].slice(0,35).join(','));
  }
  // Visicom often provides the house number in 'name' rather than a dedicated field.
  if(tag==='tagged'){
   const osmStreet=norm(f.properties.street),osmNumber=norm(f.properties.housenumber);
   const possible=items.map(candidateAddress).filter(c=>c.street&&c.name);
   const exact=possible.some(c=>norm(c.street)===osmStreet&&(norm(c.name)===osmNumber||norm(c.name).split(' ').includes(osmNumber)));
   if(exact)stats.nameNumberMatches++;
   else if(possible.length)stats.nameNumberMismatches++;
   else stats.nameNumberUncertain++;
  }
  console.log('Sample '+(i+1)+' ['+tag+']: '+items.length+' candidate(s); shape='+kind+'; addressMatch='+matchStatus+'; OSM address='+JSON.stringify(tag==='tagged'?[f.properties.street,f.properties.housenumber]:null));
  for(const [ci,item] of items.entries()){
   const c=candidateAddress(item);
   // Print only selected address properties, never raw response, URLs or credentials.
   const safe=v=>typeof v==='string'?v.slice(0,120):v;
   console.log('  Candidate '+(ci+1)+': '+JSON.stringify({name:safe(c.name),street:safe(c.street),categories:c.categories,dist_meters:c.dist}));
  }
 }catch(e){
  stats.network++;
  console.log('Sample '+(i+1)+' ['+tag+']: network/parsing error '+(e?.name||'Error'));
 }
 await new Promise(resolve=>setTimeout(resolve,400));
}
console.log('SUMMARY '+JSON.stringify(stats));
if(stats.candidateLists===0)process.exitCode=1;
