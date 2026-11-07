#!/usr/bin/env node
// The editor downloads cumulative master and merges local exports by stable ID.
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';

const html=readFileSync('index.html','utf8');
const begin=html.indexOf('function mergeManualPatchDocuments(base,incoming){');
const end=html.indexOf("document.getElementById('dtekReviewExport')",begin);
assert(begin>=0&&end>begin,'Frontend cumulative merge helper unavailable');

const doc=(decisions=[],geometryPatches=[],addressOverrides=[])=>({
 schemaVersion:1,source:'manual-dtek-borodianka-review',
 decisions,geometryPatches,addressOverrides
});
const baseGeom={type:'Polygon',coordinates:[[[0,0],[2,0],[2,2],[0,2],[0,0]]]};
const alternate={type:'Polygon',coordinates:[[[1,1],[3,1],[3,3],[1,3],[1,1]]]};
const original=doc([
 {city:'Бородянка',street:'Семашка',house:'3',action:'confirm',links:[{source:'osm',id:'7'}]}
],[{source:'osm',id:'7',geometry:alternate,baseGeometry:baseGeom}]);
const incoming=doc([],[{source:'osm',id:'7',geometry:baseGeom}],[
 {osmId:'8',baseGeometry:baseGeom,includeOriginal:false,addresses:[]}
]);
runInNewContext(html.slice(begin,end)+`
 const output=mergeManualPatchDocuments({...original,masterRevision:5},incoming);
 assert.equal(output.baseRevision,5);
 assert.throws(()=>mergeManualPatchDocuments({...original,masterRevision:5},{...incoming,baseRevision:4}),/старої ревізії/);
 assert.equal(output.decisions.length,1);
 assert.equal(output.geometryPatches.length,1);
 assert.equal(output.addressOverrides.length,1);
 assert.equal(output.geometryPatches[0].baseGeometry.coordinates[0][0][0],0);
 assert.equal(output.geometryPatches[0].geometry.coordinates[0][0][0],0);
 const incompatible=structuredClone(incoming);
 incompatible.geometryPatches[0].baseGeometry=alternate;
 assert.throws(()=>mergeManualPatchDocuments(original,incompatible),/Змінився вихідний OSM/);
`,{original,incoming,baseGeom,alternate,assert,structuredClone,Date});
assert(html.includes("fetch('./data/borodianka-manual-overrides.json'"));
assert(html.includes("fetch('./data/buildings.original.geojson'"));
console.log('PASS: browser loads cumulative master, preserves prior DTEK/geometry and guards original OSM baseline');
