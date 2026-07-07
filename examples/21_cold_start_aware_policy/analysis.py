"""
文件作用：cold_start_aware_policy 样例的结果导出与分析工具。

该文件负责导出策略对比摘要、关联验证、论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略摘要。
    """
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())
    eviction_df = outputs.get("cold_start_eviction", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    summary = (
        request_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            miss_count=("cache_hit", lambda s: int((~s.astype(bool)).sum())),
            avg_latency=("latency", "mean"),
            max_latency=("latency", "max"),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_keep_alive_window=("keep_alive_window", "mean"),
            avg_cache_used=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(hit_rate=lambda df: df["hit_count"] / df["request_count"])
    )

    if not eviction_df.empty:
        eviction_summary = (
            eviction_df
            .groupby("policy_name")
            .agg(eviction_count=("evicted_function", "count"))
            .reset_index()
        )
        summary = summary.merge(eviction_summary, on="policy_name", how="left")
    else:
        summary["eviction_count"] = 0

    summary["eviction_count"] = summary["eviction_count"].fillna(0).astype(int)
    return summary


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成策略结果摘要。
    """
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    return (
        request_df
        .groupby(["policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_keep_alive_window=("keep_alive_window", "mean"),
        )
        .reset_index()
        .assign(
            miss_count=lambda df: df["request_count"] - df["hit_count"],
            hit_rate=lambda df: df["hit_count"] / df["request_count"],
        )
    )


def build_decision_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略决策摘要。
    """
    decision_df = outputs.get("cold_start_policy_decision", pd.DataFrame())

    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["policy_name", "decision", "reason"])
        .agg(
            events=("request_id", "count"),
            avg_utility=("utility", "mean"),
            avg_keep_alive_window=("keep_alive_window", "mean"),
        )
        .reset_index()
    )


