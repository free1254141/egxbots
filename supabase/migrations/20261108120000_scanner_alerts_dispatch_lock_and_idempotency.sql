-- Migration: 20261108120000_scanner_alerts_dispatch_lock_and_idempotency.sql
-- Description: Unbreakable database-level lock and idempotency ledger to prevent duplicate Telegram alerts

CREATE TABLE IF NOT EXISTS public.scanner_dispatch_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id TEXT NOT NULL,
    dispatch_date DATE NOT NULL,
    batch_hash TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'intraday_scan',
    symbols TEXT[] NOT NULL DEFAULT '{}',
    message_id BIGINT,
    worker_node TEXT DEFAULT 'huggingface',
    status TEXT NOT NULL DEFAULT 'sent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_scanner_dispatch_per_batch UNIQUE (chat_id, dispatch_date, batch_hash)
);

CREATE INDEX IF NOT EXISTS idx_scanner_dispatch_chat_date ON public.scanner_dispatch_log (chat_id, dispatch_date);
CREATE INDEX IF NOT EXISTS idx_scanner_dispatch_created_at ON public.scanner_dispatch_log (created_at DESC);

CREATE OR REPLACE FUNCTION public.acquire_scanner_dispatch_lock(
    p_chat_id TEXT,
    p_date DATE,
    p_batch_hash TEXT,
    p_symbols TEXT[],
    p_category TEXT DEFAULT 'intraday_scan',
    p_worker TEXT DEFAULT 'huggingface',
    p_cooldown_seconds INT DEFAULT 300
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_recent_id UUID;
    v_new_id UUID;
BEGIN
    -- 1. Check if the exact same batch has already been dispatched today
    IF EXISTS (
        SELECT 1 FROM public.scanner_dispatch_log
        WHERE chat_id = p_chat_id
          AND dispatch_date = p_date
          AND batch_hash = p_batch_hash
    ) THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'exact_batch_already_dispatched_today'
        );
    END IF;

    -- 2. Check Cooldown: Has ANY dispatch occurred to this chat_id within the cooldown window?
    SELECT id INTO v_recent_id
    FROM public.scanner_dispatch_log
    WHERE chat_id = p_chat_id
      AND category = p_category
      AND created_at >= (now() - (p_cooldown_seconds || ' seconds')::INTERVAL)
    LIMIT 1;

    IF v_recent_id IS NOT NULL THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'cooldown_active',
            'cooldown_seconds', p_cooldown_seconds
        );
    END IF;

    -- 3. Atomic insertion to acquire the dispatch slot (guaranteed by UNIQUE constraint)
    BEGIN
        INSERT INTO public.scanner_dispatch_log (
            chat_id, dispatch_date, batch_hash, category, symbols, worker_node, status
        )
        VALUES (
            p_chat_id, p_date, p_batch_hash, p_category, p_symbols, p_worker, 'pending'
        )
        RETURNING id INTO v_new_id;

        RETURN jsonb_build_object(
            'allowed', true,
            'dispatch_id', v_new_id
        );
    EXCEPTION WHEN unique_violation THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'concurrent_dispatch_race_prevented'
        );
    END;
END;
$$;

CREATE OR REPLACE FUNCTION public.confirm_scanner_dispatch(
    p_dispatch_id UUID,
    p_message_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.scanner_dispatch_log
    SET message_id = p_message_id,
        status = 'delivered'
    WHERE id = p_dispatch_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.delete_pending_dispatch(p_dispatch_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM public.scanner_dispatch_log
    WHERE id = p_dispatch_id AND status = 'pending';
END;
$$;
