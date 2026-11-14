-- =============================================================================
-- Migration: 20261114130000_saudi_supabase_functions_triggers_timeouts.sql
-- Target: Saudi Supabase (ughyugwlqbdxibklcddv)
-- Purpose:
--   1. Align role timeouts (service_role 120s, authenticator 60s / lock 30s)
--   2. Create updated_at trigger helpers & 4 BEFORE UPDATE triggers
--   3. Create all 7 market-data RPCs adapted to Saudi (TADAWUL / Saudi Arabia / Asia/Riyadh)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Role Statement & Lock Timeouts
-- -----------------------------------------------------------------------------
ALTER ROLE service_role SET statement_timeout = '120s';
ALTER ROLE authenticator SET statement_timeout = '60s';
ALTER ROLE authenticator SET lock_timeout = '30s';
NOTIFY pgrst, 'reload config';

-- -----------------------------------------------------------------------------
-- 2. Trigger Helpers & BEFORE UPDATE Triggers
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_stocks_updated_at ON public.stocks;
CREATE TRIGGER trg_stocks_updated_at
  BEFORE UPDATE ON public.stocks
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_stock_fundamentals_updated_at ON public.stock_fundamentals;
CREATE TRIGGER trg_stock_fundamentals_updated_at
  BEFORE UPDATE ON public.stock_fundamentals
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_stock_scans_summary_updated_at ON public.stock_scans_summary;
CREATE TRIGGER trg_stock_scans_summary_updated_at
  BEFORE UPDATE ON public.stock_scans_summary
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS update_scan_results_updated_at ON public.scan_results;
CREATE TRIGGER update_scan_results_updated_at
  BEFORE UPDATE ON public.scan_results
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

-- -----------------------------------------------------------------------------
-- 3. RPC 1: get_active_countries
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_active_countries()
RETURNS TABLE(country text)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
  SELECT min(raw_country) AS country
  FROM (
    SELECT trim(both ' ' from COALESCE(data->>'country', country)) AS raw_country
    FROM public.stock_fundamentals
    WHERE COALESCE(data->>'country', country) IS NOT NULL
      AND trim(both ' ' from COALESCE(data->>'country', country)) <> ''
  ) t
  GROUP BY lower(raw_country)
  ORDER BY country ASC;
$function$;

-- -----------------------------------------------------------------------------
-- 4. RPC 2: get_active_symbols
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_active_symbols(p_country text DEFAULT NULL::text)
RETURNS TABLE(symbol text, exchange text, name text, country text)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
  SELECT
    f.symbol,
    f.exchange,
    COALESCE(f.name, (f.data->>'name')::text) AS name,
    COALESCE(f.country, (f.data->>'country')::text) AS country
  FROM public.stock_fundamentals f
  WHERE (
      p_country IS NULL
      OR lower(COALESCE(f.country, f.data->>'country')) = lower(p_country)
    )
    AND NOT (f.symbol ILIKE 'fund_%');
$function$;

-- -----------------------------------------------------------------------------
-- 5. RPC 3: get_exchange_symbols_prices
-- Supports both `target_exchange` and `p_exchange` parameter names seamlessly
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_exchange_symbols_prices(
  target_exchange text DEFAULT NULL::text,
  p_exchange text DEFAULT NULL::text
)
RETURNS TABLE(symbol text, count bigint, last_date date)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
  SELECT
    t.symbol,
    count(*) AS count,
    max(t.date) AS last_date
  FROM public.stock_prices t
  WHERE t.exchange = COALESCE(target_exchange, p_exchange, 'TADAWUL')
  GROUP BY t.symbol;
$function$;

