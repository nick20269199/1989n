"""规则挖掘 Step 2: 从特征矩阵中统计挖掘交易规则

方法：
- 单特征分箱 → 每档胜率
- 双特征组合 → 最佳双条件规则
- 按市场状态分层 → 牛/熊/震荡不同规则
- 过滤条件：样本量≥30，胜率≥55%或≤45%
- 输出结构化规则库供 L4 专家使用

输出：D:/1989n/stock_data/ml/rules.json
"""

import json, os
import numpy as np
import pandas as pd

DATA_DIR = "D:/1989n/stock_data"
ML_DIR = os.path.join(DATA_DIR, "ml")

# ============================================================
# Config
# ============================================================
MIN_SAMPLES = 30          # 最小样本量
MIN_WIN_RATE = 55         # 最低胜率（买入信号）
MAX_WIN_RATE = 45         # 最高胜率（卖出/规避信号）
TOP_N_SINGLE = 20         # 单特征规则最多保留数
TOP_N_DOUBLE = 30         # 双特征规则最多保留数


# ============================================================
# 单特征分箱规则
# ============================================================

def bin_feature(series, n_bins=5):
    """Bin a continuous feature into n_bins quantile-based bins."""
    if series.nunique() < n_bins:
        # Too few unique values — use value counts directly
        return series.astype(str)
    try:
        return pd.qcut(series, q=n_bins, duplicates="drop")
    except ValueError:
        return pd.cut(series, bins=n_bins, duplicates="drop")


def mine_single_feature_rules(df, feature_col, label_col="label", n_bins=5):
    """Mine rules from a single feature by binning."""
    binned = bin_feature(df[feature_col], n_bins)
    grouped = df.groupby(binned, observed=False)

    rules = []
    for bin_label, group in grouped:
        n = len(group)
        if n < MIN_SAMPLES:
            continue
        wins = group[label_col].sum()
        win_rate = wins / n * 100
        avg_profit = group["gross_pct"].mean()

        rules.append({
            "feature": feature_col,
            "condition": str(bin_label),
            "n": n,
            "wins": int(wins),
            "win_rate": round(win_rate, 1),
            "avg_profit_pct": round(avg_profit, 2),
            "type": "entry" if win_rate >= MIN_WIN_RATE else ("exit" if win_rate <= MAX_WIN_RATE else "neutral"),
        })
    return rules


# ============================================================
# 双特征组合规则
# ============================================================

def bin_simple(series, n_bins=3):
    """Bin into 3 groups: low, medium, high."""
    if series.nunique() <= 3:
        return series.astype(str)
    try:
        return pd.qcut(series, q=n_bins, labels=["low", "mid", "high"], duplicates="drop")
    except ValueError:
        return pd.cut(series, bins=n_bins, labels=["low", "mid", "high"], duplicates="drop")


def mine_double_feature_rules(df, feat1, feat2, label_col="label"):
    """Mine rules from a pair of features."""
    b1 = bin_simple(df[feat1])
    b2 = bin_simple(df[feat2])
    grouped = df.groupby([b1, b2], observed=False)

    rules = []
    for (v1, v2), group in grouped:
        n = len(group)
        if n < MIN_SAMPLES:
            continue
        wins = group[label_col].sum()
        win_rate = wins / n * 100
        avg_profit = group["gross_pct"].mean()

        if win_rate >= MIN_WIN_RATE or win_rate <= MAX_WIN_RATE:
            rules.append({
                "feature_pair": [feat1, feat2],
                "condition": f"{feat1}={v1} & {feat2}={v2}",
                "n": n,
                "wins": int(wins),
                "win_rate": round(win_rate, 1),
                "avg_profit_pct": round(avg_profit, 2),
                "type": "entry" if win_rate >= MIN_WIN_RATE else "exit",
            })
    return rules


# ============================================================
# 市场状态分层规则
# ============================================================

