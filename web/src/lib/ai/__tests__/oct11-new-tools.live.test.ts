/** Opt-in real-provider verification, seven turns with isolated read-only sessions. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createClient} from '@supabase/supabase-js';
import {runAgenticPipelineStream} from '../agentic-pipeline';
import {evidenceMemory} from '../agentic-publication';
jest.mock('server-only',()=>({}));
const live=process.env.RUN_CHAT_NEW_TOOLS==='1'?test:test.skip;

const cases=[
    {session:'fundamentals',question:'هات البيانات الأساسية المخزنة لسهم COMI: مضاعف الربحية وربحية السهم والقيمة السوقية. وضح تاريخها، وهل عندك مضاعف الدفترية ونمو الإيرادات؟',tools:['get_fundamentals']},
    {session:'fundamentals',question:'طيب قارن نفس البيانات مع TMGH وSWDY في جدول، وقولي هل الأقل في مضاعف الربحية معناها إنه الأرخص للاستثمار النهارده؟',tools:['get_fundamentals']},
    {session:'peers',question:'هات 3 نظراء للبنك التجاري الدولي COMI من نفس الصناعة، غير السهم الأصلي، وقارن مضاعف الربحية وربحية السهم والقيمة السوقية وتاريخ كل لقطة.',tools:['get_sector_peers'],symbol:'COMI',peers:3},
    {session:'peers',question:'طيب نفس الفكرة للسويدي SWDY، بس عايز نظيرين فقط غيره. لو الموجود أقل قول العدد الحقيقي، ووضح هل التصنيف صناعة ولا قطاع عام.',tools:['get_sector_peers'],symbol:'SWDY',peers:2},
    {session:'breadth',question:'هات اتساع أحدث جلسة مخزنة: عدد الأسهم الصاعدة والهابطة والثابتة والإجمالي ونسبة الصاعدة ونسبة الصاعد للهابط، في جدول مع تاريخ البيانات وتغطية العينة.',tools:['get_market_breadth']},
    {session:'breadth',question:'عيد قراءة اتساع أحدث جلسة وقولي مين الغالب، الصاعد ولا الهابط؟ وهل أقدر أعتبر النتيجة خاصة بأسهم EGX30 أو دليل على صافي شراء المؤسسات؟ وضح حدود الاستنتاج.',tools:['get_market_breadth']},
    {session:'combined',question:'هات أساسيات COMI المخزنة وقارنه بنظيرين من نفس الصناعة، وبشكل منفصل اعرض اتساع السوق الأخير في جدول. وضح تاريخ الأساسيات وتاريخ الجلسة، وماتنسبش نسبة الأسهم الصاعدة للبنك نفسه.',tools:['get_fundamentals','get_sector_peers','get_market_breadth']},
    {session:'quote',question:'هات السعر الحالي للبنك التجاري الدولي COMI من المصدر مباشرة، ووضح وقت الجلب وهل فيه تأخير؛ ماتعتبرش آخر إغلاق مخزن سعراً لحظياً.',tools:['get_live_quote']},
];

live('tests fundamentals, peers and breadth twice each plus a combined request',async()=>{
    for(const file of [path.resolve(process.cwd(),'../.env'),path.resolve(process.cwd(),'.env.local')]){
        if(!fs.existsSync(file))continue;
        for(const line of fs.readFileSync(file,'utf8').split(/\r?\n/)){
            const match=/^(SUPABASE_URL|NEXT_PUBLIC_SUPABASE_URL|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SERVICE_KEY|SUPABASE_KEY|DEEPSEEK_API_KEY|DEEPSEEK_OFFICIAL_API_KEY)\s*=\s*(.*)$/.exec(line);
            if(match&&!process.env[match[1]])process.env[match[1]]=match[2].trim().replace(/^["']|["']$/g,'');
        }
    }
    const url=process.env.SUPABASE_URL||process.env.NEXT_PUBLIC_SUPABASE_URL!;
    const key=process.env.SUPABASE_SERVICE_ROLE_KEY||process.env.SUPABASE_SERVICE_KEY||process.env.SUPABASE_KEY!;
    if(!url||!key)throw new Error('Missing read-only server credentials');
    const sb=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
    const readonly=(query:any):any=>new Proxy(query,{get(obj,method:string){
        if(['insert','update','delete','upsert','rpc'].includes(method))return()=>{throw new Error('Audit prohibits writes');};
        const value=obj[method];if(typeof value!=='function')return value;
        if(method==='then')return value.bind(obj);
        return(...args:any[])=>readonly(value.apply(obj,args));
    }});
    const db={from:(table:string)=>readonly(sb.from(table))};
    const native=global.fetch;let providerCalls=0;
    global.fetch=(async(input:any,init:any)=>{
        if(String(input).includes('api.deepseek.com')&&++providerCalls>56)throw new Error('Audit provider-call budget exhausted');
        return native(input,init);
    }) as any;
    const outputPath=path.join(os.tmpdir(),'chat-new-tools-oct11-results.json');
    const previous=fs.existsSync(outputPath)?JSON.parse(fs.readFileSync(outputPath,'utf8')).turns:[];
    const selected=process.env.CHAT_NEW_TOOL_CASES?.split(',').map(Number);
    const sessions=new Map<string,any>();const report:any[]=[];
    try{
        for(const item of cases){
            if(!sessions.has(item.session))sessions.set(item.session,{state:{current_symbol:null,last_symbols:[],summary:null},summary:null,history:[]});
            const session=sessions.get(item.session);
            if(selected&&!selected.includes(cases.indexOf(item)+1)){
                const saved=previous.find((r:any)=>r.question===item.question);
                if(saved){
                    session.history.push({role:'user',content:item.question},{role:'assistant',content:saved.response});
                    const evidence=saved.tools||[];
                    const symbols=[...new Set(evidence.flatMap((e:any)=>e.symbols||[]))];
                    session.state={current_symbol:symbols[0]||null,last_symbols:symbols,summary:null};
                    session.summary={current_symbols:symbols,last_tool_evidence:evidenceMemory([...(session.summary?.last_tool_evidence||[]),...evidence])};
                    report.push({...saved,reused_previous_result:true});
                }
                continue;
            }
            const start=Date.now(),events:any[]=[],checks:string[]=[],draftChecks:any[]=[];
            let error:string|null=null;
            try{
                for await(const event of runAgenticPipelineStream(item.question,[],session.state,session.summary,session.history,db,[],
                    'offline-audit-user','offline-audit-'+item.session,'offline-audit-message','deepseek-chat',{timeoutMs:65000,
                        diagnosticCapture:(type:string,data:any)=>{if(type==='deterministic_review')draftChecks.push(data);}}))events.push(event);
            }catch(e){error=e instanceof Error?e.message:String(e);}
            const done=events.find(e=>e.type==='done')?.data;
            const tools=events.filter(e=>e.type==='tools_data').flatMap(e=>e.data.results||[]);
            const unique=[...new Set(tools.map(e=>e.tool))];
            if(!done)checks.push('missing_final_response');
            if(done?.response_origin!=='llm')checks.push('not_llm_answer');
            if(!done?.publication_review?.final_passed)checks.push('evidence_review_failed');
            for(const expected of item.tools)if(!unique.includes(expected))checks.push('missing_tool:'+expected);
            if(item.symbol){
                const peer=[...tools].reverse().find(e=>e.tool==='get_sector_peers');
                if(peer?.arguments?.symbol!==item.symbol)checks.push('peer_target_mismatch');
                if(peer?.arguments?.max_results!==item.peers)checks.push('peer_request_count_mismatch');
            }
            report.push({question:item.question,session:item.session,latency_ms:Date.now()-start,response:done?.response||null,
                origin:done?.response_origin,review:done?.publication_review,usage:done?.usage,tools,checks,error,draftChecks});
            if(done){
                session.state=done.session_update;
                session.summary={current_symbols:session.state.last_symbols,last_tool_evidence:evidenceMemory([...(session.summary?.last_tool_evidence||[]),...tools])};
                session.history.push({role:'user',content:item.question},{role:'assistant',content:done.response});
            }
            fs.writeFileSync(path.join(os.tmpdir(),'chat-new-tools-oct11-results.json'),JSON.stringify({providerCalls,turns:report},null,2));
            console.log('NEW_TOOL_TURN',JSON.stringify({index:report.length,latency_ms:Date.now()-start,tools:unique,checks,error}));
        }
    }finally{global.fetch=native;}
    expect(report.filter(r=>r.error||r.checks.length).map(r=>({question:r.question,checks:r.checks,error:r.error}))).toEqual([]);
},480000);
