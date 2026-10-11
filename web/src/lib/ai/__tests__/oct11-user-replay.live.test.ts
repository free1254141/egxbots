/** Four explicitly bounded real-provider turns; database access is read-only.
 * Opt in with RUN_CHAT_OCT11_REPLAY=1. No customer messages or positions are written. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createClient} from '@supabase/supabase-js';
import {runAgenticPipelineStream} from '../agentic-pipeline';
import {toAgenticEvidence,evidenceMemory} from '../agentic-publication';
jest.mock('server-only',()=>({}));
const live=process.env.RUN_CHAT_OCT11_REPLAY==='1'?test:test.skip;

live('replays quantity, average cost, quote verification and AJWA backtest with the actual model',async()=>{
    for (const file of [path.resolve(process.cwd(),'../.env'),path.resolve(process.cwd(),'.env.local')]) {
        if (!fs.existsSync(file)) continue;
        for (const line of fs.readFileSync(file,'utf8').split(/\r?\n/)) {
            const match = /^(SUPABASE_URL|NEXT_PUBLIC_SUPABASE_URL|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SERVICE_KEY|SUPABASE_KEY|DEEPSEEK_API_KEY|DEEPSEEK_OFFICIAL_API_KEY)\s*=\s*(.*)$/.exec(line);
            if (match && !process.env[match[1]]) process.env[match[1]]=match[2].trim().replace(/^["']|["']$/g,'');
        }
    }
    const url=process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL!;
    const key=process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY!;
    if(!url||!key)throw new Error('Missing server database credentials');
    const sb=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
    const readonly=(query:any):any=>new Proxy(query,{get(obj,method:string){
        if(['insert','update','delete','upsert','rpc'].includes(method))return()=>{throw new Error('Replay prohibits writes');};
        const value=obj[method];
        if(typeof value!=='function')return value;
        if(method==='then')return value.bind(obj);
        return(...args:any[])=>readonly(value.apply(obj,args));
    }});
    const db={from:(table:string)=>readonly(sb.from(table))};
    const native=global.fetch;let providerCalls=0;
    global.fetch=(async(input:any,init:any)=>{
        if(String(input).includes('api.deepseek.com')&&++providerCalls>24)throw new Error('Replay provider budget exhausted');
        return native(input,init);
    }) as any;
    const initial=toAgenticEvidence('manage_portfolio',{operation:'view'},{status:'success',positions:[{
        symbol:'GTWL',quantity:1934,entry_price:63.9,current_price:153.2,date:'2026-10-11',cost:123582.6,
    }]});
    let state:any={current_symbol:'GTWL',last_symbols:['GTWL'],summary:null};
    let summary:any={current_symbols:['GTWL'],last_tool_evidence:evidenceMemory([initial])};
    const history:any[]=[{role:'user',content:'سهم جولدن تكس'},
        {role:'assistant',content:'جولدن تكس GTWL: مركزك المحفوظ 1934 سهم بمتوسط شراء 63.90 جنيه. آخر سعر في الرد السابق 153.20 جنيه.'}];
    const prompts=['اسهمي ٢١١٤','متوسط السعر ٧٣.٨٢','تأكد من إغلاق جولدن تكس؛ أنا شايفه ١٤٦.٩٠',
        'اختبر الاتجاه وMACD على AJWA خلال آخر ٥٠٠ شمعة يومية واعرض نسبة الصفقات الرابحة والعائد التراكمي ورأس المال النهائي'];
    const report:any[]=[];
    try{
        for(const prompt of prompts){
            const start=Date.now(),events:any[]=[];
            for await(const event of runAgenticPipelineStream(prompt,[],state,summary,history,db,[],
                'offline-replay-user','offline-replay-session','offline-replay-message','deepseek-chat',{timeoutMs:65000}))events.push(event);
            const done=events.find(e=>e.type==='done')?.data;
            const tools=events.filter(e=>e.type==='tools_data').flatMap(e=>e.data.results||[]);
            report.push({prompt,latency_ms:Date.now()-start,response:done?.response,review:done?.publication_review,origin:done?.response_origin,usage:done?.usage,tools});
            if(!done)throw new Error('Missing final response');
            expect(done.response_origin).toBe('llm');
            expect(done.publication_review.final_passed).toBe(true);
            expect(done.response).not.toMatch(/تعذر إكمال إجابة|king_ai_score|accumulation_score|momentum_and_volume/);
            if(prompt===prompts[0]){
                const calc=tools.find(e=>e.tool==='calculate_position');
                expect(calc?.arguments).toMatchObject({symbol:'GTWL',quantity:2114,entry_price:63.9});
                expect(done.response).not.toContain('لم يظهر معها');
            }
            if(prompt===prompts[1])expect(tools.find(e=>e.tool==='calculate_position')?.arguments).toMatchObject({symbol:'GTWL',quantity:2114,entry_price:73.82});
            if(prompt===prompts[2])expect(tools.some(e=>e.tool==='get_live_quote'&&e.symbols.includes('GTWL'))).toBe(true);
            if(prompt===prompts[3])expect(tools.some(e=>e.tool==='compare_strategies_history'&&e.symbols.includes('AJWA'))).toBe(true);
            state=done.session_update;
            summary={...summary,current_symbols:state.last_symbols,last_tool_evidence:evidenceMemory([...summary.last_tool_evidence,...tools])};
            history.push({role:'user',content:prompt},{role:'assistant',content:done.response});
        }
    }finally{
        global.fetch=native;
        fs.writeFileSync(path.join(os.tmpdir(),'chat-oct11-replay-results.json'),JSON.stringify({providerCalls,turns:report},null,2));
        console.log('OCT11_REPLAY',JSON.stringify(report.map(r=>({prompt:r.prompt,latency_ms:r.latency_ms,origin:r.origin,review:r.review}))));
    }
},290000);
