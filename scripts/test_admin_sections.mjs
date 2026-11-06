#!/usr/bin/env node
// Keep the administrator workflow sections complete and non-overlapping.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';

const html=readFileSync('index.html','utf8');
const begin=html.indexOf('(function groupSettings(){');
const end=html.indexOf('// The demo legend and note are not JS controls',begin);
assert(begin>=0&&end>begin,'Admin section configuration must exist');
const code=html.slice(begin,end);
const expected=[
 ['sources',['visicomImport','unifiedBuildingsUrl','visicomPassword','restoreVisicomCache','visicomImportStatus','clearVisicomPolygons']],
 ['layers',['showBuildings','showVisicomPolygons','unifiedBuildings','showHouseNumbers','basemap']],
 ['geometry',['showGeometryMatches','iouHigh','iouMedium','iouLow','overlapThreshold','showGeometryConflicts']],
 ['addresses',['addressMode','showAddressPoints','visicomColorMode']],
 ['editor',['inspectBuildings']],
 ['dtek',['dtekReviewSection']],
 ['streets',['showStreetColors','width','offset','centerline','streetLabels']]
];
const groups=[...code.matchAll(/\{id:'([^']+)',title:'([^']+)',[\s\S]*?ids:\[([^\]]+)\]\}/g)]
 .map(([,id,title,raw])=>({id,title,ids:[...raw.matchAll(/'([^']+)'/g)].map(v=>v[1])}));
assert.equal(groups.length,7,'Expect seven workflow groups');
const seen=new Set();
for(const [id,required] of expected){
 const g=groups.find(x=>x.id===id);
 assert(g,'Missing '+id);
 for(const control of required)assert(g.ids.includes(control),id+' missing '+control);
 for(const control of g.ids){
  assert(!seen.has(control),'Duplicate admin control: '+control);
  seen.add(control);
  assert(html.includes('id="'+control+'"'),'Control absent from HTML: '+control);
 }
}
assert(code.includes('node=el.closest(\'label\')||el'),'Move existing controls, do not clone');
assert(code.includes('localStorage.setItem'),'Save section expand/collapse state');
console.log('PASS: admin workflow sections have unique, existing controls');
