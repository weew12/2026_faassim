# faas-sim 内置 Ether / Skippy / SimPy 兼容性检查报告

## 1. 检查目标

本次检查面向当前项目中已经内置的三个原外部依赖子包：

- `ether/`：原 `edgerun-ether` 网络拓扑与流式网络仿真包；
- `skippy/`：原 `edgerun-skippy-core` 调度器核心包；
- `simpy/`：原 `simpy` 离散事件仿真核心包。

检查重点不是重新设计功能，而是确认三类问题：

1. faas-sim 当前源码中的导入路径是否能命中项目内置子包；
2. faas-sim 调用到的类、函数、字段和返回结构是否仍然存在；
3. 最新源码合入后是否出现明显接口变更、语义变更或打包遗漏。

## 2. 检查方法

本次执行了以下检查：

1. 静态扫描 `sim/`、`examples/`、`ext/`、`ether/`、`skippy/`、`simpy/` 中所有 Python 导入，确认 `ether`、`skippy`、`simpy` 的调用位置；
2. 对比用户上传的上游源码包与项目内置源码包，忽略中文注释和 docstring 后检查 AST 结构是否发生变化；
3. 执行 `python -m compileall -q .`，确认所有 Python 文件语法编译通过；
4. 通过临时测试依赖模拟 `srds`，执行核心模块导入检查；
5. 运行 `examples/basic`、`examples/custom_scheduler`、`examples/custom_function_sim`、`examples/request_gen`、`examples/watchdogs`、`examples/analysis`，确认示例层可走通；
6. 构建 wheel 包并检查 `ether/inet/graphs/*.graphml` 和 `simpy/py.typed` 是否进入构建产物；
7. 安装构建出的 wheel 到临时目录，确认 `import ether`、`import skippy`、`import simpy` 命中打包后的内置包。

## 3. 总体结论

当前内置方式整体可用，没有发现会阻断 faas-sim 基础仿真、调度、网络流模拟和示例运行的接口不兼容问题。

具体结论如下：

- `ether`：faas-sim 使用到的 `Node`、`Capacity`、`Connection`、`Route`、`Link`、`Flow`、`Topology`、`parse_size_string`、`UrbanSensingScenario` 等接口均存在，基础网络流模拟可运行；
- `skippy`：faas-sim 使用到的 `Scheduler`、`ClusterContext`、`Pod`、`PodSpec`、`Container`、`ResourceRequirements`、`ImageState`、`SchedulingResult`、`StorageIndex`、`DataItem` 等接口均存在，调度流程可运行；
- `simpy`：faas-sim 使用到的 `Environment`、`Store`、`Resource`、`Process`、`Timeout`、`Interrupt`、`env.process`、`env.timeout`、`env.run` 等接口均存在，基础事件流程可运行；
- 三个内置包都能够通过 `setuptools.find_packages()` 被项目发现并打包；
- 当前示例目录中的主要示例均已在临时依赖环境下跑通。

## 4. 逐项检查结果

### 4.1 Ether 检查结果

faas-sim 对 Ether 的核心依赖集中在以下方面：

- 拓扑节点：`ether.core.Node`、`ether.core.Capacity`；
- 拓扑连接：`ether.core.Connection`、`ether.core.Link`、`ether.topology.Topology`；
- 网络传输：`ether.core.Flow`，由 `sim/net.py` 中的 `SafeFlow` 包装；
- 场景生成：`ether.scenarios.urbansensing.UrbanSensingScenario` 等；
- 工具函数：`ether.util.parse_size_string`。

检查结论：这些接口在当前内置 Ether 中仍然存在。`Flow(env, size, route)` 的构造参数和 `start()` / `run()` 语义与 faas-sim 当前调用方式匹配。`Topology.route()`、`Topology.get_nodes()`、`Topology.add_connection()` 等接口也能被 `sim/topology.py` 正常继承和调用。

已确认的兼容性修复：

1. `ether/cell.py` 中原来的 `from collections import Iterable` 已改为 `from collections.abc import Iterable`，适配较新 Python；
2. `ether/export.py` 中原来的裸导入 `from topology import Topology`、`from core import Node` 已改为包内绝对导入，避免作为子包内置后导入失败。

注意事项：

- `ether` 仍依赖 `srds` 提供随机分布和采样器。当前项目仍把 `srds==0.1.0` 保留为外部依赖，这是正确的；如果希望完全离线运行，后续需要单独内置 `srds`；
- 构建 wheel 时，`ether/inet/graphs/*.graphml` 已被正确包含，互联网区域延迟图没有遗漏；
- 新版 setuptools 会提示 `ether.inet.graphs` 目录是数据目录但看起来像 namespace package，该提示不影响当前 wheel 中 graphml 文件被打包。

### 4.2 Skippy 检查结果

faas-sim 对 Skippy 的核心依赖集中在：

- 调度器：`skippy.core.scheduler.Scheduler`；
- 集群上下文：`skippy.core.clustercontext.ClusterContext`；
- 调度模型：`Pod`、`PodSpec`、`Container`、`ResourceRequirements`、`Node`、`Capacity`、`ImageState`、`SchedulingResult`；
- 存储索引：`StorageIndex`、`DataItem`；
- 调度优先级与谓词：`BalancedResourcePriority`、`LatencyAwareImageLocalityPriority`、`DataLocalityPriority`、`CapabilityPriority` 等。