-- -----------------------------------------------------------------------------
-- 6. RPC 4: get_latest_tech_indicators
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_latest_tech_indicators(
  p_symbol text DEFAULT NULL::text,
  p_exchange text DEFAULT 'TADAWUL'::text
)
RETURNS TABLE(
  symbol text,
  exchange text,
  date date,
  close numeric,
  volume bigint,
  rsi_14 numeric,
  ema_50 numeric,
  ema_200 numeric,
  macd numeric,
  macd_signal numeric,
  adx_14 numeric,
  atr_14 numeric,
  stoch_k numeric,
  stoch_d numeric,
  cci_20 numeric,
  vwap_20 numeric,
  roc_12 numeric,
  vol_sma20 bigint,
  momentum_10 numeric,
  change_pct numeric
)
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
  SELECT
    t.symbol,
    t.exchange,
    t.date,
    t.close::numeric,
    t.volume::bigint,
    t.rsi_14::numeric,
    t.ema_50::numeric,
    t.ema_200::numeric,
    t.macd::numeric,
    t.macd_signal::numeric,
    t.adx_14::numeric,
    t.atr_14::numeric,
    t.stoch_k::numeric,
    t.stoch_d::numeric,
    t.cci_20::numeric,
    t.vwap_20::numeric,
    t.roc_12::numeric,
    COALESCE(t.vol_sma20, t.volume_sma_20::bigint) AS vol_sma20,
    t.momentum_10::numeric,
    t.change_pct::numeric
  FROM public.stock_technical_indicators t
  WHERE (p_symbol IS NULL OR t.symbol = p_symbol)
    AND (p_exchange IS NULL OR t.exchange = p_exchange)
  ORDER BY t.date DESC NULLS LAST
  LIMIT CASE WHEN p_symbol IS NOT NULL THEN 1 ELSE 500 END;
$function$;

