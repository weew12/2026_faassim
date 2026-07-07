"""
文件作用：resource_monitor 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取资源监控、调用、部署和网络流相关指标，
并保存到 outputs/ 目录。

新增的关键导出：
- resource_utilization_per_replica.csv：每个副本的 cpu/mem util 统计
  按 (node, replica_id) 给出 avg/max cpu_util、avg/max mem_util、采样数
  直观展示 ResourceMonitor 周期性采集到的资源使用画像
- invocation_resource_join.csv：每个 invoke 在执行时间窗内的 cpu/mem util 平均值
  这是 README §5 "调用 × 资源" 关联的核心输出，
  把 invocations.csv 的 t_start/t_exec 和 function_utilization 的时序按时间窗 join
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


# 不同 faas-sim 版本中资源监控指标名称可能略有差异。
# 因此这里同时尝试多个常见名称，缺失的指标会被安全跳过。
METRIC_NAMES = [
    "function_utilization",
    "node_utilization",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
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


def find_resource_dataframe(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    从候选指标中选一个非空的资源监控 DataFrame。

    faas-sim 实际记录的指标名是 `function_utilization`（per-replica CPU/mem util），
    以及 `node_utilization`（节点级，本样例 UrbanSensing 拓扑中不会触发，因为
    sim.resource.ResourceMonitor 只在函数级调用 log_function_resource_utilization）。
    """
    for name in ["function_utilization", "node_utilization"]:
        df = dfs.get(name, pd.DataFrame())
        if not df.empty:
            return df
    return pd.DataFrame()


