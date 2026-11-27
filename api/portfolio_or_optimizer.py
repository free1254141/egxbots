"""Operations Research (OR) Portfolio Optimization & Constrained Selection Engine.

Pure-NumPy quantitative optimization module with zero extra runtime dependencies
and sub-5ms execution on Hugging Face Spaces (2 vCPU):

1. Covariance Estimation: Ledoit-Wolf–style shrinkage toward a diagonal volatility
   target from bounded historical daily returns (with ATR/volatility fallback for
   thinly traded or newly listed stocks).
2. Convex Portfolio Optimization (4 OR objectives):
   - ``balanced``: Mean-Variance utility with turnover (L1/Huber) regularization.
   - ``min_risk``: Global Minimum Variance (GMV).
   - ``risk_parity``: Equal Risk Contribution (ERC).
   - ``max_diversification``: Maximum Diversification Ratio.
3. Hard Linear Constraints via Dykstra's Alternating Projections:
   - Budget simplex (invested_weight = 1 - min_cash_weight, w >= 0)
   - Per-stock box caps (0 <= w_i <= max_weight)
   - Per-sector caps (sum_{i in sector} w_i <= max_sector_weight)
   With automatic feasibility relaxation when user constraints are mathematically
   impossible (e.g. 2 stocks with max_weight=30%, or all stocks in one sector).
4. Integer Share Knapsack & Transaction Cost Optimizer:
   - Converts continuous target weights into integer share counts minimizing
     tracking error under capital budget and estimating market brokerage fees.
5. Constrained Diversified Candidate Selection:
   - Sector-capped & correlation-capped Top-K selection for rebalance candidates
     and daily signal diversification.

Note: Strictly quantitative mathematical optimization tooling for research and
risk analysis — not personalized investment advice or return guarantees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

TRADING_DAYS_PER_YEAR = 252.0
DEFAULT_ANNUAL_VOL = 0.35

# Approximate all-in retail brokerage + exchange fees per market (one-way)
MARKET_FEE_RATES: Dict[str, float] = {
    "EGX": 0.0018,    # ~0.18% (brokerage + EGX/MCDR/FRA stamps)
    "TASI": 0.00155,  # 0.155% Saudi Tadawul standard base
    "TADAWUL": 0.00155,
    "DFM": 0.00275,   # ~0.275% Dubai Financial Market
    "ADX": 0.00275,   # ~0.275% Abu Dhabi Securities Exchange
    "UAE": 0.00275,
    "QSE": 0.00275,   # ~0.275% Qatar Stock Exchange
    "QATAR": 0.00275,
}

OBJECTIVE_LABELS_AR: Dict[str, str] = {
    "balanced": "متوازن (عائد معدّل بالمخاطرة + تنويع)",
    "min_risk": "أقل مخاطرة وتذبذب (Global Minimum Variance)",
    "risk_parity": "توزيع متكافئ للمخاطرة (Risk Parity)",
    "max_diversification": "أقصى تنويع ممكن (Max Diversification)",
    "hrp": "توزيع مخاطر هرمي صامد للتقلبات (Hierarchical Risk Parity)",
}


@dataclass
class AssetInput:
    symbol: str
    price: float
    name_ar: str = ""
    sector: str = "أخرى"
    current_shares: float = 0.0
    expected_score: float = 0.0  # Bounded quantitative score in [-1, 1]
    fallback_daily_vol: float = 0.022  # ~35% annualized fallback if history sparse
    returns_by_date: Dict[str, float] = field(default_factory=dict)
    max_weight_override: Optional[float] = None  # Per-asset hard cap (0.0 excludes from buying)
    exclusion_reason: Optional[str] = None
    avg_daily_volume: Optional[float] = None


def normalize_objective(raw: Optional[str]) -> str:
    clean = str(raw or "balanced").strip().lower().replace("-", "_").replace(" ", "_")
    if clean in {"min_risk", "min_vol", "min_variance", "gmv", "low_risk", "conservative", "defensive"}:
        return "min_risk"
    if clean in {"risk_parity", "erc", "equal_risk"}:
        return "risk_parity"
    if clean in {"max_diversification", "max_div", "diversified", "diversification"}:
        return "max_diversification"
    if clean in {"hrp", "hierarchical", "hierarchical_risk_parity", "crash_resistant"}:
        return "hrp"
    return "balanced"


def market_fee_rate(exchange: str) -> float:
    return MARKET_FEE_RATES.get(str(exchange or "EGX").strip().upper(), 0.002)


def compute_returns_by_date(price_rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Build {symbol: {date: daily_return}} from compact price rows (symbol, date, close)."""
    series: Dict[str, List[Tuple[str, float]]] = {}
    for row in price_rows or []:
        sym = str(row.get("symbol") or "").strip().upper()
        dt_str = str(row.get("date") or "").strip()[:10]
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if not sym or not dt_str or not math.isfinite(close) or close <= 0:
            continue
        series.setdefault(sym, []).append((dt_str, close))

    out: Dict[str, Dict[str, float]] = {}
    for sym, pts in series.items():
        pts.sort(key=lambda x: x[0])
        # Deduplicate dates keeping the latest entry
        dedup: List[Tuple[str, float]] = []
        for d, c in pts:
            if dedup and dedup[-1][0] == d:
                dedup[-1] = (d, c)
            else:
                dedup.append((d, c))
        # Rebase pre-split prices backward whenever an unadjusted split jump (>55% drop) occurs
        adj_closes = [c for _, c in dedup]
        for i in range(1, len(adj_closes)):
            prev_raw = adj_closes[i - 1]
            cur_raw = adj_closes[i]
            if prev_raw > 0 and cur_raw > 0:
                sp_ratio = cur_raw / prev_raw
                if sp_ratio < 0.45:
                    adj_closes[:i] = [v * sp_ratio for v in adj_closes[:i]]

        rets: Dict[str, float] = {}
        for i in range(1, len(dedup)):
            prev_c = adj_closes[i - 1]
            cur_c = adj_closes[i]
            if prev_c > 0:
                r = (cur_c - prev_c) / prev_c
                # Winsorize extreme outliers (> +/-25% single day)
                r = max(-0.25, min(0.25, r))
                rets[dedup[i][0]] = r
        out[sym] = rets
    return out


