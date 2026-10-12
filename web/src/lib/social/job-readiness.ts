type Step = { step?: string; status?: string; details?: string; recovery_attempt?: number;
  execution_started?: boolean; coverage?: { scope?: string; success?: number; total?: number } };

// Mirrors api.daily_job_outcome.effective_daily_steps. A withheld recovery did
// not execute the stage and must not erase an earlier actual result.
export function effectiveDailySteps(raw: unknown): Step[] {
  let steps: unknown;
  try { steps = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return []; }
  if (!Array.isArray(steps)) return [];
  const latest = new Map<string, Step>();
  for (const value of steps) {
    if (!value || typeof value !== 'object' || typeof value.step !== 'string') continue;
    const step = value as Step;
    const previous = latest.get(value.step);
    if (step.recovery_attempt) {
      if (step.status === 'started' && previous) continue;
      if (step.status === 'blocked' || [
        'Price sync incomplete; dependent recovery withheld',
        'Indicators incomplete; dependent recovery withheld',
      ].includes(step.details || '')) {
        if (previous && !(previous.status === 'started' && previous.recovery_attempt)) continue;
        latest.set(value.step, { ...step, status: 'blocked', execution_started: false });
        continue;
      }
      if (step.step === 'sync_prices' && !step.coverage
          && step.details?.startsWith('Recovered ') && previous?.details?.startsWith('Synced ')) continue;
    }
    latest.set(value.step, step);
  }
  return [...latest.values()];
}

export function socialJobReadiness(raw: unknown) {
  const steps = effectiveDailySteps(raw);
  const statuses = Object.fromEntries(steps.map(s => [s.step, s.status]));
  const sync = steps.find(s => s.step === 'sync_prices');
  const match = /(?:Synced|Recovered)\s+(\d+)\s*\/\s*(\d+)/.exec(sync?.details || '');
  const coverage = sync?.coverage?.scope === 'exchange'
    ? [sync.coverage.success, sync.coverage.total]
    : match ? [Number(match[1]), Number(match[2])] : undefined;
  const configured = Number(process.env.PRICE_SYNC_MIN_COVERAGE || '0.8');
  const threshold = Number.isNaN(configured) ? 0.8 : configured;
  const pricesUsable = sync?.status === 'success' || Boolean(coverage
    && ['failed', 'partial'].includes(sync?.status || '')
    && Number.isFinite(threshold) && threshold > 0 && threshold <= 1
    && coverage.every(n => typeof n === 'number' && Number.isInteger(n))
    && Number(coverage[1]) > 0 && Number(coverage[0]) >= 0 && Number(coverage[0]) <= Number(coverage[1])
    && Number(coverage[0]) / Number(coverage[1]) >= threshold);
  // This is permission to attempt a report, not proof all prices are fresh.
  // generateDailyReport separately verifies the selected evidence/session.
  return { statuses, pricesUsable };
}
