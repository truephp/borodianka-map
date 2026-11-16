import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html=fs.readFileSync('index.html','utf8');
const start=html.indexOf("const dtekR2BaseInput=");
const end=html.indexOf("async function loadDtekSchedule(){",start);
assert.ok(start>=0 && end>start);
const localStorage={getItem:()=>'',setItem:()=>{}};
const fields={
 dtekR2BaseUrl:{value:''},localTilesUrl:{value:''},unifiedBuildingsUrl:{value:''}
};
const document={getElementById(id){return fields[id]}};
fields.dtekR2BaseUrl.addEventListener=()=>{};
const sandbox={document,localStorage,URL,console,localTilesUrl:fields.localTilesUrl,loadDtekSchedule(){},dtekReviewAutoLoad(){},getUnifiedBuildingsR2Url(){return null;}};
vm.createContext(sandbox);
vm.runInContext(html.slice(start,end)+"\nthis.dynamic=dtekDynamicUrl;this.base=dtekR2Base",sandbox);
assert.equal(sandbox.dynamic('dtek-gpv-schedule.json'),'./data/dtek-gpv-schedule.json');
fields.dtekR2BaseUrl.value='https://r2.example.org/borodianka/data';
assert.equal(sandbox.dynamic('dtek-gpv-schedule.json'),'https://r2.example.org/borodianka/data/dtek-gpv-schedule.json');
assert.equal(sandbox.dynamic('dtek-all-unified-matches.enc.json'),'https://r2.example.org/borodianka/data/dtek-all-unified-matches.enc.json');
fields.dtekR2BaseUrl.value='http://unsafe.example.org/borodianka/data';
assert.throws(()=>sandbox.base(),/HTTPS/);
fields.dtekR2BaseUrl.value='';
fields.localTilesUrl.value='https://r2.example.org/borodianka/v2';
assert.equal(sandbox.dynamic('dtek-gpv-schedule.json'),'https://r2.example.org/borodianka/data/dtek-gpv-schedule.json');
assert.match(html,/if\(!dtekReviewDecisions.size && !dtekReviewSelectedLinks.size\)/);
console.log('DTEK dynamic R2 URLs and fallback safeguards: OK');
