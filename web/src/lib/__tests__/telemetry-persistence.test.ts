import { NextRequest } from "next/server";
const mockInsert = jest.fn();
jest.mock("@supabase/supabase-js", () => ({createClient:()=>({from:()=>({insert:mockInsert})})}));
jest.mock("../supabase/route-data", () => ({getSupabaseServiceClient:()=>({from:()=>({insert:mockInsert})})}));
jest.mock("../supabase/server", () => ({createSupabaseServerClient:async()=>({auth:{getUser:async()=>({data:{user:{id:"test-user"}},error:null})}})}));
jest.mock("../admin-auth", () => ({requireAdmin:jest.fn()}));
import { POST as activity } from "../../app/api/analytics/events/route";
import { POST as audit } from "../../app/api/admin-access-log/route";
beforeEach(()=>mockInsert.mockReset());
const cases = [
    {name:"activity",handler:activity,body:{event_name:"page_view",path:"/chat"},failure:202},
    {name:"audit",handler:audit,body:{eventType:"page_view"},failure:503},
];
test.each(cases)("$name acknowledges only after persistence completes",async ({handler,body})=>{
    let finish!: (result:any)=>void;
    mockInsert.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    let acknowledged=false;
    const response=handler(new NextRequest("https://egxbots.example/api/events",{method:"POST",body:JSON.stringify(body)})).then(r=>{acknowledged=true;return r;});
    await new Promise(resolve=>setImmediate(resolve));
    expect(mockInsert).toHaveBeenCalledTimes(1);
    expect(acknowledged).toBe(false);
    finish({error:null});
    expect((await response).status).toBe(200);
});
test.each(cases)("$name does not report success when database rejects write",async ({handler,body,failure})=>{
    mockInsert.mockResolvedValue({error:{code:"TEST",message:"write failed"}});
    const response=await handler(new NextRequest("https://egxbots.example/api/events",{method:"POST",body:JSON.stringify(body)}));
    expect(response.status).toBe(failure);
    expect((await response.json()).ok).toBe(false);
});
