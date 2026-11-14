"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { scanTech, type TechFilter, type TechResult } from "@/lib/api";

type Updater<T> = Partial<T> | ((prev: T) => T);

export type TechScannerState = {
  country: string;
  results: TechResult[];
  hasScanned: boolean;
  scannedCount: number;
  scanHistory: Array<{
    key: string;
    createdAt: number;
    filter: TechFilter;
    results: TechResult[];
    scannedCount: number;
  }>;
  selectedStock: TechResult | null;
  searchTerm: string;
  rsiMin: string;
  rsiMax: string;
  aboveEma50: boolean;
  aboveEma200: boolean;
  adxMin: string;
  adxMax: string;
  atrMin: string;
  atrMax: string;
  stochKMin: string;
  stochKMax: string;
  rocMin: string;
  rocMax: string;
  aboveVwap20: boolean;
  volumeAboveSma20: boolean;
  goldenCross: boolean;
  currentTab: "ai" | "overview" | "performance" | "valuation" | "dividends" | "financials";
  marketCapMin: string;
  marketCapMax: string;
  sector: string;
  industry: string;
  minPrice: string;
  useAiFilter: boolean;
  minAiPrecision: string;
  avoidDistribution: boolean;
  requireAccumulation: boolean;
  cmfMin: string;
  shariaOnly: boolean;
  activeSymbol: string | null;
  chartHeight: number;
  divergenceType: string;
  divergenceIndicator: string;
  divergenceMinStrength: string;
};

type TechnicalScannerContextType = {
  state: TechScannerState;
  activeMarket: ActiveMarket;
  setTechScanner: (u: Updater<TechScannerState>) => void;
  loading: boolean;
  error: string | null;
  runTechScan: (opts?: { force?: boolean }) => Promise<void>;
  stopTechScan: () => void;
  clearTechScannerView: () => void;
  restoreLastTechScan: () => boolean;
  resetTechScanner: () => void;
};

const SESSION_KEY_PREFIX = "egxbots_tech_scanner_v2";
const LEGACY_SESSION_KEY = "egxbots_tech_scanner_v1";
const MARKET_STORAGE_KEY = "egxbots_market";
const MARKET_CHANGE_EVENT = "egxbots:market-change";
const CACHE_TTL_MS = 15 * 60 * 1000;

export type ActiveMarket = "egx" | "tasi";

function normalizeMarketValue(value: unknown): ActiveMarket | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  if (
    normalized === "tasi" ||
    normalized === "tadawul" ||
    normalized === "saudi" ||
    normalized === "saudi arabia" ||
    normalized === "sr"
  ) {
    return "tasi";
  }
  if (normalized === "egx" || normalized === "egypt") {
    return "egx";
  }
  return null;
}

function readStoredMarket(): ActiveMarket {
  if (typeof window === "undefined") return "egx";
  try {
    return normalizeMarketValue(window.localStorage.getItem(MARKET_STORAGE_KEY)) ?? "egx";
  } catch {
    return "egx";
  }
}

function countryForMarket(market: ActiveMarket): string {
  return market === "tasi" ? "Saudi Arabia" : "Egypt";
}

function getSessionKey(market: ActiveMarket): string {
  return `${SESSION_KEY_PREFIX}:${market}`;
}

const DEFAULT_STATE: TechScannerState = {
  country: "Egypt",
  results: [],
  hasScanned: false,
  scannedCount: 0,
  scanHistory: [],
  selectedStock: null,
  searchTerm: "",
  rsiMin: "",
  rsiMax: "",
  aboveEma50: false,
  aboveEma200: false,
  adxMin: "",
  adxMax: "",
  atrMin: "",
  atrMax: "",
  stochKMin: "",
  stochKMax: "",
  rocMin: "",
  rocMax: "",
  aboveVwap20: false,
  volumeAboveSma20: false,
  goldenCross: false,
  currentTab: "ai",
  marketCapMin: "",
  marketCapMax: "",
  sector: "",
  industry: "",
  minPrice: "",
  useAiFilter: false,
  minAiPrecision: "0.6",
  avoidDistribution: false,
  requireAccumulation: false,
  cmfMin: "",
  shariaOnly: false,
  activeSymbol: null,
  chartHeight: 450,
  divergenceType: "NONE",
  divergenceIndicator: "ANY",
  divergenceMinStrength: "0",
};

const TechnicalScannerContext = createContext<TechnicalScannerContextType | undefined>(undefined);