def estimate_covariance_matrix(assets: Sequence[AssetInput]) -> Tuple[np.ndarray, np.ndarray, int]:
    """Estimate positive-definite annualized covariance & correlation matrices.

    Uses Ledoit-Wolf–style shrinkage toward a diagonal variance target so small
    sample sizes or partially overlapping histories stay well-conditioned.
    Returns: (cov_annual, corr_matrix, common_dates_count).
    """
    n = len(assets)
    if n == 0:
        return np.zeros((0, 0), dtype=float), np.zeros((0, 0), dtype=float), 0

    # Individual daily variance estimates (with fallback)
    daily_vols = np.zeros(n, dtype=float)
    for i, a in enumerate(assets):
        vals = list(a.returns_by_date.values())
        if len(vals) >= 12:
            s = float(np.std(vals, ddof=1))
            daily_vols[i] = max(0.005, min(0.10, s)) if math.isfinite(s) and s > 0 else max(0.008, a.fallback_daily_vol)
        else:
            daily_vols[i] = max(0.008, min(0.08, a.fallback_daily_vol))

    if n == 1:
        var_ann = (daily_vols[0] ** 2) * TRADING_DAYS_PER_YEAR
        return np.array([[var_ann]], dtype=float), np.array([[1.0]], dtype=float), len(assets[0].returns_by_date)

    # Pairwise correlation matrix across overlapping dates (handles staggered listings cleanly)
    corr = np.eye(n, dtype=float)
    min_overlap = 999999
    has_any_overlap = False
    for i in range(n):
        ri = assets[i].returns_by_date
        for j in range(i + 1, n):
            rj = assets[j].returns_by_date
            common = sorted(set(ri.keys()) & set(rj.keys()))
            m = len(common)
            if m >= 15:
                has_any_overlap = True
                min_overlap = min(min_overlap, m)
                xi = np.array([ri[d] for d in common], dtype=float)
                xj = np.array([rj[d] for d in common], dtype=float)
                si = float(np.std(xi, ddof=1))
                sj = float(np.std(xj, ddof=1))
                if si > 1e-9 and sj > 1e-9:
                    raw_c = float(np.corrcoef(xi, xj)[0, 1])
                    if math.isfinite(raw_c):
                        # Shrink pairwise correlation toward 0.15 prior based on sample length
                        shrink = min(0.65, max(0.15, 20.0 / (m + 20.0)))
                        c_val = (1.0 - shrink) * raw_c + shrink * 0.15
                        c_val = max(-0.85, min(0.92, c_val))
                        corr[i, j] = c_val
                        corr[j, i] = c_val
            else:
                # Weak prior correlation: slightly higher if same sector
                prior = 0.35 if (assets[i].sector and assets[i].sector == assets[j].sector and assets[i].sector != "أخرى") else 0.12
                corr[i, j] = prior
                corr[j, i] = prior

    common_dates = min_overlap if has_any_overlap and min_overlap < 999999 else 0

    # Ensure PSD via eigenvalue clipping on correlation matrix
    eigvals, eigvecs = np.linalg.eigh(corr)
    eigvals = np.maximum(eigvals, 0.05)
    corr_psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    d_inv = 1.0 / np.sqrt(np.maximum(np.diag(corr_psd), 1e-12))
    corr_psd = corr_psd * np.outer(d_inv, d_inv)
    np.fill_diagonal(corr_psd, 1.0)

    ann_vols = daily_vols * math.sqrt(TRADING_DAYS_PER_YEAR)
    cov_annual = corr_psd * np.outer(ann_vols, ann_vols)
    # Symmetrize & add tiny ridge for strict positive definiteness
    cov_annual = 0.5 * (cov_annual + cov_annual.T) + np.eye(n) * 1e-6
    return cov_annual, corr_psd, common_dates


def _project_capped_simplex(v: np.ndarray, total: float, cap: Any) -> np.ndarray:
    """Exact Euclidean projection onto {w : sum(w) = total, 0 <= w_i <= u_i} via bisection."""
    n = len(v)
    if n == 0 or total <= 0:
        return np.zeros(n, dtype=float)
    if isinstance(cap, (np.ndarray, list, tuple)):
        ub = np.maximum(0.0, np.asarray(cap, dtype=float))
        if float(np.sum(ub)) < total - 1e-9:
            ub = np.maximum(ub, total / n + 1e-12)
    else:
        eff_cap = max(float(cap), total / n + 1e-12)
        ub = np.full(n, eff_cap, dtype=float)
    lo = float(np.min(v - ub)) - 1.0
    hi = float(np.max(v)) + 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        w = np.clip(v - mid, 0.0, ub)
        if float(np.sum(w)) > total:
            lo = mid
        else:
            hi = mid
    w = np.clip(v - 0.5 * (lo + hi), 0.0, ub)
    s = float(np.sum(w))
    if s > 1e-12:
        w *= total / s
    return w


def _resolve_feasible_caps(
    sectors: Sequence[str],
    invested_total: float,
    max_weight: float,
    max_sector_weight: float,
) -> Tuple[float, float, List[str]]:
    """Ensure box and sector caps admit a non-empty feasible set; note any relaxations."""
    n = len(sectors)
    notes: List[str] = []
    if n == 0 or invested_total <= 0:
        return max_weight, max_sector_weight, notes

    eff_max_w = max(0.01, min(1.0, float(max_weight)))
    min_feasible_w = invested_total / n
    if eff_max_w + 1e-9 < min_feasible_w:
        eff_max_w = min(1.0, min_feasible_w)
        notes.append(
            f"تم رفع الحد الأقصى للسهم تلقائياً إلى {round(eff_max_w * 100, 1)}% لأن عدد الأسهم ({n}) لا يكفي للوصول إلى {round(invested_total * 100, 1)}% تحت الحد المطلوب."
        )

    eff_max_sec = max(eff_max_w, min(1.0, float(max_sector_weight)))
    sector_counts: Dict[str, int] = {}
    for sec in sectors:
        key = sec or "أخرى"
        sector_counts[key] = sector_counts.get(key, 0) + 1

    def _max_capacity(sec_cap: float) -> float:
        return sum(min(cnt * eff_max_w, sec_cap) for cnt in sector_counts.values())

    if _max_capacity(eff_max_sec) + 1e-9 < invested_total:
        # Bisect minimum feasible sector cap
        lo, hi = eff_max_sec, 1.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if _max_capacity(mid) < invested_total:
                lo = mid
            else:
                hi = mid
        eff_max_sec = min(1.0, hi + 1e-6)
        notes.append(
            f"تم تخفيف قيد القطاع تلقائياً إلى {round(eff_max_sec * 100, 1)}% بسبب تركز الأسهم المختارة في عدد محدود من القطاعات ({len(sector_counts)})."
        )

    return eff_max_w, eff_max_sec, notes


