# `sim/faas` 包结构说明

FaaS 平台包：定义函数域模型、默认平台实现、函数生命周期、负载均衡、伸缩器和 watchdog 执行模式。

## 包内 Python 文件

- `__init__.py`：该文件参与本包对应的仿真支撑逻辑。
- `core.py`：FaaS 领域模型核心文件，定义函数、镜像、容器、副本、部署、请求/响应、资源配置、生命周期状态以及 FaaS 系统抽象接口。
- `scaling.py`：函数自动伸缩后台进程实现，包含 scale-to-zero idler、基于请求数的扩缩容、平均 RPS 扩缩容和队列长度扩缩容逻辑。
- `system.py`：默认 FaaS 平台实现文件，负责函数部署、副本创建、调度队列、调用转发、扩缩容、挂起与删除等完整业务流程。
- `watchdogs.py`：OpenFaaS watchdog 执行模型抽象，模拟 Fork 模式和 HTTP worker 队列模式下函数请求如何进入用户处理逻辑。
