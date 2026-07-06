# 12 · qos 链路时延分布

> 本文档解析 `ether/qos/` 子包(只有 1 个文件,11 行),提供 4 个链路时延的对数正态分布。
>
> **核心内容**:`latency.lan` / `latency.wlan` / `latency.business_isp` / `latency.mobile_isp`

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 2 | 包入口(空 docstring) |
| `latency.py` | 11 | 4 个链路时延的对数正态分布定义 |

**超小但极常用** —— 所有 Cell 在 materialize 时都会引用这里的分布。

## 2. `latency.py` 完整代码

```python
"""网络延迟分布文件,用参数化分布描述局域网、移动 ISP 和企业 ISP 等链路时延。"""

from srds import ParameterizedDistribution as PDist

# 局域网链路时延分布。
lan = PDist.lognorm((0.25, 0.35, 0.16))
wlan = PDist.lognorm((0.635, 1.18, 3.27))
# 企业 ISP 链路时延分布。
business_isp = PDist.lognorm((0.87, 5.95, 1.21))
# 移动运营商链路时延分布。
mobile_isp = PDist.lognorm((0.49, 16.2, 8.02))
```

## 3. 4 个分布详解

参数顺序是 srds 约定的 `PDist.lognorm(sigma, scale, loc)`,众数近似公式为 `exp(log(scale) - sigma²) + loc`。

| 名称 | 参数 (σ, scale, loc) | 众数 ≈ | 适用场景 |
|---|---|---|---|
| `lan` | (0.25, 0.35, 0.16) | **0.5ms** 左右 | 局域网(机房内部、有线) |
| `wlan` | (0.635, 1.18, 3.27) | ~3.5ms | 无线局域网(WiFi) |
| `business_isp` | (0.87, 5.95, 1.21) | ~3.4ms | 企业 ISP(对称较高带宽) |
| `mobile_isp` | (0.49, 16.2, 8.02) | ~21ms | 移动运营商(高延迟、抖动大) |

### 直方图式对比(中位数/典型值)

```
mobile_isp  ████████████████████████████  ~21ms
wlan        █████                        ~3.5ms
business_isp█████                        ~3.4ms
lan         █                            ~0.5ms
```

### σ 越大抖动越大

- `lan` σ=0.25 —— 抖动小(机房内稳定)
- `wlan` σ=0.635 —— 抖动中等(WiFi 受干扰)
- `business_isp` σ=0.87 —— 抖动大(运营商网络)
- `mobile_isp` σ=0.49 —— 中等(基站稳定但绝对值大)

## 4. 在 ether 中怎么用

### 默认值

`cell.py` 的 `Host.materialize` 默认用 `latency.lan`:

```python
def materialize(self, topology, parent=None, latency_dist=latency.lan):
    topology.add_connection(Connection(node, self.link, latency_dist=latency_dist))
```

`LANCell` 普通 backhaul 也用 `latency.lan`:

```python
topology.add_connection(Connection(self.switch, self.backhaul, latency_dist=latency.lan))
```

### 回传配置(blocks/cells.py)

```python
class MobileConnection(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(125, 25, backhaul, latency.mobile_isp)

class BusinessIsp(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(500, 50, backhaul, latency.business_isp)

class FiberToExchange(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(1000, 1000, backhaul, latency.lan)
```

### 自定义使用

```python
from ether.qos import latency
from ether.cell import Host
from ether.core import Node

# 自定义时延的 Host
my_host = Host(Node('special'))
my_host.materialize(t, latency_dist=latency.mobile_isp)   # 用移动 ISP 时延
```

## 5. 自定义分布

如果想做"自定义时延分布"实验(比如"5G 时延比 4G 低"),可以这样:

```python
from srds import ParameterizedDistribution

# 5G 时延(比 mobile_isp 低一个量级)
my_5g = ParameterizedDistribution.lognorm((0.3, 5.0, 1.0))   # 众数 ~4ms

# 在 Cell 里使用
LANCell([...], backhaul=UpDownLink(1000, 100, backhaul='internet', latency_dist=my_5g))
```

## 6. 对论文的用处

| 论文实验要素 | qos 提供的接口 |
|---|---|
| **不同网络条件对比** | 4 个不同分布代表 4 种典型网络 |
| **移动边缘场景** | `latency.mobile_isp` 模拟 4G/5G |
| **WiFi 场景** | `latency.wlan` |
| **企业内部网络** | `latency.business_isp` |
| **机房/有线** | `latency.lan` |
| **自定义分布** | 继承 `ParameterizedDistribution` 或直接用 `lognorm((σ, scale, loc))` |

### 论文实验建议

**"不同网络条件下的性能对比"**:

- 固定场景(同一个 IndustrialIoTScenario)
- 改 backhaul 分布:从 `lan` → `wlan` → `business_isp` → `mobile_isp`
- 观察性能(冷启动时间、命中率、网络成本)随网络条件的变化
- 这种实验能让论文结论更立体
