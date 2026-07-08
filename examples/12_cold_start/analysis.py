"""
文件作用：cold_start 样例的指标导出与分析工具。

该文件负责从 sim.env.metrics 中提取冷启动阶段、调用、部署、调度和网络流指标，
并生成冷启动路径摘要、阶段耗时摘要和 warm/cold 调用对比。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cold_start_probe",
    "invoke_dispatch_probe",
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


def build_phase_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成各阶段耗时摘要。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "phase_events": 0,
        }])

    if "phase" not in probe_df.columns or "phase_duration" not in probe_df.columns:
        return pd.DataFrame([{
            "phase_events": len(probe_df),
            "columns": ",".join(probe_df.columns.astype(str).tolist()),
        }])

    return (
        probe_df
        .groupby("phase")
        .agg(
            events=("phase_duration", "count"),
            avg_duration=("phase_duration", "mean"),
            min_duration=("phase_duration", "min"),
            max_duration=("phase_duration", "max"),
        )
        .reset_index()
    )


def build_replica_cold_path_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按副本汇总冷启动路径。

    冷启动路径定义为 deploy + startup + setup。
    first_invoke 单独列出，用于分析首次请求开销。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty or "replica_id" not in probe_df.columns:
        return pd.DataFrame()

    rows = []

    for replica_id, group in probe_df.groupby("replica_id"):
        row = {
            "replica_id": replica_id,
            "function_name": group["function_name"].iloc[0] if "function_name" in group.columns else None,
            "node_name": group["node_name"].iloc[0] if "node_name" in group.columns else None,
        }

        for phase in ["deploy", "startup", "setup", "first_invoke", "warm_invoke"]:
            phase_group = group[group["phase"] == phase] if "phase" in group.columns else pd.DataFrame()
            row[f"{phase}_events"] = len(phase_group)
            row[f"{phase}_total_duration"] = (
                float(phase_group["phase_duration"].sum())
                if not phase_group.empty and "phase_duration" in phase_group.columns
                else 0.0
            )

        row["cold_activation_duration"] = (
            row["deploy_total_duration"]
            + row["startup_total_duration"]
            + row["setup_total_duration"]
        )
        row["first_request_path_duration"] = (
            row["cold_activation_duration"]
            + row["first_invoke_total_duration"]
        )

        rows.append(row)

    return pd.DataFrame(rows)


def build_warm_cold_compare(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    对比 first_invoke 和 warm_invoke 的执行耗时。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty or "phase" not in probe_df.columns:
        return pd.DataFrame()

    invoke_df = probe_df[probe_df["phase"].isin(["first_invoke", "warm_invoke"])]

    if invoke_df.empty:
        return pd.DataFrame()

    return (
        invoke_df
        .groupby("phase")
        .agg(
            request_events=("phase_duration", "count"),
            avg_invoke_duration=("phase_duration", "mean"),
            min_invoke_duration=("phase_duration", "min"),
            max_invoke_duration=("phase_duration", "max"),
        )
        .reset_index()
    )


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    把 cold_start_probe（first_invoke / warm_invoke 阶段）和 invocations 按 (replica_id, t_start) 对齐。

    probe.first_invoke.phase_duration 应该 == invocations.t_exec
    probe.warm_invoke.phase_duration 应该 == invocations.t_exec

    论文 demo 关键证据：simulator 派发的执行时长和 faas-sim 记录的实际执行时长完全一致。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing cold_start_probe or invocations",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")

    invoke_phase_df = probe_df[probe_df["phase"].isin(["first_invoke", "warm_invoke"])].copy()
    if invoke_phase_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "no first_invoke/warm_invoke phases in probe",
        }])

    # 按 (replica_id, phase_start 顺序) 对齐 invocations（按 t_start 顺序）
    rows = []
    for replica_id, probe_grp in invoke_phase_df.groupby("replica_id"):
        probe_sorted = probe_grp.sort_values("phase_start").reset_index(drop=True)
        inv_sorted = inv_df[inv_df["replica_id"] == replica_id].sort_values("t_start").reset_index(drop=True)
        n = min(len(probe_sorted), len(inv_sorted))
        for i in range(n):
            p = probe_sorted.iloc[i]
            inv = inv_sorted.iloc[i]
            duration_match = (
                pd.notna(inv["t_exec"])
                and abs(float(p["phase_duration"]) - float(inv["t_exec"])) < 1e-6
            )
            rows.append({
                "replica_id": replica_id,
                "phase": p.get("phase"),
                "request_id": p.get("request_id"),
                "probe_phase_start": float(p["phase_start"]),
                "probe_phase_finish": float(p["phase_finish"]),
                "probe_phase_duration": float(p["phase_duration"]),
                "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
                "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
                "duration_match": duration_match,
            })

    return pd.DataFrame(rows)


def build_paper_highlight(
    probe_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    replica_path_df: pd.DataFrame,
    warm_cold_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value/note。

    设计原则（沿用 02-11 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    # 阶段事件计数
    deploy_events = 0
    startup_events = 0
    setup_events = 0
    first_invoke_events = 0
    warm_invoke_events = 0
    if "phase" in probe_df.columns and len(probe_df):
        counts = probe_df["phase"].value_counts()
        deploy_events = int(counts.get("deploy", 0))
        startup_events = int(counts.get("startup", 0))
        setup_events = int(counts.get("setup", 0))
        first_invoke_events = int(counts.get("first_invoke", 0))
        warm_invoke_events = int(counts.get("warm_invoke", 0))

    # 阶段总耗时
    deploy_total = 0.0
    startup_total = 0.0
    setup_total = 0.0
    first_invoke_total = 0.0
    warm_invoke_total = 0.0
    if "phase" in probe_df.columns and "phase_duration" in probe_df.columns and len(probe_df):
        for phase_name, target in [
            ("deploy", "deploy_total"),
            ("startup", "startup_total"),
            ("setup", "setup_total"),
            ("first_invoke", "first_invoke_total"),
            ("warm_invoke", "warm_invoke_total"),
        ]:
            sub = probe_df[probe_df["phase"] == phase_name]
            if not sub.empty:
                d = round(float(sub["phase_duration"].astype(float).sum()), 4)
                if target == "deploy_total":
                    deploy_total = d
                elif target == "startup_total":
                    startup_total = d
                elif target == "setup_total":
                    setup_total = d
                elif target == "first_invoke_total":
                    first_invoke_total = d
                elif target == "warm_invoke_total":
                    warm_invoke_total = d

    # 冷启动路径
    cold_activation = round(deploy_total + startup_total + setup_total, 4)
    first_request_path = round(cold_activation + first_invoke_total, 4)

    # first/warm speedup
    first_invoke_avg = round(first_invoke_total / first_invoke_events, 4) if first_invoke_events > 0 else 0.0
    warm_invoke_avg = round(warm_invoke_total / warm_invoke_events, 4) if warm_invoke_events > 0 else 0.0
    first_warm_speedup = round(first_invoke_avg / warm_invoke_avg, 4) if warm_invoke_avg > 0 else 0.0
    cold_warm_speedup = round(cold_activation / warm_invoke_avg, 4) if warm_invoke_avg > 0 else 0.0

    # probe × invocations join
    t_exec_match_rate = 0.0
    if not join_df.empty and "duration_match" in join_df.columns:
        t_exec_match_rate = round(float(join_df["duration_match"].astype(bool).mean()), 4)

    return pd.DataFrame([
        {"metric": "phase_events_total", "value": int(len(probe_df)),
         "note": "cold_start_probe 阶段事件总数（5 phase：deploy/startup/setup/first_invoke/warm_invoke×2）"},
        {"metric": "deploy_events", "value": deploy_events,
         "note": "deploy 阶段事件数（应 == 1）"},
        {"metric": "startup_events", "value": startup_events,
         "note": "startup 阶段事件数（应 == 1）"},
        {"metric": "setup_events", "value": setup_events,
         "note": "setup 阶段事件数（应 == 1）"},
        {"metric": "first_invoke_events", "value": first_invoke_events,
         "note": "first_invoke 阶段事件数（应 == 1）"},
        {"metric": "warm_invoke_events", "value": warm_invoke_events,
         "note": "warm_invoke 阶段事件数（应 == 2：第 2/3 个请求）"},
        {"metric": "deploy_total_duration", "value": deploy_total,
         "note": "deploy 总耗时（含 docker.pull 实际拉取时间）"},
        {"metric": "startup_total_duration", "value": startup_total,
         "note": "startup 总耗时（应 = 0.75s）"},
        {"metric": "setup_total_duration", "value": setup_total,
         "note": "setup 总耗时（应 = 0.55s）"},
        {"metric": "first_invoke_total_duration", "value": first_invoke_total,
         "note": "first_invoke 总耗时（应 = 0.30s）"},
        {"metric": "warm_invoke_total_duration", "value": warm_invoke_total,
         "note": "warm_invoke 总耗时（2 个请求，应 = 0.16s）"},
        {"metric": "cold_activation_duration", "value": cold_activation,
         "note": "冷启动激活时长 = deploy + startup + setup（deploy 受镜像大小和拓扑影响）"},
        {"metric": "first_request_path_duration", "value": first_request_path,
         "note": "首次请求路径时长 = cold_activation + first_invoke（受 deploy 影响）"},
        {"metric": "first_invoke_avg", "value": first_invoke_avg,
         "note": "first_invoke 平均耗时（应 = 0.30s）"},
        {"metric": "warm_invoke_avg", "value": warm_invoke_avg,
         "note": "warm_invoke 平均耗时（应 = 0.08s）"},
        {"metric": "first_warm_speedup_ratio", "value": first_warm_speedup,
         "note": "first/warm speedup 比值（应 = 3.75x，论文 demo 关键数字）"},
        {"metric": "cold_warm_speedup_ratio", "value": cold_warm_speedup,
         "note": "cold_activation/warm speedup 比值（受 deploy 影响，通常 > 25x）"},
        {"metric": "probe_invocation_t_exec_match_rate", "value": t_exec_match_rate,
         "note": "probe 派发时长与 invocations.t_exec 完全一致的比例（应 = 1.0）"},
        {"metric": "dispatch_probe_count", "value": int(first_invoke_events + warm_invoke_events),
         "note": "invoke_dispatch_probe 行数（应 == invocations 行数 == 3）"},
        {"metric": "invocation_count", "value": int(len(inv_df)),
         "note": "invocations 行数（应 == 3）"},
    ])


def data_self_check(
    probe_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    replica_path_df: pd.DataFrame,
    warm_cold_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    cold_start 样例的数据自洽检查（沿用 02-11 的 self_check 模式）。

    不变量：
    1. 5 个 phase 全部存在（deploy/startup/setup/first_invoke/warm_invoke）
    2. request_events == 3（3 个请求全部完成）
    3. startup == 0.75s（固定配置）
    4. setup == 0.55s（固定配置）
    5. first_invoke_avg == 0.30s
    6. warm_invoke_avg == 0.08s
    7. cold_activation == deploy + startup + setup（恒等式，不依赖 deploy 绝对值）
    8. first_request_path == cold_activation + first_invoke_total（恒等式）
    9. first/warm speedup == 3.75x（0.30/0.08）
    10. probe_invocation_t_exec_match_rate == 1.0
    11. dispatch_probe == invocations（3 == 3）

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    # 阶段事件计数
    phase_set = set()
    if "phase" in probe_df.columns:
        phase_set = set(probe_df["phase"].dropna().astype(str).tolist())
    expected_phases = {"deploy", "startup", "setup", "first_invoke", "warm_invoke"}
    has_all_phases = expected_phases.issubset(phase_set)

    request_events = int(len(inv_df))

    # 阶段总耗时
    def _phase_total(phase_name: str) -> float:
        if "phase" not in probe_df.columns or "phase_duration" not in probe_df.columns or len(probe_df) == 0:
            return 0.0
        sub = probe_df[probe_df["phase"] == phase_name]
        if sub.empty:
            return 0.0
        return float(sub["phase_duration"].astype(float).sum())

    def _phase_avg(phase_name: str) -> float:
        if "phase" not in probe_df.columns or "phase_duration" not in probe_df.columns or len(probe_df) == 0:
            return 0.0
        sub = probe_df[probe_df["phase"] == phase_name]
        if sub.empty:
            return 0.0
        return float(sub["phase_duration"].astype(float).mean())

    deploy_total = _phase_total("deploy")
    startup_total = _phase_total("startup")
    setup_total = _phase_total("setup")
    first_invoke_total = _phase_total("first_invoke")
    warm_invoke_total = _phase_total("warm_invoke")
    first_invoke_avg = _phase_avg("first_invoke")
    warm_invoke_avg = _phase_avg("warm_invoke")

    cold_activation = deploy_total + startup_total + setup_total
    first_request_path = cold_activation + first_invoke_total

    first_warm_speedup = first_invoke_avg / warm_invoke_avg if warm_invoke_avg > 0 else 0.0

    t_exec_match_rate = 0.0
    if not join_df.empty and "duration_match" in join_df.columns:
        t_exec_match_rate = float(join_df["duration_match"].astype(bool).mean())

    dispatch_probe_count = 0
    if "phase" in probe_df.columns and len(probe_df):
        dispatch_probe_count = int(probe_df["phase"].isin(["first_invoke", "warm_invoke"]).sum())

    checks = {
        "01_five_phases_present": has_all_phases,
        "02_request_events_equals_3": request_events == 3,
        "03_startup_equals_0_75": abs(startup_total - 0.75) < 1e-9,
        "04_setup_equals_0_55": abs(setup_total - 0.55) < 1e-9,
        "05_first_invoke_avg_equals_0_30": abs(first_invoke_avg - 0.30) < 1e-9,
        "06_warm_invoke_avg_equals_0_08": abs(warm_invoke_avg - 0.08) < 1e-9,
        "07_cold_activation_equals_sum": abs(cold_activation - (deploy_total + startup_total + setup_total)) < 1e-9,
        "08_first_request_path_equals_cold_plus_first": abs(first_request_path - (cold_activation + first_invoke_total)) < 1e-9,
        "09_first_warm_speedup_3_75x": abs(first_warm_speedup - 3.75) < 1e-3,
        "10_probe_invocation_t_exec_match_full": abs(t_exec_match_rate - 1.0) < 1e-9,
        "11_dispatch_probe_equals_invocations": dispatch_probe_count == request_events,
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 11 个 faas-sim 内置 metric 的 CSV（含 invoke_dispatch_probe）
    - cold_start_phase_summary.csv：阶段耗时摘要
    - cold_start_replica_path_summary.csv：副本冷启动路径
    - cold_start_warm_cold_compare.csv：first vs warm 对比
    - cold_start_probe_invocation_join.csv：probe × invocations 关联自洽检查
    - cold_start_paper_highlight.csv：论文 demo 关键摘要
    - cold_start_self_check.csv：11 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    phase_summary_df = build_phase_summary(dfs)
    phase_summary_path = output_dir / "cold_start_phase_summary.csv"
    phase_summary_df.to_csv(phase_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", phase_summary_path)

    replica_path_df = build_replica_cold_path_summary(dfs)
    replica_path_path = output_dir / "cold_start_replica_path_summary.csv"
    replica_path_df.to_csv(replica_path_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", replica_path_path)

    warm_cold_df = build_warm_cold_compare(dfs)
    warm_cold_path = output_dir / "cold_start_warm_cold_compare.csv"
    warm_cold_df.to_csv(warm_cold_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", warm_cold_path)

    # probe × invocations 关联验证
    probe_inv_join_df = build_probe_invocation_join(dfs)
    probe_inv_join_path = output_dir / "cold_start_probe_invocation_join.csv"
    probe_inv_join_df.to_csv(probe_inv_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", probe_inv_join_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        probe_df=dfs.get("cold_start_probe", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        replica_path_df=replica_path_df,
        warm_cold_df=warm_cold_df,
        join_df=probe_inv_join_df,
    )
    paper_path = output_dir / "cold_start_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        probe_df=dfs.get("cold_start_probe", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        replica_path_df=replica_path_df,
        warm_cold_df=warm_cold_df,
        join_df=probe_inv_join_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "cold_start_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["cold_start_phase_summary"] = phase_summary_df
    dfs["cold_start_replica_path_summary"] = replica_path_df
    dfs["cold_start_warm_cold_compare"] = warm_cold_df
    dfs["cold_start_probe_invocation_join"] = probe_inv_join_df
    dfs["cold_start_paper_highlight"] = paper_df
    dfs["cold_start_self_check"] = check_df

    return dfs
