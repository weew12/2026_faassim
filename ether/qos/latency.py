"""网络延迟分布文件，用参数化分布描述局域网、移动 ISP 和企业 ISP 等链路时延。"""

from srds import ParameterizedDistribution as PDist

# 局域网链路时延分布。
lan = PDist.lognorm((0.25, 0.35, 0.16))
wlan = PDist.lognorm((0.635, 1.18, 3.27))
# 企业 ISP 链路时延分布。
business_isp = PDist.lognorm((0.87, 5.95, 1.21))
# 移动运营商链路时延分布。
mobile_isp = PDist.lognorm((0.49, 16.2, 8.02))
