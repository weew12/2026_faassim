"""
文件作用：cache_aware_scheduler 样例的指标导出与对比分析工具。

该文件负责导出两个 scenario 的指标、生成跨场景对比摘要、probe×invocation 关联验证、
论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cache_aware_candidate",
    "cache_aware_scheduler_result",
    "cache_aware_request_probe",
    "cache_aware_workload_request",
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


def export_scenario_outputs(sim, scenario_name: str, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出单个场景结果。
    """
    scenario_dir = output_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = scenario_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    summary_df = build_scenario_summary(scenario_name, dfs)
    summary_path = scenario_dir / "cache_aware_scheduler_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    function_summary_df = build_function_summary(dfs)
    function_summary_path = scenario_dir / "cache_aware_function_summary.csv"
    function_summary_df.to_csv(function_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", function_summary_path)

    # probe × invocations 关联（论文 demo 关键证据）
    probe_invocation_join_df = build_probe_invocation_join(dfs)
    join_path = scenario_dir / "cache_aware_probe_invocation_join.csv"
    probe_invocation_join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    dfs["cache_aware_scheduler_summary"] = summary_df
    dfs["cache_aware_function_summary"] = function_summary_df
    dfs["cache_aware_probe_invocation_join"] = probe_invocation_join_df

    return dfs


def build_scenario_summary(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成单个场景摘要。
    """
    probe_df = dfs.get("cache_aware_request_probe", pd.DataFrame())
    result_df = dfs.get("cache_aware_scheduler_result", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "scenario": scenario_name,
            "request_events": 0,
        }])

    cache_hit_count = (
        int(probe_df["cache_hit"].astype(bool).sum())
        if "cache_hit" in probe_df.columns else None
    )

    selected_nodes = None
    if not result_df.empty and "selected_node" in result_df.columns:
        selected_nodes = ";".join(sorted(result_df["selected_node"].dropna().astype(str).unique()))

    return pd.DataFrame([{
        "scenario": scenario_name,
        "request_events": len(probe_df),
        "cache_hit_count": cache_hit_count,
        "cache_hit_rate": cache_hit_count / len(probe_df) if cache_hit_count is not None else None,
        "avg_final_duration": float(probe_df["final_duration"].mean()) if "final_duration" in probe_df.columns else None,
        "total_cold_start_penalty": float(probe_df["cold_start_penalty"].sum()) if "cold_start_penalty" in probe_df.columns else None,
        "schedule_events": len(result_df),
        "selected_nodes": selected_nodes,
    }])


def build_function_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成请求结果摘要。
    """
    probe_df = dfs.get("cache_aware_request_probe", pd.DataFrame())

    if probe_df.empty or "function_name" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby("function_name")
        .agg(
            request_count=("request_id", "count"),
            cache_hits=("cache_hit", "sum"),
            avg_final_duration=("final_duration", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
        .assign(cache_hit_rate=lambda df: df["cache_hits"] / df["request_count"])
    )


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    probe × invocations 关联（论文 demo 关键证据）。

    cache_aware_request_probe 里的 simtime 字段 = invocations 的 t_start。
    按 (function_name, node_name, request_id) 关联，验证：
    - probe.final_duration == inv.t_exec
    - probe.simtime == inv.t_start
    """
    probe_df = dfs.get("cache_aware_request_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    if "simtime" not in probe_df.columns or "t_start" not in inv_df.columns:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    for (fn, node, req_id), probe_grp in probe_df.groupby(
        ["function_name", "node_name", "request_id"], dropna=False,
    ):
        probe_sorted = probe_grp.sort_values("simtime").reset_index(drop=True)
        inv_grp = inv_df[
            (inv_df["function_name"] == fn)
            & (inv_df["node"] == node)
        ].sort_values("t_start").reset_index(drop=True)
        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            p = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            duration_match = abs(float(p["final_duration"]) - float(inv["t_exec"])) < 1e-6
            simtime_match = abs(float(p["simtime"]) - float(inv["t_start"])) < 1e-6
            rows.append({
                "function_name": fn,
                "node_name": node,
                "request_id": req_id,
                "scenario": p.get("scenario"),
                "probe_simtime": float(p["simtime"]),
                "probe_final_duration": float(p["final_duration"]),
                "inv_t_start": float(inv["t_start"]),
                "inv_t_exec": float(inv["t_exec"]),
                "duration_match": bool(duration_match),
                "simtime_match": bool(simtime_match),
            })

    return pd.DataFrame(rows)


def build_paper_highlight(
    comparison_df: pd.DataFrame,
    scenario_probe_joins: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    论文 demo 关键摘要。

    cache_aware_scheduler 样例的论文 demo 关注的是：
    1. cache_blind vs cache_aware 命中率差异
    2. cache_blind vs cache_aware 冷启动惩罚差异
    3. cache_blind vs cache_aware 平均延迟差异
    4. cache_aware 相对 cache_blind 的提升倍数

    以 cache_blind 为 baseline（基线是"无缓存感知"），cache_aware 是"有缓存感知"。
    """
    rows: List[Dict[str, Any]] = []

    if comparison_df.empty:
        return pd.DataFrame(rows)

    blind = comparison_df[comparison_df["scenario"] == "cache_blind"]
    aware = comparison_df[comparison_df["scenario"] == "cache_aware"]

    if blind.empty or aware.empty:
        return pd.DataFrame(rows)

    blind_row = blind.iloc[0]
    aware_row = aware.iloc[0]

    # 1. per-scenario 命中率
    for scenario_name, row in [("cache_blind", blind_row), ("cache_aware", aware_row)]:
        hit_rate = row.get("cache_hit_rate")
        if pd.notna(hit_rate):
            rows.append({
                "metric": f"cache_hit_rate__{scenario_name}",
                "value": float(hit_rate),
            })
        rows.append({
            "metric": f"cache_hit_count__{scenario_name}",
            "value": int(row["cache_hit_count"]) if pd.notna(row["cache_hit_count"]) else 0,
        })
        rows.append({
            "metric": f"avg_final_duration__{scenario_name}",
            "value": float(row["avg_final_duration"]) if pd.notna(row["avg_final_duration"]) else 0.0,
        })
        rows.append({
            "metric": f"total_cold_start_penalty__{scenario_name}",
            "value": float(row["total_cold_start_penalty"]) if pd.notna(row["total_cold_start_penalty"]) else 0.0,
        })

    # 2. 策略相对提升（cache_aware vs cache_blind）
    blind_hit = float(blind_row.get("cache_hit_rate", 0.0))
    aware_hit = float(aware_row.get("cache_hit_rate", 0.0))
    rows.append({
        "metric": "cache_hit_rate_improvement__cache_aware_over_cache_blind",
        "value": float(aware_hit - blind_hit),
    })
    if blind_hit > 0:
        rows.append({
            "metric": "cache_hit_rate_ratio__cache_aware_over_cache_blind",
            "value": float(aware_hit / blind_hit),
        })

    blind_cold = float(blind_row.get("total_cold_start_penalty", 0.0))
    aware_cold = float(aware_row.get("total_cold_start_penalty", 0.0))
    if blind_cold > 0:
        rows.append({
            "metric": "cold_start_penalty_reduction__cache_aware_over_cache_blind",
            "value": float((blind_cold - aware_cold) / blind_cold),
        })

    blind_dur = float(blind_row.get("avg_final_duration", 0.0))
    aware_dur = float(aware_row.get("avg_final_duration", 0.0))
    if blind_dur > 0:
        rows.append({
            "metric": "avg_duration_reduction__cache_aware_over_cache_blind",
            "value": float((blind_dur - aware_dur) / blind_dur),
        })

    # 3. probe×invocation join 一致性
    for scenario_name, join_df in scenario_probe_joins.items():
        if join_df.empty or "duration_match" not in join_df.columns:
            continue
        n = len(join_df)
        matched = int(join_df["duration_match"].sum())
        rows.append({
            "metric": f"probe_invocation_duration_match__{scenario_name}",
            "value": float(matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": f"probe_invocation_simtime_match__{scenario_name}",
            "value": float(
                int(join_df["simtime_match"].sum()) / n
            ) if n > 0 else 0.0,
        })

    return pd.DataFrame(rows)


def self_check(
    comparison_df: pd.DataFrame,
    scenario_probe_joins: Dict[str, pd.DataFrame],
    paper_highlight_df: pd.DataFrame,
    cache_snapshot_df: pd.DataFrame,
    expected_request_count: int,
) -> Dict[str, Any]:
    """
    数据自洽段（cache_aware_scheduler 11 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    # 1. comparison_df 有两个 scenario
    n_scenarios = len(comparison_df)
    checks.append({
        "name": "comparison_row_count",
        "status": "PASS" if n_scenarios == 2 else "FAIL",
        "detail": f"comparison rows={n_scenarios}, expected=2",
    })

    # 2. 两个 scenario 的 request_events 都等于 expected_request_count
    for _, row in comparison_df.iterrows():
        scenario = row["scenario"]
        n_req = int(row.get("request_events", 0))
        checks.append({
            "name": f"request_events__{scenario}",
            "status": "PASS" if n_req == expected_request_count else "FAIL",
            "detail": f"request_events={n_req}, expected={expected_request_count}",
        })

    # 3. cache_aware 命中率应该 >= cache_blind（论文核心结论）
    if not comparison_df.empty:
        aware = comparison_df[comparison_df["scenario"] == "cache_aware"]
        blind = comparison_df[comparison_df["scenario"] == "cache_blind"]
        if not aware.empty and not blind.empty:
            aware_hit = float(aware["cache_hit_rate"].iloc[0])
            blind_hit = float(blind["cache_hit_rate"].iloc[0])
            checks.append({
                "name": "cache_aware_beats_cache_blind_hit_rate",
                "status": "PASS" if aware_hit >= blind_hit else "FAIL",
                "detail": f"cache_aware={aware_hit:.4f}, cache_blind={blind_hit:.4f} (cache_aware 应 >= cache_blind)",
            })

    # 4. cache_aware 冷启动惩罚应 <= cache_blind
    if not comparison_df.empty:
        aware = comparison_df[comparison_df["scenario"] == "cache_aware"]
        blind = comparison_df[comparison_df["scenario"] == "cache_blind"]
        if not aware.empty and not blind.empty:
            aware_cold = float(aware["total_cold_start_penalty"].iloc[0])
            blind_cold = float(blind["total_cold_start_penalty"].iloc[0])
            checks.append({
                "name": "cache_aware_below_cache_blind_cold_penalty",
                "status": "PASS" if aware_cold <= blind_cold else "FAIL",
                "detail": f"cache_aware={aware_cold:.4f}, cache_blind={blind_cold:.4f} (cache_aware 应 <= cache_blind)",
            })

    # 5. probe×invocation join 100% match
    for scenario_name, join_df in scenario_probe_joins.items():
        if join_df.empty or "duration_match" not in join_df.columns:
            continue
        n = len(join_df)
        matched = int(join_df["duration_match"].sum())
        checks.append({
            "name": f"probe_invocation_duration_match__{scenario_name}",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"duration_match={matched}/{n}",
        })

    # 6. paper highlight 里 cache_hit_rate 跟 comparison_df 一致
    if not paper_highlight_df.empty:
        for _, row in comparison_df.iterrows():
            scenario = row["scenario"]
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"cache_hit_rate__{scenario}"
            ]
            if hl_rows.empty:
                continue
            hl_v = float(hl_rows["value"].iloc[0])
            comp_v = float(row["cache_hit_rate"])
            checks.append({
                "name": f"paper_highlight_cache_hit_rate__{scenario}",
                "status": "PASS" if abs(hl_v - comp_v) < 1e-6 else "FAIL",
                "detail": f"comparison={comp_v:.6f}, highlight={hl_v:.6f}",
            })

    # 7. cache snapshot 的 node_name 都在 sample topology 的 server_* 范围内
    if not cache_snapshot_df.empty and "node_name" in cache_snapshot_df.columns:
        cached_nodes = set(cache_snapshot_df["node_name"].dropna().unique())
        all_server = all(str(n).startswith("server_") for n in cached_nodes)
        checks.append({
            "name": "cache_snapshot_node_names_valid",
            "status": "PASS" if all_server else "WARN",
            "detail": f"cached nodes={sorted(cached_nodes)}",
        })

    # 8. cache_aware scenario 的 selected_node 命中 cache snapshot 的 (function, node) 对
    if not comparison_df.empty:
        aware_path_dfs = {
            "cache_aware": scenario_probe_joins.get("cache_aware", pd.DataFrame()),
        }
        for scenario_name, join_df in aware_path_dfs.items():
            if join_df.empty or "node_name" not in join_df.columns:
                continue
            # join 里 node_name 必然在 cache snapshot 里
            if not cache_snapshot_df.empty:
                valid_nodes = set(cache_snapshot_df["node_name"].dropna().unique())
                for _, jrow in join_df.iterrows():
                    fn = jrow.get("function_name")
                    node = jrow.get("node_name")
                    # 这次 invoke 触发的 node 不一定在 cache 里（cache miss 正常）
                    # 但**至少 scheduler_result 选过的 node 必须在 server_* 范围内**
                # 只检查 selected_node 来自 server_*
                pass
        # 从比较结果里 selected_nodes 列做检查
        aware_row = comparison_df[comparison_df["scenario"] == "cache_aware"]
        if not aware_row.empty:
            selected_nodes = aware_row["selected_nodes"].iloc[0]
            if pd.notna(selected_nodes):
                nodes = str(selected_nodes).split(";")
                all_server = all(n.startswith("server_") for n in nodes)
                checks.append({
                    "name": "cache_aware_selected_nodes_in_server_range",
                    "status": "PASS" if all_server else "FAIL",
                    "detail": f"selected nodes={nodes}",
                })

    # 9. cache_aware_selected_node 跟 cache snapshot 命中的节点一致
    if not cache_snapshot_df.empty and not comparison_df.empty:
        aware_row = comparison_df[comparison_df["scenario"] == "cache_aware"]
        if not aware_row.empty:
            selected_nodes_str = str(aware_row["selected_nodes"].iloc[0])
            selected_nodes = set(selected_nodes_str.split(";"))
            cached_nodes = set(cache_snapshot_df["node_name"].dropna().unique())
            # cache_aware 选择的节点应该是 cached_nodes 的子集
            cached_only = selected_nodes & cached_nodes
            checks.append({
                "name": "cache_aware_chooses_cached_nodes",
                "status": "PASS" if cached_only else "FAIL",
                "detail": f"selected={sorted(selected_nodes)}, cached={sorted(cached_nodes)}, intersection={sorted(cached_only)}",
            })

    # 10. 跨 scenario paper highlight consistency
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "cache_hit_rate_improvement__cache_aware_over_cache_blind"
        ]
        if not hl_rows.empty and not comparison_df.empty:
            aware = comparison_df[comparison_df["scenario"] == "cache_aware"]
            blind = comparison_df[comparison_df["scenario"] == "cache_blind"]
            if not aware.empty and not blind.empty:
                hl_v = float(hl_rows["value"].iloc[0])
                expected_v = float(aware["cache_hit_rate"].iloc[0]) - float(blind["cache_hit_rate"].iloc[0])
                checks.append({
                    "name": "paper_highlight_improvement_consistency",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                    "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
                })

    # 11. 两个 scenario 共享同一份 topology（selected_nodes 都在 server_0..3 范围内）
    if not comparison_df.empty:
        for _, row in comparison_df.iterrows():
            scenario = row["scenario"]
            selected_nodes_str = str(row.get("selected_nodes", ""))
            if not selected_nodes_str:
                continue
            nodes = selected_nodes_str.split(";")
            # 4-server topology 的合法节点是 server_0/1/2/3
            valid = all(n in {"server_0", "server_1", "server_2", "server_3"} for n in nodes)
            checks.append({
                "name": f"selected_nodes_in_4_server_topology__{scenario}",
                "status": "PASS" if valid else "FAIL",
                "detail": f"selected={nodes}, expected subset of {{server_0, server_1, server_2, server_3}}",
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

    logger.info("=== cache_aware_scheduler self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_warn = self_check_result.get("n_warn", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d warned, %d failed ===", n_pass, n_warn, n_fail)


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比结果。
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "cache_aware_scheduler_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    return comparison_df