-- -----------------------------------------------------------------------------
-- 7. RPC 5: scan_technical_indicators
-- Supports Saudi TADAWUL parameters and Primary EGX parameters
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scan_technical_indicators(
  p_exchange text DEFAULT 'TADAWUL'::text,
  p_rsi_min numeric DEFAULT NULL::numeric,
  p_rsi_max numeric DEFAULT NULL::numeric,
  p_adx_min numeric DEFAULT NULL::numeric,
  p_macd_bullish boolean DEFAULT NULL::boolean,
  p_above_sma50 boolean DEFAULT NULL::boolean,
  p_above_sma200 boolean DEFAULT NULL::boolean,
  p_stoch_k_max numeric DEFAULT NULL::numeric,
  p_vol_ratio_min numeric DEFAULT NULL::numeric,
  p_sort_by text DEFAULT 'rsi_14'::text,
  p_sort_asc boolean DEFAULT true,
  p_limit integer DEFAULT 30,
  p_adx_max numeric DEFAULT NULL::numeric,
  p_atr_min numeric DEFAULT NULL::numeric,
  p_atr_max numeric DEFAULT NULL::numeric,
  p_stoch_k_min numeric DEFAULT NULL::numeric,
  p_roc_min numeric DEFAULT NULL::numeric,
  p_roc_max numeric DEFAULT NULL::numeric,
  p_above_ema50 boolean DEFAULT false,
  p_above_ema200 boolean DEFAULT false,
  p_above_vwap20 boolean DEFAULT false,
  p_volume_above_sma20 boolean DEFAULT false,
  p_golden_cross boolean DEFAULT false
)
RETURNS TABLE(
  symbol text,
  name text,
  last_close numeric,
  rsi numeric,
  volume bigint,
  ema50 numeric,
  ema200 numeric,
  momentum numeric,
  roc12 numeric,
  vol_sma20 bigint,
  change_p numeric,
  atr14 numeric,
  adx14 numeric,
  stoch_k numeric,
  stoch_d numeric,
  cci20 numeric,
  vwap20 numeric
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
  RETURN QUERY
  WITH latest_indicators AS (
    SELECT DISTINCT ON (t.symbol, t.exchange)
      t.symbol,
      t.exchange,
      t.close::numeric AS close,
      t.volume::bigint AS volume,
      t.rsi_14::numeric AS rsi_14,
      t.ema_50::numeric AS ema_50,
      t.ema_200::numeric AS ema_200,
      t.sma_50::numeric AS sma_50,
      t.sma_200::numeric AS sma_200,
      t.macd::numeric AS macd,
      t.macd_signal::numeric AS macd_signal,
      t.momentum_10::numeric AS momentum_10,
      t.roc_12::numeric AS roc_12,
      COALESCE(t.vol_sma20, t.volume_sma_20::bigint) AS vol_sma20,
      t.r_vol::numeric AS r_vol,
      t.change_pct::numeric AS change_pct,
      t.atr_14::numeric AS atr_14,
      t.adx_14::numeric AS adx_14,
      t.stoch_k::numeric AS stoch_k,
      t.stoch_d::numeric AS stoch_d,
      t.cci_20::numeric AS cci_20,
      t.vwap_20::numeric AS vwap_20
    FROM public.stock_technical_indicators t
    WHERE t.exchange = COALESCE(p_exchange, 'TADAWUL')
      AND (p_rsi_min IS NULL OR t.rsi_14 >= p_rsi_min)
      AND (p_rsi_max IS NULL OR t.rsi_14 <= p_rsi_max)
      AND (p_adx_min IS NULL OR t.adx_14 >= p_adx_min)
      AND (p_adx_max IS NULL OR t.adx_14 <= p_adx_max)
      AND (p_atr_min IS NULL OR t.atr_14 >= p_atr_min)
      AND (p_atr_max IS NULL OR t.atr_14 <= p_atr_max)
      AND (p_stoch_k_min IS NULL OR t.stoch_k >= p_stoch_k_min)
      AND (p_stoch_k_max IS NULL OR t.stoch_k <= p_stoch_k_max)
      AND (p_roc_min IS NULL OR t.roc_12 >= p_roc_min)
      AND (p_roc_max IS NULL OR t.roc_12 <= p_roc_max)
      AND (p_macd_bullish IS NULL OR (p_macd_bullish = true AND t.macd > t.macd_signal) OR (p_macd_bullish = false AND t.macd <= t.macd_signal))
      AND (p_above_sma50 IS NULL OR (p_above_sma50 = true AND t.close > COALESCE(t.sma_50, t.ema_50)) OR (p_above_sma50 = false AND t.close <= COALESCE(t.sma_50, t.ema_50)))
      AND (p_above_sma200 IS NULL OR (p_above_sma200 = true AND t.close > COALESCE(t.sma_200, t.ema_200)) OR (p_above_sma200 = false AND t.close <= COALESCE(t.sma_200, t.ema_200)))
      AND (p_vol_ratio_min IS NULL OR COALESCE(t.r_vol, CASE WHEN COALESCE(t.vol_sma20, t.volume_sma_20) > 0 THEN t.volume / COALESCE(t.vol_sma20, t.volume_sma_20) ELSE 0 END) >= p_vol_ratio_min)
      AND (NOT COALESCE(p_above_ema50, false) OR t.close > t.ema_50)
      AND (NOT COALESCE(p_above_ema200, false) OR t.close > t.ema_200)
      AND (NOT COALESCE(p_above_vwap20, false) OR t.close > t.vwap_20)
      AND (NOT COALESCE(p_volume_above_sma20, false) OR t.volume > COALESCE(t.vol_sma20, t.volume_sma_20))
      AND (NOT COALESCE(p_golden_cross, false) OR (t.ema_50 > t.ema_200))
    ORDER BY t.symbol, t.exchange, t.date DESC NULLS LAST
  )
  SELECT
    l.symbol::text,
    COALESCE(f.name, f.data->>'name', l.symbol)::text AS name,
    l.close,
    l.rsi_14,
    l.volume,
    l.ema_50,
    l.ema_200,
    l.momentum_10,
    l.roc_12,
    l.vol_sma20,
    l.change_pct,
    l.atr_14,
    l.adx_14,
    l.stoch_k,
    l.stoch_d,
    l.cci_20,
    l.vwap_20
  FROM latest_indicators l
  LEFT JOIN public.stock_fundamentals f
    ON l.symbol = f.symbol AND l.exchange = f.exchange
  ORDER BY
    CASE WHEN COALESCE(p_sort_asc, true) THEN
      CASE COALESCE(p_sort_by, 'rsi_14')
        WHEN 'rsi_14' THEN l.rsi_14
        WHEN 'adx_14' THEN l.adx_14
        WHEN 'change_pct' THEN l.change_pct
        WHEN 'volume' THEN l.volume::numeric
        WHEN 'close' THEN l.close
        ELSE l.rsi_14
      END
    END ASC NULLS LAST,
    CASE WHEN NOT COALESCE(p_sort_asc, true) THEN
      CASE COALESCE(p_sort_by, 'rsi_14')
        WHEN 'rsi_14' THEN l.rsi_14
        WHEN 'adx_14' THEN l.adx_14
        WHEN 'change_pct' THEN l.change_pct
        WHEN 'volume' THEN l.volume::numeric
        WHEN 'close' THEN l.close
        ELSE l.rsi_14
      END
    END DESC NULLS LAST
  LIMIT COALESCE(p_limit, 30);
END;
$function$;

-- -----------------------------------------------------------------------------
-- 8. RPC 6: admin_upsert_technical_indicator
-- Uses ON CONFLICT (symbol, exchange) DO UPDATE matching Saudi schema
-- Supports both individual p_* parameters and jsonb `payload`
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.admin_upsert_technical_indicator(
  p_symbol text DEFAULT NULL::text,
  p_exchange text DEFAULT 'TADAWUL'::text,
  p_date date DEFAULT NULL::date,
  p_close numeric DEFAULT NULL::numeric,
  p_volume bigint DEFAULT NULL::bigint,
  p_ema_50 numeric DEFAULT NULL::numeric,
  p_ema_200 numeric DEFAULT NULL::numeric,
  p_sma_50 numeric DEFAULT NULL::numeric,
  p_sma_200 numeric DEFAULT NULL::numeric,
  p_rsi_14 numeric DEFAULT NULL::numeric,
  p_macd numeric DEFAULT NULL::numeric,
  p_macd_signal numeric DEFAULT NULL::numeric,
  p_macd_histogram numeric DEFAULT NULL::numeric,
  p_adx_14 numeric DEFAULT NULL::numeric,
  p_atr_14 numeric DEFAULT NULL::numeric,
  p_bb_upper numeric DEFAULT NULL::numeric,
  p_bb_lower numeric DEFAULT NULL::numeric,
  p_stoch_k numeric DEFAULT NULL::numeric,
  p_stoch_d numeric DEFAULT NULL::numeric,
  p_roc_12 numeric DEFAULT NULL::numeric,
  p_momentum_10 numeric DEFAULT NULL::numeric,
  p_vol_sma20 bigint DEFAULT NULL::bigint,
  p_vwap_20 numeric DEFAULT NULL::numeric,
  p_r_vol numeric DEFAULT NULL::numeric,
  p_change_pct numeric DEFAULT NULL::numeric,
  payload jsonb DEFAULT NULL::jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
  v_symbol text := COALESCE(p_symbol, payload->>'symbol', payload->>'p_symbol');
  v_exchange text := COALESCE(p_exchange, payload->>'exchange', payload->>'p_exchange', 'TADAWUL');
  v_date date := COALESCE(p_date, (payload->>'date')::date, (payload->>'p_date')::date, CURRENT_DATE);
  v_close double precision := COALESCE(p_close, (payload->>'close')::numeric, (payload->>'p_close')::numeric)::double precision;
  v_volume double precision := COALESCE(p_volume::numeric, (payload->>'volume')::numeric, (payload->>'p_volume')::numeric)::double precision;
  v_ema_50 double precision := COALESCE(p_ema_50, (payload->>'ema_50')::numeric, (payload->>'p_ema_50')::numeric)::double precision;
  v_ema_200 double precision := COALESCE(p_ema_200, (payload->>'ema_200')::numeric, (payload->>'p_ema_200')::numeric)::double precision;
  v_sma_50 numeric := COALESCE(p_sma_50, (payload->>'sma_50')::numeric, (payload->>'p_sma_50')::numeric);
  v_sma_200 numeric := COALESCE(p_sma_200, (payload->>'sma_200')::numeric, (payload->>'p_sma_200')::numeric);
  v_rsi_14 double precision := COALESCE(p_rsi_14, (payload->>'rsi_14')::numeric, (payload->>'p_rsi_14')::numeric)::double precision;
  v_macd numeric := COALESCE(p_macd, (payload->>'macd')::numeric, (payload->>'p_macd')::numeric);
  v_macd_signal numeric := COALESCE(p_macd_signal, (payload->>'macd_signal')::numeric, (payload->>'p_macd_signal')::numeric);
  v_macd_histogram numeric := COALESCE(p_macd_histogram, (payload->>'macd_histogram')::numeric, (payload->>'p_macd_histogram')::numeric);
  v_adx_14 double precision := COALESCE(p_adx_14, (payload->>'adx_14')::numeric, (payload->>'p_adx_14')::numeric)::double precision;
  v_atr_14 double precision := COALESCE(p_atr_14, (payload->>'atr_14')::numeric, (payload->>'p_atr_14')::numeric)::double precision;
  v_bb_upper numeric := COALESCE(p_bb_upper, (payload->>'bb_upper')::numeric, (payload->>'p_bb_upper')::numeric);
  v_bb_lower numeric := COALESCE(p_bb_lower, (payload->>'bb_lower')::numeric, (payload->>'p_bb_lower')::numeric);
  v_stoch_k double precision := COALESCE(p_stoch_k, (payload->>'stoch_k')::numeric, (payload->>'p_stoch_k')::numeric)::double precision;
  v_stoch_d double precision := COALESCE(p_stoch_d, (payload->>'stoch_d')::numeric, (payload->>'p_stoch_d')::numeric)::double precision;
  v_roc_12 double precision := COALESCE(p_roc_12, (payload->>'roc_12')::numeric, (payload->>'p_roc_12')::numeric)::double precision;
  v_momentum_10 double precision := COALESCE(p_momentum_10, (payload->>'momentum_10')::numeric, (payload->>'p_momentum_10')::numeric)::double precision;
  v_vol_sma20 bigint := COALESCE(p_vol_sma20, (payload->>'vol_sma20')::bigint, (payload->>'p_vol_sma20')::bigint);
  v_vwap_20 double precision := COALESCE(p_vwap_20, (payload->>'vwap_20')::numeric, (payload->>'p_vwap_20')::numeric)::double precision;
  v_r_vol numeric := COALESCE(p_r_vol, (payload->>'r_vol')::numeric, (payload->>'p_r_vol')::numeric);
  v_change_pct double precision := COALESCE(p_change_pct, (payload->>'change_pct')::numeric, (payload->>'p_change_pct')::numeric)::double precision;
BEGIN
  IF v_symbol IS NULL THEN
    RAISE EXCEPTION 'symbol is required for admin_upsert_technical_indicator';
  END IF;

  INSERT INTO public.stock_technical_indicators (
    symbol, exchange, date, close, volume,
    ema_50, ema_200, sma_50, sma_200,
    rsi_14, macd, macd_signal, macd_histogram,
    adx_14, atr_14, bb_upper, bb_lower,
    stoch_k, stoch_d, roc_12, momentum_10,
    vol_sma20, volume_sma_20, vwap_20, r_vol, change_pct,
    updated_at, calculated_at
  )
  VALUES (
    v_symbol, v_exchange, v_date, v_close, v_volume,
    v_ema_50, v_ema_200, v_sma_50, v_sma_200,
    v_rsi_14, v_macd, v_macd_signal, v_macd_histogram,
    v_adx_14, v_atr_14, v_bb_upper, v_bb_lower,
    v_stoch_k, v_stoch_d, v_roc_12, v_momentum_10,
    v_vol_sma20, v_vol_sma20::double precision, v_vwap_20, v_r_vol, v_change_pct,
    now(), now()
  )
  ON CONFLICT (symbol, exchange)
  DO UPDATE SET
    date = EXCLUDED.date,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    ema_50 = EXCLUDED.ema_50,
    ema_200 = EXCLUDED.ema_200,
    sma_50 = EXCLUDED.sma_50,
    sma_200 = EXCLUDED.sma_200,
    rsi_14 = EXCLUDED.rsi_14,
    macd = EXCLUDED.macd,
    macd_signal = EXCLUDED.macd_signal,
    macd_histogram = EXCLUDED.macd_histogram,
    adx_14 = EXCLUDED.adx_14,
    atr_14 = EXCLUDED.atr_14,
    bb_upper = EXCLUDED.bb_upper,
    bb_lower = EXCLUDED.bb_lower,
    stoch_k = EXCLUDED.stoch_k,
    stoch_d = EXCLUDED.stoch_d,
    roc_12 = EXCLUDED.roc_12,
    momentum_10 = EXCLUDED.momentum_10,
    vol_sma20 = EXCLUDED.vol_sma20,
    volume_sma_20 = EXCLUDED.volume_sma_20,
    vwap_20 = EXCLUDED.vwap_20,
    r_vol = EXCLUDED.r_vol,
    change_pct = EXCLUDED.change_pct,
    updated_at = now(),
    calculated_at = now();
END;
$function$;

-- -----------------------------------------------------------------------------
-- 9. RPC 7: publish_public_recommendation
-- Adapted for Saudi Market (exchange = 'TADAWUL', country = 'Saudi Arabia', timezone = 'Asia/Riyadh')
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publish_public_recommendation(
  p_row jsonb DEFAULT NULL::jsonb,
  p_daily_limit integer DEFAULT 1,
  p_rolling_limit integer DEFAULT 20,
  p_open_limit integer DEFAULT 10,
  p_cooldown_days integer DEFAULT 7,
  p_symbol text DEFAULT NULL::text,
  p_target_date date DEFAULT NULL::date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
  v_row public.scan_results%rowtype;
  v_now timestamptz := now();
  v_day timestamptz := date_trunc('day', now() AT TIME ZONE 'Asia/Riyadh') AT TIME ZONE 'Asia/Riyadh';
  v_entry numeric := (p_row->>'entry_price')::numeric;
  v_target numeric := (p_row->>'target_price')::numeric;
  v_stop numeric := (p_row->>'stop_loss')::numeric;
  v_symbol text := COALESCE(nullif(trim(p_row->>'symbol'), ''), nullif(trim(p_symbol), ''));
  v_exchange text := COALESCE(nullif(trim(p_row->>'exchange'), ''), 'TADAWUL');
BEGIN
  IF p_daily_limit IS NULL OR p_rolling_limit IS NULL OR p_open_limit IS NULL
     OR p_cooldown_days IS NULL OR p_daily_limit < 1 OR p_daily_limit > 5
     OR p_rolling_limit < 1 OR p_rolling_limit > 30
     OR p_open_limit < 1 OR p_open_limit > 20 OR p_cooldown_days < 1 THEN
    RAISE EXCEPTION 'Invalid recommendation capacity';
  END IF;

  IF v_symbol IS NULL OR v_exchange IS DISTINCT FROM 'TADAWUL'
     OR nullif(trim(p_row #>> '{rich_details,recommendation_policy,version}'), '') IS NULL
     OR v_entry IS NULL OR v_stop IS NULL OR v_target IS NULL
     OR v_entry::text IN ('NaN','Infinity','-Infinity')
     OR v_target::text IN ('NaN','Infinity','-Infinity')
     OR v_stop::text IN ('NaN','Infinity','-Infinity')
     OR NOT (0 < v_stop AND v_stop < v_entry AND v_entry < v_target) THEN
    RETURN jsonb_build_object('status','rejected','reason','invalid_setup');
  END IF;

  IF (v_target - v_entry) / (v_entry - v_stop) < 1.5 THEN
    RETURN jsonb_build_object('status','rejected','reason','invalid_setup');
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended('public_tadawul_recommendation_capacity', 0));

  IF EXISTS (
    SELECT 1 FROM public.scan_results
    WHERE is_public AND exchange = 'TADAWUL'
      AND upper(symbol) = upper(v_symbol)
      AND (status = 'open' OR updated_at >= v_now - make_interval(days => p_cooldown_days))
  ) THEN
    RETURN jsonb_build_object('status','rejected','reason','duplicate_or_cooldown');
  END IF;

  IF (
    SELECT count(*) FROM public.scan_results
    WHERE is_public AND exchange = 'TADAWUL'
      AND created_at >= v_day
  ) >= p_daily_limit THEN
    RETURN jsonb_build_object('status','rejected','reason','daily_capacity');
  END IF;

  IF (
    SELECT count(*) FROM public.scan_results
    WHERE is_public AND exchange = 'TADAWUL'
      AND created_at >= v_now - interval '30 days'
      AND rich_details #>> '{recommendation_policy,version}' IS NOT NULL
  ) >= p_rolling_limit THEN
    RETURN jsonb_build_object('status','rejected','reason','rolling_capacity');
  END IF;

  IF (
    SELECT count(*) FROM public.scan_results
    WHERE is_public AND exchange = 'TADAWUL'
      AND status = 'open'
      AND rich_details #>> '{recommendation_policy,version}' IS NOT NULL
  ) >= p_open_limit THEN
    RETURN jsonb_build_object('status','rejected','reason','open_capacity');
  END IF;

  INSERT INTO public.scan_results (
    batch_id, symbol, exchange, name, model_name, country, last_close, precision, signal,
    status, entry_price, target_price, stop_loss, risk_adjusted_return, is_public,
    top_reasons, features, rich_details, created_at, updated_at
  )
  VALUES (
    (p_row->>'batch_id')::uuid, upper(v_symbol), 'TADAWUL', p_row->>'name',
    p_row->>'model_name', 'Saudi Arabia', v_entry, (p_row->>'precision')::numeric, 'BUY',
    'open', v_entry, v_target, v_stop, (p_row->>'risk_adjusted_return')::numeric, true,
    p_row->'top_reasons', p_row->'features', p_row->'rich_details', v_now, v_now
  )
  RETURNING * INTO v_row;

  RETURN jsonb_build_object('status','inserted','row',to_jsonb(v_row));
END;
$function$;

-- -----------------------------------------------------------------------------
-- 10. Permissions & PostgREST Schema Reload
-- -----------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION public.get_active_countries() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_active_symbols(text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_exchange_symbols_prices(text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_latest_tech_indicators(text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.scan_technical_indicators(
  text, numeric, numeric, numeric, boolean, boolean, boolean, numeric, numeric, text, boolean, integer,
  numeric, numeric, numeric, numeric, numeric, numeric, boolean, boolean, boolean, boolean, boolean
) TO anon, authenticated, service_role;

REVOKE ALL ON FUNCTION public.admin_upsert_technical_indicator(
  text, text, date, numeric, bigint, numeric, numeric, numeric, numeric, numeric,
  numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric,
  numeric, bigint, numeric, numeric, numeric, jsonb
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_upsert_technical_indicator(
  text, text, date, numeric, bigint, numeric, numeric, numeric, numeric, numeric,
  numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric, numeric,
  numeric, bigint, numeric, numeric, numeric, jsonb
) TO service_role;

REVOKE ALL ON FUNCTION public.publish_public_recommendation(
  jsonb, integer, integer, integer, integer, text, date
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_public_recommendation(
  jsonb, integer, integer, integer, integer, text, date
) TO service_role;

NOTIFY pgrst, 'reload schema';
NOTIFY pgrst, 'reload config';
