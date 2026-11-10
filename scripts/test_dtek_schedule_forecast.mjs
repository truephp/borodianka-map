import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const script=fs.readFileSync('scripts/dtek-schedule.js','utf8');
const sandbox={globalThis:{},Date,Intl};
vm.createContext(sandbox);
vm.runInContext(script,sandbox);
const api=sandbox.globalThis.DtekSchedule;
assert.ok(api,'DtekSchedule global missing');
const now=api.kyivWall(new Date());
const date=now.slice(0,10);
const slots=Array(24).fill('yes');
slots[12]='first';
slots[13]='second';
slots[14]='no';
const source={
 schemaVersion:1,region:'kyiv-region',timezone:'Europe/Kyiv',
 sourceUpdatedAt:new Date().toISOString(),
 days:{[date]:{'GPV1.2':slots}}
};
const raw={sub_type_reason:['GPV1.2']};
assert.deepEqual(api.decodeGroup(raw),['GPV1.2']);
assert.equal(api.stateAt(raw,source,date+'T12:15').kind,'off');
assert.equal(api.stateAt(raw,source,date+'T12:45').kind,'on');
assert.equal(api.stateAt(raw,source,date+'T13:15').kind,'on');
assert.equal(api.stateAt(raw,source,date+'T13:45').kind,'off');
assert.equal(api.stateAt(raw,source,date+'T14:30').kind,'off');
assert.equal(api.stateAt(raw,source,date+'T15:30').kind,'on');
assert.equal(api.stateAt(raw,source,'2025-01-01T15:30').kind,'unknown');
assert.equal(api.stateAt({},source,date+'T15:30').kind,'unknown');
const emergency={...raw,type:'Аварійне відключення',
 start_date:date+' 12:00',end_date:date+' 16:00'};
assert.equal(api.stateAt(emergency,source,date+'T13:30').kind,'emergency');
assert.equal(api.stateAt(emergency,source,date+'T16:30').kind,'on');
assert.equal(api.stateAt({type:'Аварійне відключення'},source,date+'T13:30').kind,'emergencyNotice');
assert.equal(api.forPolygon([{confirmed:false,record:{dtek:emergency}}],source,date+'T13:30').kind,'unconfirmed');
console.log('First-party DTEK schedule forecast tests passed');
