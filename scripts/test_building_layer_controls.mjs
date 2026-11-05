#!/usr/bin/env node
// Regression test: independent OSM/Visicom toggles vs unified layer and labels.
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';

const html=readFileSync('index.html','utf8');
const start=html.indexOf("const showOsmPolygons=document.getElementById('showBuildings');");
const end=html.indexOf('function updateUnified(){',start);
assert(start>=0&&end>start,'Building-layer control handler not found');

function control(checked){
 return {checked,callbacks:new Map(),addEventListener(type,fn){this.callbacks.set(type,fn);},
  click(){this.checked=!this.checked;this.callbacks.get('change')();}};
}
const osm=control(true),visicom=control(true),unified=control(false);
const controls={showBuildings:osm,showVisicomPolygons:visicom,unifiedBuildings:unified};
const visicomPolygonMap={size:2};
const calls={update:0,visicom:0,render:0};
const sandbox={
 document:{getElementById:id=>controls[id]},
 visicomPolygonMap,
 updateUnified:()=>calls.update++,
 renderVisicomPolygons:()=>calls.visicom++,
 scheduleRender:()=>calls.render++,
 assert,
};
runInNewContext(html.slice(start,end)+`
 assert.equal(isUnified(),false);
 showUnifiedBuildings.click();
 assert.equal(showUnifiedBuildings.checked,true);
 assert.equal(showOsmPolygons.checked,false);
 assert.equal(showVisicomPolygons.checked,false);
 assert.equal(isUnified(),true);
 showVisicomPolygons.click();
 assert.equal(showUnifiedBuildings.checked,false);
 assert.equal(showOsmPolygons.checked,false);
 assert.equal(showVisicomPolygons.checked,true);
 showOsmPolygons.click();
 assert.equal(showVisicomPolygons.checked,true);
 assert.equal(showOsmPolygons.checked,true);
 assert.equal(showUnifiedBuildings.checked,false);
 showUnifiedBuildings.click();
 assert.equal(showOsmPolygons.checked,false);
 assert.equal(showVisicomPolygons.checked,false);
 selectIndependentOsm();
 assert.equal(showUnifiedBuildings.checked,false);
 assert.equal(showOsmPolygons.checked,true);
`,sandbox);
assert(calls.render>0&&calls.visicom>0&&calls.update>0);
const numbers=html.slice(html.indexOf('function renderHouseNumbers(){'),html.indexOf('function renderArea(){'));
assert(!numbers.includes("!document.getElementById('showBuildings').checked"),
  'House numbers must not depend on OSM polygons being visible');
assert(numbers.includes("map.getZoom()<16"),'Keep house-number zoom threshold');
console.log('PASS: unified checkbox exclusivity, independent OSM+Visicom, numbers without polygon visibility');
