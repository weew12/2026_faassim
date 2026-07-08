"""
文件作用：degradation 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取性能退化、调用、调度和部署指标，
并保存到 outputs/ 目录。

新增的关键导出（沿用 02-07 的 paper_highlight / data_self_check 模式）：
- degradation_invoke_join.csv：degradation_probe / invoke_dispatch_probe / invocations 三表关联，
  论文 demo 关键证据：证明 simulator 实际用的 final_duration 就是
  degradation_factor × base_duration，和 invocations.csv 的 t_exec 完全一致。
- degradation_model_consistency.csv：跨全 probe 检查退化公式
  final_duration == base_duration * (1 + alpha * active_requests_before)，
  max abs diff 应该 ≤ 1e-9。
- degradation_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value（10 条）
- degradation_self_check.csv：
    10 项数据自检（PASS/FAIL）
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "degradation_probe",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
    "function_utilization",
    "node_utilization",
    "invoke_dispatch_probe",
]


def extract_metrics(sim) -> Dict[str, pd.DataFrame]:
    """
    从仿真对象中提取常用指标。
    """
    dfs: Dict[str, pd.DataFrame] = {}

    for name in METRIC_NAMES:
        try:
            df = sim.env.metrics.extract_dataframe(name)
            dfs[name] = df
            logger.info("metric %s extracted, rows=%d", name, len(df))
        except Exception as err:
            logger.warning("metric %s not available: %s", name, err)
            dfs[name] = pd.DataFrame()

    return dfs


def build_degradation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成性能退化摘要。

    按 (function_name, node_name) 聚合：
    - degradation_events       退化采样数
    - avg_active_requests_before / max_active_requests_before
    - avg_degradation_factor / max_degradation_factor
    - avg_final_duration / max_final_duration
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "degradation_events": 0,
        }])

    group_columns = [
        col for col in ["function_name", "node_name"]
        if col in probe_df.columns
    ]

    if not group_columns:
        return pd.DataFrame([{
            "degradation_events": len(probe_df),
            "avg_final_duration": probe_df["final_duration"].mean() if "final_duration" in probe_df.columns else None,
        }])

    return (
        probe_df
        .groupby(group_columns)
        .agg(
            degradation_events=("final_duration", "count"),
            avg_active_requests_before=("active_requests_before", "mean"),
            max_active_requests_before=("active_requests_before", "max"),
            avg_degradation_factor=("degradation_factor", "mean"),
            max_degradation_factor=("degradation_factor", "max"),
            avg_final_duration=("final_duration", "mean"),
            max_final_duration=("final_duration", "max"),
        )
        .reset_index()
    )


def build_concurrency_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计不同并发请求数下的执行时间分布。
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame())

    if probe_df.empty or "active_requests_before" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby("active_requests_before")
        .agg(
            request_count=("final_duration", "count"),
            avg_degradation_factor=("degradation_factor", "mean"),
            avg_final_duration=("final_duration", "mean"),
            min_final_duration=("final_duration", "min"),
            max_final_duration=("final_duration", "max"),
        )
        .reset_index()
        .sort_values("active_requests_before")
    )


def build_degradation_invoke_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    关联 degradation_probe、invoke_dispatch_probe 和 invocations。

    invocations.csv 没有 request_id，因此以 invoke_dispatch_probe 为桥：
    - degradation_probe 按 request_id 关联；
    - invocations 按 (function_name, replica_id, simtime/t_start) 关联。
    这样能证明 simulator 计算并派发的 final_duration 与 faas-sim 记录的
    t_exec 完全一致。
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame()).copy()
    dispatch_df = dfs.get("invoke_dispatch_probe", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty or dispatch_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing degradation_probe, invoke_dispatch_probe, or invocations dataframe",
        }])

    if "request_id" not in probe_df.columns:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "degradation_probe missing request_id column",
        }])
    if "request_id" not in dispatch_df.columns:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "invoke_dispatch_probe missing request_id column",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")
    dispatch_df["simtime"] = pd.to_numeric(dispatch_df["simtime"], errors="coerce")

    probe_by_request = {
        int(row["request_id"]): row
        for _, row in probe_df.iterrows()
        if pd.notna(row.get("request_id"))
    }

    rows: List[dict] = []
    dispatch_sorted = dispatch_df.sort_values(["simtime", "request_id"]).reset_index(drop=True)
    for _, dispatch in dispatch_sorted.iterrows():
        request_id = int(dispatch["request_id"])
        p = probe_by_request.get(request_id)
        inv_candidates = inv_df[
            (inv_df["function_name"] == dispatch["function_name"])
            & (inv_df["replica_id"].astype(str) == str(dispatch["replica_id"]))
            & ((inv_df["t_start"].astype(float) - float(dispatch["simtime"])).abs() < 1e-6)
        ]
        inv = inv_candidates.iloc[0] if not inv_candidates.empty else None

        if p is None or inv is None:
            rows.append({
                "function_name": dispatch.get("function_name"),
                "request_id": request_id,
                "replica_id": dispatch.get("replica_id"),
                "dispatch_simtime": float(dispatch["simtime"]) if pd.notna(dispatch["simtime"]) else None,
                "message": "missing matching degradation_probe or invocation row",
                "duration_match": False,
                "simtime_match": False,
                "node_match": False,
            })
            continue

        duration_match = (
            pd.notna(inv["t_exec"])
            and abs(float(p["final_duration"]) - float(inv["t_exec"])) < 1e-6
        )
        simtime_match = abs(float(dispatch["simtime"]) - float(inv["t_start"])) < 1e-6
        node_match = str(dispatch.get("node")) == str(inv.get("node"))
        rows.append({
            "function_name": p.get("function_name"),
            "request_id": int(p["request_id"]),
            "node_name": p.get("node_name"),
            "replica_id": dispatch.get("replica_id"),
            "active_requests_before": int(p["active_requests_before"]),
            "degradation_factor": float(p["degradation_factor"]),
            "probe_final_duration": float(p["final_duration"]),
            "dispatch_simtime": float(dispatch["simtime"]),
            "dispatch_final_duration": float(dispatch["final_duration"]),
            "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
            "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
            "inv_t_wait": float(inv["t_wait"]) if pd.notna(inv["t_wait"]) else None,
            "simtime_match": bool(simtime_match),
            "node_match": bool(node_match),
            "duration_match": duration_match,
        })

    return pd.DataFrame(rows)


def build_degradation_model_consistency(dfs: Dict[str, pd.DataFrame], base_duration: float = 0.4, alpha: float = 0.35) -> pd.DataFrame:
    """
    跨全 probe 验证退化公式：
    final_duration == base_duration * (1 + alpha * active_requests_before)

    返回单行 summary：probe_count / max_abs_diff / pass。
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame())
    if probe_df.empty or "final_duration" not in probe_df.columns or "active_requests_before" not in probe_df.columns:
        return pd.DataFrame([{
            "probe_count": 0,
            "message": "missing degradation_probe or required columns",
        }])

    expected = base_duration * (1 + alpha * probe_df["active_requests_before"])
    actual_diff = (probe_df["final_duration"] - expected).abs().max()
    return pd.DataFrame([{
        "probe_count": len(probe_df),
        "base_duration": base_duration,
        "alpha": alpha,
        "max_abs_diff": float(actual_diff) if pd.notna(actual_diff) else None,
        "pass_tolerance": float(actual_diff) < 1e-9 if pd.notna(actual_diff) else False,
    }])


