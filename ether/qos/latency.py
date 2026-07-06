"""网络延迟分布文件，用参数化分布描述局域网、移动 ISP 和企业 ISP 等链路时延。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【QoS 层】—— 4 个链路时延的对数正态分布。

    lan          = lognorm((0.25, 0.35, 0.16))    # 局域网 (~0.5ms 众数)
    wlan         = lognorm((0.635, 1.18, 3.27))   # 无线局域网 (~3.5ms)
    business_isp = lognorm((0.87, 5.95, 1.21))    # 企业 ISP (~3.4ms)
    mobile_isp   = lognorm((0.49, 16.2, 8.02))    # 移动运营商 (~21ms)

    srds 约定: PDist.lognorm(sigma, scale, loc)
    众数公式:  exp(log(scale) - sigma^2) + loc

设计哲学:
    1. 对数正态: 真实网络时延呈长尾分布(偶发高延迟)
    2. 参数化分布: 每次采样一个值,模拟真实抖动
    3. 4 种典型场景: 覆盖 LAN/WiFi/企业/移动 4 种网络

对 CSAC 论文的接口:
    - 不同网络条件对比: 改用不同 latency 分布
    - 移动边缘场景: 用 mobile_isp
    - 自定义分布: ParameterizedDistribution.lognorm((σ, scale, loc))
================================================================================
"""

from srds import ParameterizedDistribution as PDist

# 局域网链路时延分布。
lan = PDist.lognorm((0.25, 0.35, 0.16))
wlan = PDist.lognorm((0.635, 1.18, 3.27))
# 企业 ISP 链路时延分布。
business_isp = PDist.lognorm((0.87, 5.95, 1.21))
# 移动运营商链路时延分布。
mobile_isp = PDist.lognorm((0.49, 16.2, 8.02))
