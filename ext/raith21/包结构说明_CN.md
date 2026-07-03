# `ext/raith21` 包结构说明

Raith21 实验扩展包：包含异构设备、函数画像、拓扑、调度谓词/优先级、Benchmark 和设备生成器。

## 包内 Python 文件

- `__init__.py`：该文件参与本包对应的仿真支撑逻辑。
- `calculations.py`：设备集合统计与异构度计算工具，用于衡量生成设备与需求向量之间的属性覆盖和差异。
- `characterization.py`：Raith21 函数画像装配入口，将执行时间 Oracle 和资源 Oracle 组合成 FunctionCharacterization。
- `deployments.py`：Raith21 函数部署定义文件，创建 ResNet、MobileNet、Speech、TensorFlow、Pi、Fio 等函数部署和镜像排序。
- `device.py`：Raith21 设备抽象文件，将随机生成或真实设备参数封装为 Device/GpuDevice，并转换为调度标签。
- `etherdevices.py`：Raith21 设备到 Ether 节点的转换文件，定义 Raspberry Pi、Jetson、Xeon、Coral 等典型边缘/云节点的资源参数。
- `fet.py`：Raith21 函数执行时间画像数据，保存不同函数在不同设备上的平均或分布式 FET 估计。
- `functionsim.py`：Raith21 函数执行模拟器，基于函数画像和资源 Oracle 模拟 HTTP 函数队列、AI 推理 setup、资源占用和干扰退化。
- `generator.py`：异构设备生成器，按架构和属性概率生成设备集合，用于资源规划和大规模仿真实验。
- `images.py`：该文件参与本包对应的仿真支撑逻辑。
- `loader.py`：模型文件下载与加载辅助逻辑，处理性能退化模型等外部文件的获取和反序列化。
- `main.py`：Raith21 扩展实验入口，装配拓扑、Benchmark、调度策略和模拟器工厂后启动实验。
- `model.py`：Raith21 扩展实验的设备属性与需求模型，定义架构、位置、磁盘、加速器、连接方式、GPU/CPU 型号和资源需求枚举。
- `oracles.py`：Raith21 专用 Oracle，读取论文实验中的函数执行时间和资源画像，在给定节点上采样执行时延与资源向量。
- `predicates.py`：Skippy 调度谓词扩展，判断节点是否满足内存、架构、加速器、TPU/GPU 独占等硬约束。
- `priorities.py`：Skippy 调度优先级扩展，根据能力匹配、预计执行时间和资源竞争情况为候选节点打分。
- `resourcemonitor.py`：Raith21 专用资源监控进程，周期读取资源状态并写入资源窗口指标。
- `resources.py`：Raith21 资源画像数据，保存不同函数在不同设备上的 CPU、内存、GPU、网络、块 I/O 使用量。
- `storage.py`：Raith21 存储抽象，定义实验中对象存储或数据源在拓扑中的标识。
- `topology.py`：Raith21 拓扑构造文件，生成云、城市感知、异构边缘集群等实验拓扑，并组合 Ether 节点、链路和网络单元。
- `utils.py`：Raith21 Benchmark 辅助函数，按实验 profile 快速创建 AI、混合、服务型函数部署集合。

## 子目录

- `benchmark/`：Raith21 Benchmark 包：封装具体实验场景。
- `generators/`：设备生成配置包：按不同场景保存架构和设备属性概率分布。
- `util/`：调度策略工具包：按 vanilla/skippy/ga 等策略组合调度谓词与优先级。