function loadSessionState(market: ActiveMarket = "egx"): TechScannerState {
  const expectedCountry = countryForMarket(market);
  const baseState: TechScannerState = { ...DEFAULT_STATE, country: expectedCountry };
  if (typeof window === "undefined") return baseState;
  try {
    const key = getSessionKey(market);
    const raw =
      sessionStorage.getItem(key) ||
      (market === "egx" ? sessionStorage.getItem(LEGACY_SESSION_KEY) : null);
    if (!raw) return baseState;
    const parsed = JSON.parse(raw) as Partial<TechScannerState>;
    // Invalidate old cache if results don't contain score data
    const hasResults = Array.isArray(parsed.results) && parsed.results.length > 0;
    const hasScoreData = hasResults && parsed.results![0].fundamental_score !== undefined;
    if (hasResults && !hasScoreData) {
      sessionStorage.removeItem(key);
      if (market === "egx") sessionStorage.removeItem(LEGACY_SESSION_KEY);
      return baseState;
    }
    return {
      ...baseState,
      ...parsed,
      country: expectedCountry,
      selectedStock: null,
      activeSymbol: null,
      results: Array.isArray(parsed.results) ? parsed.results : [],
      scanHistory: Array.isArray(parsed.scanHistory) ? parsed.scanHistory : [],
    };
  } catch {
    return baseState;
  }
}

function buildFilterKey(filter: TechFilter): string {
  return JSON.stringify({
    country: filter.country,
    limit: filter.limit,
    rsi_min: filter.rsi_min,
    rsi_max: filter.rsi_max,
    min_price: filter.min_price,
    market_cap_min: filter.market_cap_min,
    market_cap_max: filter.market_cap_max,
    sector: filter.sector,
    industry: filter.industry,
    golden_cross: filter.golden_cross,
    above_ema50: filter.above_ema50,
    above_ema200: filter.above_ema200,
    adx_min: filter.adx_min,
    adx_max: filter.adx_max,
    atr_min: filter.atr_min,
    atr_max: filter.atr_max,
    stoch_k_min: filter.stoch_k_min,
    stoch_k_max: filter.stoch_k_max,
    roc_min: filter.roc_min,
    roc_max: filter.roc_max,
    above_vwap20: filter.above_vwap20,
    volume_above_sma20: filter.volume_above_sma20,
    use_ai_filter: filter.use_ai_filter,
    min_ai_precision: filter.min_ai_precision,
    avoid_distribution: filter.avoid_distribution,
    require_accumulation: filter.require_accumulation,
    cmf_min: filter.cmf_min,
    divergence_type: filter.divergence_type,
    divergence_indicator: filter.divergence_indicator,
    divergence_min_strength: filter.divergence_min_strength,
  });
}

function buildFilterFromState(s: TechScannerState): TechFilter {
  return {
    country: s.country,
    limit: 300,
    rsi_min: s.rsiMin ? parseFloat(s.rsiMin) : undefined,
    rsi_max: s.rsiMax ? parseFloat(s.rsiMax) : undefined,
    min_price: s.minPrice ? parseFloat(s.minPrice) : undefined,
    above_ema50: s.aboveEma50,
    above_ema200: s.aboveEma200,
    adx_min: s.adxMin ? parseFloat(s.adxMin) : undefined,
    adx_max: s.adxMax ? parseFloat(s.adxMax) : undefined,
    atr_min: s.atrMin ? parseFloat(s.atrMin) : undefined,
    atr_max: s.atrMax ? parseFloat(s.atrMax) : undefined,
    stoch_k_min: s.stochKMin ? parseFloat(s.stochKMin) : undefined,
    stoch_k_max: s.stochKMax ? parseFloat(s.stochKMax) : undefined,
    roc_min: s.rocMin ? parseFloat(s.rocMin) : undefined,
    roc_max: s.rocMax ? parseFloat(s.rocMax) : undefined,
    above_vwap20: s.aboveVwap20,
    volume_above_sma20: s.volumeAboveSma20,
    market_cap_min: s.marketCapMin ? parseFloat(s.marketCapMin) : undefined,
    market_cap_max: s.marketCapMax ? parseFloat(s.marketCapMax) : undefined,
    sector: s.sector || undefined,
    industry: s.industry || undefined,
    golden_cross: s.goldenCross,
    use_ai_filter: s.useAiFilter,
    min_ai_precision: s.minAiPrecision ? parseFloat(s.minAiPrecision) : undefined,
    avoid_distribution: s.avoidDistribution,
    require_accumulation: s.requireAccumulation,
    cmf_min: s.cmfMin ? parseFloat(s.cmfMin) : undefined,
    divergence_type: s.divergenceType !== "NONE" ? s.divergenceType : undefined,
    divergence_indicator: s.divergenceIndicator !== "ANY" ? s.divergenceIndicator : undefined,
    divergence_min_strength: s.divergenceMinStrength && parseFloat(s.divergenceMinStrength) > 0 ? parseFloat(s.divergenceMinStrength) / 100 : undefined,
  };
}

