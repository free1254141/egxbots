-- Migration: B2B per-group recommendations toggle + Telegram-only portfolio storage (zero web login required)
-- Date: 2026-11-15

-- 1. Add per-group allow_recommendations flag (defaults to false so B2B client groups do not leak EGX BOTS open VIP signals unless enabled)
ALTER TABLE public.b2b_group_licenses
  ADD COLUMN IF NOT EXISTS allow_recommendations BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Include allow_recommendations in check_and_consume_b2b_group_quota RPC output (single round-trip)
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
    v_today DATE := (NOW() AT TIME ZONE 'Africa/Cairo')::DATE;
    v_cooldown_seconds INTEGER := 90;
    v_member_limit INTEGER := 15;
    v_seconds_since_last NUMERIC;
BEGIN
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

    IF v_lic.last_used_date IS NULL OR v_lic.last_used_date < v_today THEN
        v_lic.daily_used := 0;
        v_lic.last_used_date := v_today;
    END IF;

    IF v_lic.daily_used >= v_lic.daily_limit THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'group_daily_limit_reached',
            'daily_limit', v_lic.daily_limit,
            'daily_used', v_lic.daily_used,
            'tier', v_lic.tier
        );
    END IF;

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

        UPDATE public.b2b_group_member_usage
        SET queries_count = queries_count + 1,
            last_query_at = NOW()
        WHERE telegram_chat_id = p_chat_id
          AND telegram_user_id = p_user_id
          AND usage_date = v_today;
    ELSE
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
        'group_title', COALESCE(v_lic.group_title, ''),
        'allow_recommendations', COALESCE(v_lic.allow_recommendations, FALSE)
    );
END;
$$;

-- 3. Add isolated Telegram-only portfolio storage for private bot users who haven't registered on egxbots.com
ALTER TABLE public.telegram_vip_chat_state
  ADD COLUMN IF NOT EXISTS portfolio_state JSONB NOT NULL DEFAULT '{"cash_balance": 0, "positions": []}'::jsonb;