def project_onto_portfolio_constraints(
    v: np.ndarray,
    sectors: Sequence[str],
    invested_total: float,
    max_weight: float,
    max_sector_weight: float,
    iters: int = 35,
    upper_bounds: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Dykstra's alternating projections onto simplex + box + per-sector cap constraints."""
    n = len(v)
    if n == 0 or invested_total <= 0:
        return np.zeros(n, dtype=float)

    ub = (
        np.maximum(0.0, np.asarray(upper_bounds, dtype=float))
        if upper_bounds is not None and len(upper_bounds) == n
        else np.full(n, float(max_weight), dtype=float)
    )
    if float(np.sum(ub)) < invested_total - 1e-6:
        ub = np.full(n, max(float(max_weight), invested_total / n + 1e-12), dtype=float)

    sector_groups: Dict[str, List[int]] = {}
    for idx, sec in enumerate(sectors):
        sector_groups.setdefault(sec or "أخرى", []).append(idx)

    # Fast path if single-asset sectors or sector cap >= invested_total
    if max_sector_weight >= invested_total - 1e-9 or all(len(idxs) == 1 for idxs in sector_groups.values()):
        return _project_capped_simplex(v, invested_total, ub)

    x = _project_capped_simplex(v, invested_total, ub)
    p_simplex = np.zeros(n, dtype=float)
    p_sectors = {sec: np.zeros(len(idxs), dtype=float) for sec, idxs in sector_groups.items()}

    for _ in range(iters):
        prev = x.copy()
        # Project onto each sector halfspace: sum_{i in sec} x_i <= max_sector_weight
        for sec, idxs in sector_groups.items():
            sub = x[idxs] + p_sectors[sec]
            sec_sum = float(np.sum(sub))
            if sec_sum > max_sector_weight:
                excess = (sec_sum - max_sector_weight) / len(idxs)
                proj_sub = np.maximum(0.0, sub - excess)
                # Ensure sum <= max_sector_weight after non-negativity clip
                s2 = float(np.sum(proj_sub))
                if s2 > max_sector_weight and s2 > 1e-12:
                    proj_sub *= max_sector_weight / s2
            else:
                proj_sub = np.maximum(0.0, sub)
            p_sectors[sec] = sub - proj_sub
            x[idxs] = proj_sub

        # Project onto capped simplex
        y = x + p_simplex
        x = _project_capped_simplex(y, invested_total, ub)
        p_simplex = y - x

        if float(np.max(np.abs(x - prev))) < 1e-7:
            break

    # Final hard-repair pass so constraints hold to floating-point precision
    x = np.clip(x, 0.0, ub)
    for _ in range(10):
        violated = False
        for sec, idxs in sector_groups.items():
            s = float(np.sum(x[idxs]))
            if s > max_sector_weight + 1e-7:
                violated = True
                x[idxs] *= max_sector_weight / s
        deficit = invested_total - float(np.sum(x))
        if abs(deficit) < 1e-7 and not violated:
            break
        if deficit > 1e-7:
            # Distribute deficit to stocks with headroom in both box and sector
            headroom = np.zeros(n, dtype=float)
            for sec, idxs in sector_groups.items():
                sec_rem = max(0.0, max_sector_weight - float(np.sum(x[idxs])))
                if sec_rem <= 1e-9:
                    continue
                box_rems = np.maximum(0.0, ub[idxs] - x[idxs])
                tot_box = float(np.sum(box_rems))
                if tot_box > 1e-9:
                    headroom[idxs] = box_rems * min(1.0, sec_rem / tot_box)
            tot_h = float(np.sum(headroom))
            if tot_h > 1e-9:
                x += headroom * min(1.0, deficit / tot_h)
            else:
                break
        elif deficit < -1e-7:
            s = float(np.sum(x))
            if s > 1e-9:
                x *= invested_total / s
    return x


def _compute_hrp_weights(cov: np.ndarray, eligible_mask: np.ndarray) -> np.ndarray:
    """Pure-NumPy Hierarchical Risk Parity (single-linkage clustering + recursive bisection)."""
    n = int(cov.shape[0])
    elig = [i for i in range(n) if bool(eligible_mask[i])]
    out = np.zeros(n, dtype=float)
    if not elig:
        return out
    if len(elig) == 1:
        out[elig[0]] = 1.0
        return out

    sub_cov = np.asarray(cov[np.ix_(elig, elig)], dtype=float)
    m = len(elig)
    diag = np.maximum(np.diag(sub_cov), 1e-10)
    vols = np.sqrt(diag)
    corr = np.clip(sub_cov / np.outer(vols, vols), -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, 1.0))

    nodes: List[Tuple[Any, List[int]]] = [(i, [i]) for i in range(m)]
    while len(nodes) > 1:
        best_d = float("inf")
        best_pair = (0, 1)
        k_len = len(nodes)
        for a in range(k_len):
            leaves_a = nodes[a][1]
            for b in range(a + 1, k_len):
                leaves_b = nodes[b][1]
                d_ab = float(np.min(dist[np.ix_(leaves_a, leaves_b)]))
                if d_ab < best_d:
                    best_d = d_ab
                    best_pair = (a, b)
        i_a, i_b = best_pair
        node_a, leaves_a = nodes[i_a]
        node_b, leaves_b = nodes[i_b]
        nodes.pop(i_b)
        nodes.pop(i_a)
        nodes.append(((node_a, node_b), leaves_a + leaves_b))

    def _seriate(node: Any) -> List[int]:
        if isinstance(node, int):
            return [node]
        return _seriate(node[0]) + _seriate(node[1])

    sort_ix = _seriate(nodes[0][0])

    def _cluster_var(cluster_indices: List[int]) -> float:
        c_cov = sub_cov[np.ix_(cluster_indices, cluster_indices)]
        c_diag = np.maximum(np.diag(c_cov), 1e-10)
        ivp = 1.0 / c_diag
        ivp /= float(np.sum(ivp))
        return float(max(1e-12, ivp @ c_cov @ ivp))

    w_sub = np.ones(m, dtype=float)
    clusters_q: List[List[int]] = [sort_ix]
    while clusters_q:
        next_q: List[List[int]] = []
        for cl in clusters_q:
            if len(cl) <= 1:
                continue
            mid = len(cl) // 2
            left_c = cl[:mid]
            right_c = cl[mid:]
            v_left = _cluster_var(left_c)
            v_right = _cluster_var(right_c)
            alpha = 1.0 - (v_left / max(v_left + v_right, 1e-12))
            w_sub[left_c] *= alpha
            w_sub[right_c] *= (1.0 - alpha)
            if len(left_c) > 1:
                next_q.append(left_c)
            if len(right_c) > 1:
                next_q.append(right_c)
        clusters_q = next_q

    total_sub = float(np.sum(w_sub))
    if total_sub > 1e-12:
        w_sub /= total_sub
    else:
        w_sub = np.full(m, 1.0 / m, dtype=float)
    for local_i, orig_i in enumerate(elig):
        out[orig_i] = float(w_sub[local_i])
    return out


