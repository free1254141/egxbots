import { NextRequest } from 'next/server';
import { generateDailyReport, DailyReportVerificationError } from '../social/daily-reports';
import { POST } from '../../app/api/social/daily-reports/route';
import { executeStructuredTools } from '../ai/tools-v2';
import { generateV2Response } from '../ai/final-v2';
import { runAnswerGate } from '../ai/answer-gate';
import { getSupabaseServiceClient } from '../supabase/route-data';

jest.mock('../ai/tools-v2', () => ({ executeStructuredTools: jest.fn() }));
jest.mock('../ai/final-v2', () => ({ generateV2Response: jest.fn() }));
jest.mock('../ai/server-secrets', () => ({ getDeepSeekApiKey: () => 'fixture-key', getNvidiaApiKeys: () => [] }));
jest.mock('../ai/answer-gate', () => ({ runAnswerGate: jest.fn() }));
jest.mock('../ai/facts', () => ({ buildFactRecords: () => [] }));
jest.mock('../supabase/route-data', () => ({ getSupabaseClient: () => ({}), getSupabaseServiceClient: jest.fn() }));

const date = '2026-10-07';
const gate = { ok: false, reasons: ['Price attributed to the wrong stock'], checked: {
  coverage: true, metric: true, attribution: true, context: true, completion: true,
} };
const savedFetch = global.fetch;
const savedSecret = process.env.REVALIDATE_SECRET;
beforeEach(() => {
  jest.clearAllMocks();
  (executeStructuredTools as jest.Mock).mockResolvedValue({ results: [{ tool: 'get_stock', data_time: date,
    data: { price: 10 }, symbols: ['TEST'], availability: 'available' }] });
  (generateV2Response as jest.Mock).mockImplementation(async (...args: any[]) => {
    Object.assign(args[11], { source: 'llm', degraded: false });
    return 'Synthetic rejected report';
  });
  (runAnswerGate as jest.Mock).mockReturnValue(gate);
});
afterAll(() => {
  global.fetch = savedFetch;
  if (savedSecret === undefined) delete process.env.REVALIDATE_SECRET;
  else process.env.REVALIDATE_SECRET = savedSecret;
});

it('preserves rejection reasons without a second LLM attempt', async () => {
  const error = await generateDailyReport({}, 'stock', date, 'TEST', []).catch(e => e);
  expect(error).toBeInstanceOf(DailyReportVerificationError);
  expect(error.validation).toEqual(gate);
  expect(generateV2Response).toHaveBeenCalledTimes(1);
});

it('persists failed validation and never marks a rejected report ready', async () => {
  const updates: any[] = [];
  (getSupabaseServiceClient as jest.Mock).mockReturnValue({ from(table: string) {
    const query: any = {
      select: () => query, eq: () => query, lt: () => query, order: () => query, limit: () => query,
      maybeSingle: async () => ({ data: table === 'daily_job_runs' ? {
        job_type: 'daily_bot', status: 'completed', started_at: date + 'T14:00:00Z',
        steps: [{ step: 'sync_prices', status: 'success' }, { step: 'calculate_indicators', status: 'success' }],
      } : null, error: null }),
      insert: async () => ({ error: null }),
      update: (payload: any) => { updates.push(payload); return query; },
      then: (resolve: any) => resolve({ error: null }),
    };
    return query;
  } });
  process.env.REVALIDATE_SECRET = 'fixture-secret';
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [
    { symbol: 'TEST', date, last_close: 10, volume: 100000 },
  ] }) });
  const response = await POST(new NextRequest('https://egxbots.example/api/social/daily-reports', {
    method: 'POST', headers: { authorization: 'Bearer fixture-secret', 'content-type': 'application/json' },
    body: JSON.stringify({ date, kind: 'stock', job_run_id: '11111111-1111-1111-1111-111111111111' }),
  }));
  expect(response.status).toBe(503);
  expect(updates).toEqual([expect.objectContaining({ status: 'failed', validation: gate })]);
  expect(generateV2Response).toHaveBeenCalledTimes(1);
});

it.each(['ready', 'generating', 'failed'])('does not replay %s reports or spend another repair attempt', async status => {
  (getSupabaseServiceClient as jest.Mock).mockReturnValue({ from(table: string) {
    const q: any = { select: () => q, eq: () => q, maybeSingle: async () => ({data: table === 'daily_job_runs' ? {
      job_type:'daily_bot',status:'completed',started_at:date+'T14:00:00Z',
      steps:[{step:'sync_prices',status:'success'},{step:'calculate_indicators',status:'success'}],
    } : {status,job_run_id:'11111111-1111-1111-1111-111111111111',updated_at:date+'T19:00:00Z',validation:{recovery_attempt:1}},error:null}) };
    return q;
  }});
  process.env.REVALIDATE_SECRET='fixture-secret';
  const r=await POST(new NextRequest('https://egxbots.example/api/social/daily-reports', {
    method:'POST',headers:{authorization:'Bearer fixture-secret','content-type':'application/json'},
    body:JSON.stringify({date,kind:'stock',job_run_id:'11111111-1111-1111-1111-111111111111',retry_failed:true}),
  }));
  expect(await r.json()).toEqual({status,duplicate:true});
  expect(generateV2Response).not.toHaveBeenCalled();
});

it('claims one confirmed failed report with a version filter and preserves the previous failure', async () => {
  const updates:any[]=[]; const filters:any[]=[];
  const jobId='11111111-1111-1111-1111-111111111111';
  const version=date+'T19:00:00Z';
  (getSupabaseServiceClient as jest.Mock).mockReturnValue({from(table:string) {
    let fields='';
    const q:any={select:(s:string)=>{fields=s;return q;},eq:(...args:any[])=>{filters.push(args);return q;},
      lt:()=>q,order:()=>q,limit:()=>q,update:(p:any)=>{updates.push(p);return q;},
      maybeSingle:async()=>({data:table==='daily_job_runs'?{
        job_type:'daily_bot',status:'completed',started_at:date+'T14:00:00Z',
        steps:[{step:'sync_prices',status:'success'},{step:'calculate_indicators',status:'success'}],
      }:fields==='status'?{status:'generating'}:fields.startsWith('status,job_run_id')?{
        status:'failed',job_run_id:jobId,updated_at:version,error:'LLM report failed verification',validation:gate,
      }:null,error:null}),then:(resolve:any)=>resolve({error:null})};
    return q;
  }});
  process.env.REVALIDATE_SECRET='fixture-secret';
  global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>({results:[{symbol:'TEST',date,last_close:10,volume:100000}]})});
  const r=await POST(new NextRequest('https://egxbots.example/api/social/daily-reports',{
    method:'POST',headers:{authorization:'Bearer fixture-secret','content-type':'application/json'},
    body:JSON.stringify({date,kind:'stock',job_run_id:jobId,retry_failed:true}),
  }));
  expect(r.status).toBe(503); // The fixture still rejects; repair cannot bypass verification.
  expect(filters).toContainEqual(['status','failed']);
  expect(filters).toContainEqual(['updated_at',version]);
  expect(updates[0].validation.recovery_attempt).toBe(1);
  expect(updates[1].validation.previous_failure.validation).toEqual(gate);
  expect(updates[1].content).toBe('Synthetic rejected report');
  expect(generateV2Response).toHaveBeenCalledTimes(1);
});