def build_resource_utilization_per_replica(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按 node × replica_id 聚合资源利用率统计。

    每个副本在 invoke 期间被 ResourceMonitor 周期性采样，得到一组 (time, cpu, memory,
    cpu_util, mem_util) 记录。本函数把它们聚合为：
    - samples          采样次数
    - avg_cpu_millis   CPU 平均占用（毫核）
    - max_cpu_millis   CPU 峰值占用（毫核）
    - avg_cpu_util     CPU 平均利用率（占节点 CPU 容量比）
    - max_cpu_util     CPU 峰值利用率
    - avg_mem_bytes    内存平均占用
    - max_mem_bytes    内存峰值占用
    - avg_mem_util     内存平均利用率
    - max_mem_util     内存峰值利用率
    """
    util_df = find_resource_dataframe(dfs)

    if util_df.empty:
        return pd.DataFrame([{
            "resource_utilization_replicas": 0,
            "message": "no resource utilization dataframe found",
        }])

    group_keys = [k for k in ["node", "replica_id"] if k in util_df.columns]
    if not group_keys:
        return pd.DataFrame([{
            "resource_utilization_events": len(util_df),
            "columns": ",".join(util_df.columns.astype(str).tolist()),
        }])

    agg_dict = {}
    if "cpu_util" in util_df.columns:
        agg_dict["avg_cpu_util"] = ("cpu_util", "mean")
        agg_dict["max_cpu_util"] = ("cpu_util", "max")
    if "cpu" in util_df.columns:
        agg_dict["avg_cpu_millis"] = ("cpu", "mean")
        agg_dict["max_cpu_millis"] = ("cpu", "max")
    if "mem_util" in util_df.columns:
        agg_dict["avg_mem_util"] = ("mem_util", "mean")
        agg_dict["max_mem_util"] = ("mem_util", "max")
    if "memory" in util_df.columns:
        agg_dict["avg_mem_bytes"] = ("memory", "mean")
        agg_dict["max_mem_bytes"] = ("memory", "max")

    if not agg_dict:
        return pd.DataFrame([{
            "resource_utilization_events": len(util_df),
            "columns": ",".join(util_df.columns.astype(str).tolist()),
        }])

    agg_dict["samples"] = (group_keys[0], "size")
    # samples 重写：上面用任意 group_keys[0] 列，pandas .agg 会忽略，这里直接用 size
    agg_dict.pop("samples", None)
    result = util_df.groupby(group_keys).agg(**agg_dict).reset_index()
    result["samples"] = util_df.groupby(group_keys).size().values

    return result


def _parse_sim_time(series: pd.Series) -> pd.Series:
    """
    把 metrics 输出的 datetime 字符串转成 float 仿真秒数（仅作辅助参考）。

    metrics.extract_dataframe 返回的 time 列是 ISO 格式的 wall clock datetime。
    本函数用最早一条 wall clock 作为 t=0 的参考点，把 datetime 转成相对秒数。
    注意：这个相对值对**单次仿真**内的 wall-clock 间隔 ≈ 0（仿真跑得太快），
    不能直接当 simtime 用；simtime 需要从 fields 里的 t_start/t_exec 字段或
    ResourceMonitor reconcile_interval 重建。
    """
    ts = pd.to_datetime(series)
    base = ts.min()
    return (ts - base).dt.total_seconds()


def build_invocation_resource_join(dfs: Dict[str, pd.DataFrame], reconcile_interval: float = 1.0) -> pd.DataFrame:
    """
    把 invocations.csv 与 function_utilization.csv 按时间窗 join。

    对每条 invoke：
    - 解析 invocations.csv 的 t_start（执行起始）和 t_exec（执行时长）作为 simtime。
    - 在 [t_start, t_start + t_exec] 窗口内取 function_utilization 采样
      （按 replica_id 对齐），计算 avg_cpu_util / max_cpu_util /
      avg_mem_util / max_mem_util。

    注意：metrics.extract_dataframe 把每条记录的 wall-clock datetime 当成 index，
    但 simtime 并不在那里。invocations.csv 在 fields 里自带 t_start/t_exec（float simtime）；
    function_utilization 没有 simtime 字段，只能按 ResourceMonitor 的 reconcile_interval
    重建：第一次 yield timeout(reconcile_interval) 后首次采样在 simtime=reconcile_interval，
    之后每次 +reconcile_interval。

    这是 README §5 "调用 × 资源" 关联的核心输出。
    """
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()
    util_df = dfs.get("function_utilization", pd.DataFrame()).copy()

    if inv_df.empty:
        return pd.DataFrame([{
            "join_invocations": 0,
            "message": "no invocations dataframe",
        }])

    # invocations 有 t_start / t_exec（float simtime 字段），直接转 numeric。
    if "t_start" not in inv_df.columns or "t_exec" not in inv_df.columns:
        return pd.DataFrame([{
            "join_invocations": 0,
            "message": "invocations dataframe missing t_start/t_exec columns",
        }])

    inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")
    inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    inv_df = inv_df.dropna(subset=["t_start", "t_exec"])

    if util_df.empty or "replica_id" not in util_df.columns:
        return pd.DataFrame([{
            "join_invocations": 0,
            "message": "no function_utilization samples",
        }])

    # 按 wall-clock index 排序，然后按 ResourceMonitor 的 reconcile_interval
    # 重建 simtime。ResourceMonitor 在每次循环里对所有 RUNNING 副本统一采样，
    # 所以同一 replica 的采样在 simtime 上是 reconcile_interval, 2*reconcile_interval, ...
    # —— 按 per-replica 排序后用 (rank+1)*reconcile_interval 重建。
    util_df = util_df.sort_index()
    util_df = util_df.reset_index(drop=True)
    util_df["simtime"] = (
        util_df.groupby("replica_id").cumcount() + 1
    ).astype(float) * float(reconcile_interval)

    rows: List[dict] = []
    for _, inv in inv_df.iterrows():
        replica_id = inv.get("replica_id")
        t_start = float(inv["t_start"])
        t_exec = float(inv["t_exec"])
        if t_exec <= 0:
            t_exec = 0.0
        t_end = t_start + t_exec

        # 同一 replica_id 上落在 [t_start, t_end] 内的采样。
        sub = util_df[
            (util_df["replica_id"] == replica_id)
            & (util_df["simtime"] >= t_start)
            & (util_df["simtime"] <= t_end)
        ]

        row = {
            "function_name": inv.get("function_name"),
            "function_image": inv.get("function_image"),
            "node": inv.get("node"),
            "replica_id": replica_id,
            "t_start": t_start,
            "t_exec": t_exec,
            "samples_in_window": len(sub),
        }
        if not sub.empty:
            if "cpu_util" in sub.columns:
                row["avg_cpu_util"] = float(sub["cpu_util"].mean())
                row["max_cpu_util"] = float(sub["cpu_util"].max())
            if "mem_util" in sub.columns:
                row["avg_mem_util"] = float(sub["mem_util"].mean())
                row["max_mem_util"] = float(sub["mem_util"].max())
            if "cpu" in sub.columns:
                row["avg_cpu_millis"] = float(sub["cpu"].mean())
                row["max_cpu_millis"] = float(sub["cpu"].max())
            if "memory" in sub.columns:
                row["avg_mem_bytes"] = float(sub["memory"].mean())
                row["max_mem_bytes"] = float(sub["memory"].max())
        rows.append(row)

    return pd.DataFrame(rows)


def build_resource_monitor_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成资源监控摘要。

    汇总指标：
    - total_resource_samples：function_utilization 总采样次数
    - monitored_replicas：被 ResourceMonitor 采样的副本数
    - monitored_nodes：被采样的节点数
    - overall_avg_cpu_util / overall_max_cpu_util：所有采样的平均/峰值 CPU 利用率
    - overall_avg_mem_util / overall_max_mem_util：所有采样的平均/峰值内存利用率
    """
    util_df = find_resource_dataframe(dfs)

    if util_df.empty:
        return pd.DataFrame([{
            "total_resource_samples": 0,
            "message": "no resource monitor dataframe found",
        }])

    summary = {
        "total_resource_samples": len(util_df),
    }
    if "replica_id" in util_df.columns:
        summary["monitored_replicas"] = int(util_df["replica_id"].nunique())
    if "node" in util_df.columns:
        summary["monitored_nodes"] = int(util_df["node"].nunique())
    if "cpu_util" in util_df.columns:
        summary["overall_avg_cpu_util"] = float(util_df["cpu_util"].mean())
        summary["overall_max_cpu_util"] = float(util_df["cpu_util"].max())
    if "mem_util" in util_df.columns:
        summary["overall_avg_mem_util"] = float(util_df["mem_util"].mean())
        summary["overall_max_mem_util"] = float(util_df["mem_util"].max())
    if "cpu" in util_df.columns:
        summary["overall_avg_cpu_millis"] = float(util_df["cpu"].mean())
        summary["overall_max_cpu_millis"] = float(util_df["cpu"].max())
    if "memory" in util_df.columns:
        summary["overall_avg_mem_bytes"] = float(util_df["memory"].mean())
        summary["overall_max_mem_bytes"] = float(util_df["memory"].max())

    return pd.DataFrame([summary])


def build_invocation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成调用摘要。
    """
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if invocations_df.empty:
        return pd.DataFrame([{
            "invocation_events": 0,
        }])

    result = {
        "invocation_events": len(invocations_df),
    }

    if "function_name" in invocations_df.columns:
        result["function_count"] = invocations_df["function_name"].nunique()

    if "duration" in invocations_df.columns:
        result["avg_duration"] = invocations_df["duration"].mean()
        result["max_duration"] = invocations_df["duration"].max()

    return pd.DataFrame([result])


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

    # 资源监控 per-replica 摘要 —— 06 关键导出。
    per_replica_df = build_resource_utilization_per_replica(dfs)
    per_replica_path = output_dir / "resource_utilization_per_replica.csv"
    per_replica_df.to_csv(per_replica_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", per_replica_path)
    dfs["resource_utilization_per_replica"] = per_replica_df

    # 调用 × 资源 join —— README §5 核心。
    # reconcile_interval 取自 ResourceMonitor，默认为 1（simtime 秒）。
    reconcile_interval = 1.0
    if sim.env.resource_monitor is not None and hasattr(sim.env.resource_monitor, "reconcile_interval"):
        reconcile_interval = float(sim.env.resource_monitor.reconcile_interval)
    join_df = build_invocation_resource_join(dfs, reconcile_interval=reconcile_interval)
    join_path = output_dir / "invocation_resource_join.csv"
    join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)
    dfs["invocation_resource_join"] = join_df

    # 资源监控总体摘要。
    resource_summary_df = build_resource_monitor_summary(dfs)
    resource_summary_path = output_dir / "resource_monitor_summary.csv"
    resource_summary_df.to_csv(resource_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", resource_summary_path)

    # 调用摘要。
    invocation_summary_df = build_invocation_summary(dfs)
    invocation_summary_path = output_dir / "resource_monitor_invocation_summary.csv"
    invocation_summary_df.to_csv(invocation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invocation_summary_path)

    dfs["resource_monitor_summary"] = resource_summary_df
    dfs["resource_monitor_invocation_summary"] = invocation_summary_df

    return dfs