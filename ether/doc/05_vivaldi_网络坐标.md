# 05 · vivaldi 网络坐标

> 本文档解析 `ether/vivaldi.py`(122 行),这是 ether 的"网络坐标"层 —— 用 Vivaldi 算法动态估算节点间 RTT,作为"拓扑模式"的轻量替代。
>
> **核心内容**:`VivaldiCoordinate` 类 + `execute(node, other, rtt)` 主函数

## 1. 文件概览

| 项 | 值 |
|---|---|
| 行数 | 122 |
| 导入 | `random`、`typing`、`numpy`、`ether.core.{Node, Coordinate}` |
| 类 | 1(`VivaldiCoordinate`) |
| 函数 | 2(`execute`、`_unit_vector_at`) |
| 角色 | **Layer 4** —— 网络坐标 RTT 估算(拓扑模式的轻量替代) |

## 2. 算法背景

Vivaldi 是一种**分布式网络坐标系统**(Dabek et al., SIGCOMM 2004),把每个节点映射到 N 维欧氏空间,用**位置向量 + 高度项**估算 RTT:

```
distance(node_a, node_b) = ||pos_a - pos_b|| + height_a + height_b
```

| 字段 | 含义 |
|---|---|
| `position` | N 维向量,描述"节点在网络空间中的位置" |
| `height` | 高度项,表示 RTT 中**无法被坐标解释的残差**(类似噪声下界) |
| `error` | 当前坐标的估计误差 |

### 参考实现

代码注释明确说明 `apply_force` 是从 **Hashicorp Serf 的 Go 实现**移植的:
> Implementation of the vivaldi algorithm [1] to calculate network coordinates.
> Parts of the implementation (especially apply_force) were ported from Hashicorp's Go implementation 'Serf' [2].

工业级算法,稳定性有保障。

## 3. 全局参数

```python
c_e = 0.9              # 误差更新权重(EMA 风格)
c_c = 0.25             # 力的强度
dimensions = 8         # 坐标维度
max_error = 1.5        # 误差上限
min_height = 10e-6     # 高度项下限
```

| 参数 | 值 | 含义 |
|---|---|---|
| `c_e` | 0.9 | 误差更新的权重(EMA 中"新样本"的占比) |
| `c_c` | 0.25 | 力的强度系数(每次更新移动多少) |
| `dimensions` | 8 | 坐标维度(N 维欧氏空间) |
| `max_error` | 1.5 | 误差上限,防止异常发散 |
| `min_height` | 10e-6 | 高度项下限,避免 0 高度导致距离为 0 |

## 4. `VivaldiCoordinate(Coordinate)` (31-93)

### 字段

```python
class VivaldiCoordinate(Coordinate):
    position: np.ndarray    # 8 维向量,默认全 0
    height: float           # 默认 min_height
    error: float            # 默认 max_error
    vivaldi_runs: int       # 累计 update 次数

    def __init__(self, position=None, height=None, error=None):
        self.position = position if position is not None else np.array([0.0] * dimensions)
        self.height = height if height is not None else min_height
        self.error = error or max_error
        self.vivaldi_runs = 0
```

### `apply_force(force, other)` (55-67) —— 弹簧式位置更新

```python
def apply_force(self, force: float, other: 'VivaldiCoordinate'):
    unit, norm = self._unit_vector_at(self.position, other.position)
    self.position += unit * force
    if norm > 0:
        self.height += (self.height + other.height) * force / norm
        self.height = max(self.height, 10e-3)
```

**逻辑**:

1. 算"指向 other 的单位向量" + 当前距离
2. 沿单位向量移动 `force` 距离
3. 调整 height 减小残差(更新后限制在 `10e-3` 以上)

### `distance_to(other)` (69-79) —— 估算节点间距离

```python
def distance_to(self, other):
    return np.linalg.norm(self.position - other.position) + self.height + other.height
```

**经典 Vivaldi 公式**:欧氏距离 + 双方高度项。

### `_unit_vector_at(v1, v2)` (81-93) —— 内部辅助

```python
@staticmethod
def _unit_vector_at(v1, v2):
    result = v1 - v2
    norm = np.linalg.norm(result)
    if result.any():
        return result/norm, norm
    else:
        # 两个坐标重合 → 返回随机方向
        result = [random.gauss(0, 1) for _ in result]
        norm = np.linalg.norm(result)
        return result/norm, 0.0
```

**特殊处理**:若两个坐标完全重合(零向量),返回**随机方向** —— 避免除以 0。

## 5. `execute(node, other, rtt)` (96-122) —— 一次 RTT 测量更新