def solve_optimal_weights(
    assets: Sequence[AssetInput],
    cov: np.ndarray,
    objective: str = "balanced",
    max_weight: float = 0.35,
    max_sector_weight: float = 0.45,
    min_cash_weight: float = 0.0,
    current_weights: Optional[np.ndarray] = None,
    turnover_penalty: float = 0.0,
) -> Tuple[np.ndarray, float, float, List[str]]:
    """Solve constrained Operations Research portfolio optimization problem."""
    n = len(assets)
    invested_total = max(0.0, min(1.0, 1.0 - max(0.0, min(0.95, float(min_cash_weight)))))
    if n == 0 or invested_total <= 0:
        return np.zeros(n, dtype=float), max_weight, max_sector_weight, []

    sectors = [a.sector or "أخرى" for a in assets]
    eligible_idx = [
        i for i, a in enumerate(assets)
        if a.max_weight_override is None or float(a.max_weight_override) > 1e-6
    ]
    if 2 <= len(eligible_idx) < n:
        eff_max_w, eff_max_sec, notes = _resolve_feasible_caps(
            [sectors[i] for i in eligible_idx], invested_total, max_weight, max_sector_weight
        )
    else:
        eff_max_w, eff_max_sec, notes = _resolve_feasible_caps(sectors, invested_total, max_weight, max_sector_weight)

    ub = np.array(
        [
            eff_max_w if a.max_weight_override is None else max(0.0, min(eff_max_w, float(a.max_weight_override)))
            for a in assets
        ],
        dtype=float,
    )
    has_explicit_overrides = any(a.max_weight_override is not None for a in assets)
    if float(np.sum(ub)) < invested_total - 1e-6:
        if has_explicit_overrides:
            # Never override safety exclusions or no-buy downtrend caps!
            # Absorb unallocated weight into Cash Reserve for healthier future opportunities.
            invested_total = max(0.0, float(np.sum(ub)))
            cash_res_pct = round((1.0 - invested_total) * 100.0, 1)
            notes.append(
                f"تم الاحتفاظ بـ {cash_res_pct:.1f}% كاش احتياطي للفرص البديلة بدلاً من إجبار المحفظة على الشراء في أسهم مستبعدة أو في مسار هابط."
            )
            if invested_total <= 1e-9:
                return np.zeros(n, dtype=float), eff_max_w, eff_max_sec, notes
        else:
            ub = np.where(ub > 1e-9, eff_max_w, 0.0)
            if float(np.sum(ub)) < invested_total - 1e-6:
                ub = np.full(n, eff_max_w, dtype=float)

    if n == 1:
        return np.array([min(invested_total, float(ub[0]))], dtype=float), eff_max_w, eff_max_sec, notes

    obj = normalize_objective(objective)
    if obj == "hrp":
        hrp_raw = _compute_hrp_weights(cov, ub > 1e-6)
        hrp_sum = float(np.sum(hrp_raw))
        if hrp_sum <= 1e-9:
            hrp_raw = np.where(ub > 1e-6, 1.0, 0.0)
            hrp_sum = max(float(np.sum(hrp_raw)), 1.0)
        hrp_w = project_onto_portfolio_constraints(
            hrp_raw * (invested_total / hrp_sum),
            sectors,
            invested_total,
            eff_max_w,
            eff_max_sec,
            iters=40,
            upper_bounds=ub,
        )
        hrp_w = np.where((hrp_w < 1e-4) | (ub <= 1e-9), 0.0, hrp_w)
        if float(np.sum(hrp_w)) > 1e-9:
            hrp_w = project_onto_portfolio_constraints(
                hrp_w, sectors, invested_total, eff_max_w, eff_max_sec, iters=30, upper_bounds=ub
            )
        hrp_w = np.where(ub <= 1e-9, 0.0, hrp_w)
        return hrp_w, eff_max_w, eff_max_sec, notes
    vols = np.sqrt(np.maximum(np.diag(cov), 1e-8))
    # Initial feasible point: inverse-volatility weights on eligible assets projected onto constraints
    inv_vol = np.where(ub > 1e-6, 1.0 / np.maximum(vols, 1e-4), 0.0)
    inv_sum = float(np.sum(inv_vol))
    if inv_sum <= 1e-9:
        inv_vol = 1.0 / np.maximum(vols, 1e-4)
        inv_sum = float(np.sum(inv_vol))
    w = project_onto_portfolio_constraints(
        inv_vol * (invested_total / max(inv_sum, 1e-12)),
        sectors,
        invested_total,
        eff_max_w,
        eff_max_sec,
        upper_bounds=ub,
    )

    # Quantitative expected-return proxy (conservatively scaled: [-8%, +14%] annualized)
    def _safe_score(val: Any) -> float:
        try:
            f = float(val)
            return f if math.isfinite(f) else 0.0
        except (TypeError, ValueError):
            return 0.0

    mu = np.array([max(-0.08, min(0.14, _safe_score(a.expected_score) * 0.12)) for a in assets], dtype=float)
    w_curr = np.asarray(current_weights, dtype=float) if current_weights is not None and len(current_weights) == n else None
    gamma = max(0.0, float(turnover_penalty))

    def _turnover_grad(vec: np.ndarray) -> np.ndarray:
        if w_curr is None or gamma <= 0:
            return np.zeros(n, dtype=float)
        diff = vec - w_curr
        # Smooth L1 (Huber) gradient with delta=0.01 for fast convergence
        delta = 0.01
        return gamma * np.clip(diff / delta, -1.0, 1.0)

    def _objective_val(vec: np.ndarray) -> float:
        var = float(vec @ cov @ vec)
        pen = float(gamma * np.sum(np.abs(vec - w_curr))) if (w_curr is not None and gamma > 0) else 0.0
        if obj == "min_risk":
            return 0.5 * var + pen
        if obj == "risk_parity":
            if var <= 1e-12:
                return 0.0
            rc = vec * (cov @ vec)
            target = var / n
            return float(np.sum((rc - target) ** 2)) / (var * var) + pen
        if obj == "max_diversification":
            vol = math.sqrt(max(var, 1e-12))
            dr = float(vec @ vols) / vol
            return -dr + pen
        # balanced: Mean-Variance utility (risk aversion ~ 2.5)
        return 1.25 * var - float(mu @ vec) + pen

    def _gradient(vec: np.ndarray) -> np.ndarray:
        cov_w = cov @ vec
        t_grad = _turnover_grad(vec)
        if obj == "min_risk":
            return cov_w + t_grad
        if obj == "risk_parity":
            var = float(vec @ cov_w)
            if var <= 1e-12:
                return t_grad
            rc = vec * cov_w
            target = var / n
            diff = rc - target
            # Exact quotient-rule gradient of sum((rc_i - var/n)^2) / var^2:
            # d(sum(diff^2))/dw = 2 * (cov_w * diff + cov @ (vec * diff)), since sum(diff) == 0;
            # d(1/var^2)/dw = -4 * cov_w / var^3
            g_num = 2.0 * (cov_w * diff + cov @ (vec * diff))
            g_den = (4.0 * float(np.sum(diff ** 2)) / (var ** 3)) * cov_w
            return (g_num / (var * var)) - g_den + t_grad
        if obj == "max_diversification":
            var = max(float(vec @ cov_w), 1e-12)
            vol = math.sqrt(var)
            num = float(vec @ vols)
            # d(-num/vol)/dw = -(vols * vol - num * (cov_w / vol)) / var
            return -(vols / vol - (num / (var * vol)) * cov_w) + t_grad
        # balanced
        return 2.5 * cov_w - mu + t_grad

    # Projected Gradient Descent with Armijo backtracking line search (guaranteed monotonic descent)
    best_w = w.copy()
    best_val = _objective_val(w)
    step = 0.5
    for _ in range(120):
        g = _gradient(w)
        g_norm = float(np.linalg.norm(g))
        if not math.isfinite(g_norm) or g_norm < 1e-9:
            break
        cur_val = _objective_val(w)
        accepted = False
        s = step
        for _bt in range(12):
            cand = project_onto_portfolio_constraints(
                w - s * g,
                sectors,
                invested_total,
                eff_max_w,
                eff_max_sec,
                iters=25,
                upper_bounds=ub,
            )
            cand_val = _objective_val(cand)
            if math.isfinite(cand_val) and cand_val <= cur_val - 1e-10:
                w = cand
                if cand_val < best_val:
                    best_val = cand_val
                    best_w = cand.copy()
                step = min(1.5, s * 1.25)
                accepted = True
                break
            s *= 0.45
        if not accepted:
            break

    # Clean tiny dust weights (< 0.1%) and strictly enforce per-asset caps
    best_w = np.where((best_w < 1e-4) | (ub <= 1e-9), 0.0, best_w)
    if float(np.sum(best_w)) > 1e-9:
        best_w = project_onto_portfolio_constraints(
            best_w, sectors, invested_total, eff_max_w, eff_max_sec, iters=30, upper_bounds=ub
        )
    best_w = np.where(ub <= 1e-9, 0.0, best_w)
    return best_w, eff_max_w, eff_max_sec, notes


