"""Vivaldi 坐标算法实现文件，用虚拟坐标近似节点间网络距离，可用于基于延迟的节点位置估计和拓扑分析。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 仿真引擎的【Layer 4】—— Vivaldi 网络坐标。

在 core.py (Node/Coordinate 抽象) + topology.py (latency 模式) 之上,
提供"轻量 RTT 估算"的实现:
    - 把节点映射到 N 维欧氏空间 (N=8)
    - position (8 维向量) + height (残差项) 估算距离
    - 实测 RTT 后用弹簧式力调整坐标 (EMA 风格误差更新)
    - 估算距离 = ||pos_a - pos_b|| + height_a + height_b

设计哲学:
    1. 分布式: 每个节点只跟自己通信过的节点交换信息,无中心协调
    2. 收敛性: 算法有论文证明 (Dabek et al., SIGCOMM 2004)
    3. 工业级: apply_force 移植自 Hashicorp Serf 的 Go 实现
    4. 轻量: O(d) 距离计算 (d=8),适合大规模仿真

对 CSAC 论文的接口:
    - VivaldiCoordinate: 节点坐标
    - vivaldi.execute(node, other, rtt): 用一次 RTT 测量更新坐标
    - topology.latency(src, dst, use_coordinates=True): 通过 Vivaldi 估算
    - 适用: 冷启动时延建模 / 大规模节点间通信成本估算
================================================================================
"""

import random
from typing import Tuple

import numpy as np

from ether.core import Node, Coordinate

"""
Implementation of the vivaldi algorithm [1] to calculate network coordinates. Parts of the implementation (especially
apply_force) were ported from Hashicorp's Go implementation 'Serf' [2].

[1] F. Dabek, R. Cox, F. Kaashoek, and R. Morris, ‘Vivaldi: A Decentralized Network Coordinate System’,
    in Proceedings of the 2004 Conference on Applications, Technologies, Architectures, and Protocols for
    Computer Communications, New York, NY, USA, 2004, pp. 15–26, doi: 10.1145/1015467.1015471.
[2] https://github.com/hashicorp/serf/blob/master/coordinate/coordinate.go
"""

c_e = 0.9
"a tuning parameter that influences the weight of the current error in each cycle"
c_c = 0.25
"tuning parameter that modulates the force"
dimensions = 8
"dimensionality of the vector space"

max_error = 1.5
min_height = 10e-6


class VivaldiCoordinate(Coordinate):
    """Vivaldi 虚拟坐标，保存二维位置和高度项，用于估计节点间网络距离。"""
    position: np.ndarray
    height: float
    error: float
    vivaldi_runs: int

    def __init__(self, position: np.ndarray = None, height: float = None, error: float = None):
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。
        """
        super().__init__()
        self.position = position if position is not None else np.array([0.0] * dimensions)
        self.height = height if height is not None else min_height
        self.error = error or max_error
        self.vivaldi_runs = 0

    def __repr__(self) -> str:
        """
        返回对象的调试字符串表示。

        """
        return f'Coordinate({self.position}, height={self.height}, error={self.error})'

    def apply_force(self, force: float, other: 'VivaldiCoordinate'):
        """
        沿"指向 other 的单位向量"移动 position，同时按 force/norm 调整 height 残差项。

        参数：
        - other：另一个坐标或节点，用于计算距离。

        ─────────────────────────────────────────────────────────────
        【设计意图】弹簧式位置调整 + 残差项更新
        ─────────────────────────────────────────────────────────────
        Vivaldi 借鉴物理弹簧模型:
          - force: 弹簧的"力", 来自 execute() 算的 c_c * weight * (rtt - old_distance)
          - 单位向量: 从 self 指向 other 的方向
          - norm: 当前欧氏距离, 用于反比调整 height

        移动公式:  self.position += unit * force
          force > 0 (实际 RTT > 估算): 朝外推 (拉远)
          force < 0 (实际 RTT < 估算): 朝内拉 (拉近)

        height 更新:  self.height += (self.height + other.height) * force / norm
          - 残差项 (height) 也会被 force 影响
          - norm > 0 才更新 (避免除零)
          - 更新后限制在 10e-3 以上,防止 height 退化为 0

        移植来源: Hashicorp Serf (Go 实现) 的同名函数。
        ─────────────────────────────────────────────────────────────
        """
        unit, norm = self._unit_vector_at(self.position, other.position)
        self.position += unit * force
        if norm > 0:
            self.height += (self.height + other.height) * force / norm
            self.height = max(self.height, 10e-3)

    def distance_to(self, other: 'VivaldiCoordinate'):
        """
        计算当前坐标或节点到另一个坐标/节点的距离。

        参数：
        - other：另一个坐标或节点，用于计算距离。

        返回：两个坐标或节点之间的距离估计。

        """
        return np.linalg.norm(self.position - other.position) + self.height + other.height

    @staticmethod
    def _unit_vector_at(v1: np.ndarray, v2: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        内部辅助方法，服务于当前模块的主要业务流程。
        """
        result = v1 - v2
        norm = np.linalg.norm(result)
        if result.any():
            return result/norm, norm
        else:
            result = [random.gauss(0, 1) for _ in result]
            norm = np.linalg.norm(result)
            return result/norm, 0.0


def execute(node: Node, other: Node, rtt: float):
    """
    用一次实测 RTT 调整 Vivaldi 坐标,实现分布式、自适应的网络距离估算。

    参数：
    - other：另一个坐标或节点，用于计算距离。
    - rtt：路径往返时延，单位为毫秒。

    ─────────────────────────────────────────────────────────────
    【设计意图】5 步核心逻辑: weight → old_distance → error → force → apply
    ─────────────────────────────────────────────────────────────
    1) weight: 平衡本地/远端误差
         w = err_self / (err_self + err_other)
       自己误差大 → 信任别人的少, 自己调整多

    2) old_distance: 当前坐标估算的距离
         ||pos_a - pos_b|| + height_a + height_b

    3) sample_error: 相对误差
         |old - rtt| / rtt

    4) EMA 更新误差 (c_e = 0.9):
         err = sample * c_e * w + err * (1 - c_e * w)
       平滑收敛, 防止抖动; 上限 max_error = 1.5 防止发散

    5) 弹簧式力:
         force = c_c * w * (rtt - old_distance)
       rtt > old → force > 0 → 朝外推 (距离被低估, 拉远)
       rtt < old → force < 0 → 朝内拉 (距离被高估, 拉近)

    论文支撑: F. Dabek et al., SIGCOMM 2004 (Vivaldi)
    ─────────────────────────────────────────────────────────────
    """
    if not node.coordinate:
        node.coordinate = VivaldiCoordinate()
    if not other.coordinate:
        other.coordinate = VivaldiCoordinate()
    elif not isinstance(other.coordinate, VivaldiCoordinate):
        raise TypeError('Nodes have different Coordinate types')

    # sample weight balances local and remote error
    weight = node.coordinate.error / (node.coordinate.error + other.coordinate.error)
    old_distance = np.linalg.norm(node.coordinate.position - other.coordinate.position)
    old_distance += node.coordinate.height + other.coordinate.height
    sample_error = np.abs(old_distance - rtt) / rtt
    node.coordinate.error = sample_error * c_e * weight + node.coordinate.error * (1 - c_e * weight)
    node.coordinate.error = min(node.coordinate.error, max_error)
    delta = c_c * weight
    force = delta * (rtt - old_distance)
    node.coordinate.apply_force(force, other.coordinate)
    node.coordinate.vivaldi_runs += 1
