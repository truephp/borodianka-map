import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync('index.html','utf8');
const begin=html.indexOf('function dtekBuildingHasAddress(feature){');
const end=html.indexOf('function dtekUnaddressedFeatures(){',begin);
assert.ok(begin>0&&end>begin,'Address classification helper missing');
const ctx={osmPolygonAddresses(feature){return feature.properties.addresses||
  (feature.properties.street&&feature.properties.housenumber?
    [{street:feature.properties.street,housenumber:feature.properties.housenumber}]:[]);}};
vm.createContext(ctx);
vm.runInContext(html.slice(begin,end)+'\nthis.hasAddress=dtekBuildingHasAddress;',ctx);
const hasAddress=ctx.hasAddress;
assert.equal(hasAddress({properties:{source:'osm',id:1}}),false);
assert.equal(hasAddress({properties:{source:'osm',street:'Вулиця'}}),false);
assert.equal(hasAddress({properties:{source:'osm',street:'Вулиця',housenumber:'3'}}),true);
assert.equal(hasAddress({properties:{source:'osm',addresses:[{street:'Вулиця',housenumber:'3'}]}}),true);
assert.equal(hasAddress({properties:{source:'osm',addresses:[]}}),false);
assert.equal(hasAddress({properties:{source:'visicom',street:'Вулиця',name:'3'}}),true);
assert.equal(hasAddress({properties:{source:'visicom',street:'Вулиця'}}),false);
assert.equal(hasAddress({properties:{source:'visicom'}}),false);
assert.match(html,/function dtekPresenceDraw\(\)\{\s*dtekPresenceLayer\.clearLayers\(\);\s*drawDtekUnaddressed\(\);/);
assert.match(html,/if\(!dtekOutageMode\.checked\)return;/);
assert.match(html,/dtekUnaddressedLayer\.clearLayers\(\);/);
console.log('Unaddressed OSM/Visicom forecast gray layer: OK');
