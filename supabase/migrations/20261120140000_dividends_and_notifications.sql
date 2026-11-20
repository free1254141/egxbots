-- Unified 4-Market Dividends Calendar, Auto-Portfolio Dividend Credits & In-App Notifications
-- Markets: EGX, TADAWUL, QSE, DFM, ADX

CREATE TABLE IF NOT EXISTS public.stock_dividends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name_ar TEXT,
    name_en TEXT,
    amount DOUBLE PRECISION NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'EGP',
    ex_date DATE NOT NULL,
    record_date DATE,
    pay_date DATE,
    close_price DOUBLE PRECISION,
    yield_pct DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'upcoming',
    source TEXT NOT NULL DEFAULT 'tradingview',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT stock_dividends_unique_event UNIQUE (exchange, symbol, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_dividends_exchange_exdate
    ON public.stock_dividends (exchange, ex_date DESC);

CREATE INDEX IF NOT EXISTS idx_stock_dividends_symbol_exdate
    ON public.stock_dividends (symbol, ex_date DESC);

ALTER TABLE public.stock_dividends ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "stock_dividends_public_read" ON public.stock_dividends;
CREATE POLICY "stock_dividends_public_read"
    ON public.stock_dividends
    FOR SELECT
    USING (true);

CREATE TABLE IF NOT EXISTS public.user_dividend_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dividend_id UUID NOT NULL REFERENCES public.stock_dividends(id) ON DELETE CASCADE,
    exchange TEXT NOT NULL DEFAULT 'EGX',
    symbol TEXT NOT NULL,
    shares_held DOUBLE PRECISION NOT NULL CHECK (shares_held > 0),
    coupon_per_share DOUBLE PRECISION NOT NULL CHECK (coupon_per_share > 0),
    gross_amount DOUBLE PRECISION NOT NULL,
    net_amount DOUBLE PRECISION NOT NULL,
    tax_rate_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EGP',
    ex_date DATE NOT NULL,
    record_date DATE,
    pay_date DATE,
    status TEXT NOT NULL DEFAULT 'upcoming',
    credited_to_cash BOOLEAN NOT NULL DEFAULT FALSE,
    credited_at TIMESTAMPTZ,
    notified_upcoming_at TIMESTAMPTZ,
    notified_paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_dividend_events_unique_user_div UNIQUE (user_id, dividend_id)
);

CREATE INDEX IF NOT EXISTS idx_user_dividend_events_user_exdate
    ON public.user_dividend_events (user_id, ex_date DESC);

ALTER TABLE public.user_dividend_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "user_dividend_events_own_read" ON public.user_dividend_events;
CREATE POLICY "user_dividend_events_own_read"
    ON public.user_dividend_events
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS public.user_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'dividend_upcoming',
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    href TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_notifications_unique_dedupe UNIQUE (user_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_unread
    ON public.user_notifications (user_id, is_read, created_at DESC);

ALTER TABLE public.user_notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "user_notifications_own_read" ON public.user_notifications;
CREATE POLICY "user_notifications_own_read"
    ON public.user_notifications
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "user_notifications_own_update" ON public.user_notifications;
CREATE POLICY "user_notifications_own_update"
    ON public.user_notifications
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