export function TechnicalScannerProvider({ children }: { children: ReactNode }) {
  const [activeMarket, setActiveMarket] = useState<ActiveMarket>("egx");
  const activeMarketRef = useRef<ActiveMarket>("egx");
  const [state, setState] = useState<TechScannerState>(DEFAULT_STATE);
  const [isLoaded, setIsLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stateRef = useRef(state);

  // Load from market-scoped session storage after mount to prevent SSR/hydration mismatch
  useEffect(() => {
    const initialMarket = readStoredMarket();
    activeMarketRef.current = initialMarket;
    setActiveMarket(initialMarket);
    const loaded = loadSessionState(initialMarket);
    stateRef.current = loaded;
    setState(loaded);
    setIsLoaded(true);
  }, []);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (!isLoaded) return;
    const market = activeMarketRef.current;
    if (state.country !== countryForMarket(market)) return;
    try {
      const { selectedStock: _selected, activeSymbol: _activeSymbol, ...persisted } = state;
      sessionStorage.setItem(getSessionKey(market), JSON.stringify(persisted));
    } catch {
      // sessionStorage may be unavailable
    }
  }, [state, isLoaded, activeMarket]);

  const setTechScanner = useCallback((u: Updater<TechScannerState>) => {
    setState((prev) => {
      const next =
        typeof u === "function" ? (u as (p: TechScannerState) => TechScannerState)(prev) : { ...prev, ...u };
      stateRef.current = next;
      return next;
    });
  }, []);

  const clearTechScannerView = useCallback(() => {
    setState((prev) => {
      const next: TechScannerState = {
        ...prev,
        results: [],
        hasScanned: false,
        scannedCount: 0,
        selectedStock: null,
        activeSymbol: null,
      };
      stateRef.current = next;
      return next;
    });
  }, []);

  const restoreLastTechScan = useCallback(() => {
    let restored = false;
    setState((prev) => {
      const last = prev.scanHistory?.[prev.scanHistory.length - 1];
      if (!last) return prev;
      restored = true;
      const next: TechScannerState = {
        ...prev,
        results: last.results,
        hasScanned: true,
        scannedCount: last.scannedCount,
        selectedStock: null,
      };
      stateRef.current = next;
      return next;
    });
    return restored;
  }, []);

  const resetTechScanner = useCallback(() => {
    const market = activeMarketRef.current;
    const next: TechScannerState = { ...DEFAULT_STATE, country: countryForMarket(market) };
    stateRef.current = next;
    setState(next);
    try {
      sessionStorage.removeItem(getSessionKey(market));
      if (market === "egx") sessionStorage.removeItem(LEGACY_SESSION_KEY);
    } catch {
      // ignore
    }
  }, []);

  const runTechScan = useCallback(async (opts?: { force?: boolean }) => {
    const reqMarket = activeMarketRef.current;
    const current = stateRef.current;
    const filter = buildFilterFromState(current);
    const key = buildFilterKey(filter);
    const now = Date.now();

    if (!opts?.force) {
      const cached = current.scanHistory?.find((h) => h.key === key && now - h.createdAt < CACHE_TTL_MS);
      if (cached) {
        setState((prev) => {
          const next: TechScannerState = {
            ...prev,
            results: cached.results,
            hasScanned: true,
            scannedCount: cached.scannedCount,
            selectedStock: null,
          };
          stateRef.current = next;
          return next;
        });
        return;
      }

      if (current.hasScanned) {
        return;
      }
    }

    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    if (opts?.force) {
      setState((prev) => {
        const next: TechScannerState = {
          ...prev,
          results: [],
          hasScanned: false,
          scannedCount: 0,
          selectedStock: null,
        };
        stateRef.current = next;
        return next;
      });
    }

    try {
      const res = await scanTech(filter, controller.signal);
      if (reqMarket !== activeMarketRef.current || controller.signal.aborted) {
        return;
      }

      let next = res.results || [];
      if (current.goldenCross) {
        next = next.filter((r) => r.ema50 > r.ema200);
      }

      setState((prev) => {
        const history = Array.isArray(prev.scanHistory) ? prev.scanHistory : [];
        const snapshot = {
          key,
          createdAt: Date.now(),
          filter,
          results: next,
          scannedCount: res.scanned_count,
        };
        const deduped = history.filter((h) => h.key !== key);
        const capped = [...deduped, snapshot].slice(-5);
        const updated: TechScannerState = {
          ...prev,
          results: next,
          hasScanned: true,
          scannedCount: res.scanned_count,
          scanHistory: capped,
          selectedStock: null,
        };
        stateRef.current = updated;
        return updated;
      });

      // ── Analytics tracking (non-blocking) ─────────────────────────────
      // Detect active filter groups to understand what users scan for
      const activeFilters: string[] = [];
      if (filter.rsi_min != null || filter.rsi_max != null) activeFilters.push("rsi");
      if (filter.above_ema50) activeFilters.push("ema50");
      if (filter.above_ema200) activeFilters.push("ema200");
      if (filter.golden_cross) activeFilters.push("golden_cross");
      if (filter.adx_min != null || filter.adx_max != null) activeFilters.push("adx");
      if (filter.volume_above_sma20) activeFilters.push("volume");
      if (filter.above_vwap20) activeFilters.push("vwap");
      if (filter.sector) activeFilters.push("sector");
      if (filter.divergence_type) activeFilters.push("divergence");
      if (filter.use_ai_filter) activeFilters.push("ai_filter");
      if (current.shariaOnly) activeFilters.push("sharia");
      // Throttle technical scan telemetry to at most once per 5 minutes
      let shouldSendScanEvent = true;
      try {
        const lastScanEvent = Number(sessionStorage.getItem("egx_last_tech_scan_telemetry") || 0);
        if (Date.now() - lastScanEvent < 5 * 60 * 1000) {
          shouldSendScanEvent = false;
        } else {
          sessionStorage.setItem("egx_last_tech_scan_telemetry", String(Date.now()));
        }
      } catch {}

      if (shouldSendScanEvent) {
        void fetch("/api/analytics/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_name: "feature_use",
            path: "/scanner/technical",
            metadata: {
              feature: "tech_scan",
              country: filter.country || "Egypt",
              results_count: next.length,
              scanned_count: res.scanned_count,
              filters: activeFilters.join(",") || "default",
              filter_count: activeFilters.length,
            },
          }),
        }).catch(() => { /* non-critical */ });
      }

    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      if (reqMarket === activeMarketRef.current) {
        setError(err instanceof Error ? err.message : "Scan failed");
      }
    } finally {
      if (abortRef.current === controller) {
        setLoading(false);
        abortRef.current = null;
      }
    }
  }, []);

  const stopTechScan = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setLoading(false);
    }
  }, []);

  // React to global market switching from the Header / Navbar.
  useEffect(() => {
    if (typeof window === "undefined") return;

    const applyMarketSwitch = (nextMarket: ActiveMarket) => {
      if (nextMarket === activeMarketRef.current) return;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
        setLoading(false);
      }
      const prevHasScanned = stateRef.current.hasScanned;
      const onScannerPage = window.location.pathname.startsWith("/scanner/technical");
      activeMarketRef.current = nextMarket;
      setActiveMarket(nextMarket);
      setError(null);

      const restoredForMarket = loadSessionState(nextMarket);
      const nextState: TechScannerState = {
        ...restoredForMarket,
        country: countryForMarket(nextMarket),
        selectedStock: null,
        activeSymbol: null,
        results: [],
        hasScanned: false,
        scannedCount: 0,
        sector: "",
        industry: "",
      };
      stateRef.current = nextState;
      setState(nextState);

      if (prevHasScanned || onScannerPage) {
        void runTechScan({ force: true });
      }
    };

    const handleMarketChange = (event: Event) => {
      const custom = event as CustomEvent<any>;
      const detailMarket = normalizeMarketValue(
        typeof custom?.detail === "string" ? custom.detail : custom?.detail?.market
      );
      applyMarketSwitch(detailMarket ?? readStoredMarket());
    };

    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === MARKET_STORAGE_KEY) {
        applyMarketSwitch(normalizeMarketValue(event.newValue) ?? "egx");
      }
    };

    window.addEventListener(MARKET_CHANGE_EVENT, handleMarketChange);
    window.addEventListener("storage", handleStorageChange);
    return () => {
      window.removeEventListener(MARKET_CHANGE_EVENT, handleMarketChange);
      window.removeEventListener("storage", handleStorageChange);
    };
  }, [runTechScan]);

  useEffect(() => {
    if (!isLoaded) return;
    const expectedCountry = countryForMarket(activeMarket);
    if (stateRef.current.country !== expectedCountry) {
      setTechScanner((prev) => ({ ...prev, country: expectedCountry }));
    }
  }, [activeMarket, state.country, setTechScanner, isLoaded]);

  const value = useMemo<TechnicalScannerContextType>(
    () => ({
      state,
      activeMarket,
      setTechScanner,
      loading,
      error,
      runTechScan,
      stopTechScan,
      clearTechScannerView,
      restoreLastTechScan,
      resetTechScanner,
    }),
    [
      state,
      activeMarket,
      setTechScanner,
      loading,
      error,
      runTechScan,
      stopTechScan,
      clearTechScannerView,
      restoreLastTechScan,
      resetTechScanner,
    ]
  );

  return <TechnicalScannerContext.Provider value={value}>{children}</TechnicalScannerContext.Provider>;
}

export function useTechnicalScanner() {
  const ctx = useContext(TechnicalScannerContext);
  if (!ctx) {
    throw new Error("useTechnicalScanner must be used within a TechnicalScannerProvider");
  }
  return ctx;
}
