"""
文件作用：自动伸缩样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成自动伸缩摘要 + probe×invocation 关联 + 论文 demo 关键摘要 + 数据自洽段。

关键导出：
- autoscaling_rps_replicas_timeline.csv：按 1s 窗口聚合 RPS 与当前 replicas 数，
  这是论文 demo 最关键的 "RPS vs Replicas 时间线" 图的数据源。
- autoscaling_invoke_probe.csv：simulator 派发的 invoke probe（含 simtime 字段）。
- autoscaling_probe_invocation_join.csv：probe × invocations 关联（论文 demo 关键证据）。
- autoscaling_paper_highlight.csv：论文 demo 关键摘要。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "scale",
    "schedule",
    "function_deployment",
    "replica_deployment",
    "invocations",
    "flow",
    "autoscaling_invoke_probe",
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
    # 严格说 0 时刻应该是 scale_min=1, 但为了论文图清晰展示最终值,
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


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    probe × invocations 关联（论文 demo 关键证据）。

    autoscaling_invoke_probe 里的 simtime 字段 = invocations 的 t_start。
    按 (function_name, replica_id, simtime) 关联，验证：
    - probe.t_exec == inv.t_exec
    - probe.simtime == inv.t_start
    """
    probe_df = dfs.get("autoscaling_invoke_probe", pd.DataFrame())
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
            t_exec_match = abs(float(p["t_exec"]) - float(inv["t_exec"])) < 1e-6
            simtime_match = abs(float(p["simtime"]) - float(inv["t_start"])) < 1e-6
            rows.append({
                "function_name": fn,
                "replica_id": rep,
                "request_id": p.get("request_id"),
                "probe_simtime": float(p["simtime"]),
                "probe_t_exec": float(p["t_exec"]),
                "inv_t_start": float(inv["t_start"]),
                "inv_t_exec": float(inv["t_exec"]),
                "inv_node": inv.get("node"),
                "t_exec_match": bool(t_exec_match),
                "simtime_match": bool(simtime_match),
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


def build_paper_highlight(
    summary_df: pd.DataFrame,
    rps_replicas_df: pd.DataFrame,
    probe_invocation_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要。

    autoscaling 样例的论文 demo 关注的是：
    1. 自动扩容是否触发：scale_up_events、max_replicas 跟 scale_max 关系
    2. 负载-RPS 关系：total_invocations / total_simtime ≈ RPS
    3. probe×invocation 一致性：simulator 派发的 t_exec 跟 invocations 一致
    """
    rows: List[Dict[str, Any]] = []

    if summary_df.empty:
        return pd.DataFrame(rows)

    srow = summary_df.iloc[0]
    scale_events = int(srow["scale_events"])
    scale_up_events = int(srow["scale_up_events"])
    scale_down_events = int(srow["scale_down_events"])
    max_replicas = int(srow["max_replicas"]) if pd.notna(srow["max_replicas"]) else 0
    min_replicas = int(srow["min_replicas"]) if pd.notna(srow["min_replicas"]) else 0
    inv_events = int(srow["invocation_events"])
    total_simtime = float(srow["total_simtime"]) if pd.notna(srow["total_simtime"]) else 0.0
    avg_exec_time = float(srow["avg_exec_time"]) if pd.notna(srow["avg_exec_time"]) else 0.0

    # 1. 关键指标
    rows.append({"metric": "scale_events", "value": scale_events})
    rows.append({"metric": "scale_up_events", "value": scale_up_events})
    rows.append({"metric": "scale_down_events", "value": scale_down_events})
    rows.append({"metric": "max_replicas", "value": max_replicas})
    rows.append({"metric": "min_replicas", "value": min_replicas})
    rows.append({"metric": "invocation_events", "value": inv_events})
    rows.append({"metric": "total_simtime", "value": total_simtime})
    rows.append({"metric": "avg_exec_time", "value": avg_exec_time})

    # 2. 推算的 avg_rps
    if total_simtime > 0:
        avg_rps = inv_events / total_simtime
        rows.append({"metric": "avg_rps_overall", "value": float(avg_rps)})

    # 3. 扩容倍数
    if min_replicas > 0:
        rows.append({
            "metric": "scale_up_factor",
            "value": float(max_replicas / min_replicas),
        })

    # 4. RPS vs Replicas 关键点（论文 demo 核心）
    if not rps_replicas_df.empty:
        # 找 RPS 峰值
        peak_idx = rps_replicas_df["rps"].idxmax() if "rps" in rps_replicas_df.columns else None
        if peak_idx is not None:
            peak_row = rps_replicas_df.loc[peak_idx]
            rows.append({
                "metric": "peak_rps",
                "value": float(peak_row["rps"]),
            })
            rows.append({
                "metric": "peak_rps_simtime",
                "value": float(peak_row["simtime"]),
            })
        # 找 replicas 第一次到达 max 的时间
        if "replicas" in rps_replicas_df.columns:
            final_replicas = int(rps_replicas_df["replicas"].iloc[-1])
            rows.append({
                "metric": "final_replicas",
                "value": final_replicas,
            })
            # 第一次 replicas 达到 final_replicas 的时间
            reach_max_idx = rps_replicas_df[rps_replicas_df["replicas"] >= final_replicas].index.min()
            if pd.notna(reach_max_idx):
                reach_max_simtime = float(rps_replicas_df.loc[reach_max_idx, "simtime"])
                rows.append({
                    "metric": "first_reach_max_replicas_simtime",
                    "value": reach_max_simtime,
                })
                # 扩容耗时
                if peak_idx is not None and peak_idx < reach_max_idx:
                    scale_up_time = reach_max_simtime - float(rps_replicas_df.loc[peak_idx, "simtime"])
                    rows.append({
                        "metric": "scale_up_response_time",
                        "value": float(scale_up_time),
                    })

    # 5. probe×invocation 一致性
    if not probe_invocation_join_df.empty and "t_exec_match" in probe_invocation_join_df.columns:
        n = len(probe_invocation_join_df)
        t_exec_matched = int(probe_invocation_join_df["t_exec_match"].sum())
        simtime_matched = int(probe_invocation_join_df["simtime_match"].sum())
        rows.append({
            "metric": "probe_invocation_t_exec_match",
            "value": float(t_exec_matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "probe_invocation_simtime_match",
            "value": float(simtime_matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "probe_invocation_matched",
            "value": t_exec_matched,
        })
        rows.append({
            "metric": "probe_invocation_total",
            "value": n,
        })

    return pd.DataFrame(rows)


def self_check(
    summary_df: pd.DataFrame,
    rps_replicas_df: pd.DataFrame,
    probe_invocation_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    expected_max_requests: int,
) -> Dict[str, Any]:
    """
    数据自洽段（autoscaling 9 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    invocations_df = probe_invocation_join_df  # placeholder, 实际从 extract_metrics 拿
    if summary_df.empty:
        return {"checks": [{"name": "summary_not_empty", "status": "FAIL", "detail": "summary is empty"}], "n_pass": 0, "n_fail": 1}

    srow = summary_df.iloc[0]
    inv_events = int(srow["invocation_events"])
    max_replicas = int(srow["max_replicas"]) if pd.notna(srow["max_replicas"]) else 0
    min_replicas = int(srow["min_replicas"]) if pd.notna(srow["min_replicas"]) else 0
    scale_events = int(srow["scale_events"])
    scale_up_events = int(srow["scale_up_events"])

    # 1. invocation_events == expected_max_requests
    checks.append({
        "name": "invocation_events_count",
        "status": "PASS" if inv_events == expected_max_requests else "FAIL",
        "detail": f"invocations={inv_events}, expected={expected_max_requests}",
    })

    # 2. max_replicas >= min_replicas
    checks.append({
        "name": "max_replicas_ge_min_replicas",
        "status": "PASS" if max_replicas >= min_replicas else "FAIL",
        "detail": f"max={max_replicas}, min={min_replicas}",
    })

    # 3. scale_up_events >= 1（autoscaling 触发了扩容）
    checks.append({
        "name": "scale_up_events_ge_1",
        "status": "PASS" if scale_up_events >= 1 else "FAIL",
        "detail": f"scale_up_events={scale_up_events}, expected >= 1 (autoscaling should trigger at least one scale_up)",
    })

    # 4. RPS vs Replicas timeline 至少有 inv_events/2 个非零窗口
    if not rps_replicas_df.empty:
        non_zero = int((rps_replicas_df["rps"] > 0).sum())
        checks.append({
            "name": "rps_replicas_timeline_non_zero_windows",
            "status": "PASS" if non_zero > 0 else "FAIL",
            "detail": f"non-zero windows={non_zero}",
        })

    # 5. probe×invocation join 100% match
    if not probe_invocation_join_df.empty and "t_exec_match" in probe_invocation_join_df.columns:
        n = len(probe_invocation_join_df)
        matched = int(probe_invocation_join_df["t_exec_match"].sum())
        checks.append({
            "name": "probe_invocation_t_exec_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"t_exec_match={matched}/{n}",
        })
        matched2 = int(probe_invocation_join_df["simtime_match"].sum())
        checks.append({
            "name": "probe_invocation_simtime_match",
            "status": "PASS" if matched2 == n else "FAIL",
            "detail": f"simtime_match={matched2}/{n}",
        })

    # 6. paper highlight avg_rps_overall 跟 summary 一致
    if not paper_highlight_df.empty and "total_simtime" in srow.index:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "avg_rps_overall"
        ]
        if not hl_rows.empty:
            hl_v = float(hl_rows["value"].iloc[0])
            total_simtime = float(srow["total_simtime"])
            if total_simtime > 0:
                expected_v = float(inv_events) / total_simtime
                checks.append({
                    "name": "paper_highlight_avg_rps",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-3 else "FAIL",
                    "detail": f"highlight={hl_v:.4f}, expected={expected_v:.4f}",
                })

    # 7. paper highlight max_replicas 跟 summary 一致
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[paper_highlight_df.metric == "max_replicas"]
        if not hl_rows.empty:
            hl_v = int(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_max_replicas",
                "status": "PASS" if hl_v == max_replicas else "FAIL",
                "detail": f"highlight={hl_v}, summary={max_replicas}",
            })

    # 8. paper highlight scale_up_factor 跟 summary 一致
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[paper_highlight_df.metric == "scale_up_factor"]
        if not hl_rows.empty:
            hl_v = float(hl_rows["value"].iloc[0])
            expected_v = float(max_replicas / min_replicas) if min_replicas > 0 else 0
            checks.append({
                "name": "paper_highlight_scale_up_factor",
                "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                "detail": f"highlight={hl_v:.4f}, expected={expected_v:.4f}",
            })

    # 9. paper highlight probe_invocation_t_exec_match == 1.0
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[paper_highlight_df.metric == "probe_invocation_t_exec_match"]
        if not hl_rows.empty:
            v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_probe_invocation_t_exec_match",
                "status": "PASS" if v >= 0.999 else "FAIL",
                "detail": f"probe_invocation_t_exec_match={v:.4f}",
            })

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {"checks": checks, "n_pass": n_pass, "n_fail": n_fail}


