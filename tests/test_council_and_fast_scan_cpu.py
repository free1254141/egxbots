import os
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

import api.council as council_mod
import api.routers.scan_ai_fast as scan_mod
import api.update_ml_scores as ml_scores_mod


class _DummyProbaModel:
    def __init__(self, probs):
        self._probs = np.asarray(probs, dtype=float)
        self.calls = 0

    def predict(self, X):
        return (self._probs[: len(X)] >= 0.5).astype(int)

    def predict_proba(self, X):
        self.calls += 1
        p1 = self._probs[: len(X)]
        return np.column_stack([1.0 - p1, p1])


def test_council_evaluate_caches_string_boosters_and_runs_single_pass(monkeypatch):
    build_calls = []

    class FakeBooster:
        def __init__(self, model_str=None):
            build_calls.append(model_str)
            self.predict_calls = 0

        def num_feature(self):
            return 2

        def feature_name(self):
            return ["f1", "f2"]

        def predict(self, X):
            self.predict_calls += 1
            return np.full(len(X), 0.72, dtype=float)

    monkeypatch.setattr(council_mod.lgb, "Booster", FakeBooster)

    council = council_mod.TheCouncil(
        {
            "m_lgb_str": {
                "kind": "lgbm_booster",
                "model_str": "FAKE_LGBM_TREE",
                "feature_names": ["f1", "f2"],
            },
            "m_xgb": {
                "kind": "xgboost",
                "model": _DummyProbaModel([0.80, 0.25]),
                "feature_names": ["f1", "f2"],
            },
        },
        weights={"m_lgb_str": 0.6, "m_xgb": 0.4},
    )

    X = pd.DataFrame({"f1": [1.0, 2.0], "f2": [3.0, 4.0]})

    for _ in range(4):
        scores, votes = council.evaluate(X)
        expected_weighted = 0.6 * 0.72 + 0.4 * 0.80
        assert np.isclose(scores[0], expected_weighted)
        # Second row has xgb=0.25 < 0.50 -> strict agreement overrides consensus to 0.0
        assert scores[1] == 0.0
        assert np.allclose(votes["m_lgb_str"], [0.72, 0.72])
        assert np.allclose(votes["m_xgb"], [0.80, 0.25])

    # Booster parsed from string only once across all 4 evaluations
    assert len(build_calls) == 1
    # Each model evaluated once per council.evaluate() call (4 total, not 8)
    assert council.models["m_xgb"]["model"].calls == 4
    assert np.allclose(council.get_consensus(X), scores)
    assert np.allclose(council.get_detailed_votes(X)["m_xgb"], votes["m_xgb"])


def test_council_evaluate_caches_meta_labeling_reconstruction(monkeypatch):
    reconstruct_calls = 0

    class FakeWrapper:
        def __init__(self):
            self.predict_calls = 0

        def predict_proba(self, X):
            self.predict_calls += 1
            return np.tile([0.3, 0.7], (len(X), 1))

    wrapper = FakeWrapper()

    def fake_reconstruct(artifact):
        nonlocal reconstruct_calls
        reconstruct_calls += 1
        return wrapper

    monkeypatch.setattr(
        "api.backtest_radar.reconstruct_meta_model",
        fake_reconstruct,
    )

    council = council_mod.TheCouncil(
        {"meta_king": {"kind": "meta_labeling_system", "feature_names": ["f1"]}}
    )
    X = pd.DataFrame({"f1": [1.5]})

    s1, v1 = council.evaluate(X)
    s2, v2 = council.evaluate(X)

    assert reconstruct_calls == 1
    assert wrapper.predict_calls == 2
    assert np.isclose(s1[0], 0.7) and np.isclose(s2[0], 0.7)
    assert np.isclose(v1["meta_king"][0], 0.7) and np.isclose(v2["meta_king"][0], 0.7)


