import { socialJobReadiness, effectiveDailySteps } from './job-readiness';

const original = [
  { step: 'sync_prices', status: 'failed', details: 'Synced 235/284 symbols' },
  { step: 'calculate_indicators', status: 'success' },
  { step: 'sync_prices', status: 'failed', details: 'Recovered 1/49 prices', recovery_attempt: 1 },
  { step: 'calculate_indicators', status: 'failed', details: 'Price sync incomplete; dependent recovery withheld', recovery_attempt: 1 },
];

test('attempts reports on usable partial inputs while retaining actual stage results', () => {
  const result = socialJobReadiness(JSON.stringify(original));
  expect(result.pricesUsable).toBe(true);
  expect(result.statuses.calculate_indicators).toBe('success');
  expect(result.statuses.sync_prices).toBe('failed');
  expect(effectiveDailySteps(original)).toHaveLength(2);
});

test('does not hide executed failures, malformed input or low coverage', () => {
  expect(socialJobReadiness('broken').pricesUsable).toBe(false);
  expect(socialJobReadiness([{step:'sync_prices',status:'failed',details:'Synced 100/284 symbols'}]).pricesUsable).toBe(false);
  expect(socialJobReadiness([...original, {step:'calculate_indicators',status:'failed',details:'Database failure',recovery_attempt:1}]).statuses.calculate_indicators).toBe('failed');
});
