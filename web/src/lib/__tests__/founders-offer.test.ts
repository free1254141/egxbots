jest.mock("@/lib/supabase/route-data", () => ({ getSupabaseServiceClient: jest.fn() }));
import { applyFoundersOffer, withFoundersOffer } from "../founders-offer";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
const config = {enabled:true, plans:[{id:"pro",amount_egp:200},{id:"pro_6m",amount_egp:1000}],founders:{count:0}};
const offer={enabled:true,limit:100,count:99,remaining:1,is_open:true,price_egp:50,regular_price_egp:200,ends_at:null};
it("uses seat count without a date and leaves other plans intact",()=>{
 const result=applyFoundersOffer(config,offer);
 expect(result.plans[0]).toMatchObject({amount_egp:50,discount:{active:true,ends_at:null,original_amount_egp:200}});
 expect(result.founders.count).toBe(99);expect(result.plans[1]).toEqual(config.plans[1]);
 expect(config.plans[0].amount_egp).toBe(200);
});
it("closes at 100 and removes the old timed discount",()=>{
 const result=applyFoundersOffer(config,{...offer,count:100,remaining:0,is_open:false,price_egp:200});
 expect(result.plans[0]).toMatchObject({amount_egp:200,discount:null});
 expect(result.founders.is_open).toBe(false);
});
it("preserves configured pricing when the offer is disabled",()=>expect(applyFoundersOffer(config,{...offer,enabled:false})).toBe(config));
it("refuses to invent pricing on a failed authoritative read",async()=>{
 (getSupabaseServiceClient as jest.Mock).mockReturnValue({rpc:jest.fn().mockResolvedValue({error:{message:"offline"}})});
 await expect(withFoundersOffer(config)).rejects.toThrow("Founders pricing unavailable");
});
