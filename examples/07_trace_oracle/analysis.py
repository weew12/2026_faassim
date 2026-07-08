"""
文件作用：trace_oracle 样例的指标导出与简要分析工具。

该文件负责导出 trace_oracle_sample、invocations、schedule 等指标，
并生成 trace-driven 执行时间摘要。

新增的关键导出（沿用 02_load_balancer / 03_skippy_scheduler / 04_network_flow / 05_image_pull_network / 06_resource_monitor 的 paper_highlight / data_self_check 模式）：
- trace_invoke_sample_join.csv：每个 invoke 与其使用的 trace sample 一一对应，
  论文 demo 关键证据：证明 oracle 取样和 invoke 实际执行时间完全一致。
- trace_cycle_summary.csv：trace 循环覆盖证据。
- trace_oracle_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value（10 条）
- trace_oracle_self_check.csv：
    10 项数据自检（PASS/FAIL）
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from oracle import TraceRuntimeOracle

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "trace_oracle_sample",
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


def build_trace_sample_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据实际取样记录生成执行时间摘要。
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame())

    if sample_df.empty:
        return pd.DataFrame([{
            "sample_events": 0,
        }])

    group_columns = [
        col for col in ["function_name"]
        if col in sample_df.columns
    ]

    if not group_columns or "duration" not in sample_df.columns:
        return pd.DataFrame([{
            "sample_events": len(sample_df),
            "columns": ",".join(sample_df.columns.astype(str).tolist()),
        }])

    return (
        sample_df
        .groupby(group_columns)
        .agg(
            sample_events=("duration", "count"),
            avg_sampled_duration=("duration", "mean"),
            min_sampled_duration=("duration", "min"),
            max_sampled_duration=("duration", "max"),
        )
        .reset_index()
    )


def build_trace_invoke_sample_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    把 trace_oracle_sample、invoke_dispatch_probe 与 invocations 按函数内取样次序一一对应。

    trace_oracle_sample 按记录顺序记录了 oracle 实际派出的样本；
    invoke_dispatch_probe 记录 invoke 派发时的 trace_sample_id / trace_duration；
    invocations 按 t_start 顺序记录了每次函数调用。
    对同一函数，把三者按各自的出现顺序对齐，就得到：

    - sample_id         trace 中本次 invoke 使用的样本序号
    - sample_duration   oracle 派出的执行时间（来自 trace）
    - probe_trace_*     invoke 派发探针中的 trace 样本信息
    - inv_t_exec        invocations.csv 中本次 invoke 的实际执行时间
    - duration_match    sample_duration 和 inv_t_exec 是否完全相等
    - probe_sample_match / probe_invocation_match

    论文 demo 关键证据：证明 oracle 取样和实际 invoke 执行时间一致。
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()
    probe_df = dfs.get("invoke_dispatch_probe", pd.DataFrame()).copy()

    if sample_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing trace_oracle_sample or invocations dataframe",
        }])

    if "function_name" not in sample_df.columns or "function_name" not in inv_df.columns:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "function_name column missing",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")
    if not probe_df.empty and "simtime" in probe_df.columns:
        probe_df["simtime"] = pd.to_numeric(probe_df["simtime"], errors="coerce")
    if not probe_df.empty and "trace_duration" in probe_df.columns:
        probe_df["trace_duration"] = pd.to_numeric(probe_df["trace_duration"], errors="coerce")

    # 按函数分别按记录顺序对齐。
    rows: List[dict] = []
    function_names = set(sample_df["function_name"].unique()) | set(inv_df["function_name"].unique())
    if not probe_df.empty and "function_name" in probe_df.columns:
        function_names |= set(probe_df["function_name"].unique())

    for fn in sorted(function_names):
        samp_fn = sample_df[sample_df["function_name"] == fn].sort_index().reset_index(drop=True)
        inv_fn = inv_df[inv_df["function_name"] == fn].sort_values("t_start").reset_index(drop=True)
        if not probe_df.empty and "function_name" in probe_df.columns:
            probe_fn = probe_df[probe_df["function_name"] == fn].sort_values("simtime").reset_index(drop=True)
        else:
            probe_fn = pd.DataFrame()

        n = min(len(samp_fn), len(inv_fn))
        if not probe_fn.empty:
            n = min(n, len(probe_fn))
        for i in range(n):
            s = samp_fn.iloc[i]
            inv = inv_fn.iloc[i]
            probe = probe_fn.iloc[i] if not probe_fn.empty else None
            duration_match = (
                pd.notna(inv["t_exec"])
                and abs(float(s["duration"]) - float(inv["t_exec"])) < 1e-6
            )
            probe_sample_match = False
            probe_invocation_match = False
            if probe is not None:
                probe_sample_match = (
                    int(probe["trace_sample_id"]) == int(s["sample_id"])
                    and abs(float(probe["trace_duration"]) - float(s["duration"])) < 1e-6
                )
                probe_invocation_match = (
                    abs(float(probe["simtime"]) - float(inv["t_start"])) < 1e-6
                    and abs(float(probe["trace_duration"]) - float(inv["t_exec"])) < 1e-6
                    and str(probe["node"]) == str(inv["node"])
                )
            rows.append({
                "function_name": fn,
                "invoke_order": i + 1,
                "sample_id": int(s["sample_id"]),
                "sample_duration": float(s["duration"]),
                "probe_trace_sample_id": int(probe["trace_sample_id"]) if probe is not None else None,
                "probe_trace_duration": float(probe["trace_duration"]) if probe is not None else None,
                "probe_simtime": float(probe["simtime"]) if probe is not None else None,
                "request_id": s.get("request_id") if "request_id" in s else None,
                "node": s.get("node_name") if "node_name" in s else None,
                "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
                "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
                "inv_t_wait": float(inv["t_wait"]) if pd.notna(inv["t_wait"]) else None,
                "duration_match": duration_match,
                "probe_sample_match": bool(probe_sample_match),
                "probe_invocation_match": bool(probe_invocation_match),
            })

    return pd.DataFrame(rows)


def build_trace_cycle_summary(
    dfs: Dict[str, pd.DataFrame],
    trace_input_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    统计每个函数的 trace 循环覆盖情况。

    - input_samples：trace CSV 中的样本数
    - actual_samples：本次 run 实际取样次数（来自 trace_oracle_sample）
    - cycles_used：actual_samples / input_samples 向上取整
      例如 fast 函数 16 次 invoke、12 个 trace 样本 → cycles_used=2
    - cycles_used_minus_first：完整 cycle 数（不含最后一个不完整 cycle）
    - last_sample_id：最后一次取样的 sample_id（用于验证循环回卷行为）
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame()).copy()

    if sample_df.empty or trace_input_summary.empty:
        return pd.DataFrame([{
            "trace_cycle_rows": 0,
            "message": "missing trace_oracle_sample or trace_input_summary",
        }])

    rows: List[dict] = []
    for fn in trace_input_summary["function_name"].tolist():
        input_count = int(
            trace_input_summary.loc[
                trace_input_summary["function_name"] == fn, "sample_count"
            ].iloc[0]
        )
        sub = sample_df[sample_df["function_name"] == fn].sort_index()
        actual = len(sub)
        cycles = (actual + input_count - 1) // input_count if input_count > 0 else 0
        full_cycles = actual // input_count if input_count > 0 else 0
        last_sample_id = int(sub["sample_id"].iloc[-1]) if not sub.empty else None
        rows.append({
            "function_name": fn,
            "input_samples": input_count,
            "actual_samples": actual,
            "cycles_used": cycles,
            "full_cycles": full_cycles,
            "last_sample_id": last_sample_id,
        })

    return pd.DataFrame(rows)


def build_invocation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据 invocations 指标生成调用摘要。
    """
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if invocations_df.empty:
        return pd.DataFrame([{
            "invocation_events": 0,
        }])

    if "function_name" not in invocations_df.columns:
        return pd.DataFrame([{
            "invocation_events": len(invocations_df),
            "columns": ",".join(invocations_df.columns.astype(str).tolist()),
        }])

    agg_dict = {
        "invocation_events": ("function_name", "count"),
    }

    if "duration" in invocations_df.columns:
        agg_dict["avg_invocation_duration"] = ("duration", "mean")
        agg_dict["max_invocation_duration"] = ("duration", "max")

    return (
        invocations_df
        .groupby("function_name")
        .agg(**agg_dict)
        .reset_index()
    )