def build_paper_highlight(
    probe_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    consistency_df: pd.DataFrame,
    concurrency_df: pd.DataFrame,
    probe_df_for_consistency: pd.DataFrame,
    base_duration: float = 0.4,
    alpha: float = 0.35,
    probe_df_unused_param: pd.DataFrame = None,
    probe_df_arg: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02-07 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([
            {"metric": "probe_count", "value": 0,
             "note": "degradation_probe 总采样数"},
        ])

    probe_count = int(len(probe_df))
    invocation_events = int(len(inv_df))

    max_active = int(probe_df["active_requests_before"].max()) if "active_requests_before" in probe_df.columns else 0
    max_factor = float(probe_df["degradation_factor"].max()) if "degradation_factor" in probe_df.columns else 0.0
    max_final = float(probe_df["final_duration"].max()) if "final_duration" in probe_df.columns else 0.0
    avg_final = float(probe_df["final_duration"].mean()) if "final_duration" in probe_df.columns else 0.0

    # duration_match
    duration_match_count = 0
    if not join_df.empty and "duration_match" in join_df.columns:
        duration_match_count = int(join_df["duration_match"].sum())
    duration_match_ratio = (
        duration_match_count / invocation_events if invocation_events > 0 else 0.0
    )

    # 数学一致性
    max_abs_diff = 0.0
    if not consistency_df.empty and "max_abs_diff" in consistency_df.columns:
        max_abs_diff = float(consistency_df["max_abs_diff"].iloc[0])

    # concurrency distribution 范围
    n_concurrency_levels = int(len(concurrency_df)) if not concurrency_df.empty else 0

    # probe 行数 == invocation_events
    probe_match_invocations = probe_count == invocation_events

    # theoretical max_final
    theoretical_max_final = base_duration * (1 + alpha * max_active)

    return pd.DataFrame([
        {"metric": "probe_count", "value": probe_count,
         "note": "degradation_probe 总采样数（应 == invocation_events）"},
        {"metric": "invocation_events", "value": invocation_events,
         "note": "实际函数调用事件数（应 == 40）"},
        {"metric": "base_duration", "value": round(base_duration, 4),
         "note": "无竞争基础执行时间（simtime 秒）"},
        {"metric": "alpha", "value": round(alpha, 4),
         "note": "每个并发请求引入的执行时间放大系数"},
        {"metric": "max_active_requests_before", "value": max_active,
         "note": "peak 并发负载（峰值 29 = 40 - 11 个 in-flight）"},
        {"metric": "max_degradation_factor", "value": round(max_factor, 4),
         "note": "peak 退化因子（应 == 1 + alpha * max_active = 11.15）"},
        {"metric": "max_final_duration", "value": round(max_final, 4),
         "note": "peak 退化后执行时间（应 ≈ 4.46s，证明退化生效）"},
        {"metric": "avg_final_duration", "value": round(avg_final, 4),
         "note": "平均退化后执行时间（由并发分布决定）"},
        {"metric": "duration_match_count", "value": duration_match_count,
         "note": "degradation_probe.final_duration 与 inv t_exec 一致的行数（应 == 40）"},
        {"metric": "duration_match_ratio", "value": round(duration_match_ratio, 4),
         "note": "duration_match 比例（应 == 1.0，证明 simulator 与 faas-sim 完全一致）"},
        {"metric": "max_abs_diff", "value": max_abs_diff,
         "note": "退化公式 final = base * (1 + alpha * active) 的 max abs diff（应 == 0）"},
        {"metric": "concurrency_levels", "value": n_concurrency_levels,
         "note": "degradation_concurrency_distribution 的不同 active_before 值数量"},
        {"metric": "probe_equals_invocations", "value": bool(probe_match_invocations),
         "note": "probe_count == invocation_events（probe×invocation 一致）"},
    ])


def data_self_check(
    probe_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    consistency_df: pd.DataFrame,
    concurrency_df: pd.DataFrame,
    probe_df_unused: pd.DataFrame = None,
    paper_df: pd.DataFrame = None,
) -> Dict[str, bool]:
    """
    degradation 样例的数据自洽检查（沿用 02-07 的 self_check 模式）。

    不变量：
    1. probe_count == 40（max_requests）
    2. invocation_events == 40
    3. join_rows == 40
    4. duration/simtime/node match 全部 True
    5. max_abs_diff == 0（数学一致性）
    6. max_active_requests_before >= 3（至少 3 个副本）
    7. max_final_duration 显著大于 base_duration（证明退化生效）
    8. concurrency_distribution 行数 >= 5
    9. probe 行数 == invocation_events
    10. paper 自洽

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if probe_df.empty or inv_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    probe_count = int(len(probe_df))
    inv_count = int(len(inv_df))
    join_count = int(len(join_df))

    # duration_match
    if not join_df.empty and "duration_match" in join_df.columns:
        all_duration_match = bool(join_df["duration_match"].all())
    else:
        all_duration_match = False
    if not join_df.empty and {"simtime_match", "node_match"}.issubset(join_df.columns):
        all_probe_invocation_match = bool(join_df["simtime_match"].all() and join_df["node_match"].all())
    else:
        all_probe_invocation_match = False

    # 数学一致性
    max_abs_diff_val = 0.0
    if not consistency_df.empty and "max_abs_diff" in consistency_df.columns:
        max_abs_diff_val = float(consistency_df["max_abs_diff"].iloc[0])
    pass_tolerance = max_abs_diff_val < 1e-9

    # max_active
    max_active = int(probe_df["active_requests_before"].max()) if "active_requests_before" in probe_df.columns else 0

    # max_final vs base
    max_final = float(probe_df["final_duration"].max()) if "final_duration" in probe_df.columns else 0.0
    final_greater_than_base = max_final > 0.4 * 2.0  # at least 2x

    # concurrency distribution
    n_concurrency_levels = int(len(concurrency_df)) if not concurrency_df.empty else 0

    # paper self-consistent
    paper_probe = -1
    paper_match = -1
    if paper_df is not None and not paper_df.empty:
        probe_row = paper_df[paper_df["metric"] == "probe_count"]
        match_row = paper_df[paper_df["metric"] == "duration_match_count"]
        if not probe_row.empty:
            paper_probe = int(probe_row["value"].iloc[0])
        if not match_row.empty:
            paper_match = int(match_row["value"].iloc[0])
    paper_consistent = paper_probe == probe_count and paper_match == probe_count

    checks = {
        "01_probe_count_is_40": probe_count == 40,
        "02_invocations_is_40": inv_count == 40,
        "03_join_rows_is_40": join_count == 40,
        "04_all_duration_and_dispatch_match_true": all_duration_match and all_probe_invocation_match,
        "05_max_abs_diff_zero": pass_tolerance,
        "06_max_active_at_least_3": max_active >= 3,
        "07_max_final_greater_than_base": final_greater_than_base,
        "08_concurrency_levels_at_least_5": n_concurrency_levels >= 5,
        "09_probe_equals_invocations": probe_count == inv_count,
        "10_paper_self_consistent": bool(paper_consistent),
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 11 个 faas-sim / probe 内置 metric 的 CSV（含 invoke_dispatch_probe）
    - degradation_summary.csv：按 (function_name, node_name) 聚合
    - degradation_concurrency_distribution.csv：按 active_requests_before 分组
    - degradation_invoke_join.csv：probe × invocations 关联（论文 demo 关键）
    - degradation_model_consistency.csv：退化公式数学一致性
    - degradation_paper_highlight.csv：论文 demo 关键摘要（13 条 metric/value）
    - degradation_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    degradation_summary_df = build_degradation_summary(dfs)
    degradation_summary_path = output_dir / "degradation_summary.csv"
    degradation_summary_df.to_csv(degradation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", degradation_summary_path)

    concurrency_distribution_df = build_concurrency_distribution(dfs)
    concurrency_distribution_path = output_dir / "degradation_concurrency_distribution.csv"
    concurrency_distribution_df.to_csv(concurrency_distribution_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", concurrency_distribution_path)

    # 调用 × probe 关联：证明 simulator 实际用的 final_duration 和 invocations 一致
    invoke_join_df = build_degradation_invoke_join(dfs)
    invoke_join_path = output_dir / "degradation_invoke_join.csv"
    invoke_join_df.to_csv(invoke_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invoke_join_path)

    # 退化模型数学一致性
    model_consistency_df = build_degradation_model_consistency(dfs)
    model_consistency_path = output_dir / "degradation_model_consistency.csv"
    model_consistency_df.to_csv(model_consistency_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", model_consistency_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        probe_df=dfs.get("degradation_probe", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=invoke_join_df,
        consistency_df=model_consistency_df,
        concurrency_df=concurrency_distribution_df,
        probe_df_for_consistency=dfs.get("degradation_probe", pd.DataFrame()),
    )
    paper_path = output_dir / "degradation_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        probe_df=dfs.get("degradation_probe", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=invoke_join_df,
        consistency_df=model_consistency_df,
        concurrency_df=concurrency_distribution_df,
        paper_df=paper_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "degradation_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["degradation_summary"] = degradation_summary_df
    dfs["degradation_concurrency_distribution"] = concurrency_distribution_df
    dfs["degradation_invoke_join"] = invoke_join_df
    dfs["degradation_model_consistency"] = model_consistency_df
    dfs["degradation_paper_highlight"] = paper_df
    dfs["degradation_self_check"] = check_df

    return dfs
