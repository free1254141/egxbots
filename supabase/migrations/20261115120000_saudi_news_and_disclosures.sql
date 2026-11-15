-- Create stock_news_sentiment and egx_disclosures in Saudi Supabase (TADAWUL)
-- Keeps identical schema to Primary Supabase so frontend, APIs, and agentic_chat work uniformly.

CREATE TABLE IF NOT EXISTS public.stock_news_sentiment (
    id bigserial PRIMARY KEY,
    symbol text NOT NULL,
    exchange text DEFAULT 'TADAWUL',
    date date NOT NULL,
    sentiment_score double precision DEFAULT 0.0,
    news_count integer DEFAULT 0,
    negative_flag integer DEFAULT 0,
    positive_flag integer DEFAULT 0,
    headlines jsonb DEFAULT '[]'::jsonb,
    sources jsonb DEFAULT '[]'::jsonb,
    created_at timestamptz DEFAULT now(),
    UNIQUE (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_stock_news_sentiment_exchange_date
    ON public.stock_news_sentiment (exchange, date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_news_sentiment_symbol_date
    ON public.stock_news_sentiment (symbol, date DESC);

ALTER TABLE public.stock_news_sentiment ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'stock_news_sentiment' AND policyname = 'Public read stock_news_sentiment'
    ) THEN
        CREATE POLICY "Public read stock_news_sentiment"
            ON public.stock_news_sentiment FOR SELECT USING (true);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.egx_disclosures (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol varchar,
    company_name text NOT NULL,
    disclosure_type varchar NOT NULL,
    disclosure_date date NOT NULL,
    title text NOT NULL,
    raw_content text,
    ai_summary text NOT NULL,
    sentiment varchar DEFAULT 'neutral',
    action_type varchar,
    shares_count bigint,
    stake_before numeric,
    stake_after numeric,
    party_name text,
    party_role text,
    source_url text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_egx_disclosures_date
    ON public.egx_disclosures (disclosure_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_egx_disclosures_symbol
    ON public.egx_disclosures (symbol, disclosure_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_egx_disclosures_unique_source
    ON public.egx_disclosures (source_url) WHERE source_url IS NOT NULL;

ALTER TABLE public.egx_disclosures ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'egx_disclosures' AND policyname = 'Public read egx_disclosures'
    ) THEN
        CREATE POLICY "Public read egx_disclosures"
            ON public.egx_disclosures FOR SELECT USING (true);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
