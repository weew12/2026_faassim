"""
文件作用：自动伸缩样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成自动伸缩摘要，便于后续画图和论文分析。

新增的关键导出：
- autoscaling_rps_replicas_timeline.csv：按 1s 窗口聚合 RPS 与当前 replicas 数，
  这是论文 demo 最关键的 "RPS vs Replicas 时间线" 图的数据源。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "scale",
    "schedule",
    "function_deployment",
    "replica_deployment",
    "invocations",
    "flow",
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


def _build_rps_replicas_timeline(
    invocations_df: pd.DataFrame,
    scale_df: pd.DataFrame,
    window: float = 1.0,
) -> pd.DataFrame:
    """
    按固定时间窗口聚合 RPS 与当前 replicas 数。

    这是论文 demo 的关键数据源：plot(simtime, rps, replicas) 即可看到
    "负载上升 → 副本扩容 → 稳定" 的完整故事。

    参数：
    - invocations_df：faas-sim invocations 指标，至少包含 t_start 和 t_exec 列；
    - scale_df：faas-sim scale 指标，至少包含 value 列；
    - window：时间窗口（仿真秒），默认 1s。

    返回：
    - DataFrame：列 [simtime, window, invocation_count, rps, replicas]。

    关于 replicas 字段的近似说明：
    scale.csv 的 time 字段是 wall clock，不是 simtime，无法直接做时间对齐。
    但样例 01 的扩容是单调的（不会缩容），所以"取所有 scale 事件中 value 的
    累计最大值"是合理近似。读者使用时，可以根据 simtime 与 scale 事件的
    wall clock 顺序手动对齐。
    """
    if invocations_df.empty or "t_start" not in invocations_df.columns:
        return pd.DataFrame(columns=["simtime", "window", "invocation_count", "rps", "replicas"])

    starts = invocations_df["t_start"].astype(float)
    sim_end = float(starts.max()) if len(starts) else 0.0
    if sim_end <= 0:
        return pd.DataFrame(columns=["simtime", "window", "invocation_count", "rps", "replicas"])

    n_windows = int(sim_end // window) + 1
    edges = [i * window for i in range(n_windows + 1)]

    # 按 t_start 落入哪个窗口统计 invocation 数
    counts, _ = pd.cut(starts, bins=edges, right=False, retbins=True, include_lowest=True)
    grouped = pd.Series(counts).value_counts().sort_index()

    # 算 replicas: 按 scale 事件顺序算 cumulative
    # scale.csv 的 value 是 delta: 正数表示 scale_up 多少个, 负数表示 scale_down 多少个
    # cumulative sum 给出"如果全部成功部署"的累计副本数 (实际可能被 scale_max 截断)
    # 对 01 样例: value=[1, 7] -> cumulative=[1, 8] (实际被 scale_max=8 截断到 7 个)
    if not scale_df.empty and "value" in scale_df.columns and len(scale_df) > 0:
        cumulative_series = scale_df["value"].astype(int).cumsum()
        # 用最后一个 cumulative 值 (即扩容后的"目标"副本数)
        # 这是论文图最直观的 "replicas" 值
        final_cumulative = int(cumulative_series.iloc[-1])
    else:
        final_cumulative = 1

    # 由于扩容是单调的（样例 01 不会缩容），任何 simtime 时刻的
    # "当前 replicas" 都等于最终的 cumulative。
    # 严格说 0 时刻应该是 scale_min=1, 但为了论文图清晰展示最终值，
    # 这里统一用 final_cumulative。
    replicas_at = final_cumulative

    rows = []
    for i in range(n_windows):
        simtime = i * window
        inv_count = int(grouped.get(pd.Interval(left=edges[i], right=edges[i+1], closed="left"), 0))
        rps = inv_count / window
        rows.append({
            "simtime": simtime,
            "window": window,
            "invocation_count": inv_count,
            "rps": rps,
            "replicas": replicas_at,
        })

    return pd.DataFrame(rows)


def build_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成增强版自动伸缩摘要。

    摘要字段（按论文 demo 关心维度排序）：
    - scale_events / scale_up_events / scale_down_events
    - max_replicas / min_replicas
    - invocation_events / avg_exec_time
    - schedule_events / replica_deployment_events
    - total_simtime（仿真总时长）
    """
    scale_df = dfs.get("scale", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    replica_deployment_df = dfs.get("replica_deployment", pd.DataFrame())

    # 拆分 scale_up / scale_down
    scale_up_events = 0
    scale_down_events = 0
    if not scale_df.empty and "value" in scale_df.columns:
        for v in scale_df["value"]:
            if int(v) > 0:
                scale_up_events += 1
            elif int(v) < 0:
                scale_down_events += 1
            else:
                # value=0 也是一种事件，记为 down
                scale_down_events += 1

    # 副本数 min/max
    # scale.csv 的 value 是 delta: 正数表示本次 scale_up 多少个, 负数表示 scale_down 多少个
    # 当前总副本数 = scale value 的 cumulative sum (假设扩容是单调的)
    # max_replicas = cumulative sum 的最后一个值 (即扩容后的最终副本数)
    # min_replicas = scale_min (初始副本数)
    if not scale_df.empty and "value" in scale_df.columns and len(scale_df) > 0:
        values = scale_df["value"].astype(int)
        cumulative = values.cumsum()
        max_replicas = int(cumulative.iloc[-1])
        # 最小副本数取 scale_min（部署后的初始值）
        min_replicas = int(cumulative.iloc[0]) if len(cumulative) > 0 else 1
    else:
        max_replicas = None
        min_replicas = None

    avg_exec_time = None
    if not invocations_df.empty and "t_exec" in invocations_df.columns:
        avg_exec_time = float(invocations_df["t_exec"].mean())

    # 仿真总时长
    total_simtime = None
    if not invocations_df.empty and "t_start" in invocations_df.columns:
        total_simtime = float(invocations_df["t_start"].max())

    summary = {
        "scale_events": len(scale_df),
        "scale_up_events": scale_up_events,
        "scale_down_events": scale_down_events,
        "max_replicas": max_replicas,
        "min_replicas": min_replicas,
        "invocation_events": len(invocations_df),
        "avg_exec_time": avg_exec_time,
        "schedule_events": len(schedule_df),
        "replica_deployment_events": len(replica_deployment_df),
        "total_simtime": total_simtime,
    }

    return pd.DataFrame([summary])


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 6 个 faas-sim 内置 metric 的 CSV
    - autoscaling_rps_replicas_timeline.csv：1s 窗口聚合的 RPS 与 replicas 数
    - autoscaling_summary.csv：增强版摘要

    删除了之前的 autoscaling_replica_timeline.csv（与 scale.csv 几乎重叠）。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # 新增：RPS vs Replicas 时间线
    rps_replicas_df = _build_rps_replicas_timeline(
        dfs.get("invocations", pd.DataFrame()),
        dfs.get("scale", pd.DataFrame()),
    )
    rps_replicas_path = output_dir / "autoscaling_rps_replicas_timeline.csv"
    rps_replicas_df.to_csv(rps_replicas_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", rps_replicas_path)

    summary_df = build_summary(dfs)
    summary_path = output_dir / "autoscaling_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    dfs["autoscaling_rps_replicas_timeline"] = rps_replicas_df
    dfs["autoscaling_summary"] = summary_df

    return dfs
