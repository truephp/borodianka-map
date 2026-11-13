/** Pure decision policy for the GitHub Actions DTEK schedule watchdog. */
'use strict';

const TARGETS = Object.freeze([
  { workflow: 'dtek-public-schedule.yml', name: 'Public GPV fact schedules' },
  { workflow: 'dtek-all-addresses.yml', name: 'House outage statuses and address matching' },
]);
const MAX_AGE_MINUTES = 65;
const ACTIVE_GRACE_MINUTES = 30;
const RETRY_COOLDOWN_MINUTES = 15;

function inspectRuns(runs, nowMs = Date.now()) {
  const mainRuns = runs.filter(run => run.head_branch === 'main');
  const lastSuccessful = mainRuns.find(run => run.conclusion === 'success');
  const ageMinutes = lastSuccessful
    ? (nowMs - Date.parse(lastSuccessful.updated_at || lastSuccessful.created_at)) / 60000
    : Infinity;
  const ongoing = mainRuns.find(run =>
    ['in_progress', 'queued', 'pending', 'waiting', 'requested'].includes(run.status) &&
    (nowMs - Date.parse(run.created_at)) / 60000 < ACTIVE_GRACE_MINUTES);
  const recentAttempt = mainRuns.find(run =>
    (nowMs - Date.parse(run.created_at)) / 60000 < RETRY_COOLDOWN_MINUTES);
  if (ageMinutes < MAX_AGE_MINUTES)
    return { action: 'fresh', ageMinutes };
  if (ongoing)
    return { action: 'running', ageMinutes, runId: ongoing.id };
  if (recentAttempt)
    return { action: 'cooldown', ageMinutes, runId: recentAttempt.id };
  return { action: 'dispatch', ageMinutes };
}

module.exports = { TARGETS, inspectRuns, MAX_AGE_MINUTES };
