"""
文件作用：resource_monitor 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取资源监控、调用、部署和网络流相关指标，
并保存到 outputs/ 目录。

新增的关键导出（沿用 02_load_balancer / 03_skippy_scheduler / 04_network_flow / 05_image_pull_network 的 paper_highlight / data_self_check 模式）：
- invocation_resource_join.csv：每个 invoke 在执行时间窗内的 cpu/mem util 平均值
  这是 README §5 "调用 × 资源" 关联的核心输出
- resource_monitor_sample_probe.csv：
    从 ResourceMonitor 的 MetricsServer 窗口导出的真实 simtime 资源采样
- resource_monitor_invoke_probe_invocation_join.csv：
    invoke_dispatch_probe 与 invocations 的逐条一致性验证
- resource_monitor_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value（10 条）
- resource_monitor_self_check.csv：
    10 项数据自检（PASS/FAIL）
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


def build_resource_monitor_sample_probe(sim) -> pd.DataFrame:
    """
    从 ResourceMonitor 的 MetricsServer 中导出真实 simtime 资源采样。

    function_utilization.csv 由 RuntimeLogger 记录 wall clock time，缺少仿真时间。
    ResourceMonitor 同时会把 ResourceWindow(time=env.now, resources=...) 写入
    env.metrics_server。本函数读取该窗口，生成带 simtime 的样例级 probe，供
    invocation_resource_join 和 timeline 图使用。
    """
    rows = []
    metric_server = getattr(sim.env, "metrics_server", None)
    if metric_server is None or not hasattr(metric_server, "_windows"):
        return pd.DataFrame()

    for node_name, pod_windows in metric_server._windows.items():
        for _pod_name, windows in pod_windows.items():
            for window in windows:
                replica = window.replica
                resources = window.resources or {}
                node = replica.node
                cpu = float(resources.get("cpu", 0.0) or 0.0)
                memory = float(resources.get("memory", 0.0) or 0.0)
                rows.append({
                    "simtime": float(window.time),
                    "function_name": replica.function.name,
                    "function_image": replica.image,
                    "node": node_name,
                    "replica_id": id(replica),
                    "cpu": cpu,
                    "memory": memory,
                    "cpu_util": cpu / node.capacity.cpu_millis if node.capacity.cpu_millis else 0.0,
                    "mem_util": memory / node.capacity.memory if node.capacity.memory else 0.0,
                })

    return (
        pd.DataFrame(rows)
        .sort_values(["simtime", "replica_id"])
        .reset_index(drop=True)
        if rows else pd.DataFrame()
    )


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
    util_df = dfs.get("resource_monitor_sample_probe", pd.DataFrame())
    if util_df.empty:
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
    util_df = dfs.get("resource_monitor_sample_probe", pd.DataFrame()).copy()
    using_real_simtime = not util_df.empty and "simtime" in util_df.columns
    if util_df.empty:
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

    if not using_real_simtime:
        # 兜底：旧指标没有 simtime 时才按采样序号近似重建。
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


def build_invoke_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    逐条关联 invoke_dispatch_probe 与 invocations。

    这张表验证 simulator 派发 probe 与 faas-sim 实际 invocation 记录在
    function / replica / simtime / node 上一致。
    """
    probe_df = dfs.get("invoke_dispatch_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    required_probe = {"function_name", "replica_id", "simtime", "node", "cpu_millis", "memory_bytes"}
    required_inv = {"function_name", "replica_id", "t_start", "node", "t_exec"}
    if not required_probe.issubset(probe_df.columns) or not required_inv.issubset(inv_df.columns):
        return pd.DataFrame()

    rows: List[dict] = []
    for (fn, replica_id), probe_grp in probe_df.groupby(["function_name", "replica_id"], dropna=False):
        probe_sorted = probe_grp.sort_values("simtime").reset_index(drop=True)
        inv_grp = inv_df[
            (inv_df["function_name"] == fn)
            & (inv_df["replica_id"].astype(str) == str(replica_id))
        ].sort_values("t_start").reset_index(drop=True)

        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            probe = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            simtime_match = abs(float(probe["simtime"]) - float(inv["t_start"])) < 1e-6
            node_match = str(probe["node"]) == str(inv["node"])
            rows.append({
                "function_name": fn,
                "replica_id": replica_id,
                "probe_simtime": float(probe["simtime"]),
                "inv_t_start": float(inv["t_start"]),
                "inv_t_exec": float(inv["t_exec"]),
                "probe_node": probe["node"],
                "inv_node": inv["node"],
                "probe_cpu_millis": float(probe["cpu_millis"]),
                "probe_memory_bytes": float(probe["memory_bytes"]),
                "simtime_match": bool(simtime_match),
                "node_match": bool(node_match),
            })

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
    util_df = dfs.get("resource_monitor_sample_probe", pd.DataFrame())
    if util_df.empty:
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


def build_paper_highlight(
    util_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    per_replica_df: pd.DataFrame,
    probe_df: pd.DataFrame,
    invoke_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02/03/04/05 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if util_df.empty:
        return pd.DataFrame([
            {"metric": "total_resource_samples", "value": 0,
             "note": "ResourceMonitor 周期性采集的 per-replica 采样次数"},
            {"metric": "monitored_replicas", "value": 0,
             "note": "被 ResourceMonitor 采样的副本数"},
        ])

    total_samples = len(util_df)
    monitored_replicas = int(util_df["replica_id"].nunique()) if "replica_id" in util_df.columns else 0
    monitored_nodes = int(util_df["node"].nunique()) if "node" in util_df.columns else 0
    overall_avg_cpu_util = float(util_df["cpu_util"].mean()) if "cpu_util" in util_df.columns else 0.0
    overall_max_cpu_util = float(util_df["cpu_util"].max()) if "cpu_util" in util_df.columns else 0.0
    overall_avg_mem_util = float(util_df["mem_util"].mean()) if "mem_util" in util_df.columns else 0.0
    overall_max_mem_util = float(util_df["mem_util"].max()) if "mem_util" in util_df.columns else 0.0
    overall_avg_cpu_millis = float(util_df["cpu"].mean()) if "cpu" in util_df.columns else 0.0
    overall_max_cpu_millis = float(util_df["cpu"].max()) if "cpu" in util_df.columns else 0.0
    per_request_cpu_util = 0.35
    peak_concurrent_requests_per_replica = (
        overall_max_cpu_util / per_request_cpu_util
        if per_request_cpu_util > 0 else 0.0
    )

    invocation_events = len(inv_df)
    join_rows = len(join_df) if not join_df.empty else 0
    join_coverage = join_rows / invocation_events if invocation_events > 0 else 0.0

    # join 中 avg_cpu_util 的均值
    if not join_df.empty and "avg_cpu_util" in join_df.columns:
        join_avg_cpu_util = float(join_df["avg_cpu_util"].mean())
        join_max_cpu_util = float(join_df["max_cpu_util"].max())
    else:
        join_avg_cpu_util = 0.0
        join_max_cpu_util = 0.0

    # probe
    probe_rows = len(probe_df) if not probe_df.empty else 0
    invoke_probe_match_ratio = 0.0
    if not invoke_join_df.empty and {"simtime_match", "node_match"}.issubset(invoke_join_df.columns):
        matched = int((invoke_join_df["simtime_match"] & invoke_join_df["node_match"]).sum())
        invoke_probe_match_ratio = matched / len(invoke_join_df) if len(invoke_join_df) > 0 else 0.0

    join_rows_with_samples = 0
    join_sample_coverage = 0.0
    if not join_df.empty and "samples_in_window" in join_df.columns:
        join_rows_with_samples = int((join_df["samples_in_window"] >= 1).sum())
        join_sample_coverage = join_rows_with_samples / len(join_df) if len(join_df) > 0 else 0.0

    return pd.DataFrame([
        {"metric": "total_resource_samples", "value": total_samples,
         "note": "ResourceMonitor 周期性采集的 per-replica 采样次数"},
        {"metric": "monitored_replicas", "value": monitored_replicas,
         "note": "被 ResourceMonitor 采样的副本数"},
        {"metric": "monitored_nodes", "value": monitored_nodes,
         "note": "被采样的节点数"},
        {"metric": "overall_avg_cpu_util", "value": round(overall_avg_cpu_util, 6),
         "note": "所有采样的平均 CPU 利用率（占节点 CPU 容量比）"},
        {"metric": "overall_max_cpu_util", "value": round(overall_max_cpu_util, 6),
         "note": "所有采样的峰值 CPU 利用率（同一 replica 上并发请求会叠加）"},
        {"metric": "peak_concurrent_requests_per_replica", "value": round(peak_concurrent_requests_per_replica, 4),
         "note": "按 0.35 CPU/request 估算的单 replica 峰值并发请求数"},
        {"metric": "overall_avg_mem_util", "value": round(overall_avg_mem_util, 6),
         "note": "所有采样的平均内存利用率"},
        {"metric": "overall_max_mem_util", "value": round(overall_max_mem_util, 6),
         "note": "所有采样的峰值内存利用率"},
        {"metric": "overall_avg_cpu_millis", "value": round(overall_avg_cpu_millis, 4),
         "note": "所有采样的平均 CPU 占用（毫核）"},
        {"metric": "overall_max_cpu_millis", "value": round(overall_max_cpu_millis, 4),
         "note": "所有采样的峰值 CPU 占用（毫核）"},
        {"metric": "invocation_events", "value": invocation_events,
         "note": "实际函数调用事件数（应 == 12）"},
        {"metric": "join_rows", "value": join_rows,
         "note": "invocation_resource_join 的行数（应 == invocation_events）"},
        {"metric": "join_coverage", "value": round(join_coverage, 6),
         "note": "join 行数 / invoke 行数（应 == 1.0）"},
        {"metric": "join_rows_with_samples", "value": join_rows_with_samples,
         "note": "invocation_resource_join 中至少包含 1 个 ResourceMonitor 采样点的行数"},
        {"metric": "join_sample_coverage", "value": round(join_sample_coverage, 6),
         "note": "带资源采样点的 invoke 行数 / invoke 行数"},
        {"metric": "join_avg_cpu_util", "value": round(join_avg_cpu_util, 6),
         "note": "join 中各 invoke 的 avg_cpu_util 均值"},
        {"metric": "join_max_cpu_util", "value": round(join_max_cpu_util, 6),
         "note": "join 中各 invoke 的 max_cpu_util 峰值"},
        {"metric": "invoke_dispatch_probe_events", "value": probe_rows,
         "note": "invoke_dispatch_probe 探针行数（应 == invocation_events）"},
        {"metric": "invoke_probe_join_match_ratio", "value": round(invoke_probe_match_ratio, 6),
         "note": "invoke_dispatch_probe 与 invocations 逐条匹配比例"},
    ])


def data_self_check(
    util_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    per_replica_df: pd.DataFrame,
    probe_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    invoke_join_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    resource_monitor 样例的数据自洽检查（沿用 02/03/04/05 的 self_check 模式）。

    不变量：
    1. function_utilization 行数 ≥ 10（至少有 10 次采样）
    2. monitored_replicas == 2（部署 2 个副本）
    3. overall_max_cpu_util > 0.5（确实采到双 replica busy）
    4. invocations_count == 12（max_requests）
    5. join_rows == invocations_count
    6. invocation_resource_join 至少部分行落入 ResourceMonitor 采样窗口
    7. per_replica 行数 == 2
    8. per_replica.samples.sum() == total_resource_samples
    9. invoke_dispatch_probe 行数 == 12
    10. invoke_dispatch_probe × invocations 逐条一致

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if util_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    total_samples = len(util_df)
    monitored_replicas = int(util_df["replica_id"].nunique()) if "replica_id" in util_df.columns else 0
    overall_max_cpu_util = float(util_df["cpu_util"].max()) if "cpu_util" in util_df.columns else 0.0

    invocations_count = len(inv_df)
    join_rows = len(join_df) if not join_df.empty else 0

    # ResourceMonitor 是周期采样，不保证每个 invoke 窗口都有采样点。
    if not join_df.empty and "samples_in_window" in join_df.columns:
        rows_with_samples = int((join_df["samples_in_window"] >= 1).sum())
        has_resource_samples = rows_with_samples > 0
    else:
        rows_with_samples = 0
        has_resource_samples = False

    per_replica_rows = len(per_replica_df) if not per_replica_df.empty else 0
    if not per_replica_df.empty and "samples" in per_replica_df.columns:
        per_replica_sum = int(per_replica_df["samples"].sum())
    else:
        per_replica_sum = 0

    probe_rows = len(probe_df) if not probe_df.empty else 0

    # paper 与 summary 自洽
    paper_total_samples = int(paper_df.loc[paper_df["metric"] == "total_resource_samples", "value"].iloc[0]) \
        if not paper_df.empty and "total_resource_samples" in paper_df["metric"].values else -1
    paper_join_coverage = float(paper_df.loc[paper_df["metric"] == "join_coverage", "value"].iloc[0]) \
        if not paper_df.empty and "join_coverage" in paper_df["metric"].values else -1.0
    paper_consistent = (
        paper_total_samples == total_samples
        and abs(paper_join_coverage - (join_rows / invocations_count if invocations_count > 0 else 0.0)) < 1e-3
    )

    invoke_join_consistent = False
    if not invoke_join_df.empty and {"simtime_match", "node_match"}.issubset(invoke_join_df.columns):
        invoke_join_consistent = bool(
            len(invoke_join_df) == invocations_count
            and invoke_join_df["simtime_match"].all()
            and invoke_join_df["node_match"].all()
        )

    checks = {
        "01_total_resource_samples_at_least_10": total_samples >= 10,
        "02_monitored_replicas_is_2": monitored_replicas == 2,
        "03_overall_max_cpu_util_above_0.5": overall_max_cpu_util > 0.5,
        "04_invocations_count_is_12": invocations_count == 12,
        "05_join_rows_equals_invocations": join_rows == invocations_count,
        "06_resource_join_has_samples": has_resource_samples,
        "07_per_replica_rows_is_2": per_replica_rows == 2,
        "08_per_replica_samples_sum_matches": per_replica_sum == total_samples,
        "09_invoke_dispatch_probe_events_is_12": probe_rows == 12,
        "10_invoke_probe_join_consistent": bool(paper_consistent and invoke_join_consistent),
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 10 个 faas-sim 内置 metric 的 CSV（含 invoke_dispatch_probe）
    - resource_utilization_per_replica.csv：per-replica CPU/mem util 聚合
    - invocation_resource_join.csv：调用 × 资源 join（README §5 核心）
    - resource_monitor_invoke_probe_invocation_join.csv：invoke probe × invocations 逐条验证
    - resource_monitor_summary.csv：总体资源摘要
    - resource_monitor_invocation_summary.csv：调用摘要
    - resource_monitor_paper_highlight.csv：论文 demo 关键摘要（15 条 metric/value）
    - resource_monitor_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # 资源监控 per-replica 摘要 —— 06 关键导出。
    sample_probe_df = build_resource_monitor_sample_probe(sim)
    sample_probe_path = output_dir / "resource_monitor_sample_probe.csv"
    sample_probe_df.to_csv(sample_probe_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", sample_probe_path)
    dfs["resource_monitor_sample_probe"] = sample_probe_df

    # 资源监控 per-replica 摘要 —— 06 关键导出。
    per_replica_df = build_resource_utilization_per_replica(dfs)
    per_replica_path = output_dir / "resource_utilization_per_replica.csv"
    per_replica_df.to_csv(per_replica_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", per_replica_path)
    dfs["resource_utilization_per_replica"] = per_replica_df

    # 调用 × 资源 join —— README §5 核心。
    reconcile_interval = 1.0
    if sim.env.resource_monitor is not None and hasattr(sim.env.resource_monitor, "reconcile_interval"):
        reconcile_interval = float(sim.env.resource_monitor.reconcile_interval)
    join_df = build_invocation_resource_join(dfs, reconcile_interval=reconcile_interval)
    join_path = output_dir / "invocation_resource_join.csv"
    join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)
    dfs["invocation_resource_join"] = join_df

    # invoke probe × invocation join —— 严格事件级验证。
    invoke_join_df = build_invoke_probe_invocation_join(dfs)
    invoke_join_path = output_dir / "resource_monitor_invoke_probe_invocation_join.csv"
    invoke_join_df.to_csv(invoke_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invoke_join_path)
    dfs["resource_monitor_invoke_probe_invocation_join"] = invoke_join_df

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

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        util_df=dfs.get("resource_monitor_sample_probe", pd.DataFrame()) if not dfs.get("resource_monitor_sample_probe", pd.DataFrame()).empty else find_resource_dataframe(dfs),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=join_df,
        per_replica_df=per_replica_df,
        probe_df=dfs.get("invoke_dispatch_probe", pd.DataFrame()),
        invoke_join_df=invoke_join_df,
    )
    paper_path = output_dir / "resource_monitor_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        util_df=dfs.get("resource_monitor_sample_probe", pd.DataFrame()) if not dfs.get("resource_monitor_sample_probe", pd.DataFrame()).empty else find_resource_dataframe(dfs),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=join_df,
        per_replica_df=per_replica_df,
        probe_df=dfs.get("invoke_dispatch_probe", pd.DataFrame()),
        paper_df=paper_df,
        invoke_join_df=invoke_join_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "resource_monitor_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["resource_monitor_summary"] = resource_summary_df
    dfs["resource_monitor_invocation_summary"] = invocation_summary_df
    dfs["resource_monitor_paper_highlight"] = paper_df
    dfs["resource_monitor_self_check"] = check_df

    return dfs
