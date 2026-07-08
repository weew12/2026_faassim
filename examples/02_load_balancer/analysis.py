"""
文件作用：负载均衡样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成负载均衡摘要，便于观察请求是否均匀分配到多个副本。

新增的关键导出：
- load_balancer_routing_sequence.csv：每次路由的 request_id -> replica_index
  序列，这是论文 demo 的关键图（"轮询路由的严格顺序"）。
- load_balancer_probe_invocation_join.csv：逐请求关联 route / probe / invocation，
  验证负载均衡选择的副本与实际执行记录一致。
- load_balancer_summary.csv：增强版，加 max/min/balance_std/balance_ratio 等
  均衡度指标。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "load_balancer",
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


def build_load_balancer_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成增强版负载均衡摘要。

    摘要字段（按论文 demo 关心维度排序）：
    - route_events / invocation_events
    - selected_replica_count / selected_node_count
    - max_routed_requests / min_routed_requests（每个 replica 的请求数）
    - balance_std（请求数标准差，越小越均衡）
    - balance_ratio（min/max，越接近 1 越均衡）
    - max_consecutive_same_replica（轮询中同一 replica 连续出现的最大次数，
      用于检查 LB 公平性，对严格轮询应该是 1）
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if lb_df.empty:
        return pd.DataFrame([{
            "route_events": 0,
            "invocation_events": len(invocations_df),
            "selected_replica_count": 0,
            "selected_node_count": 0,
            "max_routed_requests": 0,
            "min_routed_requests": 0,
            "balance_std": None,
            "balance_ratio": None,
            "max_consecutive_same_replica": None,
        }])

    selected_replica_count = lb_df["selected_replica_id"].nunique() if "selected_replica_id" in lb_df.columns else None
    selected_node_count = lb_df["selected_node"].nunique() if "selected_node" in lb_df.columns else None

    # 均衡度统计：先按 replica 分组求 count
    if "selected_replica_id" in lb_df.columns:
        per_replica = lb_df.groupby("selected_replica_id").size()
        max_routed = int(per_replica.max())
        min_routed = int(per_replica.min())
        balance_std = float(per_replica.std(ddof=0))  # 总体标准差
        balance_ratio = float(min_routed / max_routed) if max_routed > 0 else None
    else:
        max_routed = None
        min_routed = None
        balance_std = None
        balance_ratio = None

    # 同一 replica 连续出现的最大次数（对严格轮询应该是 1）
    max_consecutive = None
    if "request_id" in lb_df.columns and "selected_replica_id" in lb_df.columns:
        sorted_df = lb_df.sort_values("request_id")
        prev = None
        per_replica_consec = {}  # 每个 replica 的最大连续次数
        per_replica_cur = {}    # 当前连续计数（遇不同 replica 时必须重置为 1）
        for _, row in sorted_df.iterrows():
            rid = row["selected_replica_id"]
            if prev is not None and rid == prev:
                # 同一 replica 连续出现
                per_replica_cur[rid] = per_replica_cur.get(rid, 0) + 1
            else:
                # 不同 replica，重置为 1
                per_replica_cur[rid] = 1
            per_replica_consec[rid] = max(per_replica_consec.get(rid, 0), per_replica_cur[rid])
            prev = rid
        max_consecutive = max(per_replica_consec.values()) if per_replica_consec else None

    return pd.DataFrame([{
        "route_events": len(lb_df),
        "invocation_events": len(invocations_df),
        "selected_replica_count": selected_replica_count,
        "selected_node_count": selected_node_count,
        "max_routed_requests": max_routed,
        "min_routed_requests": min_routed,
        "balance_std": balance_std,
        "balance_ratio": balance_ratio,
        "max_consecutive_same_replica": max_consecutive,
    }])


def build_replica_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计请求在各副本之间的分布。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())

    if lb_df.empty or "selected_replica_id" not in lb_df.columns:
        return pd.DataFrame()

    group_columns = [
        col for col in [
            "function_name",
            "replica_index",
            "selected_node",
            "selected_image",
            "selected_replica_id",
            "policy",
        ]
        if col in lb_df.columns
    ]

    out = (
        lb_df
        .groupby(group_columns)
        .size()
        .reset_index(name="routed_requests")
    )
    if "replica_index" in out.columns:
        return out.sort_values("replica_index").reset_index(drop=True)
    return out.sort_values("routed_requests", ascending=False).reset_index(drop=True)


def build_routing_sequence(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成论文 demo 关键的"轮询路由序列"。

    返回 DataFrame 列：[request_id, replica_index, selected_replica_id, selected_node]
    按 request_id 升序排序。这是最直接的 "x=request_id, y=replica_index" 阶梯图数据。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())

    if lb_df.empty or "request_id" not in lb_df.columns:
        return pd.DataFrame()

    preferred = [
        "request_id",
        "simtime",
        "replica_index",
        "running_replicas",
        "selected_replica_id",
        "selected_node",
        "policy",
    ]
    existing = [c for c in preferred if c in lb_df.columns]

    if not existing:
        return pd.DataFrame()

    return (
        lb_df[existing]
        .sort_values("request_id")
        .reset_index(drop=True)
    )


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    逐请求关联 load_balancer、invoke_dispatch_probe 和 invocations。

    load_balancer.csv 带 request_id；invoke_dispatch_probe.csv 在 simulator.invoke
    入口记录 request_id、replica_id、simtime；invocations.csv 是 faas-sim 实际完成
    调用后记录的 t_start / t_exec。三者关联后可验证：
    - route 选择的 replica 与 probe 执行入口一致；
    - probe 入口的 simtime 与 invocations.t_start 一致；
    - simulator 预期执行时间与 invocations.t_exec 一致。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())
    probe_df = dfs.get("invoke_dispatch_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if lb_df.empty or probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    required_probe = {"function_name", "replica_id", "simtime", "request_id"}
    required_inv = {"function_name", "replica_id", "t_start", "t_exec"}
    required_lb = {"request_id", "selected_replica_id", "simtime"}
    if not required_probe.issubset(probe_df.columns):
        return pd.DataFrame()
    if not required_inv.issubset(inv_df.columns):
        return pd.DataFrame()
    if not required_lb.issubset(lb_df.columns):
        return pd.DataFrame()

    probe_df = probe_df.copy()
    probe_df["simtime"] = probe_df["simtime"].astype(float)
    probe_df["replica_id"] = probe_df["replica_id"].astype(str)
    probe_df["request_id"] = probe_df["request_id"].astype(int)
    probe_df["simtime_key"] = probe_df["simtime"].round(6)

    inv_df = inv_df.copy()
    inv_df["t_start"] = inv_df["t_start"].astype(float)
    inv_df["replica_id"] = inv_df["replica_id"].astype(str)
    inv_df["simtime_key"] = inv_df["t_start"].round(6)
    inv_df = inv_df.rename(columns={
        "t_start": "inv_t_start",
        "t_exec": "inv_t_exec",
        "node": "inv_node",
    })

    lb_df = lb_df.copy()
    lb_df["request_id"] = lb_df["request_id"].astype(int)
    lb_df["selected_replica_id"] = lb_df["selected_replica_id"].astype(str)
    lb_df = lb_df.rename(columns={
        "simtime": "route_simtime",
        "selected_node": "route_node",
    })

    route_cols = [
        c for c in [
            "request_id",
            "route_simtime",
            "replica_index",
            "running_replicas",
            "selected_replica_id",
            "route_node",
            "policy",
        ]
        if c in lb_df.columns
    ]
    joined = probe_df.merge(
        lb_df[route_cols],
        on="request_id",
        how="left",
        validate="one_to_one",
    )
    inv_cols = [
        c for c in [
            "function_name",
            "replica_id",
            "simtime_key",
            "inv_t_start",
            "inv_t_exec",
            "inv_node",
        ]
        if c in inv_df.columns
    ]
    joined = joined.merge(
        inv_df[inv_cols],
        on=["function_name", "replica_id", "simtime_key"],
        how="left",
        validate="one_to_one",
    )

    joined["route_probe_replica_match"] = (
        joined["selected_replica_id"].astype(str) == joined["replica_id"].astype(str)
    )
    joined["route_probe_simtime_match"] = (
        (joined["route_simtime"].astype(float) - joined["simtime"].astype(float)).abs() < 1e-6
    )
    joined["probe_invocation_simtime_match"] = (
        joined["inv_t_start"].notna()
        & ((joined["inv_t_start"].astype(float) - joined["simtime"].astype(float)).abs() < 1e-6)
    )
    if "expected_t_exec" in joined.columns:
        joined["probe_invocation_t_exec_match"] = (
            joined["inv_t_exec"].notna()
            & ((joined["inv_t_exec"].astype(float) - joined["expected_t_exec"].astype(float)).abs() < 1e-6)
        )
    else:
        joined["probe_invocation_t_exec_match"] = joined["inv_t_exec"].notna()
    joined["matched"] = (
        joined["route_probe_replica_match"]
        & joined["route_probe_simtime_match"]
        & joined["probe_invocation_simtime_match"]
        & joined["probe_invocation_t_exec_match"]
    )

    output_cols = [
        "request_id",
        "function_name",
        "replica_index",
        "running_replicas",
        "replica_id",
        "selected_replica_id",
        "route_node",
        "inv_node",
        "route_simtime",
        "simtime",
        "inv_t_start",
        "expected_t_exec",
        "inv_t_exec",
        "route_probe_replica_match",
        "route_probe_simtime_match",
        "probe_invocation_simtime_match",
        "probe_invocation_t_exec_match",
        "matched",
    ]
    output_cols = [c for c in output_cols if c in joined.columns]
    return joined[output_cols].sort_values("request_id").reset_index(drop=True)


def build_paper_highlight(
    lb_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    distribution_df: pd.DataFrame,
    routing_seq_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 14/16/17/19/20/22/23 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set
    dfs["load_balancer_routing_sequence"] 这种时序 bug。
    """
    route_events = len(lb_df)
    invocation_events = len(inv_df)
    selected_replica_count = int(lb_df["selected_replica_id"].nunique()) if "selected_replica_id" in lb_df.columns else 0
    selected_node_count = int(lb_df["selected_node"].nunique()) if "selected_node" in lb_df.columns else 0

    # 均衡度
    if "selected_replica_id" in lb_df.columns and len(lb_df) > 0:
        per_replica = lb_df.groupby("selected_replica_id").size()
        max_routed = int(per_replica.max())
        min_routed = int(per_replica.min())
        balance_std = float(per_replica.std(ddof=0))
        balance_ratio = float(min_routed / max_routed) if max_routed > 0 else 0.0
    else:
        max_routed = min_routed = 0
        balance_std = 0.0
        balance_ratio = 0.0

    # 严格轮询：相邻 replica 切换率
    switch_rate = None
    if len(routing_seq_df) >= 2 and "selected_replica_id" in routing_seq_df.columns:
        sorted_seq = routing_seq_df.sort_values("request_id") if "request_id" in routing_seq_df.columns else routing_seq_df
        rids = sorted_seq["selected_replica_id"].tolist()
        if len(rids) >= 2:
            switches = sum(1 for i in range(1, len(rids)) if rids[i] != rids[i - 1])
            switch_rate = float(switches / (len(rids) - 1))

    # route×probe×invocation join
    join_total_match = len(join_df) == route_events == invocation_events
    join_all_rows_match = bool(
        not join_df.empty
        and "matched" in join_df.columns
        and join_df["matched"].all()
    )
    t_exec_match_rate = (
        float(join_df["probe_invocation_t_exec_match"].mean())
        if not join_df.empty and "probe_invocation_t_exec_match" in join_df.columns
        else 0.0
    )

    return pd.DataFrame([
        {"metric": "route_events", "value": route_events,
         "note": "路由决策事件总数（每次 next_replica 调用）"},
        {"metric": "invocation_events", "value": invocation_events,
         "note": "实际函数调用事件总数（应 == route_events）"},
        {"metric": "selected_replica_count", "value": selected_replica_count,
         "note": "被路由到的不同 FunctionReplica 数量（应 == 3 个 RUNNING 副本）"},
        {"metric": "selected_node_count", "value": selected_node_count,
         "note": "被路由到的不同 node 数量（faas-sim 默认调度器行为诚实记录）"},
        {"metric": "max_routed_requests", "value": max_routed,
         "note": "单副本最大请求数（轮询应为 10）"},
        {"metric": "min_routed_requests", "value": min_routed,
         "note": "单副本最小请求数（轮询应为 10）"},
        {"metric": "balance_std", "value": round(balance_std, 4),
         "note": "副本请求数标准差，越小越均衡（轮询 = 0）"},
        {"metric": "balance_ratio_min_over_max", "value": round(balance_ratio, 4),
         "note": "min/max 比率，越接近 1 越均衡（轮询 = 1.0）"},
        {"metric": "adjacent_switch_rate", "value": (round(switch_rate, 4) if switch_rate is not None else None),
         "note": "相邻请求切换副本的比率（严格轮询 = 1.0）"},
        {"metric": "route_probe_invocation_total_match", "value": bool(join_total_match),
         "note": "route、probe、invocation 三张表的事件数是否一致"},
        {"metric": "route_probe_invocation_all_match", "value": bool(join_all_rows_match),
         "note": "逐请求 route×probe×invocation 关联是否全部一致"},
        {"metric": "probe_invocation_t_exec_match_rate", "value": round(t_exec_match_rate, 4),
         "note": "simulator 预期 t_exec 与 invocations.t_exec 的匹配率"},
    ])


