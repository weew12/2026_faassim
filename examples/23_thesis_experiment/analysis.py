"""
文件作用：论文实验结果导出与分析。

负责生成：
- thesis_request_result / thesis_control_decision / thesis_candidate_score / thesis_eviction_event（原始）
- thesis_policy_summary / thesis_function_summary / thesis_phase_summary / thesis_control_summary（基础摘要）
- thesis_baseline_comparison（以 LoadOnly 为 baseline 的相对改进）
- thesis_result_candidate_join（论文 demo 关键证据）
- thesis_paper_highlight（论文 demo 关键摘要）
- 数据自洽段（23 个不变量）
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())
    evict_df = outputs.get("thesis_eviction_event", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    summary = (
        df
        .groupby(["case_id", "policy_name"])
        .agg(
            request_count=("request_id", "count"),
            warm_hits=("warm_hit", "sum"),
            warm_misses=("warm_hit", lambda s: int((~s.astype(bool)).sum())),
            image_cache_hits=("image_cache_hit", "sum"),
            data_cache_hits=("data_cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            p95_latency=("latency", lambda s: float(s.quantile(0.95))),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            total_image_pull_penalty=("image_pull_penalty", "sum"),
            total_data_fetch_penalty=("data_fetch_penalty", "sum"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            avg_cache_used=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(
            warm_hit_rate=lambda x: x["warm_hits"] / x["request_count"],
            image_cache_hit_rate=lambda x: x["image_cache_hits"] / x["request_count"],
            data_cache_hit_rate=lambda x: x["data_cache_hits"] / x["request_count"],
        )
    )

    if not evict_df.empty:
        evict_summary = (
            evict_df
            .groupby(["case_id", "policy_name"])
            .agg(eviction_count=("evicted_function", "count"))
            .reset_index()
        )
        summary = summary.merge(evict_summary, on=["case_id", "policy_name"], how="left")
    else:
        summary["eviction_count"] = 0

    summary["eviction_count"] = summary["eviction_count"].fillna(0).astype(int)
    return summary


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成函数级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            warm_hit_rate=("warm_hit", "mean"),
            avg_latency=("latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_cache_utility=("cache_utility", "mean"),
            max_r_desired=("r_desired", "max"),
        )
        .reset_index()
    )


def build_phase_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成阶段级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "phase"])
        .agg(
            request_count=("request_id", "count"),
            warm_hit_rate=("warm_hit", "mean"),
            avg_latency=("latency", "mean"),
            p95_latency=("latency", lambda s: float(s.quantile(0.95))),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
    )


def build_control_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成控制动作摘要。
    """
    df = outputs.get("thesis_control_decision", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "action", "reason"])
        .agg(
            events=("request_id", "count"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            avg_cache_utility=("cache_utility", "mean"),
        )
        .reset_index()
    )


def build_baseline_comparison(policy_summary: pd.DataFrame) -> pd.DataFrame:
    """
    以 LoadOnly 为基线生成相对改进表。
    """
    if policy_summary.empty or "load_only" not in set(policy_summary["case_id"]):
        return pd.DataFrame()

    baseline = policy_summary[policy_summary["case_id"] == "load_only"].iloc[0]
    rows = []

    for row in policy_summary.itertuples(index=False):
        rows.append({
            "case_id": row.case_id,
            "policy_name": row.policy_name,
            "avg_latency": row.avg_latency,
            "avg_latency_change_vs_load_only": safe_ratio(baseline.avg_latency - row.avg_latency, baseline.avg_latency),
            "total_cold_start_penalty": row.total_cold_start_penalty,
            "cold_start_reduction_vs_load_only": safe_ratio(
                baseline.total_cold_start_penalty - row.total_cold_start_penalty,
                baseline.total_cold_start_penalty,
            ),
            "warm_hit_rate": row.warm_hit_rate,
            "warm_hit_rate_delta_vs_load_only": row.warm_hit_rate - baseline.warm_hit_rate,
        })

    return pd.DataFrame(rows)


def safe_ratio(numerator: float, denominator: float) -> float:
    """
    安全比例计算。
    """
    if abs(denominator) < 1e-9:
        return 0.0
    return numerator / denominator