def allocate_integer_shares(
    assets: Sequence[AssetInput],
    target_weights: np.ndarray,
    total_capital: float,
    min_cash_weight: float = 0.0,
    max_weight: float = 1.0,
    max_sector_weight: float = 1.0,
) -> Tuple[List[int], float]:
    """Integer Knapsack share allocator minimizing tracking error under budget & caps.

    Returns: (shares_list, remaining_cash).
    """
    n = len(assets)
    if n == 0 or total_capital <= 0:
        return [0] * n, max(0.0, float(total_capital))

    investable_budget = max(0.0, float(total_capital) * (1.0 - max(0.0, min(0.95, float(min_cash_weight)))))
    prices = [max(0.01, float(a.price)) for a in assets]
    target_vals = [max(0.0, float(target_weights[i]) * total_capital) for i in range(n)]

    # Step 1: Floor allocation
    shares = [int(math.floor(target_vals[i] / prices[i])) for i in range(n)]
    spent = sum(shares[i] * prices[i] for i in range(n))
    # Guard against floating overshoot
    while spent > investable_budget + 1e-6:
        # Remove 1 share from the most over-weight holding
        worst = max(range(n), key=lambda i: (shares[i] * prices[i] - target_vals[i]) if shares[i] > 0 else -1e18)
        if shares[worst] <= 0:
            break
        shares[worst] -= 1
        spent -= prices[worst]

    remaining = max(0.0, investable_budget - spent)

    # Step 2: Greedy marginal tracking-error improvement (Integer Knapsack fill)
    sector_map = [a.sector or "أخرى" for a in assets]
    for _ in range(5000):
        best_idx = -1
        best_gain = 1e-9
        sec_vals: Dict[str, float] = {}
        for i in range(n):
            sec_vals[sector_map[i]] = sec_vals.get(sector_map[i], 0.0) + shares[i] * prices[i]

        for i in range(n):
            p = prices[i]
            if p > remaining + 1e-9 or target_vals[i] <= 0 or (
                assets[i].max_weight_override is not None and assets[i].max_weight_override <= 0.0
            ):
                continue
            cur_v = shares[i] * p
            new_v = cur_v + p
            # Respect hard stock, override & sector caps (never exceed explicit max_weight_override)
            eff_cap_i = (
                min(max_weight, float(assets[i].max_weight_override))
                if assets[i].max_weight_override is not None
                else max_weight
            )
            cap_cushion = 0.002 if assets[i].max_weight_override is not None else 0.015
            if new_v > total_capital * (eff_cap_i + cap_cushion):
                continue
            if sec_vals[sector_map[i]] + p > total_capital * (max_sector_weight + 0.015):
                continue
            err_before = abs(cur_v - target_vals[i])
            err_after = abs(new_v - target_vals[i])
            gain = err_before - err_after
            if gain > best_gain:
                best_gain = gain
                best_idx = i
        if best_idx < 0:
            break
        shares[best_idx] += 1
        remaining -= prices[best_idx]

    total_spent = sum(shares[i] * prices[i] for i in range(n))
    leftover_cash = max(0.0, float(total_capital) - total_spent)
    return shares, leftover_cash


def _portfolio_risk_metrics(
    weights: np.ndarray,
    cov: np.ndarray,
    sectors: Sequence[str],
) -> Dict[str, Any]:
    invested = float(np.sum(weights))
    if invested <= 1e-9 or len(weights) == 0:
        return {
            "annualVolatilityPct": 0.0,
            "diversificationRatio": 1.0,
            "effectiveStocks": 0.0,
            "hhiConcentration": 0.0,
            "maxStockWeightPct": 0.0,
            "maxSectorWeightPct": 0.0,
            "maxSectorName": "",
        }
    var = max(0.0, float(weights @ cov @ weights))
    ann_vol = math.sqrt(var)
    indiv_vols = np.sqrt(np.maximum(np.diag(cov), 1e-12))
    div_ratio = float(weights @ indiv_vols) / ann_vol if ann_vol > 1e-9 else 1.0

    norm_w = weights / invested
    hhi = float(np.sum(norm_w ** 2))
    eff_n = (1.0 / hhi) if hhi > 1e-9 else 0.0

    sec_totals: Dict[str, float] = {}
    for w_i, sec in zip(weights, sectors):
        key = sec or "أخرى"
        sec_totals[key] = sec_totals.get(key, 0.0) + float(w_i)
    max_sec_name, max_sec_val = max(sec_totals.items(), key=lambda kv: kv[1]) if sec_totals else ("", 0.0)

    return {
        "annualVolatilityPct": round(ann_vol * 100.0, 2),
        "diversificationRatio": round(div_ratio, 2),
        "effectiveStocks": round(eff_n, 2),
        "hhiConcentration": round(hhi, 3),
        "maxStockWeightPct": round(float(np.max(weights)) * 100.0, 1),
        "maxSectorWeightPct": round(max_sec_val * 100.0, 1),
        "maxSectorName": max_sec_name,
    }


