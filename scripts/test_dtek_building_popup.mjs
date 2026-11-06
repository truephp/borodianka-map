#!/usr/bin/env node
// Regression: normal OSM/Visicom popups must use the decrypted DTEK report.
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';

const html=readFileSync('index.html','utf8');
const start=html.indexOf('function dtekRecordsForPolygon(source,id){');
const end=html.indexOf('const dtekMatchStatuses=',start);
assert(start>=0&&end>start,'DTEK popup matcher must exist');
const mockRecord=(house,links)=>({city:'с-ще Бородянка',street:'вул. Семашка',house,links,
 status:'confirmed',dtek:{type:'',sub_type_reason:['GPV1.2'],start_date:'',end_date:''}});
const records=[
 mockRecord('3',[{source:'visicom',id:'VIS3'},{source:'osm',id:'272972133'},{source:'osm',id:'272972143'}]),
 mockRecord('5',[{source:'osm',id:'other'}]),
];
const decisions=new Map();
const sandbox={assert,records,decisions};
runInNewContext(html.slice(start,end)+`
 const dtekPresenceRecords=records,dtekReviewDecisions=decisions,dtekSourceFetchedAt='2026-11-06';
 function dtekReviewKey(r){return JSON.stringify([r.city,r.street,r.house]);}
 function dtekReviewLinkKey(link){return link.source+':'+String(link.id);}
 function dtekReviewConfirmedLinks(decision){return decision.links||[];}
 function appendDtekFields(){}
 function documentNotUsed(){}
 assert.equal(dtekRecordsForPolygon('osm','272972133').length,1);
 assert.equal(dtekRecordsForPolygon('visicom','VIS3').length,1);
 assert.equal(dtekRecordsForPolygon('osm','missing').length,0);
 decisions.set(dtekReviewKey(records[0]),{action:'reject'});
 assert.equal(dtekRecordsForPolygon('osm','272972133').length,0);
 decisions.set(dtekReviewKey(records[0]),{action:'confirm',links:[{source:'osm',id:'272972143'}]});
 assert.equal(dtekRecordsForPolygon('osm','272972133').length,0);
 assert.equal(dtekRecordsForPolygon('osm','272972143').length,1);
`,sandbox);
assert(!html.includes('поки без даних ДТЕК'),'Stale placeholder remains in OSM popup');
assert(html.includes("appendDtekPopupForBuilding(popup,'osm',p.id)"));
assert(html.includes("appendDtekPopupForBuilding(popup,'visicom',p.visicomId)"));
console.log('PASS: DTEK popup matches current OSM/Visicom links and respects review decisions');
