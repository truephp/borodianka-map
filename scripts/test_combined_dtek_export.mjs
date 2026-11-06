#!/usr/bin/env node
// Combined DTEK export keeps its legacy decision schema and captures edits.
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
const html=readFileSync('index.html','utf8');
const start=html.indexOf('function validateCombinedDtekPatches(payload){');
const end=html.indexOf('// Resume a previous manual review',start);
assert(start>=0&&end>start,'Combined DTEK patch validation not found');
const polygon=(x)=>({type:'Polygon',coordinates:[[[x,0],[x+1,0],[x+1,1],[x,1],[x,0]]]});
const source={features:[{type:'Feature',properties:{id:42,street:'вулиця Семашка',housenumber:'3'},geometry:polygon(0)}]};
const pointData={features:[{geometry:{type:'Point',coordinates:[11,0.5]},properties:{id:72,street:'вулиця Семашка',housenumber:'3'}}]};
const sandbox={assert,source,pointData};
runInNewContext(html.slice(start,end)+`
 const buildingData=source,addressPoints=pointData;
 function currentFeatureFrom(){return null;}
 function osmOriginalPolygonAddress(f){return {street:f.properties.street,housenumber:f.properties.housenumber};}
 function osmAddressPointsInside(f){return pointData.features.filter(p=>p.geometry.coordinates[0]>f.geometry.coordinates[0][0][0]&&p.geometry.coordinates[0]<f.geometry.coordinates[0][1][0]);}
 const geometry={type:'Polygon',coordinates:[[[10,0],[12,0],[12,1],[10,1],[10,0]]]};
 const payload={schemaVersion:1,source:'manual-dtek-borodianka-review',decisions:[],
 geometryPatches:[{source:'osm',id:'42',geometry}],
 addressOverrides:[{osmId:'42',includeOriginal:false,addresses:[{street:'вулиця Семашка',housenumber:'3',pointIds:['72']}]}]};
 const valid=validateCombinedDtekPatches(payload);
 assert.equal(valid.geomChanges.length,1);
 assert.equal(valid.addressChanges.length,1);
 assert.equal(source.features[0].geometry.coordinates[0][0][0],0);
 assert.equal(validateCombinedDtekPatches({decisions:[]}).geomChanges.length,0);
 const missing=structuredClone(payload);
 missing.geometryPatches[0].id='999';
 assert.throws(()=>validateCombinedDtekPatches(missing),/Полігон OSM не знайдено/);
 const incorrect=structuredClone(payload);
 incorrect.addressOverrides[0].addresses[0].pointIds=['999'];
 assert.throws(()=>validateCombinedDtekPatches(incorrect),/Адресна точка не відповідає/);
 `,sandbox);
const exp=html.slice(html.indexOf("document.getElementById('dtekReviewExport').addEventListener"),html.indexOf("// Validate all editable OSM changes"));
assert(exp.includes('geometryPatches:[...osmGeomPatches.values()]'));
assert(exp.includes('addressOverrides:[...osmAddressOverrides.values()]'));
assert(exp.includes("source:'manual-dtek-borodianka-review'"));
console.log('PASS: combined DTEK JSON exports geometry/address edits and validates import');
