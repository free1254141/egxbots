-- Migration: 20261115180000_enable_rls_scanner_dispatch_log.sql
-- Description: Enable Row Level Security (RLS) on public.scanner_dispatch_log to resolve Supabase security advisor warning

ALTER TABLE public.scanner_dispatch_log ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'scanner_dispatch_log' 
        AND policyname = 'Service role full access on scanner_dispatch_log'
    ) THEN
        CREATE POLICY "Service role full access on scanner_dispatch_log" 
            ON public.scanner_dispatch_log 
            FOR ALL 
            TO service_role 
            USING (true) 
            WITH CHECK (true);
    END IF;
END $$;