def build_result_candidate_join(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    result × candidate_score 关联（论文 demo 关键证据）。

    每个 (case_id, policy_name, request_id) 对应一条 result + 若干条 candidate 评分。
    验证：
    - candidate 评分里 selected_node 的 total_score 是该 request 所有 candidate 的最大
    - 选中的 candidate 的 warm_hit / image_cache_hit / data_cache_hit 跟 result 一致
    - 选中的 candidate 的 estimated_latency 跟 result 的 latency 接近
    """
    result_df = outputs.get("thesis_request_result", pd.DataFrame())
    candidate_df = outputs.get("thesis_candidate_score", pd.DataFrame())

    if result_df.empty or candidate_df.empty:
        return pd.DataFrame()

    m = result_df.merge(
        candidate_df,
        on=["case_id", "policy_name", "request_id"],
        how="left",
        suffixes=("_result", "_candidate"),
    )

    rows: List[Dict[str, Any]] = []
    for (case_id, policy, req_id), group in m.groupby(["case_id", "policy_name", "request_id"]):
        if "selected_node" not in group.columns:
            continue
        result_row = group[group["selected_node"].notna()].iloc[0] if not group[group["selected_node"].notna()].empty else None
        if result_row is None:
            continue
        selected_node = result_row.get("selected_node")
        # candidate 字段名
        cand_node_col = "candidate_node" if "candidate_node" in group.columns else "node_name"
        if cand_node_col not in group.columns:
            continue
        sel_cand = group[group[cand_node_col] == selected_node]
        if sel_cand.empty:
            continue
        sel_cand_row = sel_cand.iloc[0]
        # total_score 在 suffix 后叫 total_score_candidate
        score_col = "total_score_candidate" if "total_score_candidate" in group.columns else "total_score"
        if score_col not in group.columns:
            continue
        max_score = group[score_col].max()
        # 只有 cache_aware_joint 严格要求 max-score（faascache / load_only 不一定选 max-score）
        is_max = abs(float(sel_cand_row[score_col]) - float(max_score)) < 1e-6
        require_max = (case_id == "cache_aware_joint")

        result_warm = bool(result_row.get("warm_hit"))
        cand_warm = bool(sel_cand_row.get("warm_hit"))
        warm_match = (result_warm == cand_warm)

        result_image = bool(result_row.get("image_cache_hit"))
        cand_image = bool(sel_cand_row.get("image_cache_hit"))
        image_match = (result_image == cand_image)

        result_data = bool(result_row.get("data_cache_hit"))
        cand_data = bool(sel_cand_row.get("data_cache_hit"))
        data_match = (result_data == cand_data)

        result_latency = float(result_row.get("latency"))
        # candidate 里可能叫 estimated_latency
        cand_lat_col = "estimated_latency" if "estimated_latency" in sel_cand_row.index else "latency"
        cand_latency = float(sel_cand_row.get(cand_lat_col, result_latency))
        # latency 允许 1e-3 误差（浮点累加）
        latency_match = abs(result_latency - cand_latency) < 0.01

        # match 条件：cache_hit / image / data / latency 一致；
        # 如果 require_max（cache_aware_joint），还要求 is_max
        match = warm_match and image_match and data_match and latency_match and (is_max if require_max else True)
        if not match:
            detail_parts = []
            if require_max and not is_max:
                detail_parts.append(f"not max-score: {sel_cand_row[score_col]} vs max {max_score}")
            if not warm_match:
                detail_parts.append(f"warm_hit mismatch: result={result_warm} cand={cand_warm}")
            if not image_match:
                detail_parts.append(f"image mismatch: result={result_image} cand={cand_image}")
            if not data_match:
                detail_parts.append(f"data mismatch: result={result_data} cand={cand_data}")
            if not latency_match:
                detail_parts.append(f"latency mismatch: result={result_latency} cand={cand_latency}")
            detail = "; ".join(detail_parts)
        else:
            detail = "ok"

        rows.append({
            "case_id": case_id,
            "policy_name": policy,
            "request_id": req_id,
            "function_name": result_row.get("function_name"),
            "selected_node": selected_node,
            "selected_total_score": float(sel_cand_row[score_col]),
            "max_total_score": float(max_score),
            "result_warm_hit": result_warm,
            "result_image_cache_hit": result_image,
            "result_data_cache_hit": result_data,
            "result_latency": result_latency,
            "match": bool(match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_request_decision_join(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    request × control_decision 关联（论文 demo 关键证据）。

    每个 (case_id, policy_name, request_id) 对应一条 result + 一条 control_decision。
    验证：
    - 两者 r_desired 一致
    - 两者 r_cache 一致
    - 两者 r_load 一致
    """
    result_df = outputs.get("thesis_request_result", pd.DataFrame())
    decision_df = outputs.get("thesis_control_decision", pd.DataFrame())

    if result_df.empty or decision_df.empty:
        return pd.DataFrame()

    m = result_df.merge(
        decision_df,
        on=["case_id", "policy_name", "request_id"],
        how="left",
        suffixes=("_result", "_decision"),
    )

    rows: List[Dict[str, Any]] = []
    for _, r in m.iterrows():
        # result 的 r_cache / r_load / r_desired 可能在 suffix 改名
        r_desired_result = r.get("r_desired_result", r.get("r_desired"))
        r_desired_decision = r.get("r_desired_decision", r.get("r_desired"))
        r_cache_result = r.get("r_cache_result", r.get("r_cache"))
        r_cache_decision = r.get("r_cache_decision", r.get("r_cache"))
        r_load_result = r.get("r_load_result", r.get("r_load"))
        r_load_decision = r.get("r_load_decision", r.get("r_load"))

        if pd.isna(r_desired_decision):
            continue

        r_desired_match = abs(float(r_desired_result) - float(r_desired_decision)) < 1e-6
        r_cache_match = abs(float(r_cache_result) - float(r_cache_decision)) < 1e-6
        r_load_match = abs(float(r_load_result) - float(r_load_decision)) < 1e-6

        match = r_desired_match and r_cache_match and r_load_match
        if not match:
            detail_parts = []
            if not r_desired_match:
                detail_parts.append(f"r_desired: result={r_desired_result} decision={r_desired_decision}")
            if not r_cache_match:
                detail_parts.append(f"r_cache: result={r_cache_result} decision={r_cache_decision}")
            if not r_load_match:
                detail_parts.append(f"r_load: result={r_load_result} decision={r_load_decision}")
            detail = "; ".join(detail_parts)
        else:
            detail = "ok"

        rows.append({
            "case_id": r["case_id"],
            "policy_name": r["policy_name"],
            "request_id": r["request_id"],
            "result_r_desired": float(r_desired_result) if pd.notna(r_desired_result) else None,
            "decision_r_desired": float(r_desired_decision) if pd.notna(r_desired_decision) else None,
            "result_r_cache": float(r_cache_result) if pd.notna(r_cache_result) else None,
            "decision_r_cache": float(r_cache_decision) if pd.notna(r_cache_decision) else None,
            "result_r_load": float(r_load_result) if pd.notna(r_load_result) else None,
            "decision_r_load": float(r_load_decision) if pd.notna(r_load_decision) else None,
            "match": bool(match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_paper_highlight(
    policy_summary_df: pd.DataFrame,
    result_candidate_join_df: pd.DataFrame,
    request_decision_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要（含 note 列，沿用 02-22 模式）。

    thesis_experiment 是论文实验的最终 demo，论文 demo 关注的是：
    1. CacheAwareJoint vs FaasCache vs LoadOnly 三方对比
    2. R_cache vs R_load 主导分析（CacheAwareJoint 是 R_cache 主导吗？）
    3. 三个缓存维度命中率
    4. result×candidate 一致性
    5. request×decision 一致性
    """
    rows: List[Dict[str, Any]] = []

    if policy_summary_df.empty:
        return pd.DataFrame(columns=["metric", "value", "note"])

    # 1. per-case 关键指标
    for _, srow in policy_summary_df.iterrows():
        case = srow["case_id"]
        policy = srow["policy_name"]
        rows.append({
            "metric": f"warm_hit_rate__{case}",
            "value": float(srow["warm_hit_rate"]),
            "note": f"{case} ({policy}) 函数 warm 实例命中率（论文 demo 关键指标）",
        })
        rows.append({
            "metric": f"image_cache_hit_rate__{case}",
            "value": float(srow["image_cache_hit_rate"]),
            "note": f"{case} 镜像缓存命中率（避免镜像拉取）",
        })
        rows.append({
            "metric": f"data_cache_hit_rate__{case}",
            "value": float(srow["data_cache_hit_rate"]),
            "note": f"{case} 数据缓存命中率（避免数据获取）",
        })
        rows.append({
            "metric": f"avg_latency__{case}",
            "value": float(srow["avg_latency"]),
            "note": f"{case} 平均每次 invoke latency",
        })
        rows.append({
            "metric": f"p95_latency__{case}",
            "value": float(srow["p95_latency"]),
            "note": f"{case} p95 latency（论文 demo 重要 tail-latency 指标）",
        })
        rows.append({
            "metric": f"total_cold_start_penalty__{case}",
            "value": float(srow["total_cold_start_penalty"]),
            "note": f"{case} 全部冷启动惩罚累加",
        })
        rows.append({
            "metric": f"avg_r_cache__{case}",
            "value": float(srow["avg_r_cache"]),
            "note": f"{case} 平均 R_cache（cache 驱动的副本需求）",
        })
        rows.append({
            "metric": f"avg_r_load__{case}",
            "value": float(srow["avg_r_load"]),
            "note": f"{case} 平均 R_load（负载驱动的副本需求）",
        })
        rows.append({
            "metric": f"avg_r_desired__{case}",
            "value": float(srow["avg_r_desired"]),
            "note": f"{case} 平均 R_desired = max(R_cache, R_load)",
        })
        rows.append({
            "metric": f"eviction_count__{case}",
            "value": int(srow["eviction_count"]),
            "note": f"{case} 全部 evict 事件数",
        })

    # 2. CacheAwareJoint vs LoadOnly / FaasCache
    cache_aware = policy_summary_df[policy_summary_df.case_id == "cache_aware_joint"]
    faascache = policy_summary_df[policy_summary_df.case_id == "faascache"]
    load_only = policy_summary_df[policy_summary_df.case_id == "load_only"]

    if not cache_aware.empty and not load_only.empty:
        ca_row = cache_aware.iloc[0]
        lo_row = load_only.iloc[0]
        # latency 相对降低
        if float(lo_row["avg_latency"]) > 0:
            rows.append({
                "metric": "avg_latency_reduction__cache_aware_joint_vs_load_only",
                "value": float((float(lo_row["avg_latency"]) - float(ca_row["avg_latency"])) / float(lo_row["avg_latency"])),
                "note": "CacheAwareJoint 相对 LoadOnly 平均延迟降低比例（论文 demo 关键数字）",
            })
        # cold_start 相对降低
        if float(lo_row["total_cold_start_penalty"]) > 0:
            rows.append({
                "metric": "cold_start_penalty_reduction__cache_aware_joint_vs_load_only",
                "value": float((float(lo_row["total_cold_start_penalty"]) - float(ca_row["total_cold_start_penalty"])) / float(lo_row["total_cold_start_penalty"])),
                "note": "CacheAwareJoint 相对 LoadOnly 冷启动惩罚降低比例（论文 demo 关键数字）",
            })
        # image_cache_hit_rate 提升
        rows.append({
            "metric": "image_cache_hit_rate_improvement__cache_aware_joint_vs_load_only",
            "value": float(float(ca_row["image_cache_hit_rate"]) - float(lo_row["image_cache_hit_rate"])),
            "note": "CacheAwareJoint 相对 LoadOnly 镜像缓存命中率提升",
        })
        # data_cache_hit_rate 提升
        rows.append({
            "metric": "data_cache_hit_rate_improvement__cache_aware_joint_vs_load_only",
            "value": float(float(ca_row["data_cache_hit_rate"]) - float(lo_row["data_cache_hit_rate"])),
            "note": "CacheAwareJoint 相对 LoadOnly 数据缓存命中率提升",
        })

    if not cache_aware.empty and not faascache.empty:
        ca_row = cache_aware.iloc[0]
        fc_row = faascache.iloc[0]
        # CacheAwareJoint vs FaasCache
        if float(fc_row["avg_latency"]) > 0:
            rows.append({
                "metric": "avg_latency_reduction__cache_aware_joint_vs_faascache",
                "value": float((float(fc_row["avg_latency"]) - float(ca_row["avg_latency"])) / float(fc_row["avg_latency"])),
                "note": "CacheAwareJoint 相对 FaasCache 平均延迟降低比例（论文 demo 关键证据：cache-aware 调度胜出）",
            })
        rows.append({
            "metric": "image_cache_hit_rate_improvement__cache_aware_joint_vs_faascache",
            "value": float(float(ca_row["image_cache_hit_rate"]) - float(fc_row["image_cache_hit_rate"])),
            "note": "CacheAwareJoint 相对 FaasCache 镜像缓存命中率提升",
        })
        rows.append({
            "metric": "data_cache_hit_rate_improvement__cache_aware_joint_vs_faascache",
            "value": float(float(ca_row["data_cache_hit_rate"]) - float(fc_row["data_cache_hit_rate"])),
            "note": "CacheAwareJoint 相对 FaasCache 数据缓存命中率提升",
        })

    # 3. R_cache vs R_load 主导分析（数值 metric，便于 fig04 解析；字符串描述由 avg_r_cache/r_load/desired 三个 metric 共同提供）
    if not cache_aware.empty:
        ca_row = cache_aware.iloc[0]
        r_cache = float(ca_row["avg_r_cache"])
        r_load = float(ca_row["avg_r_load"])
        rows.append({
            "metric": "r_dominant_max__cache_aware_joint",
            "value": float(max(r_cache, r_load)),
            "note": "CacheAwareJoint R_dominant = max(avg_r_cache, avg_r_load)",
        })
        rows.append({
            "metric": "r_dominant_source__cache_aware_joint",
            "value": float(1.0 if r_load >= r_cache else 0.0),
            "note": "CacheAwareJoint R_dominant 来源（1=R_load, 0=R_cache）",
        })

    if not load_only.empty:
        lo_row = load_only.iloc[0]
        r_cache = float(lo_row["avg_r_cache"])
        r_load = float(lo_row["avg_r_load"])
        rows.append({
            "metric": "r_dominant_max__load_only",
            "value": float(max(r_cache, r_load)),
            "note": "LoadOnly R_dominant = max(avg_r_cache, avg_r_load)（应 = avg_r_load）",
        })
        rows.append({
            "metric": "r_dominant_source__load_only",
            "value": float(1.0 if r_load >= r_cache else 0.0),
            "note": "LoadOnly R_dominant 来源（应 = 1 R_load）",
        })

    if not faascache.empty:
        fc_row = faascache.iloc[0]
        r_cache = float(fc_row["avg_r_cache"])
        r_load = float(fc_row["avg_r_load"])
        rows.append({
            "metric": "r_dominant_max__faascache",
            "value": float(max(r_cache, r_load)),
            "note": "FaasCache R_dominant = max(avg_r_cache, avg_r_load)（应 = avg_r_cache）",
        })
        rows.append({
            "metric": "r_dominant_source__faascache",
            "value": float(1.0 if r_load >= r_cache else 0.0),
            "note": "FaasCache R_dominant 来源（应 = 0 R_cache）",
        })

    # 4. result×candidate 一致性
    if not result_candidate_join_df.empty and "match" in result_candidate_join_df.columns:
        n = len(result_candidate_join_df)
        matched = int(result_candidate_join_df["match"].sum())
        rows.append({
            "metric": "result_candidate_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
            "note": "result × candidate join match 占比（论文 demo 关键证据，应 1.0）",
        })
        rows.append({
            "metric": "result_candidate_matched",
            "value": matched,
            "note": "matched 行数",
        })
        rows.append({
            "metric": "result_candidate_total",
            "value": n,
            "note": "join 总行数（应 == 3 case × 35 request = 105）",
        })

    # 5. request×decision 一致性
    if not request_decision_join_df.empty and "match" in request_decision_join_df.columns:
        n = len(request_decision_join_df)
        matched = int(request_decision_join_df["match"].sum())
        rows.append({
            "metric": "request_decision_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
            "note": "request × decision join match 占比（论文 demo 关键证据，应 1.0）",
        })
        rows.append({
            "metric": "request_decision_matched",
            "value": matched,
            "note": "matched 行数",
        })
        rows.append({
            "metric": "request_decision_total",
            "value": n,
            "note": "join 总行数（应 == 3 case × 35 request = 105）",
        })

    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def self_check(
    outputs: Dict[str, pd.DataFrame],
    policy_summary_df: pd.DataFrame,
    baseline_comparison_df: pd.DataFrame,
    result_candidate_join_df: pd.DataFrame,
    request_decision_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    expected_request_count: int,
    n_cases: int,
) -> Dict[str, Any]:
    """
    数据自洽段（thesis_experiment 23 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    result_df = outputs.get("thesis_request_result", pd.DataFrame())
    candidate_df = outputs.get("thesis_candidate_score", pd.DataFrame())
    decision_df = outputs.get("thesis_control_decision", pd.DataFrame())

    # 1. request_result 行数 = n_cases × expected_request_count
    n_result = len(result_df)
    expected = n_cases * expected_request_count
    checks.append({
        "name": "request_result_row_count",
        "status": "PASS" if n_result == expected else "FAIL",
        "detail": f"requests={n_result}, expected={expected} ({n_cases} cases × {expected_request_count} requests)",
    })

    # 2. candidate 行数 > result 行数
    n_cand = len(candidate_df)
    checks.append({
        "name": "candidate_score_count",
        "status": "PASS" if n_cand > n_result else "FAIL",
        "detail": f"candidates={n_cand}, requests={n_result}",
    })

    # 3. 每个 (case, policy, request) 的候选节点数一致
    if not candidate_df.empty:
        candidate_group_sizes = candidate_df.groupby(["case_id", "policy_name", "request_id"]).size()
        expected_candidates_per_request = int(candidate_group_sizes.iloc[0]) if not candidate_group_sizes.empty else 0
        consistent = bool((candidate_group_sizes == expected_candidates_per_request).all())
        checks.append({
            "name": "candidate_count_per_request_consistent",
            "status": "PASS" if consistent else "FAIL",
            "detail": f"candidate groups={len(candidate_group_sizes)}, candidates per request={expected_candidates_per_request}",
        })

    # 4. policy_summary 行数 = n_cases
    n_summary = len(policy_summary_df)
    checks.append({
        "name": "policy_summary_row_count",
        "status": "PASS" if n_summary == n_cases else "FAIL",
        "detail": f"summary rows={n_summary}, expected={n_cases}",
    })

    # 5. policy_summary per-case request_count == expected_request_count
    if not policy_summary_df.empty and "request_count" in policy_summary_df.columns:
        for _, srow in policy_summary_df.iterrows():
            case = srow["case_id"]
            rc = int(srow["request_count"])
            checks.append({
                "name": f"case_request_count__{case}",
                "status": "PASS" if rc == expected_request_count else "FAIL",
                "detail": f"request_count={rc}, expected={expected_request_count}",
            })

    # 6. baseline_comparison 行数 = n_cases
    n_baseline = len(baseline_comparison_df)
    checks.append({
        "name": "baseline_comparison_row_count",
        "status": "PASS" if n_baseline == n_cases else "FAIL",
        "detail": f"baseline rows={n_baseline}, expected={n_cases}",
    })

    # 7. baseline_comparison 必须包含 load_only 行
    if not baseline_comparison_df.empty and "case_id" in baseline_comparison_df.columns:
        has_load_only = "load_only" in set(baseline_comparison_df["case_id"])
        checks.append({
            "name": "baseline_comparison_has_load_only",
            "status": "PASS" if has_load_only else "FAIL",
            "detail": f"case_ids={list(baseline_comparison_df['case_id'])}",
        })

    # 8. result×candidate join 行数和 request_result 行数一致
    n_result_join = len(result_candidate_join_df)
    checks.append({
        "name": "result_candidate_join_row_count",
        "status": "PASS" if n_result_join == n_result else "FAIL",
        "detail": f"join rows={n_result_join}, requests={n_result}",
    })

    # 9. result×candidate join 100% match（faascache / load_only 不要求 max-score，只 cache_aware_joint 要求）
    if not result_candidate_join_df.empty and "match" in result_candidate_join_df.columns:
        n = len(result_candidate_join_df)
        matched = int(result_candidate_join_df["match"].sum())
        checks.append({
            "name": "result_candidate_join_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 10. cache_aware_joint 的 candidate 是 max-score（核心检查）
    if not result_candidate_join_df.empty and "case_id" in result_candidate_join_df.columns:
        ca = result_candidate_join_df[result_candidate_join_df.case_id == "cache_aware_joint"]
        if not ca.empty:
            n = len(ca)
            matched = int(ca["match"].sum())
            checks.append({
                "name": "cache_aware_joint_candidate_max_score",
                "status": "PASS" if matched == n else "FAIL",
                "detail": f"cache_aware_joint matched={matched}/{n} (must be max-score)",
            })

    # 11. request×decision join 行数和 request_result 行数一致
    n_decision_join = len(request_decision_join_df)
    checks.append({
        "name": "request_decision_join_row_count",
        "status": "PASS" if n_decision_join == n_result else "FAIL",
        "detail": f"join rows={n_decision_join}, requests={n_result}",
    })

    # 12. request×decision join 100% match
    if not request_decision_join_df.empty and "match" in request_decision_join_df.columns:
        n = len(request_decision_join_df)
        matched = int(request_decision_join_df["match"].sum())
        checks.append({
            "name": "request_decision_join_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 13. paper highlight 行数应稳定为 49
    n_paper = len(paper_highlight_df)
    checks.append({
        "name": "paper_highlight_metric_count",
        "status": "PASS" if n_paper == 49 else "FAIL",
        "detail": f"paper_highlight metrics={n_paper}, expected=49",
    })

    # 14. paper highlight 3 个 warm_hit_rate 跟 policy_summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        for _, srow in policy_summary_df.iterrows():
            case = srow["case_id"]
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"warm_hit_rate__{case}"
            ]
            if hl_rows.empty:
                continue
            hl_v = float(hl_rows["value"].iloc[0])
            summary_v = float(srow["warm_hit_rate"])
            checks.append({
                "name": f"paper_highlight_warm_hit_rate__{case}",
                "status": "PASS" if abs(hl_v - summary_v) < 1e-6 else "FAIL",
                "detail": f"summary={summary_v:.6f}, highlight={hl_v:.6f}",
            })

    # 15. paper highlight cache_aware_joint vs load_only 改善值跟 summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        ca = policy_summary_df[policy_summary_df.case_id == "cache_aware_joint"]
        lo = policy_summary_df[policy_summary_df.case_id == "load_only"]
        if not ca.empty and not lo.empty:
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == "image_cache_hit_rate_improvement__cache_aware_joint_vs_load_only"
            ]
            if not hl_rows.empty:
                hl_v = float(hl_rows["value"].iloc[0])
                expected_v = float(ca["image_cache_hit_rate"].iloc[0]) - float(lo["image_cache_hit_rate"].iloc[0])
                checks.append({
                    "name": "paper_highlight_image_cache_improvement",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                    "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
                })

    # 16. cache_aware_joint 命中率 >= faascache >= load_only
    if not policy_summary_df.empty:
        ca = policy_summary_df[policy_summary_df.case_id == "cache_aware_joint"]
        fc = policy_summary_df[policy_summary_df.case_id == "faascache"]
        lo = policy_summary_df[policy_summary_df.case_id == "load_only"]
        if not ca.empty and not fc.empty and not lo.empty:
            ca_warm = float(ca["warm_hit_rate"].iloc[0])
            fc_warm = float(fc["warm_hit_rate"].iloc[0])
            lo_warm = float(lo["warm_hit_rate"].iloc[0])
            order_ok = (ca_warm >= fc_warm) and (fc_warm >= lo_warm)
            checks.append({
                "name": "cache_aware_joint_ge_faascache_ge_load_only",
                "status": "PASS" if order_ok else "FAIL",
                "detail": f"ca={ca_warm:.4f}, fc={fc_warm:.4f}, lo={lo_warm:.4f} (ca >= fc >= lo 期望)",
            })

    # 17. paper highlight result_candidate_consistency == 1.0
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "result_candidate_consistency"
        ]
        if not hl_rows.empty:
            v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_result_candidate_consistency",
                "status": "PASS" if v >= 0.999 else "FAIL",
                "detail": f"result_candidate_consistency={v:.4f}",
            })

    # 18. paper highlight request_decision_consistency == 1.0
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "request_decision_consistency"
        ]
        if not hl_rows.empty:
            v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_request_decision_consistency",
                "status": "PASS" if v >= 0.999 else "FAIL",
                "detail": f"request_decision_consistency={v:.4f}",
            })

    # 19. 导出的 DataFrame 不应包含 pandas 默认索引列
    frames_to_check = {
        "request_result": result_df,
        "candidate_score": candidate_df,
        "control_decision": decision_df,
        "policy_summary": policy_summary_df,
        "baseline_comparison": baseline_comparison_df,
        "result_candidate_join": result_candidate_join_df,
        "request_decision_join": request_decision_join_df,
        "paper_highlight": paper_highlight_df,
    }
    bad_columns = []
    for name, df in frames_to_check.items():
        if df is None or df.empty:
            continue
        unnamed = [col for col in df.columns if str(col).startswith("Unnamed")]
        if unnamed:
            bad_columns.append(f"{name}:{','.join(unnamed)}")
    checks.append({
        "name": "export_tables_have_no_index_column",
        "status": "PASS" if not bad_columns else "FAIL",
        "detail": "no pandas index columns" if not bad_columns else "; ".join(bad_columns),
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

    logger.info("=== thesis_experiment self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出全部实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    result_df = outputs.get("thesis_request_result", pd.DataFrame())
    decision_df = outputs.get("thesis_control_decision", pd.DataFrame())
    candidate_df = outputs.get("thesis_candidate_score", pd.DataFrame())

    policy_summary_df = build_policy_summary(outputs)
    function_summary_df = build_function_summary(outputs)
    phase_summary_df = build_phase_summary(outputs)
    control_summary_df = build_control_summary(outputs)
    baseline_comparison_df = build_baseline_comparison(policy_summary_df)

    # result×candidate join
    result_candidate_join_df = build_result_candidate_join(outputs)
    rc_join_path = output_dir / "thesis_result_candidate_join.csv"
    result_candidate_join_df.to_csv(rc_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", rc_join_path)

    # request×decision join
    request_decision_join_df = build_request_decision_join(outputs)
    rd_join_path = output_dir / "thesis_request_decision_join.csv"
    request_decision_join_df.to_csv(rd_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", rd_join_path)

    # paper highlight
    paper_highlight_df = build_paper_highlight(
        policy_summary_df, result_candidate_join_df, request_decision_join_df,
    )
    ph_path = output_dir / "thesis_paper_highlight.csv"
    paper_highlight_df.to_csv(ph_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", ph_path)

    # 数据自洽段
    if not result_df.empty and "case_id" in result_df.columns:
        n_cases = int(result_df["case_id"].nunique())
        n_requests = int(len(result_df) // n_cases) if n_cases else 0
    else:
        n_cases = 0
        n_requests = 0

    self_check_result = self_check(
        outputs, policy_summary_df, baseline_comparison_df,
        result_candidate_join_df, request_decision_join_df, paper_highlight_df,
        n_requests, n_cases,
    )
    log_self_check(self_check_result)

    # 导出 self_check 结果到 csv（沿用 02-21 模式）
    self_check_path = output_dir / "thesis_experiment_self_check.csv"
    self_check_df = pd.DataFrame(self_check_result.get("checks") or [])
    self_check_df.to_csv(self_check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", self_check_path)

    outputs = dict(outputs)
    outputs["thesis_policy_summary"] = policy_summary_df
    outputs["thesis_function_summary"] = function_summary_df
    outputs["thesis_phase_summary"] = phase_summary_df
    outputs["thesis_control_summary"] = control_summary_df
    outputs["thesis_baseline_comparison"] = baseline_comparison_df
    outputs["thesis_result_candidate_join"] = result_candidate_join_df
    outputs["thesis_request_decision_join"] = request_decision_join_df
    outputs["thesis_paper_highlight"] = paper_highlight_df
    outputs["thesis_experiment_self_check"] = self_check_df
    outputs["self_check_result"] = self_check_result

    for name, df in outputs.items():
        # 跳过 self_check_result 字典（已通过 self_check_df 单独导出）
        if not isinstance(df, pd.DataFrame):
            continue
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    write_report(outputs, output_dir / "thesis_experiment_report.md")
    return outputs


def write_report(outputs: Dict[str, pd.DataFrame], path: Path):
    """
    生成 Markdown 实验报告。
    """
    policy_summary = outputs.get("thesis_policy_summary", pd.DataFrame())
    comparison = outputs.get("thesis_baseline_comparison", pd.DataFrame())
    phase_summary = outputs.get("thesis_phase_summary", pd.DataFrame())
    paper_highlight = outputs.get("thesis_paper_highlight", pd.DataFrame())

    lines = []
    lines.append("# Thesis Experiment Report")
    lines.append("")
    lines.append("## Policy Summary")
    lines.append("")
    lines.append(df_to_markdown(policy_summary))
    lines.append("")
    lines.append("## Comparison with LoadOnly")
    lines.append("")
    lines.append(df_to_markdown(comparison))
    lines.append("")
    lines.append("## Phase Summary")
    lines.append("")
    lines.append(df_to_markdown(phase_summary))
    lines.append("")
    lines.append("## 论文 demo 关键摘要 (Paper Highlight)")
    lines.append("")
    lines.append(df_to_markdown(paper_highlight))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `R_cache` represents cache-driven warm replica demand.")
    lines.append("- `R_load` represents load-driven replica demand.")
    lines.append("- `CacheAwareJoint` combines both terms using `R_desired = max(R_cache, R_load)` and uses cache-aware node scoring.")
    lines.append("- This example is trace-driven and independent from faas-sim core APIs, so it is stable across local source versions.")
    lines.append("- `result_candidate_join` 验证 selected_node 是 max-score node，且 cache_hit 一致")
    lines.append("- `request_decision_join` 验证 result 跟 decision 的 r_cache / r_load / r_desired 一致")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("saved %s", path)


def df_to_markdown(df: pd.DataFrame) -> str:
    """
    DataFrame 转 Markdown；缺失 tabulate 时回退为 CSV 文本。
    """
    if df is None or df.empty:
        return "_No data._"

    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```text\n" + df.to_csv(index=False) + "```"