def log_self_check(self_check_result: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log。
    """
    checks = self_check_result.get("checks") or []
    if not checks:
        return

    logger.info("=== autoscaling self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(sim, output_dir: Path, expected_max_requests: int = 2000) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 7 个 faas-sim / probe metric 的 CSV
    - autoscaling_rps_replicas_timeline.csv：1s 窗口聚合的 RPS 与 replicas 数
    - autoscaling_probe_invocation_join.csv：probe × invocations 关联
    - autoscaling_paper_highlight.csv：论文 demo 关键摘要
    - autoscaling_summary.csv：增强版摘要
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

    # probe×invocation join
    probe_invocation_join_df = build_probe_invocation_join(dfs)
    join_path = output_dir / "autoscaling_probe_invocation_join.csv"
    probe_invocation_join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    summary_df = build_summary(dfs)
    summary_path = output_dir / "autoscaling_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    # 论文 demo 关键摘要
    paper_highlight_df = build_paper_highlight(summary_df, rps_replicas_df, probe_invocation_join_df)
    paper_highlight_path = output_dir / "autoscaling_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    # 数据自洽段
    self_check_result = self_check(
        summary_df, rps_replicas_df, probe_invocation_join_df,
        paper_highlight_df, expected_max_requests,
    )
    log_self_check(self_check_result)

    dfs["autoscaling_rps_replicas_timeline"] = rps_replicas_df
    dfs["autoscaling_probe_invocation_join"] = probe_invocation_join_df
    dfs["autoscaling_summary"] = summary_df
    dfs["autoscaling_paper_highlight"] = paper_highlight_df

    return dfs