def data_self_check(
    lb_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    routing_seq_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    负载均衡样例的数据自洽检查（沿用 14/16/17/19/20/22/23 的 self_check 模式）。

    不变量：
    1. route_events == invocation_events
    2. selected_replica_count == 3（部署 3 个副本）
    3. 30/3 = 10，每个 replica 应分到 10 个请求（balance_ratio == 1.0）
    4. max_routed_requests == 10 && min_routed_requests == 10
    5. balance_std == 0
    6. adjacent_switch_rate == 1.0（严格轮询：每个相邻请求必须切换副本）
    7. probe_total_match（probe 事件数 == invocation 事件数）
    8. probe_all_groups_match（按 replica 分组 simtime 集合相等）

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    route_events = len(lb_df)
    invocation_events = len(inv_df)
    replica_count = int(lb_df["selected_replica_id"].nunique()) if "selected_replica_id" in lb_df.columns else 0

    per_replica_count = None
    if "selected_replica_id" in lb_df.columns and len(lb_df) > 0:
        per_replica_count = lb_df.groupby("selected_replica_id").size()

    max_routed = int(per_replica_count.max()) if per_replica_count is not None else 0
    min_routed = int(per_replica_count.min()) if per_replica_count is not None else 0
    balance_std = float(per_replica_count.std(ddof=0)) if per_replica_count is not None and len(per_replica_count) > 0 else 0.0
    balance_ratio = float(min_routed / max_routed) if max_routed > 0 else 0.0

    switch_rate = None
    if len(routing_seq_df) >= 2 and "selected_replica_id" in routing_seq_df.columns:
        sorted_seq = routing_seq_df.sort_values("request_id") if "request_id" in routing_seq_df.columns else routing_seq_df
        rids = sorted_seq["selected_replica_id"].tolist()
        if len(rids) >= 2:
            switches = sum(1 for i in range(1, len(rids)) if rids[i] != rids[i - 1])
            switch_rate = float(switches / (len(rids) - 1))

    join_total_match = len(join_df) == route_events == invocation_events
    join_all_rows_match = bool(
        not join_df.empty
        and "matched" in join_df.columns
        and join_df["matched"].all()
    )

    checks = {
        "01_route_equals_invocation": route_events == invocation_events,
        "02_three_replicas_routed": replica_count == 3,
        "03_per_replica_get_10_requests": (per_replica_count is not None
                                            and (per_replica_count == 10).all()),
        "04_balance_ratio_is_one": abs(balance_ratio - 1.0) < 1e-9,
        "05_balance_std_is_zero": abs(balance_std) < 1e-9,
        "06_max_routed_equals_10": max_routed == 10,
        "07_min_routed_equals_10": min_routed == 10,
        "08_strict_round_robin_switch": (switch_rate is not None and abs(switch_rate - 1.0) < 1e-9),
        "09_route_probe_invocation_total_match": join_total_match,
        "10_route_probe_invocation_all_match": join_all_rows_match,
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 8 个 faas-sim 内置 metric 的 CSV
    - load_balancer_routing_sequence.csv：路由序列（论文 demo 关键）
    - load_balancer_summary.csv：增强版摘要
    - load_balancer_replica_distribution.csv：副本分布
    - load_balancer_probe_invocation_join.csv：probe×invocation 关联自洽检查
    - load_balancer_paper_highlight.csv：论文 demo 关键摘要
    - load_balancer_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # 新增：轮询路由序列（论文 demo 关键图）
    routing_seq_df = build_routing_sequence(dfs)
    routing_seq_path = output_dir / "load_balancer_routing_sequence.csv"
    routing_seq_df.to_csv(routing_seq_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", routing_seq_path)

    summary_df = build_load_balancer_summary(dfs)
    summary_path = output_dir / "load_balancer_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    distribution_df = build_replica_distribution(dfs)
    distribution_path = output_dir / "load_balancer_replica_distribution.csv"
    distribution_df.to_csv(distribution_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", distribution_path)

    # probe×invocation join
    join_df = build_probe_invocation_join(dfs)
    join_path = output_dir / "load_balancer_probe_invocation_join.csv"
    join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        lb_df=dfs.get("load_balancer", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        distribution_df=distribution_df,
        routing_seq_df=routing_seq_df,
        join_df=join_df,
    )
    paper_path = output_dir / "load_balancer_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        lb_df=dfs.get("load_balancer", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        routing_seq_df=routing_seq_df,
        join_df=join_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "load_balancer_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["load_balancer_routing_sequence"] = routing_seq_df
    dfs["load_balancer_summary"] = summary_df
    dfs["load_balancer_replica_distribution"] = distribution_df
    dfs["load_balancer_probe_invocation_join"] = join_df
    dfs["load_balancer_paper_highlight"] = paper_df
    dfs["load_balancer_self_check"] = check_df

    return dfs
