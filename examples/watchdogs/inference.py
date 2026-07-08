"""
推理函数模拟器示例。

InferenceFunctionSim 继承 HTTPWatchdog，用固定数量的 HTTP worker 表示一个
函数副本内部的并发处理能力。请求进入副本后先等待 worker token，再声明执行期
资源、模拟推理耗时并释放资源。
"""

from sim import docker
from sim.core import Environment
from sim.faas import HTTPWatchdog, FunctionReplica, FunctionRequest, simulate_data_download


class InferenceFunctionSim(HTTPWatchdog):
    """
    ResNet 推理函数的 HTTP watchdog 实现。

    该类把推理函数拆成几个可观测阶段：
    - deploy：拉取函数镜像。
    - setup：初始化副本并登记常驻资源。
    - claim_resources / release_resources：登记单次请求的临时 CPU 占用。
    - execute：模拟一次推理请求的用户代码耗时。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        拉取推理镜像。

        ``docker.pull`` 会根据镜像大小和网络状态推进仿真时间，因此部署耗时会反映
        在后续副本可用时间上。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        初始化 HTTP worker 队列并登记副本常驻资源。

        ``super().setup`` 会创建 HTTPWatchdog 的 worker 队列；随后登记模型服务常驻
        CPU/内存占用，并模拟模型或输入数据下载。
        """
        super().setup(env, replica)
        env.resource_state.put_resource(replica, 'cpu', 0.08)
        env.resource_state.put_resource(replica, 'memory', 200)

        yield from simulate_data_download(env, replica)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        关闭推理副本并释放常驻资源。

        本示例不额外模拟关闭耗时，因此释放资源后用 ``timeout(0)`` 交还事件控制权。
        """
        env.resource_state.remove_resource(replica, 'cpu', 0.08)
        env.resource_state.remove_resource(replica, 'memory', 200)
        yield env.timeout(0)

    def claim_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        为单次推理请求登记临时 CPU 占用。

        HTTP worker token 已在 HTTPWatchdog.invoke 中获取；这里仅描述请求执行期间对
        节点资源的额外压力。
        """
        env.resource_state.put_resource(replica, 'cpu', 0.2)
        yield env.timeout(0)

    def release_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        释放单次推理请求的临时 CPU 占用。
        """
        env.resource_state.remove_resource(replica, 'cpu', 0.2)
        yield env.timeout(0)

    def execute(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次模型推理耗时。

        这里固定为 0.2 个仿真时间单位；如需更真实的模型，可按请求大小、硬件类型
        或 batch size 改成动态耗时。
        """
        yield env.timeout(0.2)
