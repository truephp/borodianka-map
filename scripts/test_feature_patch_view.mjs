#!/usr/bin/env node
// Regression tests for the map's central immutable-feature patch store.
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';

const html = readFileSync('index.html', 'utf8');
const start = html.indexOf('const featurePatches=new Map();');
const end = html.indexOf('const osmAddressOverrides=new Map();', start);
assert(start >= 0 && end > start, 'central patch store must exist');

const original = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties: { id: 7, source: 'osm', street: 'Паркова', housenumber: '2' },
      geometry: { type: 'Polygon', coordinates: [[[0,0],[1,0],[1,1],[0,0]]] } },
    { type: 'Feature', properties: { id: 7, source: 'visicom', visicomId: 7, street: 'Паркова', name: '2' },
      geometry: { type: 'Polygon', coordinates: [[[2,2],[3,2],[3,3],[2,2]]] } },
  ],
};
const sandbox = { original, assert };
runInNewContext(html.slice(start, end) + `
 const first=currentDataset(original);
 assert.equal(first.features[0],original.features[0]);
 const changed={type:'Polygon',coordinates:[[[10,10],[11,10],[11,11],[10,10]]]};
 setFeaturePatch('osm','7',{geometry:changed});
 const updated=currentDataset(original);
 assert.equal(updated.features[0].geometry.coordinates[0][0][0],10);
 assert.equal(updated.features[1].geometry.coordinates[0][0][0],2);
 assert.equal(original.features[0].geometry.coordinates[0][0][0],0);
 assert.equal(currentFeatureFrom(original,'osm','7').geometry,changed);
 setFeaturePatch('osm','7',{properties:{street:'Нова',housenumber:'3е',addresses:[]}});
 const withAddress=currentDataset(original);
 assert.equal(withAddress.features[0].geometry,changed);
 assert.equal(withAddress.features[0].properties.housenumber,'3е');
 assert.equal(original.features[0].properties.housenumber,'2');
 clearFeaturePatch('osm','7','geometry');
 const onlyAddress=currentDataset(original);
 assert.equal(onlyAddress.features[0].geometry,original.features[0].geometry);
 assert.equal(onlyAddress.features[0].properties.housenumber,'3е');
 clearFeaturePatch('osm','7','properties');
 assert.equal(currentDataset(original).features[0],original.features[0]);
`, sandbox);
console.log('PASS: immutable source, single feature patch view, source ID isolation, geometry/address reset');
