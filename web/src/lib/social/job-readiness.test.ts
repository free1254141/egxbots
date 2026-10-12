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

test('accepts full exchange recovered coverage after interrupted close run', () => {
  expect(socialJobReadiness([{step:'sync_prices',status:'failed',details:'Recovered 236/284 prices'}]).pricesUsable).toBe(true);
  expect(socialJobReadiness([{step:'sync_prices',status:'partial',coverage:{scope:'exchange',success:236,total:284}}]).pricesUsable).toBe(true);
  expect(socialJobReadiness([{step:'sync_prices',status:'partial',coverage:{scope:'exchange',success:300,total:284}}]).pricesUsable).toBe(false);
});

test('blocked recovery does not consume or fabricate an actual result', () => {
  const blocked = {step:'calculate_indicators',status:'failed',details:'Indicators incomplete; dependent recovery withheld',recovery_attempt:1};
  expect(effectiveDailySteps([blocked])[0].status).toBe('blocked');
  expect(effectiveDailySteps([{step:'calculate_indicators',status:'started',recovery_attempt:1}, blocked])[0].status).toBe('blocked');
  expect(effectiveDailySteps([{step:'calculate_indicators',status:'success'}, blocked])[0].status).toBe('success');
});

test('subset recovery cannot masquerade as full coverage, structured exchange coverage can replace it', () => {
  const full = {step:'sync_prices',status:'failed',details:'Synced 100/284 symbols'};
  const subset = {step:'sync_prices',status:'success',details:'Recovered 1/1 prices',recovery_attempt:1};
  expect(socialJobReadiness([full, subset]).pricesUsable).toBe(false);
  expect(socialJobReadiness([full, {...subset,status:'partial',coverage:{scope:'exchange',success:236,total:284}}]).pricesUsable).toBe(true);
});
