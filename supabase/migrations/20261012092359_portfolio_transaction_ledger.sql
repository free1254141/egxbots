-- Manual portfolio bookkeeping only. All writes run atomically as the caller under RLS.
create unique index if not exists position_events_portfolio_request_idx
on public.position_events (user_id, (payload->>'request_id'))
where payload ? 'request_id' and event_type in ('portfolio_buy','portfolio_sell','portfolio_cash_add','portfolio_cash_withdraw');

create or replace function public.record_portfolio_transaction(
  p_action text, p_symbol text, p_quantity numeric, p_price numeric,
  p_amount numeric, p_fees numeric, p_occurred_at timestamptz, p_request_id uuid
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  owner_id uuid := auth.uid(); cash numeric; held public.positions%rowtype;
  stock_name text; stock_count int; max_stocks int := 5; new_quantity numeric;
  cost numeric; proceeds numeric; event_kind text; details jsonb; previous jsonb;
  position_id uuid; resulting_cash numeric;
begin
  if owner_id is null then raise exception 'unauthorized'; end if;
  if p_action is null or p_action not in ('buy','sell','deposit','withdraw') then raise exception 'invalid_action'; end if;
  if p_request_id is null or p_occurred_at is null or p_occurred_at > now() then raise exception 'invalid_date_or_request'; end if;
  if p_fees is null or p_fees < 0 or p_fees::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid_fees'; end if;
  details := jsonb_build_object('request_id',p_request_id,'action',p_action,'symbol',upper(trim(p_symbol)),
    'quantity',p_quantity,'price',p_price,'amount',p_amount,'fees',p_fees,'occurred_at',p_occurred_at);
  -- One per-owner lock prevents concurrent ledger operations from overwriting cash.
  select coalesce(cash_balance,0) into cash from public.profiles where id=owner_id for update;
  if not found then raise exception 'profile_unavailable'; end if;
  select payload into previous from public.position_events where user_id=owner_id
    and payload->>'request_id'=p_request_id::text limit 1;
  if found then
    if previous->'request' is distinct from details then raise exception 'request_conflict'; end if;
    return jsonb_build_object('ok',true,'duplicate',true);
  end if;
  if cash < 0 or cash::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid_cash_balance'; end if;
  -- Dates describe recorded transactions; they must not reorder a previously recorded ledger.
  if exists(select 1 from public.position_events where user_id=owner_id and payload ? 'request_id' and event_at > p_occurred_at) then
    raise exception 'date_before_last_transaction';
  end if;
  if p_action in ('buy','sell') then
    if p_symbol is null or p_quantity is null or p_price is null or p_quantity <= 0 or p_price <= 0
      or p_quantity::text in ('NaN','Infinity','-Infinity') or p_price::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid_trade'; end if;
    select name into stock_name from public.stocks where symbol=upper(trim(p_symbol)) and exchange='EGX' limit 1;
    if not found then raise exception 'unknown_symbol'; end if;
    if (select count(*) from public.positions where user_id=owner_id and symbol=upper(trim(p_symbol)) and status='open' and quantity>0)>1 then raise exception 'duplicate_holdings'; end if;
    select * into held from public.positions where user_id=owner_id and symbol=upper(trim(p_symbol)) and status='open'
      order by quantity desc nulls last limit 1 for update;
    position_id := held.id;
    if p_action='buy' then
      cost := p_quantity*p_price+p_fees;
      if cash < cost then raise exception 'insufficient_cash'; end if;
      if held.id is null or coalesce(held.quantity,0)<=0 then
        if exists(select 1 from public.subscriptions where user_id=owner_id and lower(plan_id) in ('pro','lifetime','pro_lifetime') and lower(status) in ('active','trialing')
          and (current_period_end is null or current_period_end>now())) then max_stocks:=10; end if;
        select count(distinct symbol) into stock_count from public.positions where user_id=owner_id and status='open' and quantity>0;
        if stock_count>=max_stocks then raise exception 'holding_limit'; end if;
      end if;
      new_quantity:=coalesce(held.quantity,0)+p_quantity;
      if held.id is null then
        insert into public.positions(user_id,symbol,name,source,status,quantity,entry_price,entry_at)
          values(owner_id,upper(trim(p_symbol)),stock_name,'chatbot','open',p_quantity,cost/p_quantity,p_occurred_at)
          returning id into position_id;
      else
        update public.positions set quantity=new_quantity, source='chatbot',
          entry_price=case when coalesce(held.quantity,0)=0 then cost/p_quantity when held.entry_price>0 then (held.quantity*held.entry_price+cost)/new_quantity else null end,
          updated_at=now() where id=held.id and user_id=owner_id;
      end if;
      resulting_cash:=cash-cost; event_kind:='portfolio_buy';
      details:=details||jsonb_build_object('entry_price',p_price,'total_cost',cost);
    else
      if held.id is null or held.quantity is null or p_quantity>held.quantity then raise exception 'quantity_exceeds_holding'; end if;
      proceeds:=p_quantity*p_price-p_fees;
      if proceeds<0 then raise exception 'fees_exceed_proceeds'; end if;
      if p_quantity=held.quantity then
        update public.positions set status='closed',quantity=0,status_at=p_occurred_at,status_price=p_price,updated_at=now() where id=held.id and user_id=owner_id;
      else
        update public.positions set quantity=held.quantity-p_quantity,updated_at=now() where id=held.id and user_id=owner_id;
      end if;
      resulting_cash:=cash+proceeds; event_kind:='portfolio_sell';
      details:=details||jsonb_build_object('sell_price',p_price,'entry_price',held.entry_price,'proceeds',proceeds);
    end if;
  else
    if p_amount is null or p_amount<=0 or p_amount::text in ('NaN','Infinity','-Infinity') or p_fees<>0 then raise exception 'invalid_cash_amount'; end if;
    if p_action='withdraw' and p_amount>cash then raise exception 'insufficient_cash'; end if;
    resulting_cash:=cash+case when p_action='deposit' then p_amount else -p_amount end;
    event_kind:=case when p_action='deposit' then 'portfolio_cash_add' else 'portfolio_cash_withdraw' end;
  end if;
  update public.profiles set cash_balance=resulting_cash where id=owner_id;
  insert into public.position_events(user_id,position_id,event_type,event_at,payload)
    values(owner_id,position_id,event_kind,p_occurred_at,details||jsonb_build_object('request',jsonb_build_object('request_id',p_request_id,'action',p_action,'symbol',upper(trim(p_symbol)),'quantity',p_quantity,'price',p_price,'amount',p_amount,'fees',p_fees,'occurred_at',p_occurred_at),'previous_cash',cash,'updated_cash',resulting_cash));
  return jsonb_build_object('ok',true);
end;
$$;
revoke all on function public.record_portfolio_transaction(text,text,numeric,numeric,numeric,numeric,timestamptz,uuid) from public,anon;
grant execute on function public.record_portfolio_transaction(text,text,numeric,numeric,numeric,numeric,timestamptz,uuid) to authenticated;
