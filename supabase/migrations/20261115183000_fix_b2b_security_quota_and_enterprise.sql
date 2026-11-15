-- Fix B2B Security, RLS Leaks, Cairo Quota Timezone, Enterprise Dual-Group Provisioning, and Trial Abuse Guard
-- Date: 2026-11-15

-- 1. Close public/anon RLS leak on b2b_group_licenses & restrict authenticated users to SELECT their own rows only
DROP POLICY IF EXISTS "Allow public read of active licenses by chat id" ON public.b2b_group_licenses;
DROP POLICY IF EXISTS "Allow owners to read and update their licenses" ON public.b2b_group_licenses;
DROP POLICY IF EXISTS "Allow owners to read their licenses" ON public.b2b_group_licenses;

CREATE POLICY "Allow owners to read their licenses"
ON public.b2b_group_licenses FOR SELECT
TO authenticated
USING (owner_user_id = auth.uid());

-- 2. Track Telegram group chat_ids that already claimed a B2B free trial (prevents multi-account trial farming)
CREATE TABLE IF NOT EXISTS public.b2b_trial_chat_history (
    telegram_chat_id BIGINT PRIMARY KEY,
    first_license_id UUID,
    first_owner_user_id UUID,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.b2b_trial_chat_history ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.b2b_trial_chat_history FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.b2b_trial_chat_history TO service_role;

CREATE POLICY "Allow service role full access on b2b_trial_chat_history"
ON public.b2b_trial_chat_history FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

INSERT INTO public.b2b_trial_chat_history (telegram_chat_id, first_license_id, first_owner_user_id)
SELECT DISTINCT ON (telegram_chat_id)
    telegram_chat_id,
    id,
    owner_user_id
FROM public.b2b_group_licenses
WHERE telegram_chat_id IS NOT NULL
  AND order_id LIKE 'B2B-TRIAL-%'
ORDER BY telegram_chat_id, created_at ASC
ON CONFLICT (telegram_chat_id) DO NOTHING;

-- 3. Fix Cairo midnight reset in check_and_consume_b2b_group_quota (was UTC CURRENT_DATE causing a 2-hour drift vs Python cache)
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
        'group_title', COALESCE(v_lic.group_title, '')
    );
END;
$$;

-- 4. Atomic idempotent B2B license activation (supports EasyKash & Direct Wallet + 2 separate group licenses for Enterprise)
CREATE OR REPLACE FUNCTION public.activate_b2b_group_license(
    p_user_id UUID,
    p_tier TEXT,
    p_duration_days INTEGER,
    p_payment_order_id UUID
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_now TIMESTAMPTZ := NOW();
    v_claimed_order_id UUID;
    v_limit INTEGER;
    v_needed_slots INTEGER;
    v_updated_count INTEGER := 0;
    v_lic RECORD;
    v_start TIMESTAMPTZ;
    v_end TIMESTAMPTZ;
    v_max_end TIMESTAMPTZ := NULL;
    v_slot INTEGER;
BEGIN
    IF p_tier NOT IN ('b2b_starter', 'b2b_pro', 'b2b_enterprise') THEN
        RAISE EXCEPTION 'Unsupported B2B tier: %', p_tier;
    END IF;
    IF p_duration_days IS NULL OR p_duration_days <= 0 THEN
        p_duration_days := 30;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 1));

    IF p_payment_order_id IS NOT NULL THEN
        INSERT INTO public.payment_entitlement_events (payment_order_id, user_id)
        VALUES (p_payment_order_id, p_user_id)
        ON CONFLICT (payment_order_id) DO NOTHING
        RETURNING payment_order_id INTO v_claimed_order_id;

        IF NOT FOUND THEN
            SELECT MAX(expires_at) INTO v_max_end
            FROM public.b2b_group_licenses
            WHERE owner_user_id = p_user_id;
            RETURN COALESCE(v_max_end, v_now);
        END IF;
    END IF;

    v_limit := CASE p_tier
        WHEN 'b2b_starter' THEN 50
        WHEN 'b2b_pro' THEN 120
        WHEN 'b2b_enterprise' THEN 250
        ELSE 50
    END;
    v_needed_slots := CASE WHEN p_tier = 'b2b_enterprise' THEN 2 ELSE 1 END;

    FOR v_lic IN
        SELECT *
        FROM public.b2b_group_licenses
        WHERE owner_user_id = p_user_id
        ORDER BY (telegram_chat_id IS NOT NULL) DESC, expires_at DESC
        LIMIT v_needed_slots
        FOR UPDATE
    LOOP
        v_start := GREATEST(COALESCE(v_lic.expires_at, v_now), v_now);
        v_end := v_start + make_interval(days => p_duration_days);
        UPDATE public.b2b_group_licenses
        SET status = 'active',
            tier = p_tier,
            daily_limit = v_limit,
            order_id = COALESCE(p_payment_order_id::text, order_id),
            expires_at = v_end,
            updated_at = v_now
        WHERE id = v_lic.id;
        v_updated_count := v_updated_count + 1;
        IF v_max_end IS NULL OR v_end > v_max_end THEN
            v_max_end := v_end;
        END IF;
    END LOOP;

    IF v_updated_count < v_needed_slots THEN
        FOR v_slot IN (v_updated_count + 1)..v_needed_slots LOOP
            v_end := v_now + make_interval(days => p_duration_days);
            INSERT INTO public.b2b_group_licenses (
                owner_user_id,
                order_id,
                tier,
                daily_limit,
                daily_used,
                custom_signature,
                group_title,
                status,
                starts_at,
                expires_at
            ) VALUES (
                p_user_id,
                COALESCE(p_payment_order_id::text, 'B2B-PAID'),
                p_tier,
                v_limit,
                0,
                '⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS',
                CASE WHEN v_needed_slots = 2 THEN 'مجموعة تليجرام ' || v_slot || ' (بانتظار التفعيل)' ELSE 'مجموعة تليجرام (بانتظار التفعيل)' END,
                'active',
                v_now,
                v_end
            );
            IF v_max_end IS NULL OR v_end > v_max_end THEN
                v_max_end := v_end;
            END IF;
        END LOOP;
    END IF;

    RETURN COALESCE(v_max_end, v_now);
END;
$$;

REVOKE ALL ON FUNCTION public.activate_b2b_group_license(uuid, text, integer, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.activate_b2b_group_license(uuid, text, integer, uuid) TO service_role;

REVOKE ALL ON FUNCTION public.check_and_consume_b2b_group_quota(bigint, bigint) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_and_consume_b2b_group_quota(bigint, bigint) TO service_role;