def build_request_decision_join(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    request × policy_decision 关联（论文 demo 关键证据）。

    每个 request 都对应一个 policy_decision。验证：
    - 行数一致
    - cache_hit=True ↔ decision=extend_keep_alive
    - cache_hit=False ↔ decision=keep_after_cold_start
    - keep_alive_window 一致
    """
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())
    decision_df = outputs.get("cold_start_policy_decision", pd.DataFrame())

    if request_df.empty or decision_df.empty:
        return pd.DataFrame()

    m = request_df.merge(
        decision_df,
        on=["policy_name", "request_id"],
        how="left",
        suffixes=("_request", "_decision"),
    )

    rows: List[Dict[str, Any]] = []
    for _, r in m.iterrows():
        cache_hit = bool(r.get("cache_hit_request", r.get("cache_hit")))
        decision = r.get("decision")
        keep_alive_req = r.get("keep_alive_window_request")
        keep_alive_dec = r.get("keep_alive_window_decision")

        if pd.isna(decision):
            rows.append({
                "policy_name": r["policy_name"],
                "request_id": r["request_id"],
                "function_name": r.get("function_name_request"),
                "cache_hit": cache_hit,
                "decision": None,
                "match": False,
                "detail": "no matching decision",
            })
            continue

        # 决策一致性
        expected_decision = "extend_keep_alive" if cache_hit else "keep_after_cold_start"
        decision_match = (decision == expected_decision)
        # 保活窗口一致
        window_match = abs(float(keep_alive_req) - float(keep_alive_dec)) < 1e-6 if pd.notna(keep_alive_dec) else False
        match = decision_match and window_match
        detail = "ok" if match else (
            f"decision mismatch: cache_hit={cache_hit} but decision={decision}"
            if not decision_match else "keep_alive_window mismatch"
        )

        rows.append({
            "policy_name": r["policy_name"],
            "request_id": r["request_id"],
            "function_name": r.get("function_name_request"),
            "cache_hit": cache_hit,
            "decision": decision,
            "expected_decision": expected_decision,
            "keep_alive_window": float(keep_alive_req) if pd.notna(keep_alive_req) else None,
            "match": bool(match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_eviction_state_join(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    eviction × policy_decision 关联（论文 demo 关键证据）。

    每次 eviction 之后，policy_decision.warm_keys（这次 request 之后的 warm 集合）
    不应再包含被驱逐的函数（除非又重新 keep 进来）。
    """
    eviction_df = outputs.get("cold_start_eviction", pd.DataFrame())
    decision_df = outputs.get("cold_start_policy_decision", pd.DataFrame())

    if eviction_df.empty or decision_df.empty:
        return pd.DataFrame()

    if "warm_keys" not in decision_df.columns:
        return pd.DataFrame()

    # 按 policy_name 关联每个 eviction 跟"同时间点或之后的第一个 decision"
    rows: List[Dict[str, Any]] = []
    for policy_name in eviction_df["policy_name"].unique():
        sub_ev = eviction_df[eviction_df.policy_name == policy_name].sort_values("time")
        sub_dec = decision_df[decision_df.policy_name == policy_name].sort_values("time")
        if sub_dec.empty:
            continue
        for _, ev_row in sub_ev.iterrows():
            ev_time = float(ev_row["time"])
            # 找时间 >= ev_time 的第一个 decision
            future = sub_dec[sub_dec["time"] >= ev_time]
            if future.empty:
                continue
            next_dec = future.iloc[0]
            warm_keys_str = str(next_dec.get("warm_keys", ""))
            warm_keys_set = set(warm_keys_str.split(";")) if warm_keys_str else set()
            evicted = str(ev_row["evicted_function"])
            # 被驱逐的函数不应在这次 decision 之后的 warm_keys 里
            # 但如果这次 request 触发了 keep_after_cold_start 又把该函数 keep 进来，OK
            not_in_keys = evicted not in warm_keys_set
            rows.append({
                "policy_name": policy_name,
                "ev_time": ev_time,
                "evicted_function": evicted,
                "ev_reason": ev_row.get("reason"),
                "next_dec_warm_keys": warm_keys_str,
                "match": bool(not_in_keys),
            })
    return pd.DataFrame(rows)


def build_paper_highlight(
    policy_summary_df: pd.DataFrame,
    request_decision_join_df: pd.DataFrame,
    eviction_state_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要。

    cold_start_aware_policy 样例跟 17 一样：trace 驱动的缓存算法实验。
    论文 demo 关注的是：
    1. 策略命中率：cold_start_aware vs fixed_keep_alive
    2. 平均延迟：cold_start_aware 是不是更优
    3. 冷启动惩罚降低：cold_start_aware 命中率高 → 冷启动惩罚低
    4. request×decision 一致性：cache_hit 跟 decision 映射正确
    5. eviction 跟 state 一致性：每次 eviction 后 cache_used 跟紧邻的 decision 一致

    以 fixed_keep_alive 为 baseline，cold_start_aware 是优化版。
    """
    rows: List[Dict[str, Any]] = []

    if policy_summary_df.empty:
        return pd.DataFrame(rows)

    # 1. 每 policy 关键指标
    for _, srow in policy_summary_df.iterrows():
        policy = srow["policy_name"]
        rows.append({
            "metric": f"hit_rate__{policy}",
            "value": float(srow["hit_rate"]),
        })
        rows.append({
            "metric": f"avg_latency__{policy}",
            "value": float(srow["avg_latency"]),
        })
        rows.append({
            "metric": f"total_cold_start_penalty__{policy}",
            "value": float(srow["total_cold_start_penalty"]),
        })
        rows.append({
            "metric": f"avg_keep_alive_window__{policy}",
            "value": float(srow["avg_keep_alive_window"]),
        })
        rows.append({
            "metric": f"eviction_count__{policy}",
            "value": int(srow["eviction_count"]),
        })

    # 2. 策略相对提升（以 fixed_keep_alive 为 baseline）
    baseline = "fixed_keep_alive"
    base_row = policy_summary_df[policy_summary_df.policy_name == baseline]
    if not base_row.empty:
        base_row = base_row.iloc[0]
        base_hit = float(base_row["hit_rate"])
        base_latency = float(base_row["avg_latency"])
        base_cold = float(base_row["total_cold_start_penalty"])
        base_window = float(base_row["avg_keep_alive_window"])

        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            if policy == baseline:
                continue
            hit_rate = float(srow["hit_rate"])
            latency = float(srow["avg_latency"])
            cold = float(srow["total_cold_start_penalty"])
            window = float(srow["avg_keep_alive_window"])

            # 命中率绝对差
            rows.append({
                "metric": f"hit_rate_improvement__{policy}_over_{baseline}",
                "value": float(hit_rate - base_hit),
            })
            # 命中率倍数
            if base_hit > 0:
                rows.append({
                    "metric": f"hit_rate_ratio__{policy}_over_{baseline}",
                    "value": float(hit_rate / base_hit),
                })
            # 延迟相对降低
            if base_latency > 0:
                rows.append({
                    "metric": f"latency_reduction__{policy}_over_{baseline}",
                    "value": float((base_latency - latency) / base_latency),
                })
            # 冷启动惩罚相对降低
            if base_cold > 0:
                rows.append({
                    "metric": f"cold_start_penalty_reduction__{policy}_over_{baseline}",
                    "value": float((base_cold - cold) / base_cold),
                })
            # 平均 keep-alive window 差异
            rows.append({
                "metric": f"avg_keep_alive_window_diff__{policy}_over_{baseline}",
                "value": float(window - base_window),
            })

    # 3. request×decision 一致性
    if not request_decision_join_df.empty and "match" in request_decision_join_df.columns:
        n = len(request_decision_join_df)
        matched = int(request_decision_join_df["match"].sum())
        rows.append({
            "metric": "request_decision_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "request_decision_matched",
            "value": matched,
        })
        rows.append({
            "metric": "request_decision_total",
            "value": n,
        })

    # 4. eviction 跟 state 一致性
    if not eviction_state_join_df.empty and "match" in eviction_state_join_df.columns:
        n = len(eviction_state_join_df)
        matched = int(eviction_state_join_df["match"].sum())
        rows.append({
            "metric": "eviction_state_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "eviction_state_matched",
            "value": matched,
        })
        rows.append({
            "metric": "eviction_state_total",
            "value": n,
        })

    return pd.DataFrame(rows)


def self_check(
    outputs: Dict[str, pd.DataFrame],
    policy_summary_df: pd.DataFrame,
    function_summary_df: pd.DataFrame,
    request_decision_join_df: pd.DataFrame,
    eviction_state_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    expected_request_count: int,
    n_policies: int,
) -> Dict[str, Any]:
    """
    数据自洽段（cold_start_aware_policy 10 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    request_df = outputs.get("cold_start_request_result", pd.DataFrame())
    decision_df = outputs.get("cold_start_policy_decision", pd.DataFrame())
    eviction_df = outputs.get("cold_start_eviction", pd.DataFrame())

    # 1. request 行数 = n_policies × expected_request_count
    n_req = len(request_df)
    expected = n_policies * expected_request_count
    checks.append({
        "name": "request_result_row_count",
        "status": "PASS" if n_req == expected else "FAIL",
        "detail": f"requests={n_req}, expected={expected}",
    })

    # 2. decision 行数 == request 行数
    n_dec = len(decision_df)
    checks.append({
        "name": "policy_decision_row_count",
        "status": "PASS" if n_dec == n_req else "FAIL",
        "detail": f"decisions={n_dec}, requests={n_req}",
    })

    # 3. policy_summary 行数 == n_policies
    n_summary = len(policy_summary_df)
    checks.append({
        "name": "policy_summary_row_count",
        "status": "PASS" if n_summary == n_policies else "FAIL",
        "detail": f"summary rows={n_summary}, expected={n_policies}",
    })

    # 4. policy_summary per-policy request_count == expected_request_count
    if not policy_summary_df.empty and "request_count" in policy_summary_df.columns:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            rc = int(srow["request_count"])
            checks.append({
                "name": f"policy_request_count__{policy}",
                "status": "PASS" if rc == expected_request_count else "FAIL",
                "detail": f"request_count={rc}, expected={expected_request_count}",
            })

    # 5. function_summary per-policy 求和 == expected_request_count
    if not function_summary_df.empty:
        for policy in function_summary_df["policy_name"].unique():
            sub = function_summary_df[function_summary_df.policy_name == policy]
            total = int(sub["request_count"].sum())
            checks.append({
                "name": f"function_summary_total_requests__{policy}",
                "status": "PASS" if total == expected_request_count else "FAIL",
                "detail": f"sum={total}, expected={expected_request_count}",
            })

    # 6. request×decision join 100% match
    if not request_decision_join_df.empty and "match" in request_decision_join_df.columns:
        n = len(request_decision_join_df)
        matched = int(request_decision_join_df["match"].sum())
        checks.append({
            "name": "request_decision_consistency",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 7. eviction 跟 state 100% match
    if not eviction_state_join_df.empty and "match" in eviction_state_join_df.columns:
        n = len(eviction_state_join_df)
        matched = int(eviction_state_join_df["match"].sum())
        checks.append({
            "name": "eviction_state_consistency",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 8. paper highlight 里 hit_rate 跟 policy_summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"hit_rate__{policy}"
            ]
            if hl_rows.empty:
                continue
            hl_v = float(hl_rows["value"].iloc[0])
            summary_v = float(srow["hit_rate"])
            checks.append({
                "name": f"paper_highlight_hit_rate__{policy}",
                "status": "PASS" if abs(hl_v - summary_v) < 1e-6 else "FAIL",
                "detail": f"summary={summary_v:.6f}, highlight={hl_v:.6f}",
            })

    # 9. paper highlight 里 hit_rate_ratio 跟 summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "hit_rate_ratio__cold_start_aware_over_fixed_keep_alive"
        ]
        if not hl_rows.empty:
            aware = policy_summary_df[policy_summary_df.policy_name == "cold_start_aware"]
            fixed = policy_summary_df[policy_summary_df.policy_name == "fixed_keep_alive"]
            if not aware.empty and not fixed.empty:
                hl_v = float(hl_rows["value"].iloc[0])
                expected_v = float(aware["hit_rate"].iloc[0] / fixed["hit_rate"].iloc[0])
                checks.append({
                    "name": "paper_highlight_hit_rate_ratio",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                    "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
                })

    # 10. cold_start_aware 命中率应该 >= fixed_keep_alive
    if not policy_summary_df.empty and "policy_name" in policy_summary_df.columns:
        aware = policy_summary_df[policy_summary_df.policy_name == "cold_start_aware"]
        fixed = policy_summary_df[policy_summary_df.policy_name == "fixed_keep_alive"]
        if not aware.empty and not fixed.empty:
            aware_hit = float(aware["hit_rate"].iloc[0])
            fixed_hit = float(fixed["hit_rate"].iloc[0])
            checks.append({
                "name": "cold_start_aware_beats_fixed_keep_alive",
                "status": "PASS" if aware_hit >= fixed_hit else "FAIL",
                "detail": f"cold_start_aware={aware_hit:.4f}, fixed={fixed_hit:.4f} (cold_start_aware 应 >= fixed)",
            })

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {"checks": checks, "n_pass": n_pass, "n_fail": n_fail}


def log_self_check(self_check_result: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log。
    """
    checks = self_check_result.get("checks") or []
    if not checks:
        return

    logger.info("=== cold_start_aware_policy self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出策略实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_summary_df = build_policy_summary(outputs)
    function_summary_df = build_function_summary(outputs)
    decision_summary_df = build_decision_summary(outputs)

    # request×decision 关联
    request_decision_join_df = build_request_decision_join(outputs)

    # eviction×state 关联
    eviction_state_join_df = build_eviction_state_join(outputs)

    # 论文 demo 关键摘要
    paper_highlight_df = build_paper_highlight(
        policy_summary_df, request_decision_join_df, eviction_state_join_df,
    )

    # 数据自洽段
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())
    if not request_df.empty and "policy_name" in request_df.columns:
        n_policies = int(request_df["policy_name"].nunique())
        n_requests = int(len(request_df) // n_policies) if n_policies else 0
    else:
        n_policies = 0
        n_requests = 0

    self_check_result = self_check(
        outputs, policy_summary_df, function_summary_df,
        request_decision_join_df, eviction_state_join_df, paper_highlight_df,
        n_requests, n_policies,
    )
    log_self_check(self_check_result)

    outputs = dict(outputs)
    outputs["cold_start_policy_summary"] = policy_summary_df
    outputs["cold_start_function_summary"] = function_summary_df
    outputs["cold_start_decision_summary"] = decision_summary_df
    outputs["cold_start_request_decision_join"] = request_decision_join_df
    outputs["cold_start_eviction_state_join"] = eviction_state_join_df
    outputs["cold_start_policy_paper_highlight"] = paper_highlight_df

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