```python
def execute(node: Node, other: Node, rtt: float):
    if not node.coordinate:
        node.coordinate = VivaldiCoordinate()
    if not other.coordinate:
        other.coordinate = VivaldiCoordinate()
    elif not isinstance(other.coordinate, VivaldiCoordinate):
        raise TypeError('Nodes have different Coordinate types')

    # 1. weight 平衡本地和远端误差
    weight = node.coordinate.error / (node.coordinate.error + other.coordinate.error)

    # 2. 旧估算距离
    old_distance = np.linalg.norm(node.coordinate.position - other.coordinate.position)
    old_distance += node.coordinate.height + other.coordinate.height

    # 3. 相对误差
    sample_error = np.abs(old_distance - rtt) / rtt

    # 4. EMA 更新误差
    node.coordinate.error = sample_error * c_e * weight + node.coordinate.error * (1 - c_e * weight)
    node.coordinate.error = min(node.coordinate.error, max_error)

    # 5. 弹簧式力
    delta = c_c * weight
    force = delta * (rtt - old_distance)
    node.coordinate.apply_force(force, other.coordinate)

    # 6. 累计次数
    node.coordinate.vivaldi_runs += 1
```

### 5 步核心逻辑

| 步骤 | 做什么 | 公式 |
|---|---|---|
| 1. **weight** | 平衡本地/远端误差 | `w = err_self / (err_self + err_other)` |
| 2. **old_distance** | 当前坐标估算的距离 | `‖pos_a - pos_b‖ + h_a + h_b` |
| 3. **sample_error** | 相对误差 | `\|old - rtt\| / rtt` |
| 4. **EMA 更新误差** | 平滑更新 | `err = sample * c_e * w + err * (1 - c_e * w)` |
| 5. **弹簧式力** | 调整 position | `force = c_c * w * (rtt - old_distance)` |

**两个非对称细节**:

- `weight`:自己的误差大 → 信任别人的少,自己调整多
- `force`:估算距离 < 实测 RTT → force 为正,position 朝外推

## 6. 关键设计要点

### 1) 分布式特性

每个节点只跟自己通信过的节点交换信息,**无中心协调**,符合边缘计算"分布式"特点。

### 2) EMA 误差更新

平滑收敛,不抖动。`c_e = 0.9` 表示"新样本占 90%,旧值占 10%"。

### 3) 高度项防退化

`height` 不能太低(限制在 `10e-3`),否则距离会退化为 0(欧氏距离可能很小,但实际 RTT 不可能为 0)。

### 4) 与 `topology.py` 配合

`Topology.latency(use_coordinates=True)` 直接调 `node.distance_to(other)`,走到 `VivaldiCoordinate.distance_to`:

```
node.distance_to(other)
  ↓
self.coordinate.distance_to(other.coordinate)  # core.py
  ↓
VivaldiCoordinate.distance_to(other)            # vivaldi.py
  ↓
np.linalg.norm(...) + self.height + other.height
```

## 7. 对论文的接口清单

| 论文实验要素 | `vivaldi.py` 提供的接口 | 关键位置 |
|---|---|---|
| 创建坐标 | `VivaldiCoordinate()` | 38-46 |
| 单次更新 | `execute(node, other, rtt)` | 96-122 |
| 估算距离 | `coord.distance_to(other)` | 69-79 |
| 轻量 RTT 查询 | `topology.latency(src, dst, use_coordinates=True)` | `topology.py` 75-89 |
| 位置调整 | `coord.apply_force(force, other)` | 55-67 |
| 节点装上 Vivaldi 坐标 | `node.coordinate = VivaldiCoordinate()` | 用户代码 |

### 典型用法

```python
from ether.core import Node
from ether.vivaldi import VivaldiCoordinate, execute
import random

# 1. 给节点装上 Vivaldi 坐标
node_a = Node('a')
node_b = Node('b')
node_a.coordinate = VivaldiCoordinate()
node_b.coordinate = VivaldiCoordinate()

# 2. 模拟 N 次 RTT 测量,更新坐标
for _ in range(100):
    true_rtt = 50.0  # 模拟测得的 RTT(ms)
    execute(node_a, node_b, rtt=true_rtt + random.gauss(0, 5))

# 3. 估算两个节点的距离
estimated_rtt = node_a.distance_to(node_b)
print(f'estimated: {estimated_rtt:.2f}ms, true: {true_rtt:.2f}ms')
```

### 对论文的用处

| 论文场景 | 价值 |
|---|---|
| **轻量级 RTT 估算** | 不用每次都跑 shortest_path,直接用坐标距离 O(d) |
| **冷启动时延建模** | 新加入节点到已有节点的预期 RTT,可用 Vivaldi 坐标估算作为初值 |
| **大规模仿真** | O(d) 距离计算 vs O(E) shortest_path |
| **分布式特性** | 符合边缘计算无中心协调 |
| **算法可证明** | Vivaldi 有收敛性证明,论文里可以引用 |