def mine_market_stratified_rules(df, label_col="label"):
    """Mine rules stratified by market_trend + market_sentiment."""
    rules = []
    for trend in df["market_trend"].unique():
        subset = df[df["market_trend"] == trend]
        if len(subset) < MIN_SAMPLES:
            continue

        # Baseline: what's the win rate in this market state?
        n_all = len(subset)
        win_all = subset[label_col].sum()
        wr_all = win_all / n_all * 100

        # For each feature, find best conditions within this market state
        for feat in ["price_ma20_ratio", "volume_ratio", "rsi_14",
                     "price_position_20", "hold_days", "volatility_20"]:
            if feat not in subset.columns:
                continue
            binned = bin_simple(subset[feat])
            for v, grp in subset.groupby(binned, observed=False):
                n = len(grp)
                if n < MIN_SAMPLES:
                    continue
                wins = grp[label_col].sum()
                wr = wins / n * 100
                if wr >= MIN_WIN_RATE or wr <= MAX_WIN_RATE:
                    rules.append({
                        "market_filter": f"market_trend={trend}",
                        "feature": feat,
                        "condition": f"{feat}={v}",
                        "n": n,
                        "wins": int(wins),
                        "win_rate": round(wr, 1),
                        "market_baseline": round(wr_all, 1),
                        "avg_profit_pct": round(grp["gross_pct"].mean(), 2),
                        "type": "entry" if wr >= MIN_WIN_RATE else "exit",
                        "layer": "market_stratified",
                    })
    return rules


# ============================================================
# 持仓天数分析
# ============================================================

def mine_hold_duration_rules(df):
    """Analyze win rate by hold duration."""
    bins = [0, 1, 2, 3, 5, 7, 10, 15, 20, 999]
    labels = ["0天(日内)", "1天", "2天", "3天", "4-5天", "6-7天", "8-10天", "11-15天", "16-20天", "20天+"]
    df = df.copy()
    df["hold_bin"] = pd.cut(df["hold_days"], bins=bins, labels=labels[:len(bins)-1], right=True)

    rules = []
    for label, group in df.groupby("hold_bin", observed=False):
        n = len(group)
        if n < MIN_SAMPLES:
            continue
        wins = group["label"].sum()
        wr = wins / n * 100
        rules.append({
            "feature": "hold_days",
            "condition": f"hold_days in {label}",
            "n": n,
            "wins": int(wins),
            "win_rate": round(wr, 1),
            "avg_profit_pct": round(group["gross_pct"].mean(), 2),
            "type": "entry" if wr >= MIN_WIN_RATE else ("exit" if wr <= MAX_WIN_RATE else "neutral"),
            "layer": "hold_duration",
        })
    return rules


# ============================================================
# 市场情绪分层
# ============================================================