def _finite_or(value: Any, default: float) -> float:
    try:
        f = float(value)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def optimize_portfolio_or(
    assets: Sequence[AssetInput],
    total_capital: float,
    *,
    objective: str = "balanced",
    max_weight_pct: float = 35.0,
    max_sector_pct: float = 45.0,
    min_cash_pct: float = 0.0,
    exchange: str = "EGX",
    turnover_penalty: float = 0.0,
) -> Dict[str, Any]:
    """Run full Operations Research optimization and return rich structured results."""
    valid_assets: List[AssetInput] = []
    for a in assets:
        px = _finite_or(a.price, 0.0)
        if px <= 0:
            continue
        valid_assets.append(
            AssetInput(
                symbol=a.symbol,
                price=px,
                name_ar=a.name_ar,
                sector=a.sector,
                current_shares=max(0.0, _finite_or(a.current_shares, 0.0)),
                expected_score=max(-1.0, min(1.0, _finite_or(a.expected_score, 0.0))),
                fallback_daily_vol=max(0.005, min(0.10, _finite_or(a.fallback_daily_vol, 0.022))),
                returns_by_date=a.returns_by_date,
                max_weight_override=a.max_weight_override,
                exclusion_reason=a.exclusion_reason,
                avg_daily_volume=a.avg_daily_volume,
            )
        )
    if not valid_assets:
        raise ValueError("لا توجد أسهم صالحة بأسعار متاحة لتشغيل التحسين الرياضي.")
    cap_raw = _finite_or(total_capital, -1.0)
    if cap_raw <= 0:
        raise ValueError("يجب إدخال رأس مال صحيح وموجب لتشغيل التحسين الرياضي.")
    capital = max(1.0, cap_raw)
    obj = normalize_objective(objective)
    max_w = max(0.05, min(1.0, _finite_or(max_weight_pct, 35.0) / 100.0))
    max_sec = max(0.10, min(1.0, _finite_or(max_sector_pct, 45.0) / 100.0))
    min_cash = max(0.0, min(0.80, _finite_or(min_cash_pct, 0.0) / 100.0))

    cov, corr, common_dates = estimate_covariance_matrix(valid_assets)
    sectors = [a.sector or "أخرى" for a in valid_assets]

    # Current weights (if existing holdings exist)
    curr_vals = np.array([max(0.0, float(a.current_shares)) * float(a.price) for a in valid_assets], dtype=float)
    has_existing = float(np.sum(curr_vals)) > 0
    curr_weights = (curr_vals / capital) if has_existing else None

    target_w, eff_max_w, eff_max_sec, relaxation_notes = solve_optimal_weights(
        valid_assets,
        cov,
        objective=obj,
        max_weight=max_w,
        max_sector_weight=max_sec,
        min_cash_weight=min_cash,
        current_weights=curr_weights,
        turnover_penalty=turnover_penalty if has_existing else 0.0,
    )

    target_shares, leftover_cash = allocate_integer_shares(
        valid_assets,
        target_w,
        capital,
        min_cash_weight=min_cash,
        max_weight=eff_max_w,
        max_sector_weight=eff_max_sec,
    )

    actual_vals = np.array([target_shares[i] * float(valid_assets[i].price) for i in range(len(valid_assets))], dtype=float)
    actual_weights = actual_vals / capital

    # Risk contributions (marginal variance share)
    port_var = max(float(actual_weights @ cov @ actual_weights), 1e-12)
    risk_contribs = (actual_weights * (cov @ actual_weights)) / port_var

    fee_rate = market_fee_rate(exchange)
    # Scale-safe dust threshold: prevents small portfolios (e.g. 250-5,000 EGP) from misclassifying
    # a 39% rebalance sell as HOLD while preserving the 200 EGP dust floor on large portfolios.
    dust_threshold = min(200.0, max(5.0, capital * 0.01))
    total_turnover_val = 0.0
    allocations: List[Dict[str, Any]] = []
    sector_breakdown: Dict[str, float] = {}
    current_sector_breakdown: Dict[str, float] = {}
    execution_notes: List[str] = []

    # First pass: determine actionable BUY/SELL/HOLD and snap sub-dust HOLD deltas to current shares
    # so `allocatedValue`, `leftoverCash`, and `tradeSummary.totalSellValue` reconcile 100% identically!
    final_shares: List[int] = [int(target_shares[i]) for i in range(len(valid_assets))]
    final_actions: List[str] = []
    for i, a in enumerate(valid_assets):
        cur_sh = int(round(max(0.0, float(a.current_shares))))
        tgt_sh = final_shares[i]
        delta_sh = tgt_sh - cur_sh
        trade_val = abs(delta_sh) * float(a.price)
        is_excluded = a.max_weight_override is not None and float(a.max_weight_override) <= 0.0
        if has_existing:
            if not is_excluded and delta_sh > 0 and trade_val >= dust_threshold:
                act = "BUY"
            elif delta_sh < 0 and (trade_val >= dust_threshold or is_excluded):
                act = "SELL"
            else:
                act = "HOLD"
                # Keep current shares intact for HOLD rows so cash and trade totals reconcile exactly
                final_shares[i] = cur_sh
        else:
            act = "BUY" if (tgt_sh > 0 and not is_excluded) else "SKIP"
        final_actions.append(act)

    # Enforce strict budget ceiling after HOLD snapping: if absorbing sub-dust SELLs into HOLD pushed
    # total invested value above available capital, deterministically trim BUY rows down until
    # sum(final_shares * price) <= capital + 1e-6 (converting any BUY falling below dust_threshold to HOLD).
    if has_existing:
        total_inv = sum(final_shares[i] * float(valid_assets[i].price) for i in range(len(valid_assets)))
        if total_inv > capital + 1e-6:
            for _ in range(10000):
                if total_inv <= capital + 1e-6:
                    break
                buy_candidates = [
                    i
                    for i in range(len(valid_assets))
                    if final_actions[i] == "BUY"
                    and final_shares[i] > int(round(max(0.0, float(valid_assets[i].current_shares))))
                ]
                if not buy_candidates:
                    break
                pick_i = max(
                    buy_candidates,
                    key=lambda idx: (
                        (final_shares[idx] * float(valid_assets[idx].price) / capital) - float(target_w[idx]),
                        float(valid_assets[idx].price),
                    ),
                )
                px_pick = float(valid_assets[pick_i].price)
                cur_pick = int(round(max(0.0, float(valid_assets[pick_i].current_shares))))
                final_shares[pick_i] -= 1
                total_inv -= px_pick
                rem_buy_val = (final_shares[pick_i] - cur_pick) * px_pick
                if final_shares[pick_i] <= cur_pick or rem_buy_val < dust_threshold:
                    total_inv -= max(0, final_shares[pick_i] - cur_pick) * px_pick
                    final_shares[pick_i] = cur_pick
                    final_actions[pick_i] = "HOLD"

    actual_vals = np.array([final_shares[i] * float(valid_assets[i].price) for i in range(len(valid_assets))], dtype=float)
    actual_weights = actual_vals / capital
    leftover_cash = max(0.0, float(capital - float(np.sum(actual_vals))))
    port_var = max(float(actual_weights @ cov @ actual_weights), 1e-12)
    risk_contribs = (actual_weights * (cov @ actual_weights)) / port_var

    for i, a in enumerate(valid_assets):
        cur_sh = int(round(max(0.0, float(a.current_shares))))
        tgt_sh = final_shares[i]
        delta_sh = tgt_sh - cur_sh
        trade_val = abs(delta_sh) * float(a.price)
        if has_existing:
            total_turnover_val += trade_val
        else:
            total_turnover_val += tgt_sh * float(a.price)

        act_w_pct = round(float(actual_weights[i]) * 100.0, 1)
        cur_w_pct = round(float(curr_weights[i]) * 100.0, 1) if curr_weights is not None else 0.0
        tgt_w_pct = round(float(target_w[i]) * 100.0, 1)
        sec_key = a.sector or "أخرى"
        sector_breakdown[sec_key] = round(sector_breakdown.get(sec_key, 0.0) + act_w_pct, 1)
        if cur_w_pct > 0:
            current_sector_breakdown[sec_key] = round(current_sector_breakdown.get(sec_key, 0.0) + cur_w_pct, 1)

        action = final_actions[i]

        px_f = float(a.price)
        px_dec = 4 if abs(px_f) < 2.0 else (3 if abs(px_f) < 10.0 else 2)
        row_dict: Dict[str, Any] = {
            "symbol": a.symbol,
            "nameAr": a.name_ar or a.symbol,
            "sector": sec_key,
            "price": round(px_f, px_dec),
            "currentShares": cur_sh,
            "currentWeightPct": cur_w_pct,
            "targetWeightPct": tgt_w_pct,
            "actualWeightPct": act_w_pct,
            "targetShares": tgt_sh,
            "deltaShares": delta_sh,
            "allocatedValue": round(float(actual_vals[i]), 2),
            "tradeValue": round(trade_val, 2),
            "action": action,
            "riskContributionPct": round(max(0.0, float(risk_contribs[i])) * 100.0, 1),
            "annualVolPct": round(math.sqrt(max(float(cov[i, i]), 0.0)) * 100.0, 1),
        }
        if a.exclusion_reason:
            row_dict["exclusionReason"] = a.exclusion_reason
        if action in ("BUY", "SELL") and abs(delta_sh) > 0 and a.avg_daily_volume and math.isfinite(float(a.avg_daily_volume)) and float(a.avg_daily_volume) > 0:
            adv = float(a.avg_daily_volume)
            participation_cap = max(1, int(0.10 * adv))
            raw_sessions = max(1, int(math.ceil(abs(delta_sh) / participation_cap)))
            if raw_sessions > 1:
                eff_sessions = min(raw_sessions, 15)
                shares_per_session = int(math.ceil(abs(delta_sh) / eff_sessions))
                daily_vol_frac = math.sqrt(max(float(cov[i, i]), 0.0) / 252.0)
                q_over_adv = abs(delta_sh) / max(adv, 1.0)
                est_impact_bps = round(min(500.0, 0.5 * daily_vol_frac * math.sqrt(q_over_adv) * 10000.0), 1)
                act_ar = "شراء" if action == "BUY" else "بيع"
                note_ar = (
                    f"سيولة محدودة ({int(adv):,} سهم/جلسة) — قسّم {act_ar} {a.symbol} على "
                    f"{eff_sessions} جلسات (~{shares_per_session:,} سهم/جلسة) لتجنّب الانزلاق السعري"
                )
                row_dict["executionPlan"] = {
                    "sessions": eff_sessions,
                    "rawSessions": raw_sessions,
                    "sharesPerSession": shares_per_session,
                    "participationPct": round(min(100.0, (abs(delta_sh) / adv) * 100.0), 1),
                    "estImpactBps": est_impact_bps,
                    "noteAr": note_ar,
                }
                execution_notes.append(note_ar)
        allocations.append(row_dict)

    allocations.sort(key=lambda r: r["actualWeightPct"], reverse=True)

    # Top correlated pairs (useful risk insight)
    top_corr_pairs: List[Dict[str, Any]] = []
    for i in range(len(valid_assets)):
        for j in range(i + 1, len(valid_assets)):
            c_ij = float(corr[i, j])
            if c_ij >= 0.55:
                top_corr_pairs.append(
                    {
                        "pair": f"{valid_assets[i].symbol} / {valid_assets[j].symbol}",
                        "correlation": round(c_ij, 2),
                    }
                )
    top_corr_pairs.sort(key=lambda x: x["correlation"], reverse=True)

    after_metrics = _portfolio_risk_metrics(actual_weights, cov, sectors)
    equal_w = np.full(len(valid_assets), (1.0 - min_cash) / len(valid_assets), dtype=float)
    baseline_weights = curr_weights if has_existing else equal_w
    before_metrics = _portfolio_risk_metrics(baseline_weights, cov, sectors)

    vol_delta = round(after_metrics["annualVolatilityPct"] - before_metrics["annualVolatilityPct"], 2)
    est_fees = round(total_turnover_val * fee_rate, 2)

    sell_rows = [r for r in allocations if r.get("action") == "SELL"]
    buy_rows = [r for r in allocations if r.get("action") == "BUY"]
    hold_rows = [r for r in allocations if r.get("action") == "HOLD"]
    total_sell_val = round(sum(float(r.get("tradeValue") or 0.0) for r in sell_rows), 2)
    total_buy_val = round(sum(float(r.get("tradeValue") or 0.0) for r in buy_rows), 2)
    net_cash_delta = round(total_sell_val - total_buy_val, 2)
    leftover_r = round(leftover_cash, 2)

    return {
        "objective": obj,
        "objectiveLabelAr": OBJECTIVE_LABELS_AR.get(obj, obj),
        "exchange": str(exchange or "EGX").upper(),
        "totalCapital": round(capital, 2),
        "investedAmount": round(float(np.sum(actual_vals)), 2),
        "leftoverCash": leftover_r,
        "leftoverCashPct": round((leftover_cash / capital) * 100.0, 1),
        "estimatedFees": est_fees,
        "feeRatePct": round(fee_rate * 100.0, 3),
        "historyOverlapDays": common_dates,
        "hasExistingHoldings": has_existing,
        "tradeSummary": {
            "sellCount": len(sell_rows),
            "buyCount": len(buy_rows),
            "holdCount": len(hold_rows),
            "sellSymbols": [r["symbol"] for r in sell_rows],
            "buySymbols": [r["symbol"] for r in buy_rows],
            "holdSymbols": [r["symbol"] for r in hold_rows],
            "totalSellValue": total_sell_val,
            "totalBuyValue": total_buy_val,
            "netCashDelta": net_cash_delta,
            "estimatedFees": est_fees,
            "leftoverCash": leftover_r,
            "exactSummaryAr": (
                f"إجمالي المبيعات المحسوب حتمياً ({len(sell_rows)} أسهم): {total_sell_val:,.2f} | "
                f"إجمالي المشتريات المحسوب حتمياً ({len(buy_rows)} أسهم): {total_buy_val:,.2f} | "
                f"العمولة التقديرية: {est_fees:,.2f} | الكاش المتبقي: {leftover_r:,.2f}"
            ),
        },
        "constraints": {
            "maxStockWeightPct": round(eff_max_w * 100.0, 1),
            "maxSectorWeightPct": round(eff_max_sec * 100.0, 1),
            "minCashPct": round(min_cash * 100.0, 1),
            "relaxationNotes": relaxation_notes,
        },
        "metricsBefore": before_metrics,
        "metricsAfter": after_metrics,
        "volatilityChangePct": vol_delta,
        "currentSectorBreakdown": [
            {"sector": k, "weightPct": v}
            for k, v in sorted(current_sector_breakdown.items(), key=lambda kv: kv[1], reverse=True)
            if v > 0
        ],
        "sectorBreakdown": [
            {"sector": k, "weightPct": v}
            for k, v in sorted(sector_breakdown.items(), key=lambda kv: kv[1], reverse=True)
            if v > 0
        ],
        "highCorrelationPairs": top_corr_pairs[:5],
        "excludedFromBuying": [
            {"symbol": a.symbol, "reason": a.exclusion_reason}
            for a in valid_assets
            if a.exclusion_reason
        ],
        "allocations": allocations,
        **({"executionNotes": execution_notes} if execution_notes else {}),
    }


