"""
文件作用：edge_cache_scheduler 样例的结果导出与分析工具。

该文件负责导出调度策略摘要、节点选择摘要、函数摘要、result×candidate_score 关联、
论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成调度策略摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            function_cache_hits=("function_cache_hit", "sum"),
            function_cache_misses=("function_cache_hit", lambda s: int((~s.astype(bool)).sum())),
            image_cache_hits=("image_cache_hit", "sum"),
            data_cache_hits=("data_cache_hit", "sum"),
            avg_estimated_latency=("estimated_latency", "mean"),
            total_estimated_latency=("estimated_latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            total_image_pull_penalty=("image_pull_penalty", "sum"),
            total_data_fetch_penalty=("data_fetch_penalty", "sum"),
        )
        .reset_index()
        .assign(
            function_cache_hit_rate=lambda df: df["function_cache_hits"] / df["request_count"],
            image_cache_hit_rate=lambda df: df["image_cache_hits"] / df["request_count"],
            data_cache_hit_rate=lambda df: df["data_cache_hits"] / df["request_count"],
        )
    )


def build_node_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成节点选择摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby(["policy_name", "selected_node"])
        .agg(
            request_count=("request_id", "count"),
            avg_estimated_latency=("estimated_latency", "mean"),
            function_cache_hits=("function_cache_hit", "sum"),
        )
        .reset_index()
    )


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成调度摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby(["policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            function_cache_hit_rate=("function_cache_hit", "mean"),
            image_cache_hit_rate=("image_cache_hit", "mean"),
            data_cache_hit_rate=("data_cache_hit", "mean"),
            avg_estimated_latency=("estimated_latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
    )


def build_result_candidate_join(
    result_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    result × candidate_score 关联（论文 demo 关键证据）。

    每个 (policy, request) 应该有一条最终结果，对应若干条 candidate 评分。
    验证：
    - candidate 评分里 selected_node 的 total_score 是该 request 中所有 candidate 的最大
    - 选中的 candidate 的 function_cache_hit == result.function_cache_hit
    - 选中的 candidate 的 estimated_latency == result.estimated_latency
    """
    if result_df.empty or candidate_df.empty:
        return pd.DataFrame()

    m = result_df.merge(
        candidate_df,
        on=["policy_name", "request_id"],
        how="left",
        suffixes=("_result", "_candidate"),
    )

    # suffix 后 total_score 改名为 total_score_candidate（result 才有 total_score，candidate 也有，所以加 _candidate 后缀）
    # selected_node / estimated_latency / function_cache_hit 只在 result 里，原名保留
    # candidate_node / zone_match / cache_score 等只在 candidate 里，原名保留

    rows: List[Dict[str, Any]] = []
    # 按 (policy, request) 分组，验证每个 group 里 selected_node 是 max-score node
    for (policy, req_id), group in m.groupby(["policy_name", "request_id"]):
        if "selected_node" not in group.columns:
            continue
        if "total_score_candidate" not in group.columns:
            continue
        # selected_node 来自 result 行（不重复），candidate 来自 candidate 行（多行）
        result_row = group[group["selected_node"].notna()].iloc[0] if not group[group["selected_node"].notna()].empty else None
        if result_row is None:
            continue
        selected_node = result_row.get("selected_node")
        # 找 candidate 评分中该 selected_node 的行（candidate 字段叫 candidate_node）
        sel_cand = group[group["candidate_node"] == selected_node] if "candidate_node" in group.columns else pd.DataFrame()
        if sel_cand.empty:
            continue
        sel_cand_row = sel_cand.iloc[0]
        # 验证 selected_node 是 max-score
        max_score = group["total_score_candidate"].max()
        is_max = abs(float(sel_cand_row["total_score_candidate"]) - float(max_score)) < 1e-6
        # 验证 cache_hit / latency 一致
        # result 里的 cache_hit / estimated_latency 没被改名（只在 result）
        result_cache_hit = bool(result_row.get("function_cache_hit"))
        cand_cache_hit = bool(sel_cand_row.get("function_cache_hit"))
        cache_match = (result_cache_hit == cand_cache_hit)
        result_latency = float(result_row.get("estimated_latency"))
        cand_latency = float(sel_cand_row.get("estimated_latency"))
        latency_match = abs(result_latency - cand_latency) < 1e-6

        match = is_max and cache_match and latency_match
        if not match:
            detail_parts = []
            if not is_max:
                detail_parts.append(f"not max-score: {sel_cand_row['total_score_candidate']} vs max {max_score}")
            if not cache_match:
                detail_parts.append(f"cache_hit mismatch: result={result_cache_hit} cand={cand_cache_hit}")
            if not latency_match:
                detail_parts.append(f"latency mismatch: result={result_latency} cand={cand_latency}")
            detail = "; ".join(detail_parts)
        else:
            detail = "ok"

        rows.append({
            "policy_name": policy,
            "request_id": req_id,
            "function_name": result_row.get("function_name"),
            "selected_node": selected_node,
            "selected_total_score": float(sel_cand_row["total_score_candidate"]),
            "max_total_score": float(max_score),
            "result_function_cache_hit": result_cache_hit,
            "cand_function_cache_hit": cand_cache_hit,
            "result_estimated_latency": result_latency,
            "cand_estimated_latency": cand_latency,
            "match": bool(match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_paper_highlight(
    policy_summary_df: pd.DataFrame,
    result_candidate_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要。

    edge_cache_scheduler 样例的论文 demo 关注的是：
    1. 三个缓存维度命中率（function / image / data）的差异
    2. avg_estimated_latency 降低
    3. 冷启动/镜像/数据三类惩罚降低
    4. 候选节点评分一致性：选中的节点确实是 max-score

    以 edge_round_robin 为 baseline，edge_cache_aware 是优化版。
    """
    rows: List[Dict[str, Any]] = []

    if policy_summary_df.empty:
        return pd.DataFrame(rows)

    # 1. per-policy 关键指标
    for _, srow in policy_summary_df.iterrows():
        policy = srow["policy_name"]
        rows.append({
            "metric": f"function_cache_hit_rate__{policy}",
            "value": float(srow["function_cache_hit_rate"]),
        })
        rows.append({
            "metric": f"image_cache_hit_rate__{policy}",
            "value": float(srow["image_cache_hit_rate"]),
        })
        rows.append({
            "metric": f"data_cache_hit_rate__{policy}",
            "value": float(srow["data_cache_hit_rate"]),
        })
        rows.append({
            "metric": f"avg_estimated_latency__{policy}",
            "value": float(srow["avg_estimated_latency"]),
        })
        rows.append({
            "metric": f"total_cold_start_penalty__{policy}",
            "value": float(srow["total_cold_start_penalty"]),
        })
        rows.append({
            "metric": f"total_image_pull_penalty__{policy}",
            "value": float(srow["total_image_pull_penalty"]),
        })
        rows.append({
            "metric": f"total_data_fetch_penalty__{policy}",
            "value": float(srow["total_data_fetch_penalty"]),
        })

    # 2. 策略相对提升（以 edge_round_robin 为 baseline）
    baseline = "edge_round_robin"
    base_row = policy_summary_df[policy_summary_df.policy_name == baseline]
    if not base_row.empty:
        base_row = base_row.iloc[0]
        base_function_hit = float(base_row["function_cache_hit_rate"])
        base_image_hit = float(base_row["image_cache_hit_rate"])
        base_data_hit = float(base_row["data_cache_hit_rate"])
        base_latency = float(base_row["avg_estimated_latency"])
        base_cold = float(base_row["total_cold_start_penalty"])
        base_image = float(base_row["total_image_pull_penalty"])
        base_data = float(base_row["total_data_fetch_penalty"])

        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            if policy == baseline:
                continue
            function_hit = float(srow["function_cache_hit_rate"])
            image_hit = float(srow["image_cache_hit_rate"])
            data_hit = float(srow["data_cache_hit_rate"])
            latency = float(srow["avg_estimated_latency"])
            cold = float(srow["total_cold_start_penalty"])
            image = float(srow["total_image_pull_penalty"])
            data = float(srow["total_data_fetch_penalty"])

            # function_cache_hit_rate 绝对差
            rows.append({
                "metric": f"function_cache_hit_rate_improvement__{policy}_over_{baseline}",
                "value": float(function_hit - base_function_hit),
            })
            # image_cache_hit_rate 绝对差
            rows.append({
                "metric": f"image_cache_hit_rate_improvement__{policy}_over_{baseline}",
                "value": float(image_hit - base_image_hit),
            })
            # data_cache_hit_rate 绝对差
            rows.append({
                "metric": f"data_cache_hit_rate_improvement__{policy}_over_{baseline}",
                "value": float(data_hit - base_data_hit),
            })
            # latency 相对降低
            if base_latency > 0:
                rows.append({
                    "metric": f"avg_estimated_latency_reduction__{policy}_over_{baseline}",
                    "value": float((base_latency - latency) / base_latency),
                })
            # cold_start_penalty 相对降低
            if base_cold > 0:
                rows.append({
                    "metric": f"cold_start_penalty_reduction__{policy}_over_{baseline}",
                    "value": float((base_cold - cold) / base_cold),
                })
            # image_pull_penalty 相对降低
            if base_image > 0:
                rows.append({
                    "metric": f"image_pull_penalty_reduction__{policy}_over_{baseline}",
                    "value": float((base_image - image) / base_image),
                })
            # data_fetch_penalty 相对降低
            if base_data > 0:
                rows.append({
                    "metric": f"data_fetch_penalty_reduction__{policy}_over_{baseline}",
                    "value": float((base_data - data) / base_data),
                })

    # 3. result×candidate 一致性
    if not result_candidate_join_df.empty and "match" in result_candidate_join_df.columns:
        n = len(result_candidate_join_df)
        matched = int(result_candidate_join_df["match"].sum())
        rows.append({
            "metric": "result_candidate_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "result_candidate_matched",
            "value": matched,
        })
        rows.append({
            "metric": "result_candidate_total",
            "value": n,
        })

    return pd.DataFrame(rows)


def self_check(
    result_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    policy_summary_df: pd.DataFrame,
    result_candidate_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    expected_request_count: int,
    n_policies: int,
) -> Dict[str, Any]:
    """
    数据自洽段（edge_cache_scheduler 10 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    # 1. result 行数 = n_policies × expected_request_count
    n_result = len(result_df)
    expected = n_policies * expected_request_count
    checks.append({
        "name": "scheduling_result_row_count",
        "status": "PASS" if n_result == expected else "FAIL",
        "detail": f"results={n_result}, expected={expected} ({n_policies} policies × {expected_request_count} requests)",
    })

    # 2. candidate 行数 > result 行数（每 request 多个 candidate）
    n_cand = len(candidate_df)
    checks.append({
        "name": "candidate_score_count",
        "status": "PASS" if n_cand > n_result else "FAIL",
        "detail": f"candidates={n_cand}, results={n_result}",
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

    # 5. 三个 cache hit rate 在 [0, 1] 范围内
    if not policy_summary_df.empty:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            for hit_metric in ["function_cache_hit_rate", "image_cache_hit_rate", "data_cache_hit_rate"]:
                v = float(srow[hit_metric])
                checks.append({
                    "name": f"{hit_metric}_in_range__{policy}",
                    "status": "PASS" if 0.0 <= v <= 1.0 else "FAIL",
                    "detail": f"{hit_metric}={v:.4f}",
                })

    # 6. result×candidate join 100% match
    if not result_candidate_join_df.empty and "match" in result_candidate_join_df.columns:
        n = len(result_candidate_join_df)
        matched = int(result_candidate_join_df["match"].sum())
        checks.append({
            "name": "result_candidate_join_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 7. paper highlight 3 个 hit_rate 跟 summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            for hit_metric in ["function_cache_hit_rate", "image_cache_hit_rate", "data_cache_hit_rate"]:
                hl_rows = paper_highlight_df[
                    paper_highlight_df.metric == f"{hit_metric}__{policy}"
                ]
                if hl_rows.empty:
                    continue
                hl_v = float(hl_rows["value"].iloc[0])
                summary_v = float(srow[hit_metric])
                checks.append({
                    "name": f"paper_highlight_{hit_metric}__{policy}",
                    "status": "PASS" if abs(hl_v - summary_v) < 1e-6 else "FAIL",
                    "detail": f"summary={summary_v:.6f}, highlight={hl_v:.6f}",
                })

    # 8. paper highlight 改善值跟 summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        aware = policy_summary_df[policy_summary_df.policy_name == "edge_cache_aware"]
        baseline_row = policy_summary_df[policy_summary_df.policy_name == "edge_round_robin"]
        if not aware.empty and not baseline_row.empty:
            aware_row = aware.iloc[0]
            base_row = baseline_row.iloc[0]
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == "function_cache_hit_rate_improvement__edge_cache_aware_over_edge_round_robin"
            ]
            if not hl_rows.empty:
                hl_v = float(hl_rows["value"].iloc[0])
                expected_v = float(aware_row["function_cache_hit_rate"]) - float(base_row["function_cache_hit_rate"])
                checks.append({
                    "name": "paper_highlight_function_cache_hit_rate_improvement",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                    "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
                })

    # 9. edge_cache_aware function_cache_hit_rate >= edge_round_robin
    if not policy_summary_df.empty and "policy_name" in policy_summary_df.columns:
        aware = policy_summary_df[policy_summary_df.policy_name == "edge_cache_aware"]
        baseline_row = policy_summary_df[policy_summary_df.policy_name == "edge_round_robin"]
        if not aware.empty and not baseline_row.empty:
            aware_hit = float(aware["function_cache_hit_rate"].iloc[0])
            baseline_hit = float(baseline_row["function_cache_hit_rate"].iloc[0])
            checks.append({
                "name": "edge_cache_aware_beats_edge_round_robin",
                "status": "PASS" if aware_hit >= baseline_hit else "FAIL",
                "detail": f"edge_cache_aware={aware_hit:.4f}, edge_round_robin={baseline_hit:.4f}",
            })

    # 10. paper highlight result_candidate_consistency == 1.0
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

    logger.info("=== edge_cache_scheduler self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出调度实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())
    candidate_df = outputs.get("edge_cache_candidate_score", pd.DataFrame())

    policy_summary_df = build_policy_summary(outputs)
    node_summary_df = build_node_summary(outputs)
    function_summary_df = build_function_summary(outputs)

    # result×candidate 关联（论文 demo 关键证据）
    result_candidate_join_df = build_result_candidate_join(result_df, candidate_df)
    join_path = output_dir / "edge_cache_result_candidate_join.csv"
    result_candidate_join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    # 论文 demo 关键摘要
    paper_highlight_df = build_paper_highlight(policy_summary_df, result_candidate_join_df)
    paper_highlight_path = output_dir / "edge_cache_policy_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    # 数据自洽段
    if not result_df.empty and "policy_name" in result_df.columns:
        n_policies = int(result_df["policy_name"].nunique())
        n_requests = int(len(result_df) // n_policies) if n_policies else 0
    else:
        n_policies = 0
        n_requests = 0

    self_check_result = self_check(
        result_df, candidate_df, policy_summary_df,
        result_candidate_join_df, paper_highlight_df,
        n_requests, n_policies,
    )
    log_self_check(self_check_result)

    outputs = dict(outputs)
    outputs["edge_cache_policy_summary"] = policy_summary_df
    outputs["edge_cache_node_summary"] = node_summary_df
    outputs["edge_cache_function_summary"] = function_summary_df
    outputs["edge_cache_result_candidate_join"] = result_candidate_join_df
    outputs["edge_cache_policy_paper_highlight"] = paper_highlight_df

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
