"""
文件作用：协同仿真的外部控制循环。

ExternalController 周期性读取外部 trace 中的当前阶段，并把状态写入 CosimulationContext。
同时，它将每次状态交换记录为 cosim_exchange 指标，用于后续分析。
"""

import logging
from typing import Optional

from sim.core import Environment

from context import CosimulationContext, ExternalPhase
from external_model import ExternalEnvironmentTrace

logger = logging.getLogger(__name__)


class ExternalController:
    """
    外部控制器。

    当前实现是 trace-driven 控制器。
    它不直接修改 faas-sim 核心调度器，而是通过共享上下文影响函数执行时间。
    """

    def __init__(
        self,
        external_trace: ExternalEnvironmentTrace,
        context: CosimulationContext,
        control_interval: float = 0.5,
    ):
        """
        初始化控制器。
        """
        self.external_trace = external_trace
        self.context = context
        self.control_interval = control_interval
        self.last_phase_name: Optional[str] = None

    def run(self, env: Environment):
        """
        控制循环。

        每隔 control_interval：
        - 查询当前外部阶段；
        - 更新共享上下文；
        - 记录 cosim_exchange。
        """
        end_time = self.external_trace.total_duration() + 1.0

        while env.now <= end_time:
            phase = self.external_trace.phase_at(env.now)

            if phase is not None:
                self.context.update_from_phase(phase)
                self._log_phase_change(env, phase)

                env.metrics.log(
                    "cosim_exchange",
                    {
                        "runtime_factor": phase.runtime_factor,
                        "network_delay": phase.network_delay,
                        "rps": phase.rps,
                        "observed_active_requests": self._observe_active_requests(env),
                    },
                    phase_name=phase.phase_name,
                    controller_action=phase.controller_action,
                    description=phase.description,
                )
            else:
                env.metrics.log(
                    "cosim_exchange",
                    {
                        "runtime_factor": self.context.runtime_factor,
                        "network_delay": self.context.network_delay,
                        "rps": 0,
                        "observed_active_requests": self._observe_active_requests(env),
                    },
                    phase_name="idle",
                    controller_action="observe",
                    description="no active external phase",
                )

            yield env.timeout(self.control_interval)

    def _log_phase_change(self, env: Environment, phase: ExternalPhase):
        """
        记录外部阶段切换事件。
        """
        if self.last_phase_name == phase.phase_name:
            return

        self.last_phase_name = phase.phase_name

        logger.info(
            "[simtime=%.2f] external phase changed to %s action=%s runtime_factor=%.2f network_delay=%.2f",
            env.now,
            phase.phase_name,
            phase.controller_action,
            phase.runtime_factor,
            phase.network_delay,
        )

        env.metrics.log(
            "cosim_phase",
            {
                "start_time": phase.start_time,
                "duration": phase.duration,
                "rps": phase.rps,
                "runtime_factor": phase.runtime_factor,
                "network_delay": phase.network_delay,
            },
            phase_name=phase.phase_name,
            controller_action=phase.controller_action,
            description=phase.description,
        )

    @staticmethod
    def _observe_active_requests(env: Environment) -> int:
        """
        尝试统计当前拓扑节点上的活跃请求数。

        不同 faas-sim / Ether 版本中节点集合结构可能不同，因此采用兼容式读取。
        """
        total = 0

        topology_nodes = getattr(getattr(env, "topology", None), "nodes", [])

        try:
            iterator = list(topology_nodes)
        except Exception:
            iterator = []

        for node in iterator:
            current_requests = getattr(node, "current_requests", None)
            if current_requests is None:
                continue

            try:
                total += len(current_requests)
            except Exception:
                continue

        return total
