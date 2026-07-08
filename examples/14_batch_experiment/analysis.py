"""
文件作用：batch_experiment 样例的单次实验指标导出和批量汇总分析。

该文件负责：
- 导出每个 run 的原始指标；
- 从原始指标中提取单行结果；
- 汇总所有 run 为 batch_results.csv；
- 按策略和负载聚合为 batch_summary.csv；
- 论文 demo 关键证据：probe × invocations 关联 + 跨 case 论文摘要。

新增的关键导出：
- batch_probe_invocation_join.csv（每个 run 目录）：probe × invocations 关联验证
  simulator 派发的 duration 和 faas-sim 记录的 t_exec 完全一致。
- batch_paper_highlight.csv（顶层）：跨 policy × workload 对比，含
  saved_invocation_seconds / policy_speedup_ratio 等论文关键字段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from experiment_config import ExperimentCase

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "batch_invoke_probe",
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


def export_case_outputs(sim, case: ExperimentCase, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出单个实验 case 的结果。
    """
    case_dir = output_dir / "runs" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = case_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # probe × invocations 关联
    join_df = build_probe_invocation_join(dfs)
    join_path = case_dir / "batch_probe_invocation_join.csv"
    join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    case_result_df = pd.DataFrame([build_case_result(case, dfs)])
    case_result_path = case_dir / "case_result.csv"
    case_result_df.to_csv(case_result_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", case_result_path)

    dfs["batch_probe_invocation_join"] = join_df
    dfs["case_result"] = case_result_df
    return dfs


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    把 batch_invoke_probe 和 invocations 按 (function_name, replica_id, request_id) 关联。

    probe 记录 simulator 派发的执行时间，invocations 记录 faas-sim 实际执行时间，
    论文 demo 关键证据：两者应该完全相等。
    """
    probe_df = dfs.get("batch_invoke_probe", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing batch_invoke_probe or invocations",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")

    rows = []
    # probe 没有 replica_id 列，按 (function_name, node_name) 分组；不同 node 上的请求不会混
    for (fn, node), probe_grp in probe_df.groupby(["function_name", "node_name"], dropna=False):
        probe_sorted = probe_grp.sort_index().reset_index(drop=True)
        inv_grp = inv_df[(inv_df["function_name"] == fn) & (inv_df["node"] == node)].sort_values("t_start").reset_index(drop=True)
        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            p = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            duration_match = (
                pd.notna(inv["t_exec"])
                and abs(float(p["duration"]) - float(inv["t_exec"])) < 1e-6
            )
            rows.append({
                "function_name": fn,
                "node_name": node,
                "request_id": p.get("request_id"),
                "probe_duration": float(p["duration"]),
                "probe_jitter": float(p["jitter"]) if pd.notna(p.get("jitter")) else None,
                "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
                "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
                "inv_replica_id": inv.get("replica_id"),
                "duration_match": duration_match,
            })

    return pd.DataFrame(rows)


def build_case_result(case: ExperimentCase, dfs: Dict[str, pd.DataFrame]) -> Dict[str, object]:
    """
    从单次实验指标中提取单行结果。
    """
    probe_df = dfs.get("batch_invoke_probe", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    flow_df = dfs.get("flow", pd.DataFrame())

    result = {
        "case_id": case.case_id,
        "policy": case.policy.name,
        "scheduler": case.policy.scheduler,
        "workload": case.workload.name,
        "rps": case.workload.rps,
        "max_requests": case.workload.max_requests,
        "seed": case.seed,
        "probe_events": len(probe_df),
        "invocation_events": len(invocations_df),
        "schedule_events": len(schedule_df),
        "flow_events": len(flow_df),
    }

    # 实际调度到的节点（探针中看到的 node_name）
    if not probe_df.empty and "node_name" in probe_df.columns:
        result["scheduled_node"] = probe_df["node_name"].iloc[0]
        result["scheduled_node_count"] = int(probe_df["node_name"].nunique())

    if not probe_df.empty and "duration" in probe_df.columns:
        result["avg_probe_duration"] = float(probe_df["duration"].mean())
        result["max_probe_duration"] = float(probe_df["duration"].max())
        result["p95_probe_duration"] = float(probe_df["duration"].quantile(0.95))

    invocation_duration_col = None
    if not invocations_df.empty:
        if "t_exec" in invocations_df.columns:
            invocation_duration_col = "t_exec"
        elif "duration" in invocations_df.columns:
            invocation_duration_col = "duration"

    if invocation_duration_col is not None:
        invocation_duration = pd.to_numeric(
            invocations_df[invocation_duration_col],
            errors="coerce",
        )
        result["avg_invocation_duration"] = float(invocation_duration.mean())
        result["max_invocation_duration"] = float(invocation_duration.max())
        result["p95_invocation_duration"] = float(invocation_duration.quantile(0.95))

    if not flow_df.empty and "bytes" in flow_df.columns:
        result["flow_total_bytes"] = int(flow_df["bytes"].sum())

    return result


def export_batch_results(output_dir: Path, case_results: List[pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    导出批量实验总结果 + 论文 demo 关键摘要。
    """
    if case_results:
        batch_results_df = pd.concat(case_results, ignore_index=True)
    else:
        batch_results_df = pd.DataFrame()

    batch_results_path = output_dir / "batch_results.csv"
    batch_results_df.to_csv(batch_results_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", batch_results_path)

    batch_summary_df = build_batch_summary(batch_results_df)
    batch_summary_path = output_dir / "batch_summary.csv"
    batch_summary_df.to_csv(batch_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", batch_summary_path)

    # 论文 demo 关键摘要：policy 效果对比
    paper_highlight_df = build_paper_highlight(batch_results_df)
    paper_highlight_path = output_dir / "batch_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    return {
        "batch_results": batch_results_df,
        "batch_summary": batch_summary_df,
        "batch_paper_highlight": paper_highlight_df,
    }


def self_check_batch_results(
    case_results: List[pd.DataFrame],
    output_dir: Path,
    batch_results_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    批量实验数据自洽段。

    校验：
    1. probe×invocation join（每个 case 都有 batch_probe_invocation_join.csv），
       duration_match 必须 100% True。
    2. batch_results 行数 = 实际 case 数（避免 silent case 被丢）。
    3. paper highlight 的 high_capacity_hit_ratio 必须跟 batch_results 一致。

    返回的 dict 包含：
    - checks：list[dict]（name/status/detail）
    - n_pass / n_fail：统计
    - output_path：batch_self_check.csv 路径
    """
    if not case_results:
        return {"checks": [], "n_pass": 0, "n_fail": 0}

    checks = []

    # 1. probe×invocation join 自洽
    case_ids = []
    if not batch_results_df.empty and "case_id" in batch_results_df.columns:
        case_ids = batch_results_df["case_id"].astype(str).tolist()
    else:
        case_ids = [d.name for d in sorted(output_dir.glob("runs/*")) if d.is_dir()]

    if case_ids:
        for case_id in case_ids:
            case_dir = output_dir / "runs" / case_id
            join_path = case_dir / "batch_probe_invocation_join.csv"
            if not join_path.exists():
                checks.append({
                    "name": f"probe_join_exists__{case_id}",
                    "status": "FAIL",
                    "detail": f"missing {join_path.name}",
                })
                continue

            join_df = pd.read_csv(join_path, encoding="utf-8-sig")
            probe_path = case_dir / "batch_invoke_probe.csv"
            inv_path = case_dir / "invocations.csv"
            probe_rows = len(pd.read_csv(probe_path, encoding="utf-8-sig")) if probe_path.exists() else -1
            inv_rows = len(pd.read_csv(inv_path, encoding="utf-8-sig")) if inv_path.exists() else -1

            total = len(join_df)
            match_series = join_df.get("duration_match", pd.Series(dtype=bool))
            matched = int(match_series.sum()) if total else 0
            ok = (
                total > 0
                and probe_rows == inv_rows == total
                and match_series.notna().all()
                and matched == total
            )
            checks.append({
                "name": f"probe_invocation_join_match__{case_id}",
                "status": "PASS" if ok else "FAIL",
                "detail": f"duration_match={matched}/{total}, probe_rows={probe_rows}, invocation_rows={inv_rows}",
            })

    # 2. batch_results 行数 == case 数
    n_cases_ran = len(case_results)
    n_results = len(batch_results_df)
    checks.append({
        "name": "batch_results_row_count",
        "status": "PASS" if n_results == n_cases_ran else "FAIL",
        "detail": f"batch_results rows={n_results}, ran cases={n_cases_ran}",
    })

    # 3. paper highlight 命中率
    expected_high_capacity_ratio = {
        "default_skippy": 1.0,
        "fixed_node": 0.0,
    }
    if not batch_results_df.empty and "scheduled_node" in batch_results_df.columns:
        for policy in batch_results_df["policy"].unique():
            sub = batch_results_df[batch_results_df.policy == policy]
            total = len(sub)
            high = int((sub["scheduled_node"] == "server_1").sum())
            ratio = (high / total) if total > 0 else 0.0
            expected_ratio = expected_high_capacity_ratio.get(policy)
            if expected_ratio is None:
                ok = total > 0
                expected_text = "not fixed"
            else:
                ok = abs(ratio - expected_ratio) < 1e-9
                expected_text = f"{expected_ratio:.2f}"
            checks.append({
                "name": f"high_capacity_hit_ratio__{policy}",
                "status": "PASS" if ok else "FAIL",
                "detail": f"hit {high}/{total} = {ratio:.2f}, expected={expected_text}",
            })

    # 写到 batch_self_check.csv
    check_df = pd.DataFrame(checks)
    if "status" in check_df.columns:
        check_df["passed"] = check_df["status"] == "PASS"
    output_path = output_dir / "batch_self_check.csv"
    check_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", output_path)

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")

    return {
        "checks": checks,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "output_path": output_path,
    }


def log_self_check(self_check: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log。
    """
    checks = self_check.get("checks") or []
    if not checks:
        return

    logger.info("=== batch experiment self-check ===")
    for c in checks:
        status = c["status"]
        name = c["name"]
        detail = c.get("detail", "")
        logger.info("  [%s] %s : %s", status, name, detail)

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def build_batch_summary(batch_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    按 policy 和 workload 汇总批量实验结果。
    """
    if batch_results_df.empty:
        return pd.DataFrame()

    agg_spec = {
        "runs": ("case_id", "count"),
        "avg_probe_events": ("probe_events", "mean"),
        "avg_invocation_events": ("invocation_events", "mean"),
    }

    if "avg_probe_duration" in batch_results_df.columns:
        agg_spec["mean_avg_probe_duration"] = ("avg_probe_duration", "mean")
        agg_spec["mean_p95_probe_duration"] = ("p95_probe_duration", "mean")

    if "avg_invocation_duration" in batch_results_df.columns:
        agg_spec["mean_avg_invocation_duration"] = ("avg_invocation_duration", "mean")

    if "scheduled_node" in batch_results_df.columns:
        agg_spec["distinct_scheduled_nodes"] = ("scheduled_node", "nunique")

    if "flow_total_bytes" in batch_results_df.columns:
        agg_spec["avg_flow_total_bytes"] = ("flow_total_bytes", "mean")

    return (
        batch_results_df
        .groupby(["policy", "workload"])
        .agg(**agg_spec)
        .reset_index()
    )


def build_paper_highlight(batch_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    论文 demo 关键摘要（沿用 02-13 的 paper_highlight 模式：metric/value/note 三列）。

    在当前最小 4-server topology 里：
    - server_0 1cpu（small）
    - server_1 8cpu（large）
    - server_2/3 4cpu（medium）

    default_skippy（实现走 CapacityAwareScheduler）应选 server_1，
    fixed_node 强制选 server_0。

    当前 sim 模型的 `t_exec` 等于 base_duration（节点 capacity 不会
    改变 single-invocation duration），所以两个 policy 的 avg_probe_duration
    在 batch_results 里基本一致；真正可量化的差异在 **scheduled_node 选择**：

    - per-policy scheduled_nodes 列表
    - per-policy scheduled_node==server_1 的比例（"容量感知命中率"）
    - per-workload policy 命中率对比
    - 跨 case 聚合（total_invocations / total_policies / total_workloads）
    """
    if batch_results_df.empty:
        return pd.DataFrame()

    rows = []

    # 跨 case 聚合 metric
    total_cases = int(len(batch_results_df))
    rows.append({
        "metric": "total_cases",
        "value": total_cases,
        "note": "批量实验总 case 数（= policies × workloads × seeds）",
    })

    if "policy" in batch_results_df.columns:
        rows.append({
            "metric": "total_policies",
            "value": int(batch_results_df["policy"].nunique()),
            "note": "策略数",
        })
    if "workload" in batch_results_df.columns:
        rows.append({
            "metric": "total_workloads",
            "value": int(batch_results_df["workload"].nunique()),
            "note": "负载数",
        })
    if "seed" in batch_results_df.columns:
        rows.append({
            "metric": "total_seeds",
            "value": int(batch_results_df["seed"].nunique()),
            "note": "随机种子数",
        })
    if "invocation_events" in batch_results_df.columns:
        total_invocations = int(batch_results_df["invocation_events"].sum())
        rows.append({
            "metric": "total_invocations",
            "value": total_invocations,
            "note": "跨所有 case 的总 invoke 次数",
        })
        rows.append({
            "metric": "avg_invocations_per_case",
            "value": round(total_invocations / total_cases, 4) if total_cases > 0 else 0.0,
            "note": "每个 case 平均 invoke 次数（= total_invocations / total_cases）",
        })

    # 每个 policy 实际选过的节点
    if "scheduled_node" in batch_results_df.columns:
        for policy in batch_results_df["policy"].unique():
            sub = batch_results_df[batch_results_df.policy == policy]
            nodes = sorted(sub["scheduled_node"].dropna().unique().tolist())
            rows.append({
                "metric": f"scheduled_nodes__{policy}",
                "value": ",".join(nodes),
                "note": f"{policy} 策略实际选过的节点集合",
            })
            # 命中率：选到 capacity 最大的 server_1 的比例
            total = len(sub)
            high = int((sub["scheduled_node"] == "server_1").sum())
            ratio = (high / total) if total > 0 else 0.0
            if policy == "default_skippy":
                expected_note = "应 = 1.0，表示 capacity-aware 策略全部选中 server_1"
            elif policy == "fixed_node":
                expected_note = "应 = 0.0，表示 fixed_node 策略不会选中 server_1"
            else:
                expected_note = "按策略定义解释"
            rows.append({
                "metric": f"high_capacity_hit_ratio__{policy}",
                "value": float(ratio),
                "note": f"{policy} 策略选中 capacity 最大的 server_1 的比例（{expected_note}）",
            })

    # 节点层 probe duration（= simulator.base_duration, sim 不可分；保留作 sanity check）
    if "avg_probe_duration" in batch_results_df.columns:
        pivot_dur = batch_results_df.pivot_table(
            index="workload", columns="policy",
            values="avg_probe_duration", aggfunc="mean",
        )
        for workload in pivot_dur.index:
            for policy in pivot_dur.columns:
                v = pivot_dur.loc[workload, policy]
                if pd.notna(v):
                    rows.append({
                        "metric": f"{policy}__avg_probe_seconds__{workload}",
                        "value": float(v),
                        "note": f"{policy} 策略在 {workload} 下的 avg_probe_seconds（sim 模型诚实特性：capacity 不改 single-invoke duration）",
                    })

    return pd.DataFrame(rows)
