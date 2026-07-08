"""
文件作用：自动伸缩样例的 FaaS 系统工厂。

该文件集中封装系统创建逻辑，避免 main.py 中混入过多底层对象构造代码。
当前样例使用 faas-sim 原生 DefaultFaasSystem，并开启基于平均请求数的伸缩逻辑。
同时额外记录一份按仿真时间对齐的 autoscaling_scale_probe，便于论文图直接展示
"负载上升 -> 副本扩容" 的时间线。
"""

import logging

from sim.core import Environment
from sim.faas.system import DefaultFaasSystem

logger = logging.getLogger(__name__)


class AutoscalingFaasSystem(DefaultFaasSystem):
    """
    示例专用 FaaS system。

    DefaultFaasSystem 的 scale.csv 使用 RuntimeLogger 的 wall clock time，
    不适合直接和 invocations.t_start 做仿真时间对齐。这里保留原生伸缩逻辑，
    只在 scale_up / scale_down 入口额外记录 env.now 下的副本目标数。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._autoscaling_probe_replicas = {}

    def _current_probe_replicas(self, fn_name: str) -> int:
        return int(
            self._autoscaling_probe_replicas.get(
                fn_name,
                self.replica_count.get(fn_name, 0),
            )
        )

    def _log_scale_probe(self, fn_name: str, action: str, delta: int, requested_delta: int) -> None:
        before = self._current_probe_replicas(fn_name)
        after = max(before + int(delta), 0)
        self._autoscaling_probe_replicas[fn_name] = after

        self.env.metrics.log(
            "autoscaling_scale_probe",
            {
                "simtime": float(self.env.now),
                "delta": int(delta),
                "requested_delta": int(requested_delta),
                "replicas_before": int(before),
                "replicas": int(after),
            },
            function_name=fn_name,
            action=action,
        )

    def scale_up(self, fn_name: str, replicas: int):
        fd = self.functions_deployments[fn_name]
        config = fd.scaling_config
        before = self._current_probe_replicas(fn_name)
        scale = max(min(int(replicas), int(config.scale_max) - before), 0)

        if scale > 0:
            self._log_scale_probe(fn_name, "scale_up", scale, replicas)

        yield from super().scale_up(fn_name, replicas)

    def scale_down(self, fn_name: str, remove: int):
        if fn_name not in self.functions_deployments:
            yield from super().scale_down(fn_name, remove)
            return

        config = self.functions_deployments[fn_name].scaling_config
        before = self._current_probe_replicas(fn_name)
        scale = max(min(int(remove), before - int(config.scale_min)), 0)

        if scale > 0:
            self._log_scale_probe(fn_name, "scale_down", -scale, remove)

        yield from super().scale_down(fn_name, remove)


def create_autoscaling_faas_system(env: Environment) -> DefaultFaasSystem:
    """
    创建启用自动伸缩能力的 DefaultFaasSystem。

    参数：
    - env：faas-sim 运行时环境。

    返回：
    - DefaultFaasSystem：启用 scale_by_average_requests 的 FaaS 系统实例。

    说明：
    - scale_by_average_requests=True 表示系统会根据平均请求负载触发副本伸缩；
    - 具体伸缩边界和目标负载由 FunctionDeployment 中的 ScalingConfiguration 决定；
    - 该函数用于被 Simulation.create_faas_system 接口引用。
    """
    logger.info("creating autoscaling DefaultFaasSystem with simtime scale probe")
    return AutoscalingFaasSystem(env, scale_by_average_requests=True)
