const assert = require('node:assert/strict');
const {inspectRuns, TARGETS} = require('./dtek-watchdog.cjs');
const now=Date.parse('2026-11-13T10:00:00Z');
const run=(status,conclusion,minutes,id=1)=>({
  id,head_branch:'main',status,conclusion,
  created_at:new Date(now-minutes*60000).toISOString(),
  updated_at:new Date(now-(minutes-1)*60000).toISOString()
});
assert.equal(TARGETS.length,2);
assert.equal(inspectRuns([run('completed','success',60)],now).action,'fresh');
assert.equal(inspectRuns([run('completed','success',75)],now).action,'dispatch');
assert.equal(inspectRuns([
  run('in_progress',null,6,2),run('completed','success',150,1)
],now).action,'running');
assert.equal(inspectRuns([
  run('completed','failure',9,2),run('completed','success',150,1)
],now).action,'cooldown');
assert.equal(inspectRuns([
  run('in_progress',null,45,2),run('completed','success',150,1)
],now).action,'dispatch');
assert.equal(inspectRuns([],now).action,'dispatch');
assert.equal(inspectRuns([{
  ...run('completed','success',8),head_branch:'feature'
}],now).action,'dispatch');
console.log('DTEK freshness watchdog policy: OK');
