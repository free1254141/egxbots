import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {PGlite}=await import(process.env.FOUNDERS_PGLITE_MODULE || '@electric-sql/pglite');
const db=new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role;
create table public.local_billing_settings(id integer primary key,pro_price_egp numeric,
 discount_enabled boolean,discount_ends_at timestamptz,discount_price_egp numeric,
 discount_label_ar text,discount_label_en text,updated_at timestamptz);
insert into public.local_billing_settings values(1,null,true,'2026-10-09',50,'old','old',now());
create table public.subscriptions(id uuid primary key default gen_random_uuid(),user_id uuid,
 plan_id text,status text,created_at timestamptz default now());
create table public.local_payment_orders(id uuid primary key default gen_random_uuid(),user_id text,plan_id text,amount_egp numeric,status text);
insert into public.subscriptions(user_id,plan_id,status)
 select ('00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid,'pro','active' from generate_series(1,13) i;`);
await db.exec(await fs.readFile(new URL('../../supabase/migrations/20261012144000_founders_offer_seat_limit.sql',import.meta.url),'utf8'));
const status=async()=> (await db.query('select public.founders_offer_status() as offer')).rows[0].offer;
assert.deepEqual(await status(),{enabled:true,limit:100,count:13,remaining:87,is_open:true,price_egp:50,regular_price_egp:200,ends_at:null});
await db.exec(`update public.local_billing_settings set discount_enabled=true,discount_ends_at='2000-01-01',pro_price_egp=200 where id=1;
update public.subscriptions set status='canceled' where user_id='00000000-0000-0000-0000-000000000001';
update public.subscriptions set status='active' where user_id='00000000-0000-0000-0000-000000000001';`);
assert.equal((await status()).count,13); assert.equal((await status()).price_egp,50);
await assert.rejects(()=>db.exec(`insert into local_payment_orders(user_id,plan_id,amount_egp) values('buyer','pro',200)`),/Monthly price changed/);
await db.exec(`insert into local_payment_orders(user_id,plan_id,amount_egp,status) values('old-quote','pro',50,'pending');
insert into subscriptions(user_id,plan_id,status) select ('00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid,'pro','active' from generate_series(14,99) i;`);
assert.equal((await status()).count,99);assert.equal((await status()).price_egp,50);
await db.exec(`insert into subscriptions(user_id,plan_id,status) values('00000000-0000-0000-0000-000000000100','pro','active');`);
assert.equal((await status()).count,100);assert.equal((await status()).price_egp,200);assert.equal((await status()).is_open,false);
await db.exec(`update subscriptions set status='canceled';
insert into subscriptions(user_id,plan_id,status) values('00000000-0000-0000-0000-000000000101','pro','active');
update local_payment_orders set status='approved' where user_id='old-quote';`);
assert.equal((await status()).count,100);assert.equal((await status()).price_egp,200);
await assert.rejects(()=>db.exec(`insert into local_payment_orders(user_id,plan_id,amount_egp) values('stale','pro',50)`),/Monthly price changed/);
await db.exec(`insert into local_payment_orders(user_id,plan_id,amount_egp) values('normal','pro',200),('other','pro_6m',1000);
set role anon;`);
assert.equal((await status()).count,100);
await assert.rejects(()=>db.query('select * from public.founders_offer_members'),/permission denied/);
await assert.rejects(()=>db.exec("insert into public.founders_offer_members(user_id) values('00000000-0000-0000-0000-000000000102')"),/permission denied/);
await assert.rejects(()=>db.query('select public.record_founders_subscription_activation()'),/permission denied/);
await db.close();console.log('Founders offer checks passed: 13/99/100 boundary, renewals, cancellations, stale quotes, previous quotes, other plans, and anonymous isolation.');