def test_process_symbol_return_raw_prob_skips_heavy_post_steps(monkeypatch, capsys):
    dates = pd.date_range("2025-01-01", periods=70, freq="B")
    df = pd.DataFrame(
        {
            "Open": np.full(70, 10.0),
            "High": np.full(70, 10.5),
            "Low": np.full(70, 9.8),
            "Close": np.full(70, 10.2),
            "Volume": np.full(70, 100000.0),
            "f1": np.full(70, 1.0),
        },
        index=dates,
    )

    monkeypatch.setattr(scan_mod, "_is_stock_active", lambda raw, current_date=None: (True, "Active"))
    monkeypatch.setattr(scan_mod, "_get_data_with_indicators_cached", lambda sym, ex, raw, fn: raw.copy())
    monkeypatch.setattr(scan_mod, "_get_massive_features_cached", lambda sym, ex, feat: feat)
    monkeypatch.setattr(scan_mod, "prepare_for_ai", lambda feat, **kwargs: feat)

    def _must_not_run(*args, **kwargs):
        raise AssertionError("Expensive secondary scoring or news lookup ran in return_raw_prob mode")

    monkeypatch.setattr(scan_mod.stock_ai, "_get_latest_news_sentiment", _must_not_run)
    monkeypatch.setattr(scan_mod, "get_distribution_gate", _must_not_run)
    monkeypatch.setattr(scan_mod, "calculate_acceleration_score", _must_not_run)
    monkeypatch.setattr(scan_mod, "calculate_dynamic_risk", _must_not_run)
    monkeypatch.setattr(scan_mod, "get_top_reasons", _must_not_run)

    model = _DummyProbaModel([0.8123])
    out = scan_mod._process_symbol(
        sym="TMGH",
        ex="EGX",
        name="TMG Holding",
        df=df,
        model=model,
        predictors=["f1"],
        min_precision=0.0,
        buy_threshold=0.0,
        return_raw_prob=True,
    )

    captured = capsys.readouterr()
    assert "DEBUG SCAN" not in captured.out
    assert out is not None
    assert out["symbol"] == "TMGH"
    assert np.isclose(out["precision"], 0.8123)
    assert out["last_close"] == 10.2
    assert set(out.keys()) == {"date", "symbol", "exchange", "name", "precision", "last_close", "signal"}


def test_update_all_scores_uses_thread_local_updates(monkeypatch):
    import threading
    import api.stock_ai as stock_ai_mod

    fresh_local = threading.local()
    monkeypatch.setattr(stock_ai_mod, "_supabase_local", fresh_local)
    init_threads = []

    def fake_fast_scan(**kwargs):
        if kwargs["model_name"] == "KING.bin":
            return {"results": [{"symbol": "COMI", "precision": 0.71}, {"symbol": "TMGH", "precision": 0.65}]}
        return {"results": [{"symbol": "COMI", "precision": 0.77}, {"symbol": "SWDY", "precision": 0.54}]}

    monkeypatch.setattr(ml_scores_mod, "fast_scan", fake_fast_scan)

    recorded_updates = []
    record_lock = threading.Lock()

    class FakeQuery:
        def __init__(self, payload=None):
            self.payload = payload
            self.sym = None

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, col, val):
            if col == "symbol":
                self.sym = val
            return self

        def execute(self):
            with record_lock:
                recorded_updates.append((self.sym, self.payload))
            res = MagicMock()
            res.data = [{"symbol": self.sym}]
            return res

    class FakeSupabase:
        def table(self, name):
            assert name == "stock_technical_indicators"
            return FakeQuery()

    def fake_init_supabase(force=False):
        if stock_ai_mod._get_thread_local_supabase() is None or force:
            init_threads.append(threading.get_ident())
            stock_ai_mod._set_thread_local_supabase(FakeSupabase())

    # Route update_ml_scores to the real _get_thread_local_supabase and a thread-local initializer
    monkeypatch.setattr(ml_scores_mod, "_get_thread_local_supabase", stock_ai_mod._get_thread_local_supabase)
    monkeypatch.setattr(ml_scores_mod, "_init_supabase", fake_init_supabase)

    ml_scores_mod.update_all_scores(bulk_cache_ttl_seconds=120)

    assert len(init_threads) >= 2  # Main thread + at least one worker thread initialized independently
    by_sym = dict(recorded_updates)
    assert by_sym == {
        "COMI": {"king_ai_score": 0.71, "egx_ai_score": 0.77},
        "TMGH": {"king_ai_score": 0.65},
        "SWDY": {"egx_ai_score": 0.54},
    }


def test_dockerfile_limits_native_math_threads():
    with open(os.path.join(os.path.dirname(__file__), "..", "Dockerfile"), "r", encoding="utf-8") as fh:
        content = fh.read()
    for var in (
        "OMP_NUM_THREADS=1",
        "OPENBLAS_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "NUMEXPR_NUM_THREADS=1",
        "LOKY_MAX_CPU_COUNT=2",
    ):
        assert var in content


def test_get_supabase_symbols_caches_repeated_search_calls(monkeypatch):
    import api.stock_ai as stock_ai_mod

    stock_ai_mod.clear_supabase_symbols_cache()
    rpc_calls = 0

    class FakeExec:
        def __init__(self, data):
            self.data = data

    class FakeRPC:
        def range(self, a, b):
            return self

        def execute(self):
            nonlocal rpc_calls
            rpc_calls += 1
            return FakeExec([
                {"symbol": "COMI", "exchange": "EGX", "name": "CIB", "country": "Egypt"},
                {"symbol": "TMGH", "exchange": "EGX", "name": "TMG", "country": "Egypt"},
            ])

    class FakeTable:
        def select(self, *args, **kwargs):
            return self

        def eq(self, *args, **kwargs):
            return self

        def range(self, a, b):
            return self

        def execute(self):
            return FakeExec([])

    class FakeSB:
        def rpc(self, name, params):
            return FakeRPC()

        def table(self, name):
            return FakeTable()

    monkeypatch.setattr(stock_ai_mod, "_init_supabase", lambda *a, **k: None)
    monkeypatch.setattr(stock_ai_mod, "supabase", FakeSB())

    first = stock_ai_mod.get_supabase_symbols(country="Egypt")
    second = stock_ai_mod.get_supabase_symbols(country="egypt")
    assert len(first) == 2 and first == second
    assert rpc_calls == 1
    stock_ai_mod.clear_supabase_symbols_cache()


