"""
文件作用：故障模型定义与判定逻辑。

本文件提供一个确定性故障模型，用于演示三类常见故障：
1. node_outage：节点不可用窗口，请求快速失败；
2. replica_error：函数副本瞬时错误，请求快速失败；
3. network_degradation：网络退化，请求仍成功，但执行时间被放大。

说明：
faas-sim 当前没有统一的故障模型接口。本样例通过独立 FaultModel 在模拟器中判断故障，
并把故障判定结果写入自定义指标，不修改 faas-sim 核心代码。
"""

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class FaultEvent:
    """
    故障事件描述。

    字段：
    - name：事件名称；
    - fault_type：故障类型；
    - start_time：故障开始时间；
    - end_time：故障结束时间；
    - target_node：目标节点；
    - severity：故障严重程度；
    - extra_delay：网络退化等软故障引入的额外延迟；
    - description：事件说明。
    """

    name: str
    fault_type: str
    start_time: float
    end_time: float
    target_node: Optional[str]
    severity: str
    extra_delay: float
    description: str


@dataclass
class FaultDecision:
    """
    单次请求的故障判定结果。
    """

    success: bool
    reason: str
    active_fault: str
    base_duration: float
    extra_delay: float
    final_duration: float
    failure_latency: float


class DeterministicFaultModel:
    """
    确定性故障模型。

    该模型设计成确定性规则，便于样例复现和结果解释：
    - 在 node_outage 时间窗口内，请求失败；
    - 每隔若干个请求触发一次 replica_error；
    - 在 network_degradation 时间窗口内，请求成功但执行时间增加。
    """

    def __init__(self):
        """
        初始化故障事件。
        """
        self.base_duration = 0.25
        self.failure_latency = 0.03
        self.replica_error_mod = 7

        self.events: List[FaultEvent] = [
            FaultEvent(
                name="node_outage_server_0",
                fault_type="node_outage",
                start_time=1.00,
                end_time=1.80,
                target_node="server_0",
                severity="hard",
                extra_delay=0.0,
                description="server_0 在该窗口内不可用，请求快速失败。",
            ),
            FaultEvent(
                name="network_degradation_server_0",
                fault_type="network_degradation",
                start_time=2.20,
                end_time=3.60,
                target_node="server_0",
                severity="soft",
                extra_delay=0.45,
                description="server_0 网络路径退化，请求仍成功但执行时间增加。",
            ),
        ]

    def active_events(self, now: float, node_name: str) -> List[FaultEvent]:
        """
        返回当前时刻作用于指定节点的故障事件。
        """
        result = []

        for event in self.events:
            if event.target_node is not None and event.target_node != node_name:
                continue

            if event.start_time <= now <= event.end_time:
                result.append(event)

        return result

    def decide(self, now: float, request_id, node_name: str) -> FaultDecision:
        """
        对一次请求进行故障判定。

        优先级：
        1. 节点不可用属于硬故障，优先返回失败；
        2. replica_error 用请求编号周期性触发；
        3. 网络退化属于软故障，只增加执行时间；
        4. 没有故障时正常执行。
        """
        active = self.active_events(now, node_name)

        for event in active:
            if event.fault_type == "node_outage":
                return FaultDecision(
                    success=False,
                    reason="node_outage",
                    active_fault=event.name,
                    base_duration=self.base_duration,
                    extra_delay=0.0,
                    final_duration=self.failure_latency,
                    failure_latency=self.failure_latency,
                )

        numeric_request_id = self._safe_request_id(request_id)
        if numeric_request_id > 0 and numeric_request_id % self.replica_error_mod == 0:
            return FaultDecision(
                success=False,
                reason="replica_error",
                active_fault="periodic_replica_error",
                base_duration=self.base_duration,
                extra_delay=0.0,
                final_duration=self.failure_latency,
                failure_latency=self.failure_latency,
            )

        extra_delay = 0.0
        active_fault = "none"
        reason = "normal"

        for event in active:
            if event.fault_type == "network_degradation":
                extra_delay += event.extra_delay
                active_fault = event.name
                reason = "network_degradation"

        return FaultDecision(
            success=True,
            reason=reason,
            active_fault=active_fault,
            base_duration=self.base_duration,
            extra_delay=extra_delay,
            final_duration=self.base_duration + extra_delay,
            failure_latency=0.0,
        )

    def emit_timeline(self, env):
        """
        将故障时间线写入指标。

        该协程只负责记录故障开始和结束事件，便于输出 fault_timeline.csv。
        """
        for event in sorted(self.events, key=lambda item: item.start_time):
            yield env.timeout(max(event.start_time - env.now, 0))
            env.metrics.log(
                "fault_timeline",
                {
                    "event_type": "start",
                    "fault_type": event.fault_type,
                    "severity": event.severity,
                    "extra_delay": event.extra_delay,
                },
                fault_name=event.name,
                target_node=event.target_node,
                description=event.description,
            )

            yield env.timeout(max(event.end_time - env.now, 0))
            env.metrics.log(
                "fault_timeline",
                {
                    "event_type": "end",
                    "fault_type": event.fault_type,
                    "severity": event.severity,
                    "extra_delay": event.extra_delay,
                },
                fault_name=event.name,
                target_node=event.target_node,
                description=event.description,
            )

    def events_dataframe(self) -> pd.DataFrame:
        """
        将故障事件表转换为 DataFrame。
        """
        return pd.DataFrame([event.__dict__ for event in self.events])

    @staticmethod
    def _safe_request_id(request_id) -> int:
        """
        尝试把 request_id 转成整数。
        """
        try:
            return int(request_id)
        except Exception:
            return -1
