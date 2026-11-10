import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// The former "GPV group present" classifier was replaced by time-specific
// evaluation in scripts/dtek-schedule.js. Check the new integration points.
const html=readFileSync('index.html','utf8');
const engine=readFileSync('scripts/dtek-schedule.js','utf8');
assert.match(html,/id="dtekOutageMode"/);
assert.match(html,/id="dtekForecastTime"/);
assert.match(html,/id="dtekForecastNow"/);
assert.match(html,/dtekOutageMode\.addEventListener\('change',dtekPresenceDraw\)/);
assert.match(html,/DtekSchedule\.forPolygon\(entries,dtekScheduleData,dtekForecastTime.value\)/);
assert.match(html,/dtekOutageColors\[d\?\.forecast\?\.kind\|\|'unknown'\]/);
assert.match(engine,/function emergency\(raw,wall\)/);
assert.match(engine,/function stateAt\(raw,data,wall\)/);
assert.match(engine,/if\(em==='active'\)return \{kind:'emergency'/);
assert.match(engine,/if\(!sourceFresh\(data,wall\)\)return \{kind:'unknown'/);
console.log('DTEK outage forecast integration: OK');
