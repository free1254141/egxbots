-- Idempotent audit log for private Telegram subscription renewal reminders
CREATE TABLE IF NOT EXISTS public.telegram_subscription_reminder_log (
    id BIGSERIAL PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES public.subscriptions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    reminder_days INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    telegram_message_id BIGINT,
    error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT telegram_sub_reminder_uniq UNIQUE (subscription_id, period_end, reminder_days)
);

CREATE INDEX IF NOT EXISTS idx_sub_reminder_lookup 
    ON public.telegram_subscription_reminder_log(subscription_id, period_end, reminder_days);

CREATE INDEX IF NOT EXISTS idx_sub_reminder_user 
    ON public.telegram_subscription_reminder_log(user_id, status);

ALTER TABLE public.telegram_subscription_reminder_log ENABLE ROW LEVEL SECURITY;

-- Service role full access policy
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'telegram_subscription_reminder_log' 
        AND policyname = 'Service role full access on reminder log'
    ) THEN
        CREATE POLICY "Service role full access on reminder log" 
            ON public.telegram_subscription_reminder_log 
            FOR ALL 
            TO service_role 
            USING (true) 
            WITH CHECK (true);
    END IF;
END $$;