def test_macro_correlation_reuses_preloaded_data(monkeypatch):
    import api.macro_correlation as macro_mod

    monkeypatch.setattr(
        macro_mod,
        "build_or_update_macro_history",
        lambda: (_ for _ in ()).throw(AssertionError("Should reuse caller macro_data")),
    )
    monkeypatch.setattr(
        macro_mod,
        "get_stock_history_from_db",
        lambda sym: (_ for _ in ()).throw(AssertionError("Should reuse caller stock_data")),
    )

    dates = pd.date_range("2026-01-01", periods=35, freq="B").strftime("%Y-%m-%d").tolist()
    macro_data = [
        {"date": d, "usd_official": 49.0 + i * 0.1, "usd_parallel": 50.0 + i * 0.2, "gold_24k": 6000.0 + i * 10}
        for i, d in enumerate(dates)
    ]
    stock_data = [{"date": d, "close": 10.0 + i * 0.5} for i, d in enumerate(dates)]

    res = macro_mod.calculate_macro_correlation("COMI", macro_data=macro_data, stock_data=stock_data)
    assert res["symbol"] == "COMI"
    assert res["corr_usd_parallel"] > 0.99
    assert res["rating"] == "High Protection"


def test_short_swings_persist_sanitizes_non_finite_floats(monkeypatch):
    import json
    import api.short_swings_engine as sse

    captured = {}
    monkeypatch.setattr("api.daily_recovery_state.read_checkpoint", lambda client, key: None)

    def fake_replace(client, key, payload, expected):
        # Strictly verify JSON has zero NaN/Inf tokens (matching Postgres jsonb constraint)
        json.dumps(payload, allow_nan=False)
        captured["payload"] = payload
        return {"payload": payload}

    monkeypatch.setattr("api.daily_recovery_state.replace_checkpoint", fake_replace)

    ok = sse._persist_saved_snapshot(
        object(),
        {
            "as_of": "2026-11-15",
            "computed_at": "2026-11-15T15:00:00+00:00",
            "active_trades": [{"ema10_trend": float("nan"), "return_pct": np.float64(2.5)}],
            "signal_audit": [{"return_20": float("inf"), "liquid": np.bool_(True)}],
        },
    )
    assert ok is True
    assert captured["payload"]["swings"]["active_trades"][0]["ema10_trend"] is None
    assert captured["payload"]["swings"]["active_trades"][0]["return_pct"] == 2.5
    assert captured["payload"]["swings"]["signal_audit"][0]["return_20"] is None
    assert captured["payload"]["swings"]["signal_audit"][0]["liquid"] is True


def test_payment_config_deduplicates_eligibility_queries_per_request(monkeypatch):
    import api.easykash_payments as ek
    import api.payment_common as pc

    calls_50 = 0
    calls_100 = 0

    monkeypatch.setattr(pc, "_init_supabase", lambda *a, **k: None)
    monkeypatch.setattr(ek, "_init_supabase", lambda *a, **k: None)

    class FakeExec:
        def __init__(self, data=None, count=0):
            self.data = data if data is not None else []
            self.count = count

    class FakeTable:
        def __init__(self, name):
            self.name = name

        def select(self, *a, **k):
            return self

        def eq(self, col, val):
            nonlocal calls_50, calls_100
            if self.name == "founders_offer_members" and col == "user_id":
                calls_100 += 1
            return self

        def lt(self, col, val):
            nonlocal calls_50
            if self.name == "founders_offer_members" and col == "joined_at":
                calls_50 += 1
            return self

        def in_(self, *a, **k):
            return self

        def lte(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            return FakeExec(data=[], count=2)

    class FakeSB:
        def table(self, name):
            return FakeTable(name)

    fake_sb = FakeSB()
    monkeypatch.setattr(pc, "supabase", fake_sb)
    monkeypatch.setattr(ek, "supabase", fake_sb)
    monkeypatch.setattr(ek, "_get_thread_local_supabase", lambda: fake_sb)

    cfg = ek.payment_config(user_id="user-dedup-test")
    assert cfg["provider"] == "easykash"
    # Even though plan_amount_egp + payment_config check eligibility multiple times,
    # eligibility_scope ensures the 50 EGP & 100 EGP DB checks each execute only ONCE per request.
    assert calls_50 == 1
    assert calls_100 == 2  # once from lt/eq in 50 EGP check + once in 100 EGP check

