-- Guard consume_ai_chat_quota against p_limit <= 0 so the INSERT branch never
-- leaks 1 free message per day when callers compute monthly today_cap = max(0, quota - prior_used).

create or replace function public.consume_ai_chat_quota(p_user_id uuid, p_date date, p_limit integer)
returns table(allowed boolean, chat_count integer)
language plpgsql
security definer
set search_path to 'public'
as $$
begin
    if coalesce(p_limit, 0) <= 0 then
        return query select false, 0;
        return;
    end if;

    insert into public.ai_chatbot_limits(user_id, date, chat_count)
    values (p_user_id, p_date, 1)
    on conflict (user_id, date) do update
        set chat_count = public.ai_chatbot_limits.chat_count + 1
        where public.ai_chatbot_limits.chat_count < p_limit
    returning true, public.ai_chatbot_limits.chat_count into allowed, chat_count;

    if not found then
        select false, l.chat_count into allowed, chat_count
        from public.ai_chatbot_limits l where l.user_id = p_user_id and l.date = p_date;
    end if;
    return next;
end;
$$;
