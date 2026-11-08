-- Migration: Create B2B Telegram Group Bot Licensing Tables & Atomic Quota Handler
-- Date: 2026-11-08

CREATE TABLE IF NOT EXISTS public.b2b_group_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    order_id TEXT,
    telegram_chat_id BIGINT UNIQUE,
    group_title TEXT,
    tier TEXT NOT NULL DEFAULT 'b2b_starter', -- 'b2b_starter', 'b2b_pro', 'b2b_enterprise'
    daily_limit INTEGER NOT NULL DEFAULT 50,  -- 50, 120, 250
    daily_used INTEGER NOT NULL DEFAULT 0,
    last_used_date DATE DEFAULT CURRENT_DATE,
    custom_signature TEXT DEFAULT '⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS',
    status TEXT NOT NULL DEFAULT 'active',    -- 'active', 'expired', 'paused'
    starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_b2b_licenses_chat_id ON public.b2b_group_licenses (telegram_chat_id);
CREATE INDEX IF NOT EXISTS idx_b2b_licenses_owner ON public.b2b_group_licenses (owner_user_id);
CREATE INDEX IF NOT EXISTS idx_b2b_licenses_status ON public.b2b_group_licenses (status, expires_at);

-- Per-member usage inside each licensed group (anti-spam & individual fair use)
CREATE TABLE IF NOT EXISTS public.b2b_group_member_usage (
    telegram_chat_id BIGINT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    queries_count INTEGER NOT NULL DEFAULT 1,
    last_query_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (telegram_chat_id, telegram_user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_b2b_member_usage_lookup 
ON public.b2b_group_member_usage (telegram_chat_id, telegram_user_id, usage_date);

-- Atomic Check & Consume RPC for Telegram Group Queries
CREATE OR REPLACE FUNCTION public.check_and_consume_b2b_group_quota(
    p_chat_id BIGINT,
    p_user_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_lic RECORD;
    v_member RECORD;
    v_today DATE := CURRENT_DATE;
    v_cooldown_seconds INTEGER := 90;
    v_member_limit INTEGER := 15;
    v_seconds_since_last NUMERIC;
BEGIN
    -- 1. Find active license for this Telegram group
    SELECT * INTO v_lic
    FROM public.b2b_group_licenses
    WHERE telegram_chat_id = p_chat_id
      AND status = 'active'
      AND expires_at > NOW()
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'not_licensed',
            'chat_id', p_chat_id
        );
    END IF;

    -- 2. Reset daily counter if a new day has arrived (Cairo date / UTC)
    IF v_lic.last_used_date IS NULL OR v_lic.last_used_date < v_today THEN
        v_lic.daily_used := 0;
        v_lic.last_used_date := v_today;
    END IF;

    -- 3. Check group daily limit
    IF v_lic.daily_used >= v_lic.daily_limit THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'group_daily_limit_reached',
            'daily_limit', v_lic.daily_limit,
            'daily_used', v_lic.daily_used,
            'tier', v_lic.tier
        );
    END IF;

    -- 4. Check member anti-spam cooldown and daily limit
    SELECT * INTO v_member
    FROM public.b2b_group_member_usage
    WHERE telegram_chat_id = p_chat_id
      AND telegram_user_id = p_user_id
      AND usage_date = v_today;

    IF FOUND THEN
        v_seconds_since_last := EXTRACT(EPOCH FROM (NOW() - v_member.last_query_at));
        IF v_seconds_since_last < v_cooldown_seconds THEN
            RETURN jsonb_build_object(
                'allowed', false,
                'reason', 'member_cooldown',
                'cooldown_remaining', GREATEST(1, ROUND(v_cooldown_seconds - v_seconds_since_last)),
                'daily_used', v_lic.daily_used,
                'daily_limit', v_lic.daily_limit
            );
        END IF;

        IF v_member.queries_count >= v_member_limit THEN
            RETURN jsonb_build_object(
                'allowed', false,
                'reason', 'member_daily_limit_reached',
                'member_limit', v_member_limit,
                'daily_used', v_lic.daily_used,
                'daily_limit', v_lic.daily_limit
            );
        END IF;

        -- Update member record
        UPDATE public.b2b_group_member_usage
        SET queries_count = queries_count + 1,
            last_query_at = NOW()
        WHERE telegram_chat_id = p_chat_id
          AND telegram_user_id = p_user_id
          AND usage_date = v_today;
    ELSE
        -- Insert new member record for today
        INSERT INTO public.b2b_group_member_usage (
            telegram_chat_id,
            telegram_user_id,
            usage_date,
            queries_count,
            last_query_at
        ) VALUES (
            p_chat_id,
            p_user_id,
            v_today,
            1,
            NOW()
        );
    END IF;

    -- 5. Increment group daily counter
    v_lic.daily_used := v_lic.daily_used + 1;
    UPDATE public.b2b_group_licenses
    SET daily_used = v_lic.daily_used,
        last_used_date = v_today,
        updated_at = NOW()
    WHERE id = v_lic.id;

    RETURN jsonb_build_object(
        'allowed', true,
        'tier', v_lic.tier,
        'daily_used', v_lic.daily_used,
        'daily_limit', v_lic.daily_limit,
        'custom_signature', COALESCE(v_lic.custom_signature, ''),
        'group_title', COALESCE(v_lic.group_title, '')
    );
END;
$$;

-- RLS
ALTER TABLE public.b2b_group_licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.b2b_group_member_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read of active licenses by chat id"
ON public.b2b_group_licenses FOR SELECT
TO anon, authenticated
USING (status = 'active');

CREATE POLICY "Allow owners to read and update their licenses"
ON public.b2b_group_licenses FOR ALL
TO authenticated
USING (owner_user_id = auth.uid())
WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY "Allow service role full access on b2b_licenses"
ON public.b2b_group_licenses FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Allow service role full access on b2b_member_usage"
ON public.b2b_group_member_usage FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
