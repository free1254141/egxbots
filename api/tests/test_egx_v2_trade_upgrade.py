"""Unit tests for the EGX v2 stationary model promotion and trade-quality gates."""

import os
import numpy as np
import pandas as pd


def _synthetic_egx_ohlcv(n_bars: int = 160, downtrend: bool = False) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-11-24", periods=n_bars)
    if downtrend:
        close = np.linspace(50.0, 32.0, n_bars)
    else:
        close = np.linspace(30.0, 50.0, n_bars)
    return pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.015,
            "Low": close * 0.985,
            "Close": close,
            "Volume": np.full(n_bars, 1_500_000.0),
        },
        index=dates,
    )


def test_promoted_egx_models_load_with_stationary_calibration():
    from api.routers.scan_ai_fast import _load_model

    for fname in ("model_EGX.bin", "KING.bin"):
        model, predictors, is_lgbm = _load_model(fname, return_raw_prob=False)
        assert is_lgbm is True
        assert predictors and len(predictors) > 20
        assert getattr(model, "feature_preset", None) == "stationary"
        opt_th = getattr(model, "optimal_threshold", None)
        assert isinstance(opt_th, float) and 0.30 < opt_th < 0.55


def test_process_symbol_scores_stationary_features_and_rejects_downtrend(monkeypatch):
    from api.routers import scan_ai_fast as saf

    model, predictors, _ = saf._load_model("model_EGX.bin", return_raw_prob=False)
    monkeypatch.setattr(saf.stock_ai, "_get_latest_news_sentiment", lambda sym: {"negative_flag": 0, "news_count": 0})

    # Verify model scores cleanly with stationary features & category alignment (raw mode bypasses quality gate)
    up_df = _synthetic_egx_ohlcv(160, downtrend=False)
    res_raw = saf._process_symbol(
        sym="COMI",
        ex="EGX",
        name="CIB",
        df=up_df,
        model=model,
        predictors=predictors,
        min_precision=0.35,
        buy_threshold=0.0,
        fundamentals_map={"COMI": {"sector": "Banks"}},
        return_raw_prob=True,
    )
    assert res_raw is not None
    assert 0.0 <= res_raw["precision"] <= 1.0

    # Falling knife downtrend (EMA_50_Ratio <= 0) must ALWAYS be rejected in live BUY scan mode
    down_df = _synthetic_egx_ohlcv(160, downtrend=True)
    res_down = saf._process_symbol(
        sym="DOWN",
        ex="EGX",
        name="Falling Co",
        df=down_df,
        model=model,
        predictors=predictors,
        min_precision=0.01,
        buy_threshold=0.01,
        fundamentals_map={"DOWN": {"sector": "Banks"}},
        return_raw_prob=False,
    )
    assert res_down is None


def test_sync_manifest_includes_promoted_egx_models():
    import scripts.sync_to_hf_space as sync_mod

    manifest = set(sync_mod.FILES_TO_SYNC)
    for req in (
        "api/models/model_EGX.bin",
        "api/models/model_EGX.pkl.model_card.json",
        "api/models/KING.bin",
        "api/models/KING.pkl.model_card.json",
    ):
        assert req in manifest, f"Missing {req} in FILES_TO_SYNC"
        assert os.path.exists(os.path.join(os.path.dirname(os.path.dirname(sync_mod.__file__)), req))


def test_consensus_ratio_uses_calibrated_threshold_and_no_perf_warning(monkeypatch):
    """Consensus ratio uses calibrated model optimal_threshold instead of hardcoded 0.55 and avoids PerformanceWarning."""
    import warnings
    from api.routers import scan_ai_fast as saf

    model, predictors, _ = saf._load_model("model_EGX.bin", return_raw_prob=False)
    monkeypatch.setattr(saf.stock_ai, "_get_latest_news_sentiment", lambda sym: {"negative_flag": 0, "news_count": 0})

    class _FakeVoter:
        def __init__(self, optimal_threshold):
            self.optimal_threshold = optimal_threshold

    class _FakeCouncil:
        def __init__(self):
            self.models = {
                "model_EGX.bin": _FakeVoter(0.391),
                "KING.bin": _FakeVoter(0.332),
            }

        def evaluate(self, df):
            return np.array([0.42]), {
                "model_EGX.bin": np.array([0.41]),
                "KING.bin": np.array([0.36]),
            }

    up_df = _synthetic_egx_ohlcv(160, downtrend=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", pd.errors.PerformanceWarning)
        res = saf._process_symbol(
            sym="COMI",
            ex="EGX",
            name="CIB",
            df=up_df,
            model=model,
            predictors=predictors,
            min_precision=0.35,
            buy_threshold=0.0,
            fundamentals_map={"COMI": {"sector": "Banks"}},
            council=_FakeCouncil(),
            return_raw_prob=False,
        )
    perf_warnings = [w for w in caught if issubclass(w.category, pd.errors.PerformanceWarning)]
    assert perf_warnings == []
    assert res is not None
    assert res["consensus_ratio"] == "2/2"