检查结论：这些接口在当前内置 Skippy 中均存在。`Scheduler.schedule(pod)` 返回的 `SchedulingResult(suggested_host, feasible_nodes, needed_images)` 与 `sim/faas/system.py` 中的使用方式一致。

本次对比发现：忽略中文注释和 docstring 后，内置 Skippy 与用户上传的上游 Skippy 源码 AST 结构一致，没有发现因注释重构引入的业务逻辑差异。

注意事项：

- Skippy 调度器在 `schedule()` 中会立即调用 `cluster_context.place_pod_on_node()` 更新调度状态。因此 faas-sim 当前语义是“调度成功即扣减调度器视角资源”，随后才模拟镜像拉取、启动和 setup；这与原 faas-sim 设计保持一致；
- `ClusterContext.remove_pod_from_node()` 只释放 CPU / 内存，不删除镜像缓存。缩容后镜像仍留在节点本地，这对镜像本地性评分有影响，但属于 Skippy/原 faas-sim 的既有语义，不是本次内置造成的问题；
- `CapabilityPriority` 的实现使用节点标签集合来筛选能力标签，再与 Pod 标签比对。该逻辑来自上游源码，当前没有改动。若后续要做严格能力约束实验，建议单独复查该优先级函数是否符合实验语义。

### 4.3 SimPy 检查结果

faas-sim 对 SimPy 的使用方式主要是：

- `Environment()` 创建仿真环境；
- `env.process(generator)` 注册部署、调用、调度、监控等协程；
- `env.timeout(t)` 推进冷启动、执行、网络传输等仿真时间；
- `simpy.Store(env)` 实现调度队列和请求队列；
- `simpy.Resource(env, capacity=n)` 实现 watchdog / HTTP worker 并发限制；
- `simpy.Interrupt` 用于 Ether 流传输中的带宽重分配中断。

检查结论：当前内置 SimPy 中这些接口均存在，基础事件、队列、资源和中断流程可运行。`examples/watchdogs` 中的 `simpy.Resource` 并发 worker 语义也能跑通。

需要注意的语义边界：

- 原 faas-sim 依赖声明是 `simpy==3.0.11`，而当前内置的是用户上传的 SimPy 最新源码。当前 faas-sim 用到的是 SimPy 的稳定基础 API，因此基础运行兼容；
- 最新 SimPy 源码的项目声明中要求 Python `>=3.8`，而 faas-sim 当前 `setup.py` 仍写着 `python_requires='>=3.7'`。如果后续要正式分发这个内置版，建议把 faas-sim 的 Python 版本边界同步调整为 `>=3.8`；
- 当前代码没有直接访问 SimPy 内部事件队列、回调列表等私有字段，因此没有发现典型的 SimPy 3 到 SimPy 4 私有语义兼容问题。

## 5. 动态验证结果

在临时测试依赖环境中，以下模块导入通过：

- `ether.core`
- `ether.scenarios.urbansensing`
- `skippy.core.scheduler`
- `sim.core`
- `sim.faassim`
- `sim.faas.system`
- `sim.skippy`
- `examples.basic.main`
- `examples.custom_scheduler.main`
- `examples.custom_function_sim.main`
- `examples.request_gen.main`
- `examples.watchdogs.main`
- `examples.analysis.main`

以下示例运行通过：

- `python -m examples.basic.main`
- `python -m examples.custom_scheduler.main`
- `python -m examples.custom_function_sim.main`
- `python -m examples.request_gen.main`
- `python -m examples.watchdogs.main`
- `python -m examples.analysis.main`

说明：当前沙箱没有安装真实 `srds`，测试时使用临时 stub 仅用于验证内置依赖接口联通性。真实实验环境仍应按 `requirements.txt` 安装 `srds==0.1.0`。

## 6. 打包验证结果

执行 wheel 构建后确认：

- `ether`、`skippy`、`simpy` 均出现在 wheel 的 top-level 包中；
- `ether/inet/graphs/` 下 8 个 `.graphml` 文件均进入 wheel；
- `simpy/py.typed` 已进入 wheel；
- 通过 `pip install --no-deps --target ...` 安装 wheel 后，`import ether`、`import skippy`、`import simpy` 均命中打包后的内置包。

## 7. 建议处理项

当前没有必须立即修复的阻断性问题。建议后续按优先级处理以下事项：

1. 若准备长期使用当前内置 SimPy 最新源码，建议将 `setup.py` 中的 `python_requires` 从 `>=3.7` 调整为 `>=3.8`；
2. 若后续希望完全离线运行，应继续内置 `srds`，否则 `ether` 和 `sim/oracle` 仍需要外部安装 `srds==0.1.0`；
3. 若要将该项目发布为 wheel，建议进一步清理 `setup.py` 中旧式 `setup_requires`、`test_suite`、`tests_require`，这些不是当前运行错误，但新版 setuptools 会给出弃用警告；
4. 对论文实验而言，建议后续专门复查 Skippy 的 `CapabilityPriority`、镜像缓存保持语义、数据本地性带宽单位语义，确保其与论文实验设定完全一致。

## 8. 结论

本次检查表明，当前将 Ether、Skippy、SimPy 作为 faas-sim 项目内置独立子包的做法是可行的。faas-sim 基础仿真流程、默认调度流程、网络流传输流程、watchdog 示例和示例分析流程均能正常运行。当前需要重点关注的不是接口阻断，而是后续实验语义校准：尤其是缓存/镜像本地性、数据本地性、能力匹配和 Python 版本边界。