def select_diversified_candidates(
    scored_candidates: Sequence[Dict[str, Any]],
    returns_map: Dict[str, Dict[str, float]],
    *,
    k: int = 3,
    max_per_sector: int = 1,
    max_correlation: float = 0.78,
    existing_sector_counts: Optional[Dict[str, int]] = None,
    max_total_per_sector: int = 2,
) -> List[Dict[str, Any]]:
    """Constrained Top-K selection respecting sector limits and pairwise correlation cap.

    Expects each candidate dict to have: ``symbol``, ``score``, and optional ``sector``.
    Falls back cleanly if strict constraints yield fewer than ``k`` items.
    """
    if not scored_candidates or k <= 0:
        return []

    ordered = sorted(scored_candidates, key=lambda c: float(c.get("score") or 0.0), reverse=True)

    def _pair_corr(sym_a: str, sym_b: str) -> float:
        ra = returns_map.get(sym_a) or {}
        rb = returns_map.get(sym_b) or {}
        common = sorted(set(ra.keys()) & set(rb.keys()))
        if len(common) < 15:
            return 0.0
        xa = np.array([ra[d] for d in common], dtype=float)
        xb = np.array([rb[d] for d in common], dtype=float)
        sa = float(np.std(xa, ddof=1))
        sb = float(np.std(xb, ddof=1))
        if sa <= 1e-9 or sb <= 1e-9:
            return 0.0
        c = float(np.corrcoef(xa, xb)[0, 1])
        return c if math.isfinite(c) else 0.0

    selected: List[Dict[str, Any]] = []
    picked_syms: set[str] = set()
    new_sec_counts: Dict[str, int] = {}
    base_sec = dict(existing_sector_counts or {})

    # Pass 1: Strict sector & correlation constraints
    for cand in ordered:
        if len(selected) >= k:
            break
        sym = str(cand.get("symbol") or "").upper()
        if not sym or sym in picked_syms:
            continue
        sec = str(cand.get("sector") or "أخرى").strip() or "أخرى"
        if sec != "أخرى":
            if new_sec_counts.get(sec, 0) >= max_per_sector:
                continue
            if base_sec.get(sec, 0) + new_sec_counts.get(sec, 0) >= max_total_per_sector:
                continue
        if any(_pair_corr(sym, str(s.get("symbol") or "").upper()) > max_correlation for s in selected):
            continue
        selected.append(cand)
        picked_syms.add(sym)
        new_sec_counts[sec] = new_sec_counts.get(sec, 0) + 1

    # Pass 2: Graceful backfill if strict pass returned < k
    if len(selected) < k:
        for cand in ordered:
            if len(selected) >= k:
                break
            sym = str(cand.get("symbol") or "").upper()
            if not sym or sym in picked_syms:
                continue
            selected.append(cand)
            picked_syms.add(sym)

    return selected


