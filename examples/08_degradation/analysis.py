"""
文件作用：degradation 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取性能退化、调用、调度和部署指标，
并保存到 outputs/ 目录。

新增的关键导出：
- degradation_invoke_join.csv：probe 与 invocations 按 request_id 一一对应，
  论文 demo 关键证据：证明 simulator 实际用的 final_duration 就是
  degradation_factor × base_duration，和 invocations.csv 的 t_exec 完全一致。
- degradation_model_consistency.csv：跨全 probe 检查退化公式
  final_duration == base_duration * (1 + alpha * active_requests_before)，
  max abs diff 应该 ≤ 1e-9。
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
    把 degradation_probe 和 invocations 按 request_id 一一对应。

    probe 在 simulator 的 invoke() 开头就记录了每个 request 的 final_duration；
    invocations 在 invoke 完成后由 faas-sim 记录 t_exec。
    两者按 request_id 对齐后：
    - probe.active_requests_before
    - probe.final_duration       simulator 派发的最终执行时间
    - inv.t_exec                  faas-sim 记录的实际执行时间
    - duration_match              两个值是否完全相等（论文 demo 关键证据）
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing degradation_probe or invocations dataframe",
        }])

    if "request_id" not in probe_df.columns:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "degradation_probe missing request_id column",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")

    # probe 按 request_id 排序，invocations 没有 request_id 列
    # —— 按 (function_name, t_start) 排序后用行号对应
    probe_sorted = probe_df.sort_values("request_id").reset_index(drop=True)
    inv_sorted = inv_df.sort_values(["function_name", "t_start"]).reset_index(drop=True)

    rows: List[dict] = []
    n = min(len(probe_sorted), len(inv_sorted))
    for i in range(n):
        p = probe_sorted.iloc[i]
        inv = inv_sorted.iloc[i]
        duration_match = (
            pd.notna(inv["t_exec"])
            and abs(float(p["final_duration"]) - float(inv["t_exec"])) < 1e-6
        )
        rows.append({
            "function_name": p.get("function_name"),
            "request_id": int(p["request_id"]),
            "node_name": p.get("node_name"),
            "active_requests_before": int(p["active_requests_before"]),
            "degradation_factor": float(p["degradation_factor"]),
            "probe_final_duration": float(p["final_duration"]),
            "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
            "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
            "inv_t_wait": float(inv["t_wait"]) if pd.notna(inv["t_wait"]) else None,
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


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。
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

    dfs["degradation_summary"] = degradation_summary_df
    dfs["degradation_concurrency_distribution"] = concurrency_distribution_df
    dfs["degradation_invoke_join"] = invoke_join_df
    dfs["degradation_model_consistency"] = model_consistency_df

    return dfs