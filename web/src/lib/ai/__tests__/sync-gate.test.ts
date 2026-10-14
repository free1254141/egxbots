import { isDailySyncComplete, shouldPreferLiveBeforeSync } from '../sync-gate';

function db(job: any, date = '2026-09-16') {
    return { from(table: string) {
        const q: any = new Proxy({}, { get: (_, key: string) => key === 'then'
            ? (yes: any, no: any) => Promise.resolve({ data: table === 'daily_job_runs' ? [job] : [{ date }], error: null }).then(yes, no)
            : () => q });
        return q;
    } };
}
const completed = { status: 'completed', completed_at: '2026-09-16T17:45:00Z',
    steps: [{ name: 'sync_prices', status: 'started' }, { name: 'sync_prices', status: 'success' }] };
test('live preference continues beyond 18:00 until the close job proves completion', () => {
    expect(shouldPreferLiveBeforeSync(new Date('2026-09-16T08:30:00+03:00'))).toBe(false);
    expect(shouldPreferLiveBeforeSync(new Date('2026-09-16T11:00:00+03:00'))).toBe(true);
    expect(shouldPreferLiveBeforeSync(new Date('2026-09-16T15:30:00+03:00'))).toBe(true);
    expect(shouldPreferLiveBeforeSync(new Date('2026-09-16T18:01:00+03:00'))).toBe(true);
    expect(shouldPreferLiveBeforeSync(new Date('2026-09-18T12:00:00+03:00'))).toBe(false);
});
test('completed close sync and the current stock date are both required', async () => {
    expect(await isDailySyncComplete(db(completed), '2026-09-16')).toBe(true);
    expect(await isDailySyncComplete(db(completed, '2026-09-15'), '2026-09-16')).toBe(false);
});
test.each([[[]], [[{ name: 'sync_prices', status: 'success' }]], [[{ name: 'sync_prices', status: 'started' }, { name: 'sync_prices', status: 'failed' }]]])('an incomplete price ledger cannot certify a final close: %j', async steps => {
    expect(await isDailySyncComplete(db({ ...completed, steps }), '2026-09-16')).toBe(false);
});
test('a newer price cannot validate the previous day’s completed run', async () => {
    expect(await isDailySyncComplete(db({ ...completed, completed_at: '2026-09-15T17:45:00Z' }), '2026-09-16')).toBe(false);
});
test('the previous day’s matching price and run do not certify today', async () => {
    expect(await isDailySyncComplete(db({ ...completed, completed_at: '2026-09-15T17:45:00Z' }, '2026-09-15'), '2026-09-16')).toBe(false);
});