def build_smart_dca_plan(
    *,
    symbol: str,
    exchange: str = "EGX",
    currency: str = "ج.م",
    current_price: float,
    old_shares: float,
    old_avg_price: float,
    dca_budget: Optional[float] = None,
    support_1: Optional[float] = None,
    support_2: Optional[float] = None,
    stop_loss: Optional[float] = None,
    setup_regime: Optional[str] = None,
    dist_score: Optional[float] = None,
    fund_score: Optional[float] = None,
    is_loss_making: Optional[bool] = None,
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]] = None,
    reference_shares_used: bool = False,
) -> Dict[str, Any]:
    """
    Operations Research Smart DCA & Break-Even Optimizer.
    Rejects averaging down on falling-knife / distribution / loss-making traps,
    or computes a 2-tranche integer-share support ladder with brokerage fees
    and calibrated 10-session Monte Carlo break-even probability boost.
    """
    sym_u = str(symbol or "").strip().upper()
    ex_u = str(exchange or "EGX").strip().upper()
    cur_p = float(current_price or 0.0)
    if cur_p <= 0:
        return {"symbol": sym_u, "dca_allowed": False, "verdict_ar": "⚠️ تعذّر الحساب لعدم توفر السعر الحالي"}

    dec = 4 if abs(cur_p) < 2.0 else (3 if abs(cur_p) < 10.0 else 2)
    old_qty = max(float(old_shares or 100.0), 1.0)
    old_avg = float(old_avg_price or cur_p)
    current_loss_pct = round(((cur_p - old_avg) / old_avg) * 100.0, 2) if old_avg > 0 else 0.0

    # Eligibility Gate: block mathematically destructive averaging down on traps
    reasons: List[str] = []
    if setup_regime == "high_risk_avoid":
        reasons.append("التصنيف الكمي يرصد مخاطرة مرتفعة أو ضغط بيعي غالب")
    if dist_score is not None and float(dist_score) >= 65.0:
        reasons.append(f"رصد تصريف مؤسسي قوي ({float(dist_score):.0f}/100)")
    if is_loss_making is True:
        reasons.append("الشركة تحقق خسائر مالية صافية حالياً")
    if fund_score is not None and float(fund_score) < 42.0:
        reasons.append(f"الجودة المالية ضعيفة ({float(fund_score):.0f}/100)")

    if reasons:
        hard_stop = round(stop_loss if (stop_loss and 0 < stop_loss < cur_p) else (cur_p * 0.94), dec)
        return {
            "symbol": sym_u,
            "exchange": ex_u,
            "currency": currency,
            "dca_allowed": False,
            "verdict_ar": "⛔ غير مناسب للتبريد حالياً — أولوية حماية رأس المال",
            "rejection_reason_ar": "؛ ".join(reasons),
            "old_shares": round(old_qty, 2),
            "old_avg_price": round(old_avg, dec),
            "current_price": round(cur_p, dec),
            "current_loss_pct": current_loss_pct,
            "capital_protection_stop": hard_stop,
            "reference_100_shares": bool(reference_shares_used),
        }

    budget_estimated = not (dca_budget is not None and float(dca_budget) > 0)
    budget = float(dca_budget) if not budget_estimated else round(old_qty * cur_p * 0.50, 2)
    fee_r = market_fee_rate(ex_u)

    if support_1 and (cur_p * 0.90) <= float(support_1) <= cur_p:
        t1_price = round(float(support_1), dec)
    else:
        t1_price = round(cur_p, dec)

    if support_2 and (cur_p * 0.78) <= float(support_2) < t1_price:
        t2_price = round(float(support_2), dec)
    else:
        t2_price = round(t1_price * 0.95, dec)

    t1_alloc = budget * 0.45
    t1_shares = int(math.floor(max(t1_alloc, 0.0) / max(t1_price * (1.0 + fee_r), 1e-6)))
    t1_cost = round(t1_shares * t1_price, 2)
    t1_fee = round(t1_cost * fee_r, 2)

    remaining_budget = max(budget - t1_cost - t1_fee, 0.0)
    t2_shares = int(math.floor(remaining_budget / max(t2_price * (1.0 + fee_r), 1e-6)))
    t2_cost = round(t2_shares * t2_price, 2)
    t2_fee = round(t2_cost * fee_r, 2)
    total_dca_cash = round(t1_cost + t1_fee + t2_cost + t2_fee, 2)
    leftover_cash = round(max(budget - total_dca_cash, 0.0), 2)

    old_cost = old_qty * old_avg
    qty_after_t1 = old_qty + t1_shares
    new_avg_t1 = round((old_cost + t1_cost + t1_fee) / qty_after_t1, dec) if qty_after_t1 > 0 else round(old_avg, dec)
    qty_after_full = old_qty + t1_shares + t2_shares
    new_avg_full = round((old_cost + total_dca_cash) / qty_after_full, dec) if qty_after_full > 0 else round(old_avg, dec)

    post_full_ref = t2_price if (t2_shares > 0 and t2_price > 0) else min(cur_p, t1_price)
    post_t1_ref = min(cur_p, t1_price) if (t1_shares > 0 and t1_price > 0) else cur_p
    rally_from_cur_before = round(((old_avg - cur_p) / cur_p) * 100.0, 2) if old_avg > cur_p else 0.0
    rally_before = round(((old_avg - post_full_ref) / post_full_ref) * 100.0, 2) if old_avg > post_full_ref else 0.0
    rally_after = round(((new_avg_full - post_full_ref) / post_full_ref) * 100.0, 2) if new_avg_full > post_full_ref else 0.0
    rally_after_t1 = round(((new_avg_t1 - post_t1_ref) / post_t1_ref) * 100.0, 2) if new_avg_t1 > post_t1_ref else 0.0
    hard_stop = round(stop_loss if (stop_loss and 0 < stop_loss < t2_price) else (t2_price * 0.96), dec)

    try:
        from api.agentic_chat.quant_engine import prob_touch_level
        prob_be_before = prob_touch_level(
            ohlcv_rows,
            close=post_full_ref,
            target_level=old_avg,
            exchange=ex_u,
            symbol=sym_u,
            horizon_days=10,
        )
        prob_be_after = prob_touch_level(
            ohlcv_rows,
            close=post_full_ref,
            target_level=new_avg_full,
            exchange=ex_u,
            symbol=sym_u,
            horizon_days=10,
        )
    except Exception:
        prob_be_before = None
        prob_be_after = None

    return {
        "symbol": sym_u,
        "exchange": ex_u,
        "currency": currency,
        "dca_allowed": True,
        "verdict_ar": "✅ خطة تبريد متدرجة محسوبة على الدعوم لتقريب نقطة التعادل",
        "old_shares": round(old_qty, 2),
        "old_avg_price": round(old_avg, dec),
        "current_price": round(cur_p, dec),
        "current_loss_pct": current_loss_pct,
        "dca_budget": round(budget, 2),
        "budget_estimated": bool(budget_estimated),
        "reference_100_shares": bool(reference_shares_used),
        "new_avg_price_t1": new_avg_t1,
        "new_avg_price_full": new_avg_full,
        "breakeven_reference_price": round(post_full_ref, dec),
        "rally_needed_from_current_before_pct": rally_from_cur_before,
        "rally_needed_before_pct": rally_before,
        "rally_needed_after_pct": rally_after,
        "rally_needed_after_t1_pct": rally_after_t1,
        "breakeven_note_ar": (
            f"مقارنة عادلة من سعر تنفيذ الدفعة الأخيرة ({round(post_full_ref, dec)} {currency}): "
            f"بدون تبريد تحتاج +{rally_before}% للعودة لمتوسط {round(old_avg, dec)}، "
            f"وبعد التبريد الكامل تحتاج +{rally_after}% فقط للعودة لمتوسط {new_avg_full} "
            "(لا يوجد تعادل فوري قبل تنفيذ الدفعة الثانية)."
        ),
        "prob_breakeven_10d_before_pct": prob_be_before,
        "prob_breakeven_10d_after_pct": prob_be_after,
        "hard_invalidation_stop": hard_stop,
        "estimated_fees": round(t1_fee + t2_fee, 2),
        "leftover_cash": leftover_cash,
        "tranches": [
            {
                "tranche": 1,
                "label": "الدفعة الأولى (عند الدعم القريب / السعر الحالي)",
                "weight_pct": 45,
                "limit_price": t1_price,
                "shares": t1_shares,
                "cost": t1_cost,
                "fee": t1_fee,
                "avg_after": new_avg_t1,
            },
            {
                "tranche": 2,
                "label": "الدفعة الثانية (عند الدعم الثاني الاحتياطي)",
                "weight_pct": 55,
                "limit_price": t2_price,
                "shares": t2_shares,
                "cost": t2_cost,
                "fee": t2_fee,
                "avg_after": new_avg_full,
            },
        ],
    }
