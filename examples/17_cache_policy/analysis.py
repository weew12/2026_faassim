"""
文件作用：cache_policy 样例的结果导出与分析工具。

该文件负责导出请求结果、驱逐事件、缓存状态、策略对比摘要、eviction×state 关联验证、
论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据请求级结果生成策略摘要。
    """
    request_df = outputs.get("cache_request_result", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    return (
        request_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            max_latency=("latency", "max"),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_cache_used_after=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(
            miss_count=lambda df: df["request_count"] - df["hit_count"],
            hit_rate=lambda df: df["hit_count"] / df["request_count"],
            miss_rate=lambda df: 1.0 - df["hit_rate"],
        )
    )


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按策略和函数生成摘要。
    """
    request_df = outputs.get("cache_request_result", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    return (
        request_df
        .groupby(["policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
        .assign(
            miss_count=lambda df: df["request_count"] - df["hit_count"],
            hit_rate=lambda df: df["hit_count"] / df["request_count"],
        )
    )


def build_eviction_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成驱逐摘要。
    """
    eviction_df = outputs.get("cache_eviction", pd.DataFrame())

    if eviction_df.empty:
        return pd.DataFrame([{
            "policy_name": "none",
            "eviction_count": 0,
        }])

    return (
        eviction_df
        .groupby(["policy_name", "reason"])
        .agg(
            eviction_count=("evicted_function", "count"),
            avg_score=("score", "mean"),
            avg_evicted_memory_units=("evicted_memory_units", "mean"),
        )
        .reset_index()
    )


def build_eviction_state_join(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    eviction × cache_state 关联（论文 demo 关键证据）。

    每次 eviction 之后，runner 会 add 新 entry，所以 state cache_used 不一定
    = eviction 之后 used（还要 + new_entry_memory）。

    唯一可靠的不变量：**state cache_keys 不应包含刚被 evict 的函数**。
    按 (policy_name, time, function_name) 关联 cache_state，验证：
    - state.cache_keys 不含 evicted_function（至少非末位 evicted_function）
    """
    eviction_df = outputs.get("cache_eviction", pd.DataFrame())
    state_df = outputs.get("cache_state", pd.DataFrame())

    if eviction_df.empty or state_df.empty:
        return pd.DataFrame()

    state_join = state_df.rename(columns={
        "time": "state_time",
        "function_name": "state_function_name",
        "cache_used": "state_cache_used",
        "cache_keys": "state_cache_keys",
    })

    m = eviction_df.merge(
        state_join,
        left_on=["policy_name", "time", "function_name"],
        right_on=["policy_name", "state_time", "state_function_name"],
        how="left",
    )

    rows: List[Dict[str, Any]] = []
    for _, r in m.iterrows():
        state_keys = r.get("state_cache_keys")
        if pd.isna(state_keys):
            continue
        state_keys_set = set(str(state_keys).split(";")) if state_keys else set()
        evicted = str(r["evicted_function"])
        # 验证：刚被 evict 的函数不应出现在 state cache_keys 里
        not_in_keys = evicted not in state_keys_set
        rows.append({
            "policy_name": r["policy_name"],
            "time": r["time"],
            "function_name": r["function_name"],
            "evicted_function": evicted,
            "state_cache_used": int(r["state_cache_used"]) if pd.notna(r["state_cache_used"]) else None,
            "state_cache_keys": state_keys,
            "eviction_state_match": bool(not_in_keys),
        })
    return pd.DataFrame(rows)


def build_paper_highlight(
    policy_summary_df: pd.DataFrame,
    function_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要（沿用 02-16 的 metric/value/note 三列模式）。

    cache_policy 样例跟前 3 个不一样：它不跑 faas-sim Simulation，是 in-memory
    缓存算法实验。论文 demo 关注的是：
    1. 每个策略的命中率（hit_rate）
    2. 平均延迟（avg_latency）
    3. 总冷启动惩罚（total_cold_start_penalty）
    4. **策略对比**：以 fifo 为 baseline，其他策略的相对提升

    输出格式与 02-16 风格一致：metric / value / note 三列。
    """
    rows: List[Dict[str, Any]] = []

    if policy_summary_df.empty:
        return pd.DataFrame(rows)

    # 0. 跨策略聚合 metric
    rows.append({
        "metric": "total_policies",
        "value": int(policy_summary_df["policy_name"].nunique()),
        "note": "策略数（fifo / lru / utility_aware）",
    })
    if "request_count" in policy_summary_df.columns:
        rows.append({
            "metric": "total_requests_per_policy",
            "value": int(policy_summary_df["request_count"].iloc[0]) if len(policy_summary_df) > 0 else 0,
            "note": "每个 policy 的 request 数（应一致，因为 trace 共享）",
        })
    if not function_summary_df.empty and "function_name" in function_summary_df.columns:
        rows.append({
            "metric": "total_functions",
            "value": int(function_summary_df["function_name"].nunique()),
            "note": "函数规格数（5 个：img-resize / json-parse / fft / video-transcode / ml-infer）",
        })
        rows.append({
            "metric": "total_function_summary_rows",
            "value": int(len(function_summary_df)),
            "note": "function_summary 总行数（应 == policies × functions = 15）",
        })

    rows.append({
        "metric": "policy_summary_count",
        "value": int(len(policy_summary_df)),
        "note": "policy_summary 总行数（应 == policies 数）",
    })

    # 1. 每 policy 关键指标
    for _, srow in policy_summary_df.iterrows():
        policy = srow["policy_name"]
        rows.append({
            "metric": f"hit_rate__{policy}",
            "value": float(srow["hit_rate"]),
            "note": f"{policy} 策略命中率（应 == hit_count / request_count）",
        })
        rows.append({
            "metric": f"avg_latency__{policy}",
            "value": float(srow["avg_latency"]),
            "note": f"{policy} 策略平均延迟（含冷启动惩罚）",
        })
        rows.append({
            "metric": f"total_cold_start_penalty__{policy}",
            "value": float(srow["total_cold_start_penalty"]),
            "note": f"{policy} 策略累计冷启动惩罚（命中率越低，惩罚越大）",
        })
        rows.append({
            "metric": f"avg_cache_used_after__{policy}",
            "value": float(srow["avg_cache_used_after"]),
            "note": f"{policy} 策略平均缓存占用（应 <= capacity=4）",
        })
        rows.append({
            "metric": f"miss_count__{policy}",
            "value": int(srow["miss_count"]),
            "note": f"{policy} 策略 miss 次数（= request_count - hit_count）",
        })

    # 2. 策略相对提升（以 fifo 为 baseline）
    baseline = "fifo"
    base_row = policy_summary_df[policy_summary_df.policy_name == baseline]
    if not base_row.empty:
        base_row = base_row.iloc[0]
        base_hit_rate = float(base_row["hit_rate"])
        base_latency = float(base_row["avg_latency"])
        base_cold = float(base_row["total_cold_start_penalty"])

        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            if policy == baseline:
                continue
            hit_rate = float(srow["hit_rate"])
            latency = float(srow["avg_latency"])
            cold = float(srow["total_cold_start_penalty"])

            # 命中率绝对差
            rows.append({
                "metric": f"hit_rate_improvement__{policy}_over_{baseline}",
                "value": float(hit_rate - base_hit_rate),
                "note": f"{policy} vs {baseline} 命中率绝对差（论文 demo 关键数字）",
            })
            # 命中率倍数
            if base_hit_rate > 0:
                rows.append({
                    "metric": f"hit_rate_ratio__{policy}_over_{baseline}",
                    "value": float(hit_rate / base_hit_rate),
                    "note": f"{policy} vs {baseline} 命中率倍数（论文 demo 一句话核心：utility_aware=2.5x）",
                })
            # 平均延迟相对降低
            if base_latency > 0:
                rows.append({
                    "metric": f"latency_reduction__{policy}_over_{baseline}",
                    "value": float((base_latency - latency) / base_latency),
                    "note": f"{policy} vs {baseline} 平均延迟相对降低",
                })
            # 冷启动惩罚相对降低
            if base_cold > 0:
                rows.append({
                    "metric": f"cold_start_penalty_reduction__{policy}_over_{baseline}",
                    "value": float((base_cold - cold) / base_cold),
                    "note": f"{policy} vs {baseline} 冷启动惩罚相对降低",
                })

    # 3. per-function summary 的最高 hit_rate（哪条函数最能受益）
    if not function_summary_df.empty and "hit_rate" in function_summary_df.columns:
        for policy in function_summary_df["policy_name"].unique():
            sub = function_summary_df[function_summary_df.policy_name == policy]
            if sub.empty:
                continue
            best = sub.loc[sub["hit_rate"].idxmax()]
            rows.append({
                "metric": f"best_function_hit_rate__{policy}__{best['function_name']}",
                "value": float(best["hit_rate"]),
                "note": f"{policy} 策略下命中率最高的函数（img-resize 最频繁，最受益）",
            })

    return pd.DataFrame(rows)


def self_check(
    outputs: Dict[str, pd.DataFrame],
    policy_summary_df: pd.DataFrame,
    function_summary_df: pd.DataFrame,
    eviction_state_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    expected_request_count: int,
    n_policies: int,
) -> Dict[str, Any]:
    """
    数据自洽段（cache_policy 不变量）。
    """
    checks: List[Dict[str, str]] = []

    request_df = outputs.get("cache_request_result", pd.DataFrame())
    eviction_df = outputs.get("cache_eviction", pd.DataFrame())
    state_df = outputs.get("cache_state", pd.DataFrame())

    # 1. cache_request_result 行数 = n_policies × expected_request_count
    n_req = len(request_df)
    expected = n_policies * expected_request_count
    checks.append({
        "name": "cache_request_result_row_count",
        "status": "PASS" if n_req == expected else "FAIL",
        "detail": f"rows={n_req}, expected={expected} ({n_policies} policies × {expected_request_count} requests)",
    })

    # 2. cache_state 行数 == cache_request_result 行数
    n_state = len(state_df)
    checks.append({
        "name": "cache_state_row_count",
        "status": "PASS" if n_state == n_req else "FAIL",
        "detail": f"state rows={n_state}, request rows={n_req}",
    })

    # 3. policy_summary 行数 == n_policies
    n_summary = len(policy_summary_df)
    checks.append({
        "name": "cache_policy_summary_row_count",
        "status": "PASS" if n_summary == n_policies else "FAIL",
        "detail": f"summary rows={n_summary}, expected={n_policies}",
    })

    # 4. policy_summary per-policy request_count == expected_request_count
    if not policy_summary_df.empty and "request_count" in policy_summary_df.columns:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            rc = int(srow["request_count"])
            checks.append({
                "name": f"policy_request_count__{policy}",
                "status": "PASS" if rc == expected_request_count else "FAIL",
                "detail": f"request_count={rc}, expected={expected_request_count}",
            })

    # 5. function_summary per-function request_count 求和 == expected_request_count（每个 policy）
    if not function_summary_df.empty:
        for policy in function_summary_df["policy_name"].unique():
            sub = function_summary_df[function_summary_df.policy_name == policy]
            total = int(sub["request_count"].sum())
            checks.append({
                "name": f"function_summary_total_requests__{policy}",
                "status": "PASS" if total == expected_request_count else "FAIL",
                "detail": f"sum of function request_count={total}, expected={expected_request_count}",
            })

    # 6. eviction×state join 行数必须覆盖全部 eviction
    n_eviction = len(eviction_df)
    n_eviction_join = len(eviction_state_join_df)
    checks.append({
        "name": "eviction_state_join_row_count",
        "status": "PASS" if n_eviction_join == n_eviction else "FAIL",
        "detail": f"join rows={n_eviction_join}, eviction rows={n_eviction}",
    })

    # 7. eviction 跟 cache_state 一致（evicted_function 不应出现在驱逐后 state cache_keys 中）
    if not eviction_state_join_df.empty and "eviction_state_match" in eviction_state_join_df.columns:
        n = len(eviction_state_join_df)
        matched = int(eviction_state_join_df["eviction_state_match"].sum())
        checks.append({
            "name": "eviction_state_consistency",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 8. paper highlight 里 hit_rate__<policy> 跟 policy_summary 一致
    if not paper_highlight_df.empty and not policy_summary_df.empty:
        for _, srow in policy_summary_df.iterrows():
            policy = srow["policy_name"]
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"hit_rate__{policy}"
            ]
            if hl_rows.empty:
                continue
            hl_v = float(hl_rows["value"].iloc[0])
            summary_v = float(srow["hit_rate"])
            checks.append({
                "name": f"paper_highlight_hit_rate__{policy}",
                "status": "PASS" if abs(hl_v - summary_v) < 1e-6 else "FAIL",
                "detail": f"summary={summary_v:.6f}, highlight={hl_v:.6f}",
            })

    # 9. utility_aware 命中率应 >= fifo（论文核心结论）
    if not policy_summary_df.empty and "policy_name" in policy_summary_df.columns:
        u_row = policy_summary_df[policy_summary_df.policy_name == "utility_aware"]
        f_row = policy_summary_df[policy_summary_df.policy_name == "fifo"]
        if not u_row.empty and not f_row.empty:
            u_hit = float(u_row["hit_rate"].iloc[0])
            f_hit = float(f_row["hit_rate"].iloc[0])
            checks.append({
                "name": "utility_aware_beats_fifo",
                "status": "PASS" if u_hit >= f_hit else "FAIL",
                "detail": f"utility_aware={u_hit:.4f}, fifo={f_hit:.4f} (utility_aware 应 >= fifo)",
            })

    # 10. paper highlight 里 hit_rate_improvement__utility_aware_over_fifo 跟 summary 一致
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "hit_rate_improvement__utility_aware_over_fifo"
        ]
        if not hl_rows.empty and not policy_summary_df.empty:
            u_row = policy_summary_df[policy_summary_df.policy_name == "utility_aware"]
            f_row = policy_summary_df[policy_summary_df.policy_name == "fifo"]
            if not u_row.empty and not f_row.empty:
                hl_v = float(hl_rows["value"].iloc[0])
                expected_v = float(u_row["hit_rate"].iloc[0] - f_row["hit_rate"].iloc[0])
                checks.append({
                    "name": "paper_highlight_hit_rate_improvement",
                    "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                    "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
                })

    # 11. 导出的表结构不应包含 pandas 默认索引列
    frames_to_export = dict(outputs)
    frames_to_export.update({
        "cache_policy_summary": policy_summary_df,
        "cache_function_summary": function_summary_df,
        "cache_eviction_state_join": eviction_state_join_df,
        "cache_policy_paper_highlight": paper_highlight_df,
    })
    bad_columns = []
    for name, df in frames_to_export.items():
        if df is None or df.empty:
            continue
        unnamed = [col for col in df.columns if str(col).startswith("Unnamed")]
        if unnamed:
            bad_columns.append(f"{name}:{','.join(unnamed)}")
    checks.append({
        "name": "export_tables_have_no_index_column",
        "status": "PASS" if not bad_columns else "FAIL",
        "detail": "no pandas index columns" if not bad_columns else "; ".join(bad_columns),
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

    logger.info("=== cache_policy self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出缓存策略实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_summary_df = build_policy_summary(outputs)
    function_summary_df = build_function_summary(outputs)
    eviction_summary_df = build_eviction_summary(outputs)

    # eviction×state 关联
    eviction_state_join_df = build_eviction_state_join(outputs)

    # 论文 demo 关键摘要
    paper_highlight_df = build_paper_highlight(policy_summary_df, function_summary_df)

    # 数据自洽段
    request_df = outputs.get("cache_request_result", pd.DataFrame())
    if not request_df.empty and "policy_name" in request_df.columns:
        n_policies = int(request_df["policy_name"].nunique())
        n_requests = int(len(request_df) // n_policies) if n_policies else 0
    else:
        n_policies = 0
        n_requests = 0

    self_check_result = self_check(
        outputs, policy_summary_df, function_summary_df,
        eviction_state_join_df, paper_highlight_df, n_requests, n_policies,
    )
    log_self_check(self_check_result)

    outputs = dict(outputs)
    outputs["cache_policy_summary"] = policy_summary_df
    outputs["cache_function_summary"] = function_summary_df
    outputs["cache_eviction_summary"] = eviction_summary_df
    outputs["cache_eviction_state_join"] = eviction_state_join_df
    outputs["cache_policy_paper_highlight"] = paper_highlight_df

    # 写 self_check.csv（仿 02-16 模式）
    check_df = pd.DataFrame(self_check_result.get("checks") or [])
    if "status" in check_df.columns:
        check_df["passed"] = check_df["status"] == "PASS"
    outputs["cache_policy_self_check"] = check_df

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
