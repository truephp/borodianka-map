import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync('index.html','utf8');
assert.match(html,/id="dtekOutageMode"/);
assert.match(html,/dtekOutageMode\.addEventListener\('change',dtekPresenceDraw\)/);
const start=html.indexOf('function dtekOutageCategory(fields){');
const end=html.indexOf('function dtekPresenceDraw(){',start);
assert.ok(start>=0&&end>start,'DTEK classification helpers not found');
const sandbox={};
vm.createContext(sandbox);
vm.runInContext(html.slice(start,end)+
  '\nthis.classify=dtekOutageCategory;this.polygon=dtekPolygonOutageCategory;',sandbox);

const classify=sandbox.classify;
assert.equal(classify({type:'',sub_type:'',sub_type_reason:['GPV1.2']}),'scheduled');
assert.equal(classify({type:'Аварійне відключення'}),'emergency');
assert.equal(classify({type:'',sub_type:'',sub_type_reason:[]}), 'unknown');
assert.equal(classify({}), 'unknown');
assert.equal(classify(null),'unknown');
const polygon=sandbox.polygon;
assert.equal(polygon([{confirmed:true,record:{dtek:{sub_type_reason:['GPV1.2']}}}]),'scheduled');
assert.equal(polygon([{confirmed:false,record:{dtek:{sub_type_reason:['GPV1.2']}}}]),'unconfirmed');
assert.equal(polygon([
 {confirmed:true,record:{dtek:{sub_type_reason:['GPV1.2']}}},
 {confirmed:true,record:{dtek:{type:'Аварійне відключення'}}}
]),'conflict');
console.log('DTEK outage-signal classification: OK');