def mine_sentiment_rules(df):
    """Analyze win rate by market sentiment at buy."""
    rules = []
    for sentiment, group in df.groupby("market_sentiment", observed=False):
        n = len(group)
        if n < MIN_SAMPLES:
            continue
        wins = group["label"].sum()
        wr = wins / n * 100
        rules.append({
            "feature": "market_sentiment",
            "condition": f"sentiment={sentiment}",
            "n": n,
            "wins": int(wins),
            "win_rate": round(wr, 1),
            "avg_profit_pct": round(group["gross_pct"].mean(), 2),
            "type": "entry" if wr >= MIN_WIN_RATE else ("exit" if wr <= MAX_WIN_RATE else "neutral"),
            "layer": "sentiment",
        })
    return rules


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 50)
    print("规则挖掘 Step 2: 规则挖掘")
    print("=" * 50)

    # Load features
    print("\n[1/3] 加载特征矩阵...")
    fpath = os.path.join(ML_DIR, "trade_features.parquet")
    df = pd.read_parquet(fpath)
    print(f"  加载: {len(df)} 行, {len(df.columns)} 列")
    print(f"  盈利: {df['label'].sum()}, 亏损: {len(df) - df['label'].sum()}")
    print(f"  整体胜率: {df['label'].mean() * 100:.1f}%")

    all_rules = []

    # --- Single feature rules ---
    print("\n[2/3] 挖掘单特征规则...")
    continuous_features = [
        "price_ma5_ratio", "price_ma10_ratio", "price_ma20_ratio", "price_ma60_ratio",
        "volume_ratio", "rsi_14", "hold_days", "volatility_20",
        "price_position_20", "pct_5d_before_buy",
    ]
    for feat in continuous_features:
        if feat not in df.columns:
            continue
        rules = mine_single_feature_rules(df, feat)
        for r in rules:
            r["layer"] = "single_feature"
        all_rules.extend(rules)

    # --- Double feature rules ---
    print("  挖掘双特征组合规则...")
    top_features = ["price_ma20_ratio", "volume_ratio", "rsi_14",
                    "price_ma60_ratio", "price_position_20", "hold_days"]
    for i in range(len(top_features)):
        for j in range(i + 1, len(top_features)):
            rules = mine_double_feature_rules(df, top_features[i], top_features[j])
            for r in rules:
                r["layer"] = "double_feature"
            all_rules.extend(rules)

    # --- Market stratified ---
    print("  挖掘市场分层规则...")
    all_rules.extend(mine_market_stratified_rules(df))

    # --- Hold duration ---
    print("  挖掘持仓时长规则...")
    all_rules.extend(mine_hold_duration_rules(df))

    # --- Sentiment ---
    print("  挖掘市场情绪规则...")
    all_rules.extend(mine_sentiment_rules(df))

    # ============================================================
    # Filter and sort
    # ============================================================
    print("\n[3/3] 过滤和排序规则...")

    # Split by type
    entry_rules = [r for r in all_rules if r["type"] == "entry"]
    exit_rules = [r for r in all_rules if r["type"] == "exit"]

    # Sort by win_rate descending for entry, ascending for exit
    entry_rules.sort(key=lambda x: (-x["win_rate"], -x["n"]))
    exit_rules.sort(key=lambda x: (x["win_rate"], -x["n"]))

    # Take top N
    entry_top = entry_rules[:TOP_N_SINGLE]
    exit_top = exit_rules[:TOP_N_SINGLE]

    # Collect double-feature rules
    entry_double = sorted(
        [r for r in all_rules if r["type"] == "entry" and r.get("layer") == "double_feature"],
        key=lambda x: (-x["win_rate"], -x["n"])
    )[:TOP_N_DOUBLE]
    exit_double = sorted(
        [r for r in all_rules if r["type"] == "exit" and r.get("layer") == "double_feature"],
        key=lambda x: (x["win_rate"], -x["n"])
    )[:TOP_N_DOUBLE]

    # Market stratified
    mkt_entry = sorted(
        [r for r in all_rules if r["type"] == "entry" and r.get("layer") == "market_stratified"],
        key=lambda x: (-x["win_rate"], -x["n"])
    )[:TOP_N_DOUBLE]
    mkt_exit = sorted(
        [r for r in all_rules if r["type"] == "exit" and r.get("layer") == "market_stratified"],
        key=lambda x: (x["win_rate"], -x["n"])
    )[:TOP_N_DOUBLE]

    # Hold/sentiment rules
    hold_exit = sorted(
        [r for r in all_rules if r["type"] == "exit" and r.get("layer") == "hold_duration"],
        key=lambda x: (x["win_rate"], -x["n"])
    )

    # Build final output
    output = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "metadata": {
            "total_samples": len(df),
            "overall_win_rate": round(df["label"].mean() * 100, 1),
            "total_rules_mined": len(all_rules),
            "min_samples": MIN_SAMPLES,
            "min_win_rate_entry": MIN_WIN_RATE,
            "max_win_rate_exit": MAX_WIN_RATE,
        },
        "rules": {
            "entry": {
                "single_feature": entry_top,
                "double_feature": entry_double,
                "market_stratified": mkt_entry,
            },
            "exit": {
                "single_feature": exit_top,
                "double_feature": exit_double,
                "market_stratified": mkt_exit,
                "hold_duration": hold_exit,
                "sentiment": [r for r in all_rules if r.get("layer") == "sentiment"],
            },
        },
        # Also include best rules for quick reference
        "top_10_entry_rules": entry_top[:10],
        "top_10_exit_rules": exit_top[:10],
    }

    # Save
    out_path = os.path.join(ML_DIR, "rules.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 规则库已保存: {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")

    # Print summary
    print(f"\n规则统计:")
    print(f"  总规则数: {len(all_rules)}")
    print(f"  买入规则 (胜率≥{MIN_WIN_RATE}%): {len(entry_rules)}")
    print(f"  卖出规则 (胜率≤{MAX_WIN_RATE}%): {len(exit_rules)}")
    print(f"\n最佳5条买入规则:")
    for r in entry_top[:5]:
        print(f"  [{r['win_rate']}%] {r.get('condition','?')} (n={r['n']}, 均利={r['avg_profit_pct']}%)")
    print(f"\n最差5条（卖出信号）:")
    for r in exit_top[:5]:
        print(f"  [{r['win_rate']}%] {r.get('condition','?')} (n={r['n']}, 均利={r['avg_profit_pct']}%)")


if __name__ == "__main__":
    main()
