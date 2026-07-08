"""
文件作用：cosimulation 样例的指标导出与分析工具。

该文件负责导出外部 trace、控制交换记录、阶段切换记录、函数调用探针和 faas-sim 常规指标，
并生成协同仿真摘要、probe×invocation 关联验证、论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cosim_exchange",
    "cosim_phase",
    "cosim_workload_phase",
    "cosim_invoke_probe",
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


def build_phase_invoke_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按外部阶段汇总函数调用耗时。
    """
    invoke_df = dfs.get("cosim_invoke_probe", pd.DataFrame())

    if invoke_df.empty:
        return pd.DataFrame([{
            "invoke_events": 0,
        }])

    if "phase_name" not in invoke_df.columns or "final_duration" not in invoke_df.columns:
        return pd.DataFrame([{
            "invoke_events": len(invoke_df),
            "columns": ",".join(invoke_df.columns.astype(str).tolist()),
        }])

    return (
        invoke_df
        .groupby(["phase_name", "controller_action"])
        .agg(
            invoke_events=("final_duration", "count"),
            avg_final_duration=("final_duration", "mean"),
            max_final_duration=("final_duration", "max"),
            avg_runtime_factor=("runtime_factor", "mean"),
            avg_network_delay=("network_delay", "mean"),
        )
        .reset_index()
    )


def build_exchange_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    汇总外部控制器与 faas-sim 之间的交换记录。
    """
    exchange_df = dfs.get("cosim_exchange", pd.DataFrame())

    if exchange_df.empty:
        return pd.DataFrame([{
            "exchange_events": 0,
        }])

    if "phase_name" not in exchange_df.columns:
        return pd.DataFrame([{
            "exchange_events": len(exchange_df),
            "columns": ",".join(exchange_df.columns.astype(str).tolist()),
        }])

    return (
        exchange_df
        .groupby(["phase_name", "controller_action"])
        .agg(
            exchange_events=("runtime_factor", "count"),
            avg_runtime_factor=("runtime_factor", "mean"),
            avg_network_delay=("network_delay", "mean"),
            avg_observed_active_requests=("observed_active_requests", "mean"),
        )
        .reset_index()
    )


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    probe × invocations 关联（论文 demo 关键证据）。

    cosim_invoke_probe 里的 simtime 字段 = invocations 的 t_start。
    按 (function_name, replica_id) 分组，并按 probe.simtime / inv.t_start 顺序对齐，验证：
    - probe.final_duration == inv.t_exec
    - probe.simtime == inv.t_start
    """
    probe_df = dfs.get("cosim_invoke_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    if "simtime" not in probe_df.columns or "t_start" not in inv_df.columns:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    for (fn, rep), probe_grp in probe_df.groupby(
        ["function_name", "replica_id"], dropna=False,
    ):
        probe_sorted = probe_grp.sort_values("simtime").reset_index(drop=True)
        inv_grp = inv_df[
            (inv_df["function_name"] == fn) & (inv_df["replica_id"] == rep)
        ].sort_values("t_start").reset_index(drop=True)
        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            p = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            duration_match = abs(float(p["final_duration"]) - float(inv["t_exec"])) < 1e-6
            simtime_match = abs(float(p["simtime"]) - float(inv["t_start"])) < 1e-6
            rows.append({
                "function_name": fn,
                "replica_id": rep,
                "request_id": p.get("request_id"),
                "phase_name": p.get("phase_name"),
                "probe_simtime": float(p["simtime"]),
                "probe_final_duration": float(p["final_duration"]),
                "inv_t_start": float(inv["t_start"]),
                "inv_t_exec": float(inv["t_exec"]),
                "inv_node": inv.get("node"),
                "duration_match": bool(duration_match),
                "simtime_match": bool(simtime_match),
            })

    return pd.DataFrame(rows)