def build_paper_highlight(
    sample_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    cycle_df: pd.DataFrame,
    input_summary_df: pd.DataFrame,
    probe_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02/03/04/05/06 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if sample_df.empty or inv_df.empty:
        return pd.DataFrame([
            {"metric": "duration_match_count", "value": 0,
             "note": "trace_oracle_sample 与 invocations 一致的行数"},
        ])

    total_trace_samples = int(sample_df["sample_id"].count())
    invocation_events = int(len(inv_df))

    duration_match_count = 0
    if not join_df.empty and "duration_match" in join_df.columns:
        duration_match_count = int(join_df["duration_match"].sum())
    duration_match_ratio = (
        duration_match_count / invocation_events if invocation_events > 0 else 0.0
    )

    # cycles
    cycles_used_fast = 0
    last_sample_id_fast = 0
    if not cycle_df.empty and "function_name" in cycle_df.columns:
        fast_row = cycle_df[cycle_df["function_name"].str.contains("fast", case=False)]
        if not fast_row.empty:
            cycles_used_fast = int(fast_row["cycles_used"].iloc[0])
            last_sample_id_fast = int(fast_row["last_sample_id"].iloc[0])

    # avg duration per function
    fast_avg_duration = 0.0
    slow_avg_duration = 0.0
    if not inv_df.empty and "t_exec" in inv_df.columns and "function_name" in inv_df.columns:
        for fn, sub in inv_df.groupby("function_name"):
            if "fast" in str(fn).lower():
                fast_avg_duration = float(pd.to_numeric(sub["t_exec"], errors="coerce").mean())
            elif "slow" in str(fn).lower():
                slow_avg_duration = float(pd.to_numeric(sub["t_exec"], errors="coerce").mean())

    # probe
    probe_rows = int(len(probe_df)) if not probe_df.empty else 0
    probe_sample_match_ratio = 0.0
    probe_invocation_match_ratio = 0.0
    if not join_df.empty and "probe_sample_match" in join_df.columns:
        probe_sample_match_ratio = float(join_df["probe_sample_match"].mean())
    if not join_df.empty and "probe_invocation_match" in join_df.columns:
        probe_invocation_match_ratio = float(join_df["probe_invocation_match"].mean())

    return pd.DataFrame([
        {"metric": "trace_oracle_sample_events", "value": total_trace_samples,
         "note": "trace_oracle_sample 总行数（应 == 28）"},
        {"metric": "invocation_events", "value": invocation_events,
         "note": "实际函数调用事件数（应 == 28）"},
        {"metric": "duration_match_count", "value": duration_match_count,
         "note": "trace sample_duration 与 inv t_exec 一致的行数（应 == 28）"},
        {"metric": "duration_match_ratio", "value": round(duration_match_ratio, 4),
         "note": "duration_match 比例（应 == 1.0，证明 oracle 行为正确）"},
        {"metric": "cycles_used_fast", "value": cycles_used_fast,
         "note": "fast 函数 cursor 循环次数（应 == 2）"},
        {"metric": "last_sample_id_fast", "value": last_sample_id_fast,
         "note": "fast 函数最后一次取样的 sample_id（应 == 4，证明循环到第 4 个样本停止）"},
        {"metric": "fast_avg_duration_s", "value": round(fast_avg_duration, 4),
         "note": "fast 函数平均执行时间（应 ≈ 0.10s）"},
        {"metric": "slow_avg_duration_s", "value": round(slow_avg_duration, 4),
         "note": "slow 函数平均执行时间（应 ≈ 0.53s）"},
        {"metric": "invoke_dispatch_probe_events", "value": probe_rows,
         "note": "invoke_dispatch_probe 探针行数（应 == invocation_events）"},
        {"metric": "probe_sample_match_ratio", "value": round(probe_sample_match_ratio, 4),
         "note": "invoke_dispatch_probe 与 trace_oracle_sample 的样本匹配比例"},
        {"metric": "probe_invocation_match_ratio", "value": round(probe_invocation_match_ratio, 4),
         "note": "invoke_dispatch_probe 与 invocations 的时间/执行时长/节点匹配比例"},
    ])


def data_self_check(
    sample_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
    cycle_df: pd.DataFrame,
    input_summary_df: pd.DataFrame,
    probe_df: pd.DataFrame,
    paper_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    trace_oracle 样例的数据自洽检查（沿用 02/03/04/05/06 的 self_check 模式）。

    不变量：
    1. trace_oracle_sample 行数 == 28
    2. invocations 行数 == 28
    3. join 行数 == 28
    4. duration_match 全部 True
    5. cycles_used_fast == 2
    6. cycles_used_slow == 1
    7. last_sample_id_fast == 4
    8. fast invocations == 16
    9. slow invocations == 12
    10. probe×invocation 一致

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if sample_df.empty or inv_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    sample_count = int(len(sample_df))
    inv_count = int(len(inv_df))
    join_count = int(len(join_df))

    # duration_match
    if not join_df.empty and "duration_match" in join_df.columns:
        all_duration_match = bool(join_df["duration_match"].all())
    else:
        all_duration_match = False

    # cycles
    cycles_used_fast = 0
    cycles_used_slow = 0
    last_sample_id_fast = 0
    if not cycle_df.empty and "function_name" in cycle_df.columns:
        fast_row = cycle_df[cycle_df["function_name"].str.contains("fast", case=False)]
        slow_row = cycle_df[cycle_df["function_name"].str.contains("slow", case=False)]
        if not fast_row.empty:
            cycles_used_fast = int(fast_row["cycles_used"].iloc[0])
            last_sample_id_fast = int(fast_row["last_sample_id"].iloc[0])
        if not slow_row.empty:
            cycles_used_slow = int(slow_row["cycles_used"].iloc[0])

    # per-function invocations
    fast_inv_count = 0
    slow_inv_count = 0
    if not inv_df.empty and "function_name" in inv_df.columns:
        fast_rows = inv_df[inv_df["function_name"].str.contains("fast", case=False)]
        slow_rows = inv_df[inv_df["function_name"].str.contains("slow", case=False)]
        fast_inv_count = int(len(fast_rows))
        slow_inv_count = int(len(slow_rows))

    # probe
    probe_rows = int(len(probe_df)) if not probe_df.empty else 0
    probe_sample_all_match = False
    probe_invocation_all_match = False
    if not join_df.empty and {"probe_sample_match", "probe_invocation_match"}.issubset(join_df.columns):
        probe_sample_all_match = bool(join_df["probe_sample_match"].all())
        probe_invocation_all_match = bool(join_df["probe_invocation_match"].all())

    # paper self-consistent
    paper_match_count = -1
    paper_match_ratio = -1.0
    if not paper_df.empty:
        match_row = paper_df[paper_df["metric"] == "duration_match_count"]
        ratio_row = paper_df[paper_df["metric"] == "duration_match_ratio"]
        if not match_row.empty:
            paper_match_count = int(match_row["value"].iloc[0])
        if not ratio_row.empty:
            paper_match_ratio = float(ratio_row["value"].iloc[0])

    paper_consistent = (
        paper_match_count == sample_count
        and abs(paper_match_ratio - (sample_count / inv_count if inv_count > 0 else 0.0)) < 1e-3
    )

    checks = {
        "01_trace_oracle_sample_is_28": sample_count == 28,
        "02_invocations_is_28": inv_count == 28,
        "03_join_rows_is_28": join_count == 28,
        "04_all_duration_match_true": all_duration_match,
        "05_cycles_used_fast_is_2": cycles_used_fast == 2,
        "06_cycles_used_slow_is_1": cycles_used_slow == 1,
        "07_last_sample_id_fast_is_4": last_sample_id_fast == 4,
        "08_fast_invocations_is_16": fast_inv_count == 16,
        "09_slow_invocations_is_12": slow_inv_count == 12,
        "10_probe_sample_invocation_consistent": (
            bool(paper_consistent)
            and probe_rows == inv_count
            and probe_sample_all_match
            and probe_invocation_all_match
        ),
    }

    return checks


def export_outputs(sim, output_dir: Path, trace_path: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 9 个 faas-sim / oracle 内置 metric 的 CSV（含 invoke_dispatch_probe）
    - trace_input_summary.csv：trace CSV 自身摘要
    - trace_sample_summary.csv：实际取样摘要
    - trace_invoke_sample_join.csv：调用 × 取样关联（论文 demo 关键）
    - trace_cycle_summary.csv：trace 循环覆盖证据
    - trace_invocation_summary.csv：invocations.csv 按函数聚合
    - trace_oracle_paper_highlight.csv：论文 demo 关键摘要（9 条 metric/value）
    - trace_oracle_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    trace_oracle = TraceRuntimeOracle(trace_path)
    trace_input_summary_df = trace_oracle.summary_dataframe()
    trace_input_summary_path = output_dir / "trace_input_summary.csv"
    trace_input_summary_df.to_csv(trace_input_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_input_summary_path)

    trace_sample_summary_df = build_trace_sample_summary(dfs)
    trace_sample_summary_path = output_dir / "trace_sample_summary.csv"
    trace_sample_summary_df.to_csv(trace_sample_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_sample_summary_path)

    trace_join_df = build_trace_invoke_sample_join(dfs)
    trace_join_path = output_dir / "trace_invoke_sample_join.csv"
    trace_join_df.to_csv(trace_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_join_path)

    trace_cycle_df = build_trace_cycle_summary(dfs, trace_input_summary_df)
    trace_cycle_path = output_dir / "trace_cycle_summary.csv"
    trace_cycle_df.to_csv(trace_cycle_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_cycle_path)

    invocation_summary_df = build_invocation_summary(dfs)
    invocation_summary_path = output_dir / "trace_invocation_summary.csv"
    invocation_summary_df.to_csv(invocation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invocation_summary_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        sample_df=dfs.get("trace_oracle_sample", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=trace_join_df,
        cycle_df=trace_cycle_df,
        input_summary_df=trace_input_summary_df,
        probe_df=dfs.get("invoke_dispatch_probe", pd.DataFrame()),
    )
    paper_path = output_dir / "trace_oracle_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        sample_df=dfs.get("trace_oracle_sample", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=trace_join_df,
        cycle_df=trace_cycle_df,
        input_summary_df=trace_input_summary_df,
        probe_df=dfs.get("invoke_dispatch_probe", pd.DataFrame()),
        paper_df=paper_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "trace_oracle_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["trace_input_summary"] = trace_input_summary_df
    dfs["trace_sample_summary"] = trace_sample_summary_df
    dfs["trace_invoke_sample_join"] = trace_join_df
    dfs["trace_cycle_summary"] = trace_cycle_df
    dfs["trace_invocation_summary"] = invocation_summary_df
    dfs["trace_oracle_paper_highlight"] = paper_df
    dfs["trace_oracle_self_check"] = check_df

    return dfs
