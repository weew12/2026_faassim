"""
文件作用：image_pull_network 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取镜像拉取、网络流、部署生命周期等指标，
并保存到 outputs/ 目录。

新增的关键导出（沿用 02_load_balancer / 03_skippy_scheduler 的 paper_highlight / data_self_check 模式）：
- image_pull_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value（10 条）
- image_pull_self_check.csv：
    10 项数据自检（PASS/FAIL）
- image_pull_invoke_probe_invocation_join.csv：
    逐条关联 invoke_dispatch_probe 与 invocations，验证 invoke 探针和实际调用记录一致

升级：
- invoke_dispatch_probe 探针加入 METRIC_NAMES
- image_pull_cold_warm_comparison 加 cache_savings_seconds / cache_savings_ratio
- image_pull_size_duration_comparison 加 pull_speed_mb_per_sec
- image_pull_deploy_phase_duration 加 deploy_to_finish_simtime
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "image_pull_probe",
    "flow",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
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


def build_image_pull_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成镜像拉取摘要。
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame()

    group_columns = [
        col for col in ["function_name", "image", "node_name"]
        if col in probe_df.columns
    ]

    if not group_columns:
        return probe_df

    return (
        probe_df
        .groupby(group_columns)
        .agg(
            pull_events=("image_pull_duration", "count"),
            avg_pull_duration=("image_pull_duration", "mean"),
            max_pull_duration=("image_pull_duration", "max"),
            cache_hit_like_count=("cache_hit_like", "sum"),
        )
        .reset_index()
    )


def build_flow_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成网络 Flow 摘要（按 action_type × source × sink 分组）。
    flow.csv 不含 image 列，所以这里的分组不包含 image。
    如需按 image 拆分的拉取对比，请使用 image_pull_cold_warm_comparison.csv。
    """
    flow_df = dfs.get("flow", pd.DataFrame())

    if flow_df.empty:
        return pd.DataFrame()

    group_columns = [
        col for col in ["action_type", "source", "sink"]
        if col in flow_df.columns
    ]

    if not group_columns:
        return flow_df

    return (
        flow_df
        .groupby(group_columns)
        .agg(
            flow_count=("bytes", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
            max_duration=("duration", "max"),
        )
        .reset_index()
        .sort_values(["action_type", "source"], ascending=[True, True])
    )


def build_cold_warm_comparison(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成冷/热拉取对比摘要（增强版）。

    字段：
    - image / cold_or_warm / pull_events
    - avg_pull_duration / min_pull_duration / max_pull_duration
    - cache_savings_seconds / cache_savings_ratio
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())

    if probe_df.empty or "image_pull_duration" not in probe_df.columns:
        return pd.DataFrame()

    work_df = probe_df.copy()
    work_df["cold_or_warm"] = work_df["cache_hit_like"].map(
        {True: "warm_cache_hit", False: "cold_pull"}
    ).fillna("unknown")

    group_columns = ["image", "cold_or_warm"]
    available = [c for c in group_columns if c in work_df.columns]
    if not available:
        return pd.DataFrame()

    summary = (
        work_df
        .groupby(available)
        .agg(
            pull_events=("image_pull_duration", "count"),
            avg_pull_duration=("image_pull_duration", "mean"),
            min_pull_duration=("image_pull_duration", "min"),
            max_pull_duration=("image_pull_duration", "max"),
        )
        .reset_index()
        .sort_values(["image", "cold_or_warm"], ascending=[True, True])
    )

    # 加 cache_savings_seconds / cache_savings_ratio 列
    summary = _enrich_cold_warm_with_savings(summary)

    return summary


def _enrich_cold_warm_with_savings(cold_warm_df: pd.DataFrame) -> pd.DataFrame:
    """
    给 cold_warm_df 加上 cache_savings_seconds 和 cache_savings_ratio 列。

    对每个 image：
    - 找到 cold_pull 行的 avg_pull_duration
    - 找到 warm_cache_hit 行的 avg_pull_duration
    - 计算 savings
    """
    if cold_warm_df.empty or "image" not in cold_warm_df.columns or "cold_or_warm" not in cold_warm_df.columns:
        return cold_warm_df

    enriched = cold_warm_df.copy()

    cold_durations = {}
    warm_durations = {}
    for _, row in enriched.iterrows():
        img = row["image"]
        if row["cold_or_warm"] == "cold_pull":
            cold_durations[img] = row["avg_pull_duration"]
        elif row["cold_or_warm"] == "warm_cache_hit":
            warm_durations[img] = row["avg_pull_duration"]

    def _savings_seconds(img):
        if img in cold_durations and img in warm_durations:
            return cold_durations[img] - warm_durations[img]
        return None

    def _savings_ratio(img):
        if img in cold_durations and img in warm_durations:
            cd = cold_durations[img]
            wd = warm_durations[img]
            if cd > 0:
                return 1.0 - (wd / cd)
        return None

    enriched["cache_savings_seconds"] = enriched["image"].apply(_savings_seconds)
    enriched["cache_savings_ratio"] = enriched["image"].apply(_savings_ratio)

    return enriched


def build_size_duration_comparison(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    论文 demo 关键图：镜像大小 vs 拉取耗时。

    派生自 image_pull_probe (image / image_pull_duration)。

    输出列：function_name / image / node_name / image_size_mb /
            pull_duration_seconds / pull_speed_mb_per_sec

    镜像大小按命名推断（small=32M, large=192M），与 main.py 设定一致。
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame()

    cols = ["function_name", "image", "node_name", "image_pull_duration"]
    available = [c for c in cols if c in probe_df.columns]
    if "image" not in available or "image_pull_duration" not in available:
        return pd.DataFrame()

    work_df = probe_df[available].copy()

    def _infer_size_mb(image_name: str) -> float:
        if "small" in str(image_name).lower():
            return 32.0
        if "large" in str(image_name).lower():
            return 192.0
        return None

    work_df["image_size_mb"] = work_df["image"].apply(_infer_size_mb)
    work_df["pull_duration_seconds"] = work_df["image_pull_duration"]
    work_df["pull_speed_mb_per_sec"] = work_df.apply(
        lambda r: (r["image_size_mb"] / r["pull_duration_seconds"])
        if (r["pull_duration_seconds"] and r["pull_duration_seconds"] > 0
            and r["image_size_mb"] is not None)
        else None,
        axis=1,
    )

    preferred = [
        "function_name",
        "image",
        "node_name",
        "image_size_mb",
        "pull_duration_seconds",
        "pull_speed_mb_per_sec",
    ]
    existing = [c for c in preferred if c in work_df.columns]

    return (
        work_df[existing]
        .sort_values("image_size_mb", na_position="last")
        .reset_index(drop=True)
    )


def build_deploy_phase_duration(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    论文 demo 关键图：3 个 pod 的 deploy 阶段耗时（simtime-aware）。

    用 image_pull_probe (image_pull_duration) + simulator.py 的固定 startup/setup 时长
    推算 deploy_to_finish_simtime：

      deploy_to_finish_simtime = image_pull_duration + startup_simtime + setup_simtime

    其中 startup_simtime = 0.1, setup_simtime = 0（来自 simulator.py）。
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())
    if probe_df.empty:
        return pd.DataFrame()

    if "image_pull_duration" not in probe_df.columns:
        return pd.DataFrame()

    startup_simtime = 0.1
    setup_simtime = 0.0

    work_df = probe_df.copy()
    work_df["startup_simtime"] = startup_simtime
    work_df["setup_simtime"] = setup_simtime
    work_df["deploy_to_finish_simtime"] = (
        work_df["image_pull_duration"] + startup_simtime + setup_simtime
    )

    preferred = [
        "function_name",
        "image",
        "node_name",
        "cache_hit_like",
        "image_pull_duration",
        "startup_simtime",
        "setup_simtime",
        "deploy_to_finish_simtime",
    ]
    existing = [c for c in preferred if c in work_df.columns]

    return (
        work_df[existing]
        .sort_values("deploy_to_finish_simtime", ascending=False)
        .reset_index(drop=True)
    )


def build_invoke_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    逐条关联 invoke_dispatch_probe 与 invocations。

    关联键使用 (function_name, replica_id, simtime/t_start)。该表用于证明
    simulator 派发的 invoke probe 与 faas-sim 实际 invocation 记录一致。
    """
    probe_df = dfs.get("invoke_dispatch_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    required_probe = {"function_name", "replica_id", "simtime", "node"}
    required_inv = {"function_name", "replica_id", "t_start", "node", "t_exec"}
    if not required_probe.issubset(probe_df.columns) or not required_inv.issubset(inv_df.columns):
        return pd.DataFrame()

    rows = []
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
                "simtime_match": bool(simtime_match),
                "node_match": bool(node_match),
            })

    return pd.DataFrame(rows)


def build_paper_highlight(
    probe_df: pd.DataFrame,
    cold_warm_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    invoke_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02_load_balancer / 03_skippy_scheduler 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if probe_df.empty:
        return pd.DataFrame([
            {"metric": "small_cold_pull_duration_s", "value": 0.0,
             "note": "small 镜像冷拉取耗时（秒）"},
            {"metric": "small_warm_cache_hit_duration_s", "value": 0.0,
             "note": "small 镜像 cache 命中耗时（秒）"},
            {"metric": "large_cold_pull_duration_s", "value": 0.0,
             "note": "large 镜像冷拉取耗时（秒）"},
        ])

    # 按 function_name 切分
    small_cold = probe_df[(probe_df["image"].astype(str).str.contains("small", case=False))
                          & (probe_df["cache_hit_like"] == False)]
    small_warm = probe_df[(probe_df["image"].astype(str).str.contains("small", case=False))
                          & (probe_df["cache_hit_like"] == True)]
    large_cold = probe_df[(probe_df["image"].astype(str).str.contains("large", case=False))
                          & (probe_df["cache_hit_like"] == False)]

    small_cold_dur = float(small_cold["image_pull_duration"].iloc[0]) if len(small_cold) > 0 else 0.0
    small_warm_dur = float(small_warm["image_pull_duration"].iloc[0]) if len(small_warm) > 0 else 0.0
    large_cold_dur = float(large_cold["image_pull_duration"].iloc[0]) if len(large_cold) > 0 else 0.0

    # 镜像大小
    small_size_mb = 32.0
    large_size_mb = 192.0

    # 拉取速度（MB/s）
    small_cold_speed = small_size_mb / small_cold_dur if small_cold_dur > 0 else 0.0
    large_cold_speed = large_size_mb / large_cold_dur if large_cold_dur > 0 else 0.0

    # 缓存节省
    cache_savings_seconds = small_cold_dur - small_warm_dur
    cache_savings_ratio = 1.0 - (small_warm_dur / small_cold_dur) if small_cold_dur > 0 else 0.0

    # docker_pull 流数
    docker_pull_flow_count = 0
    if not flow_df.empty and "action_type" in flow_df.columns:
        docker_pull_flow_count = int((flow_df["action_type"] == "docker_pull").sum())

    # 端到端 pull_speed（用最大字节数 / 最长耗时 推算链路利用率）
    # 实际更直接：1000Mbps × 0.97 / 8 = 121.25 MB/s
    expected_speed_mb_per_sec = 1000 * 0.97 / 8.0  # ≈ 121.25
    actual_avg_speed = (small_cold_speed + large_cold_speed) / 2 if small_cold_speed > 0 and large_cold_speed > 0 else 0.0
    bandwidth_utilization = actual_avg_speed / expected_speed_mb_per_sec if expected_speed_mb_per_sec > 0 else 0.0

    # invocations
    invocation_count = len(inv_df)
    invoke_probe_join_match_ratio = 0.0
    if not invoke_join_df.empty and {"simtime_match", "node_match"}.issubset(invoke_join_df.columns):
        matched = int((invoke_join_df["simtime_match"] & invoke_join_df["node_match"]).sum())
        invoke_probe_join_match_ratio = matched / len(invoke_join_df) if len(invoke_join_df) > 0 else 0.0

    return pd.DataFrame([
        {"metric": "small_image_size_mb", "value": small_size_mb,
         "note": "small 镜像大小（MB）"},
        {"metric": "large_image_size_mb", "value": large_size_mb,
         "note": "large 镜像大小（MB）"},
        {"metric": "small_cold_pull_duration_s", "value": round(small_cold_dur, 6),
         "note": "small 镜像冷拉取耗时（秒），首次部署 32M 镜像"},
        {"metric": "small_warm_cache_hit_duration_s", "value": round(small_warm_dur, 6),
         "note": "small 镜像 cache 命中耗时（秒），同节点复用"},
        {"metric": "large_cold_pull_duration_s", "value": round(large_cold_dur, 6),
         "note": "large 镜像冷拉取耗时（秒），首次部署 192M 镜像"},
        {"metric": "small_cold_pull_speed_mb_per_sec", "value": round(small_cold_speed, 4),
         "note": "small 冷拉取速度（MB/s），应接近 121 MB/s（1Gbps/8×0.97）"},
        {"metric": "large_cold_pull_speed_mb_per_sec", "value": round(large_cold_speed, 4),
         "note": "large 冷拉取速度（MB/s），应接近 121 MB/s"},
        {"metric": "cache_savings_seconds", "value": round(cache_savings_seconds, 6),
         "note": "small 缓存命中节省时间（秒），论文 demo 关键数字"},
        {"metric": "cache_savings_ratio", "value": round(cache_savings_ratio, 6),
         "note": "small 缓存节省比例（warm/cold），越接近 1 缓存越有效"},
        {"metric": "docker_pull_flow_count", "value": docker_pull_flow_count,
         "note": "docker_pull 网络流数量（small-cold + large-cold = 2，warm 不算）"},
        {"metric": "bandwidth_utilization_ratio", "value": round(bandwidth_utilization, 4),
         "note": "实测拉取速度 / 理论最大速度（链路利用率，越接近 1 越好）"},
        {"metric": "invocation_events", "value": invocation_count,
         "note": "invoke 调用事件数（small-cold 触发 10 个请求）"},
        {"metric": "invoke_probe_join_match_ratio", "value": round(invoke_probe_join_match_ratio, 6),
         "note": "invoke_dispatch_probe 与 invocations 逐条匹配比例"},
    ])


def data_self_check(
    probe_df: pd.DataFrame,
    cold_warm_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    invoke_join_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    image_pull_network 样例的数据自洽检查（沿用 02/03 的 self_check 模式）。

    不变量：
    1. total_pulls == 3（cold + warm + cold）
    2. small_cold_pull_duration > 0
    3. small_warm_pull_duration <= 1e-9（cache hit）
    4. large_cold_pull_duration > small_cold_pull_duration
    5. cache_savings_seconds (small) ≈ small_cold_pull_duration
    6. cache_savings_ratio (small) ≈ 1.0
    7. invocations_count == 10
    8. docker_pull_flow_count == 2（small-cold + large-cold，warm 不算）
    9. paper_docker_pull_flow_count == 2
    10. invoke_dispatch_probe × invocations 逐条一致

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if probe_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    total_pulls = len(probe_df)

    # 按 function/image 切分
    small_cold = probe_df[(probe_df["image"].astype(str).str.contains("small", case=False))
                          & (probe_df["cache_hit_like"] == False)]
    small_warm = probe_df[(probe_df["image"].astype(str).str.contains("small", case=False))
                          & (probe_df["cache_hit_like"] == True)]
    large_cold = probe_df[(probe_df["image"].astype(str).str.contains("large", case=False))
                          & (probe_df["cache_hit_like"] == False)]

    small_cold_dur = float(small_cold["image_pull_duration"].iloc[0]) if len(small_cold) > 0 else 0.0
    small_warm_dur = float(small_warm["image_pull_duration"].iloc[0]) if len(small_warm) > 0 else 0.0
    large_cold_dur = float(large_cold["image_pull_duration"].iloc[0]) if len(large_cold) > 0 else 0.0

    # invocations
    invocations_count = len(inv_df)

    # docker_pull flow
    docker_pull_flow_count = 0
    if not flow_df.empty and "action_type" in flow_df.columns:
        docker_pull_flow_count = int((flow_df["action_type"] == "docker_pull").sum())

    # paper_docker_pull_flow_count
    paper_docker_pull_flow_count = 0
    if not paper_df.empty and "docker_pull_flow_count" in paper_df["metric"].values:
        paper_docker_pull_flow_count = int(paper_df.loc[paper_df["metric"] == "docker_pull_flow_count", "value"].iloc[0])

    invoke_join_consistent = False
    if not invoke_join_df.empty and {"simtime_match", "node_match"}.issubset(invoke_join_df.columns):
        invoke_join_consistent = bool(
            len(invoke_join_df) == invocations_count
            and invoke_join_df["simtime_match"].all()
            and invoke_join_df["node_match"].all()
        )

    checks = {
        "01_total_pulls_is_3": total_pulls == 3,
        "02_small_cold_pull_positive": small_cold_dur > 0.0,
        "03_small_warm_is_cache_hit": small_warm_dur <= 1e-9,
        "04_large_cold_longer_than_small_cold": large_cold_dur > small_cold_dur,
        "05_cache_savings_seconds_close_to_cold": abs((small_cold_dur - small_warm_dur) - small_cold_dur) < 1e-3,
        "06_cache_savings_ratio_near_one": abs((1.0 - small_warm_dur / small_cold_dur) - 1.0) < 1e-3 if small_cold_dur > 0 else False,
        "07_invocations_count_is_10": invocations_count == 10,
        "08_docker_pull_flow_count_is_2": docker_pull_flow_count == 2,
        "09_paper_docker_pull_flow_count_is_2": paper_docker_pull_flow_count == 2,
        "10_invoke_probe_invocation_join_consistent": invoke_join_consistent,
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 9 个 faas-sim 内置 metric 的 CSV（含 invoke_dispatch_probe）
    - image_pull_summary.csv：按 function × image × node 分组
    - image_pull_flow_summary.csv：按 action_type × source × sink 分组
    - image_pull_cold_warm_comparison.csv：含 cache_savings_seconds / cache_savings_ratio
    - image_pull_size_duration_comparison.csv：论文 demo 关键图（image_size vs duration）
    - image_pull_deploy_phase_duration.csv：3 个 pod 的 deploy 阶段总耗时
    - image_pull_invoke_probe_invocation_join.csv：invoke probe × invocations 逐条关联
    - image_pull_paper_highlight.csv：论文 demo 关键摘要（13 条 metric/value）
    - image_pull_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    image_pull_summary_df = build_image_pull_summary(dfs)
    image_pull_summary_path = output_dir / "image_pull_summary.csv"
    image_pull_summary_df.to_csv(image_pull_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", image_pull_summary_path)

    flow_summary_df = build_flow_summary(dfs)
    flow_summary_path = output_dir / "image_pull_flow_summary.csv"
    flow_summary_df.to_csv(flow_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", flow_summary_path)

    cold_warm_df = build_cold_warm_comparison(dfs)
    cold_warm_path = output_dir / "image_pull_cold_warm_comparison.csv"
    cold_warm_df.to_csv(cold_warm_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", cold_warm_path)

    # 镜像大小 vs 拉取耗时（论文 demo 关键图）
    size_duration_df = build_size_duration_comparison(dfs)
    size_duration_path = output_dir / "image_pull_size_duration_comparison.csv"
    size_duration_df.to_csv(size_duration_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", size_duration_path)

    # deploy 阶段耗时（论文 demo 关键图）
    deploy_phase_df = build_deploy_phase_duration(dfs)
    deploy_phase_path = output_dir / "image_pull_deploy_phase_duration.csv"
    deploy_phase_df.to_csv(deploy_phase_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", deploy_phase_path)

    # invoke probe × invocation join
    invoke_join_df = build_invoke_probe_invocation_join(dfs)
    invoke_join_path = output_dir / "image_pull_invoke_probe_invocation_join.csv"
    invoke_join_df.to_csv(invoke_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invoke_join_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        probe_df=dfs.get("image_pull_probe", pd.DataFrame()),
        cold_warm_df=cold_warm_df,
        flow_df=dfs.get("flow", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        invoke_join_df=invoke_join_df,
    )
    paper_path = output_dir / "image_pull_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        probe_df=dfs.get("image_pull_probe", pd.DataFrame()),
        cold_warm_df=cold_warm_df,
        flow_df=dfs.get("flow", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        paper_df=paper_df,
        invoke_join_df=invoke_join_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "image_pull_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["image_pull_summary"] = image_pull_summary_df
    dfs["image_pull_flow_summary"] = flow_summary_df
    dfs["image_pull_cold_warm_comparison"] = cold_warm_df
    dfs["image_pull_size_duration_comparison"] = size_duration_df
    dfs["image_pull_deploy_phase_duration"] = deploy_phase_df
    dfs["image_pull_invoke_probe_invocation_join"] = invoke_join_df
    dfs["image_pull_paper_highlight"] = paper_df
    dfs["image_pull_self_check"] = check_df

    return dfs
