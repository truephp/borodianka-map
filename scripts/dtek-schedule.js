/* Conservative schedule inference for Borodianka. The schedule is a forecast,
   not a sensor reporting physical voltage at the address. */
(function(root){
  'use strict';
  const DAY_MS=86400000;
  const GROUP=/^GPV([1-6])\.([12])$/;
  function kyivWall(date){
    const parts=new Intl.DateTimeFormat('en-GB',{
      timeZone:'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',hourCycle:'h23'
    }).formatToParts(date);
    const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
    return p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute;
  }
  function isoWall(value){
    return /^\d{4}-\d\d-\d\dT(?:[01]\d|2[0-3]):[0-5]\d$/.test(value||'')?value:null;
  }
  function decodeGroup(raw){
    const values=[raw?.sub_type_reason,raw?.sub_type,raw?.type].flat(Infinity);
    return [...new Set(values.filter(x=>typeof x==='string')
      .flatMap(x=>[...x.matchAll(/GPV[1-6]\.[12]/gi)].map(m=>m[0].toUpperCase()))
      .filter(x=>GROUP.test(x)))];
  }
  function emergencyText(raw){
    return [raw?.type,raw?.sub_type,raw?.sub_type_reason].flat(Infinity)
      .filter(x=>typeof x==='string').join(' ').toLowerCase();
  }
  function toWall(value){
    if(typeof value!=='string'||!value.trim())return null;
    const v=value.trim();
    let m=v.match(/^(\d\d)\.(\d\d)\.(\d{4})\s+(\d\d):(\d\d)/);
    if(m)return m[3]+'-'+m[2]+'-'+m[1]+'T'+m[4]+':'+m[5];
    m=v.match(/^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d)/);
    if(m&&!/(Z|[+-]\d\d:?\d\d)$/.test(v))return m[1]+'T'+m[2];
    const instant=new Date(v);
    return Number.isNaN(instant.getTime())?null:kyivWall(instant);
  }
  function emergency(raw,wall){
    const str=emergencyText(raw);
    if(!/аварійн|аварийн|emergency|accident/.test(str))return null;
    const start=toWall(raw?.start_date),end=toWall(raw?.end_date);
    if(start&&wall<start)return null;
    if(end&&wall>=end)return null;
    if(!start&&!end)return 'reported'; // Report exists, but interval is unverified.
    return 'active';
  }
  function sourceFresh(data,wall){
    if(data?.schemaVersion!==1||data?.region!=='kyiv-region'||data?.timezone!=='Europe/Kyiv')return false;
    const source=new Date(data.sourceUpdatedAt);
    if(!Number.isFinite(source.getTime()))return false;
    // Evaluation can be historical or future, but not outside the published day.
    // Enforce an age limit relative to the current clock, not the selected date.
    const age=Date.now()-source.getTime();
    return age>=-15*60000&&age<=12*3600000&&!!isoWall(wall);
  }
  function stateAt(raw,data,wall){
    if(!isoWall(wall))return {kind:'unknown',reason:'invalid_time'};
    const em=emergency(raw,wall);
    if(em==='active')return {kind:'emergency',reason:'active_address_emergency'};
    if(em==='reported')return {kind:'emergencyNotice',reason:'emergency_without_valid_interval'};
    const groups=decodeGroup(raw);
    if(!groups.length)return {kind:'unknown',reason:'no_group'};
    if(!sourceFresh(data,wall))return {kind:'unknown',reason:'missing_or_stale_schedule',groups};
    const date=wall.slice(0,10);
    const day=data.days?.[date];
    if(!day)return {kind:'unknown',reason:'unpublished_day',groups};
    const hour=Number(wall.slice(11,13));
    const minute=Number(wall.slice(14,16));
    const statuses=[];
    for(const group of groups){
      const slots=day[group];
      if(!Array.isArray(slots)||slots.length!==24)return {kind:'unknown',reason:'missing_group',groups};
      const value=slots[hour];
      if(!['yes','no','first','second','maybe','mfirst','msecond'].includes(value))
        return {kind:'unknown',reason:'invalid_slot',groups};
      const off=value==='no'||(value==='first'&&minute<30)||(value==='second'&&minute>=30);
      const maybe=value==='maybe'||(value==='mfirst'&&minute<30)||(value==='msecond'&&minute>=30);
      statuses.push(maybe?'possible':off?'off':'on');
    }
    const distinct=[...new Set(statuses)];
    return {kind:distinct.length===1?distinct[0]:'mixed',groups,reason:'published_schedule'};
  }
  function forPolygon(entries,data,wall){
    if(!Array.isArray(entries)||!entries.length)return {kind:'unknown',reason:'no_address'};
    if(!entries.every(x=>x.confirmed))return {kind:'unconfirmed',reason:'unverified_match'};
    const results=entries.map(x=>stateAt(x.record?.dtek,data,wall));
    if(results.some(x=>x.kind==='emergency'))return {kind:'emergency',reason:'active_address_emergency'};
    if(results.some(x=>x.kind==='emergencyNotice'))return {kind:'emergencyNotice',reason:'emergency_without_valid_interval'};
    const distinct=[...new Set(results.map(x=>x.kind))];
    return {kind:distinct.length===1?distinct[0]:'mixed',reason:'combined_addresses'};
  }
  root.DtekSchedule={kyivWall,decodeGroup,toWall,stateAt,forPolygon};
})(typeof window!=='undefined'?window:globalThis);