def build_paper_highlight(
    phase_invoke_summary_df: pd.DataFrame,
    exchange_summary_df: pd.DataFrame,
    external_trace_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要（沿用 02-15 的 metric/value/note 三列模式）。

    cosim 样例跟 14/15 不一样：它只跑一个 trace，没有"policy 对比"。
    论文 demo 关注的是：**外部阶段切换如何在 faas-sim 里产生可量化的影响**。

    输出：
    - 跨阶段聚合 metric（total_phases / total_invocations / total_exchange_events）
    - per-phase invoke_events（probe 记录的实际 invoke 数）
    - per-phase avg_final_duration（外部因子 + 网络延迟的最终耗时）
    - per-phase impact_relative_to_normal（相对于 normal phase 的耗时倍数）
    - controller exchange events（外部控制循环状态交换密度）
    - phase timeline（每个阶段的 start/duration/rps/runtime_factor/network_delay）
    """
    rows: List[Dict[str, Any]] = []

    # 0. 跨阶段聚合 metric
    total_phases = 0
    if not external_trace_df.empty and "phase_name" in external_trace_df.columns:
        total_phases = int(external_trace_df["phase_name"].nunique())
    rows.append({
        "metric": "total_phases",
        "value": total_phases,
        "note": "外部 trace 的 phase 数（normal / edge_pressure / network_slowdown / cooldown）",
    })

    if not phase_invoke_summary_df.empty and "invoke_events" in phase_invoke_summary_df.columns:
        total_invocations = int(phase_invoke_summary_df["invoke_events"].sum())
        rows.append({
            "metric": "total_invocations",
            "value": total_invocations,
            "note": "所有 phase 的 invoke 总数（应 == trace 总 request 数）",
        })

    if not exchange_summary_df.empty and "exchange_events" in exchange_summary_df.columns:
        total_exchange = int(exchange_summary_df["exchange_events"].sum())
        rows.append({
            "metric": "total_exchange_events",
            "value": total_exchange,
            "note": "外部控制器与 faas-sim 的总状态交换数（每 0.5s 一次 × trace duration）",
        })

    rows.append({
        "metric": "phase_summary_count",
        "value": int(len(phase_invoke_summary_df)) if not phase_invoke_summary_df.empty else 0,
        "note": "cosim_phase_invoke_summary.csv 的行数（应 == 不同 (phase, action) 组合数）",
    })
    rows.append({
        "metric": "exchange_summary_count",
        "value": int(len(exchange_summary_df)) if not exchange_summary_df.empty else 0,
        "note": "cosim_exchange_summary.csv 的行数（应 == 不同 (phase, action) 组合数）",
    })

    if not phase_invoke_summary_df.empty and "phase_name" in phase_invoke_summary_df.columns:
        # 取 normal phase 作为 baseline
        baseline_dur = None
        for _, srow in phase_invoke_summary_df.iterrows():
            if srow["phase_name"] == "normal":
                baseline_dur = float(srow["avg_final_duration"])
                break

        for _, srow in phase_invoke_summary_df.iterrows():
            phase = srow["phase_name"]
            action = srow["controller_action"]
            inv_events = int(srow["invoke_events"])
            avg_dur = float(srow["avg_final_duration"])
            rt_factor = float(srow["avg_runtime_factor"])
            net_delay = float(srow["avg_network_delay"])

            rows.append({
                "metric": f"invoke_events__{phase}__{action}",
                "value": inv_events,
                "note": f"{phase} phase 的 probe 记录 invoke 数（= trigger 量，受 phase 边界 lag 影响）",
            })
            rows.append({
                "metric": f"avg_final_duration__{phase}__{action}",
                "value": avg_dur,
                "note": f"{phase} phase 的 avg_final_duration = base_duration × runtime_factor + network_delay",
            })
            if baseline_dur and baseline_dur > 0 and phase != "normal":
                impact = float(avg_dur / baseline_dur)
                rows.append({
                    "metric": f"impact_relative_to_normal__{phase}__{action}",
                    "value": impact,
                    "note": f"{phase} phase 相对 normal baseline 的耗时倍数（论文 demo 关键数字）",
                })

    if not exchange_summary_df.empty and "phase_name" in exchange_summary_df.columns:
        for _, xrow in exchange_summary_df.iterrows():
            phase = xrow["phase_name"]
            action = xrow["controller_action"]
            events = int(xrow["exchange_events"])
            rows.append({
                "metric": f"exchange_events__{phase}__{action}",
                "value": events,
                "note": f"{phase} phase 内外部控制器状态交换次数（控制循环 0.5s 一次）",
            })

    if not external_trace_df.empty and "phase_name" in external_trace_df.columns:
        for _, trow in external_trace_df.iterrows():
            phase = trow["phase_name"]
            rows.append({
                "metric": f"trace_rps__{phase}",
                "value": float(trow["rps"]),
                "note": f"{phase} phase 的 trace 设定 RPS（外部环境负载）",
            })
            rows.append({
                "metric": f"trace_runtime_factor__{phase}",
                "value": float(trow["runtime_factor"]),
                "note": f"{phase} phase 的 trace 设定 runtime_factor（= 1.0 表示无 CPU 放大）",
            })
            rows.append({
                "metric": f"trace_network_delay__{phase}",
                "value": float(trow["network_delay"]),
                "note": f"{phase} phase 的 trace 设定 network_delay（额外的网络延迟）",
            })

    return pd.DataFrame(rows)


def self_check(
    dfs: Dict[str, pd.DataFrame],
    phase_invoke_summary_df: pd.DataFrame,
    exchange_summary_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    probe_join_df: pd.DataFrame,
    expected_total_requests: int,
) -> Dict[str, Any]:
    """
    数据自洽段（cosim 不变量）。
    """
    checks: List[Dict[str, str]] = []

    probe_df = dfs.get("cosim_invoke_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    # 1. cosim_invoke_probe 行数 == expected_total_requests
    n_probe = len(probe_df)
    checks.append({
        "name": "cosim_invoke_probe_count",
        "status": "PASS" if n_probe == expected_total_requests else "FAIL",
        "detail": f"probe rows={n_probe}, expected={expected_total_requests}",
    })

    # 2. invocations 行数 == expected_total_requests
    n_inv = len(inv_df)
    checks.append({
        "name": "invocations_count",
        "status": "PASS" if n_inv == expected_total_requests else "FAIL",
        "detail": f"inv rows={n_inv}, expected={expected_total_requests}",
    })

    # 3. cosim_exchange 行数 > 0（每 0.5s 一次状态交换）
    n_exch = len(dfs.get("cosim_exchange", pd.DataFrame()))
    checks.append({
        "name": "cosim_exchange_count",
        "status": "PASS" if n_exch > 0 else "FAIL",
        "detail": f"exchange rows={n_exch}",
    })

    # 4. cosim_phase 行数 == trace 行数（每个 phase 切一次）
    n_phase = len(dfs.get("cosim_phase", pd.DataFrame()))
    n_trace = len(dfs.get("external_environment_trace", pd.DataFrame()))
    checks.append({
        "name": "cosim_phase_count",
        "status": "PASS" if n_phase == n_trace else "FAIL",
        "detail": f"phase rows={n_phase}, trace rows={n_trace}",
    })

    # 5. probe 有 simtime 字段
    if not probe_df.empty and "simtime" in probe_df.columns:
        checks.append({
            "name": "cosim_invoke_probe_has_simtime",
            "status": "PASS",
            "detail": "simtime column present",
        })
    else:
        checks.append({
            "name": "cosim_invoke_probe_has_simtime",
            "status": "FAIL",
            "detail": "simtime column missing",
        })

    # 6. probe×invocation join 行数必须同时覆盖 probe 和 invocations
    n_join = len(probe_join_df)
    checks.append({
        "name": "probe_invocation_join_row_count",
        "status": "PASS" if n_join == n_probe == n_inv == expected_total_requests else "FAIL",
        "detail": f"join rows={n_join}, probe rows={n_probe}, "
                  f"inv rows={n_inv}, expected={expected_total_requests}",
    })

    # 7. probe×invocation join duration_match 100%
    if not probe_join_df.empty and "duration_match" in probe_join_df.columns:
        n = len(probe_join_df)
        matched = int(probe_join_df["duration_match"].sum())
        checks.append({
            "name": "probe_invocation_duration_match",
            "status": "PASS" if n > 0 and matched == n else "FAIL",
            "detail": f"duration_match={matched}/{n}",
        })
    else:
        checks.append({
            "name": "probe_invocation_duration_match",
            "status": "FAIL",
            "detail": "probe_join empty or missing duration_match column",
        })

    # 8. probe×invocation join simtime_match 100%
    if not probe_join_df.empty and "simtime_match" in probe_join_df.columns:
        n = len(probe_join_df)
        matched = int(probe_join_df["simtime_match"].sum())
        checks.append({
            "name": "probe_invocation_simtime_match",
            "status": "PASS" if n > 0 and matched == n else "FAIL",
            "detail": f"simtime_match={matched}/{n}",
        })

    # 9. per-phase invoke_events 跟 trace rps*duration 接近
    # 注意：phase 边界 lag 会让"前一 phase 触发的 invoke"被 probe 记到前一 phase
    # （probe 在 invoke 开始时记 phase_name，但 invoke 可能跨过 phase 边界完成）。
    # 所以每 phase 实际计数 ∈ [trace_max/2, trace_max * 2] 范围都算合理。
    if not phase_invoke_summary_df.empty and "phase_name" in phase_invoke_summary_df.columns:
        for _, srow in phase_invoke_summary_df.iterrows():
            phase = srow["phase_name"]
            if phase == "idle":
                continue
            n_inv_phase = int(srow["invoke_events"])
            trace_row = dfs.get("external_environment_trace", pd.DataFrame())
            if not trace_row.empty and phase in trace_row["phase_name"].values:
                t = trace_row[trace_row.phase_name == phase].iloc[0]
                trace_max = max(int(float(t["rps"]) * float(t["duration"])), 1)
                # 接受 ±100% 边界：phase 边界 lag 可能在两个 phase 间移动 invoke
                low = max(trace_max // 2, 1)
                high = trace_max * 2
                if low <= n_inv_phase <= high:
                    status = "PASS"
                else:
                    status = "WARN"
                checks.append({
                    "name": f"phase_invoke_count__{phase}",
                    "status": status,
                    "detail": f"actual={n_inv_phase}, trace_max={trace_max} "
                              f"(phase 边界 lag 可能让 ±100% 范围内都算合理)",
                })

    # 10. paper highlight 里每 phase invoke_events 跟 phase_invoke_summary 一致
    if not paper_highlight_df.empty and not phase_invoke_summary_df.empty:
        for _, srow in phase_invoke_summary_df.iterrows():
            phase = srow["phase_name"]
            action = srow["controller_action"]
            expected = int(srow["invoke_events"])
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"invoke_events__{phase}__{action}"
            ]
            if hl_rows.empty:
                continue
            hl_v = int(float(hl_rows["value"].iloc[0]))
            checks.append({
                "name": f"paper_highlight_invoke_events__{phase}__{action}",
                "status": "PASS" if hl_v == expected else "FAIL",
                "detail": f"phase_summary={expected}, paper_highlight={hl_v}",
            })

    # 11. cosim_invoke_probe 必须跟 controller 的 cosim_exchange 同样包含 normal phase
    if not probe_df.empty and "phase_name" in probe_df.columns:
        probe_phases = set(probe_df["phase_name"].dropna().unique())
        exch_df = dfs.get("cosim_exchange", pd.DataFrame())
        if not exch_df.empty and "phase_name" in exch_df.columns:
            exch_phases = set(exch_df["phase_name"].dropna().unique())
            missing = probe_phases - exch_phases
            checks.append({
                "name": "phase_coverage_probe_vs_exchange",
                "status": "PASS" if not missing else "WARN",
                "detail": f"probe phases={sorted(probe_phases)}, "
                          f"exchange phases={sorted(exch_phases)}, missing={sorted(missing)}",
            })

    # 12. cosim_invoke_probe 必须包含 controller action 字段
    if not probe_df.empty and "controller_action" in probe_df.columns:
        n_with_action = int(probe_df["controller_action"].notna().sum())
        checks.append({
            "name": "cosim_invoke_probe_has_controller_action",
            "status": "PASS" if n_with_action == len(probe_df) else "FAIL",
            "detail": f"{n_with_action}/{len(probe_df)} probe rows have controller_action",
        })

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_warn = sum(1 for c in checks if c["status"] == "WARN")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {"checks": checks, "n_pass": n_pass, "n_warn": n_warn, "n_fail": n_fail}


def log_self_check(self_check_result: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log。
    """
    checks = self_check_result.get("checks") or []
    if not checks:
        return

    logger.info("=== cosimulation self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_warn = self_check_result.get("n_warn", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d warned, %d failed ===", n_pass, n_warn, n_fail)


def export_outputs(sim, output_dir: Path, external_trace) -> Dict[str, pd.DataFrame]:
    """
    导出协同仿真结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    trace_df = external_trace.to_dataframe()
    trace_path = output_dir / "external_environment_trace.csv"
    trace_df.to_csv(trace_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_path)

    phase_invoke_summary_df = build_phase_invoke_summary(dfs)
    phase_invoke_summary_path = output_dir / "cosim_phase_invoke_summary.csv"
    phase_invoke_summary_df.to_csv(phase_invoke_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", phase_invoke_summary_path)

    exchange_summary_df = build_exchange_summary(dfs)
    exchange_summary_path = output_dir / "cosim_exchange_summary.csv"
    exchange_summary_df.to_csv(exchange_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", exchange_summary_path)

    # probe×invocation join（论文 demo 关键证据）
    probe_join_df = build_probe_invocation_join(dfs)
    probe_join_path = output_dir / "cosim_probe_invocation_join.csv"
    probe_join_df.to_csv(probe_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", probe_join_path)

    # 论文 demo 关键摘要
    paper_highlight_df = build_paper_highlight(
        phase_invoke_summary_df, exchange_summary_df, trace_df,
    )
    paper_highlight_path = output_dir / "cosim_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    # 在 self_check 之前把 trace_df 加进 dfs，让 cosim_phase_count 自检能拿到 trace 行数
    dfs["external_environment_trace"] = trace_df
    dfs["cosim_phase_invoke_summary"] = phase_invoke_summary_df
    dfs["cosim_exchange_summary"] = exchange_summary_df
    dfs["cosim_probe_invocation_join"] = probe_join_df
    dfs["cosim_paper_highlight"] = paper_highlight_df

    # 数据自洽段
    expected_total = int(
        sum(max(p.rps * p.duration, 1) for p in external_trace.phases)
    )
    self_check_result = self_check(
        dfs, phase_invoke_summary_df, exchange_summary_df,
        paper_highlight_df, probe_join_df, expected_total,
    )
    log_self_check(self_check_result)

    # 把 self_check 写到 self_check.csv（仿 02-15 模式）
    check_df = pd.DataFrame(self_check_result.get("checks") or [])
    if "status" in check_df.columns:
        check_df["passed"] = check_df["status"] == "PASS"
        check_df["warned"] = check_df["status"] == "WARN"
    check_path = output_dir / "self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)
    dfs["self_check"] = check_df

    return dfs
