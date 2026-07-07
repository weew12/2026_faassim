# 论文说明

**Serverless edge computing 很难评测，因为它同时涉及函数调度、弹性伸缩、请求路由、异构边缘设备、网络传输和真实工作负载性能退化；作者提出 `faas-sim`，用真实 profiling trace 驱动离散事件仿真，帮助研究者在边缘-云连续体上设计、验证和优化 serverless edge 平台。**

论文信息：

- 标题：`faas-sim: A trace-driven simulation framework for serverless edge computing platforms`
- 作者：Philipp Raith, Thomas Rausch, Alireza Furutanpey, Schahram Dustdar
- 发表：Software: Practice and Experience, 2023
- DOI：`10.1002/spe.3277`
- 关键词：co-simulation, edge-cloud continuum, serverless edge computing, simulation

**1. 这篇论文要解决什么问题**

Serverless computing 在云数据中心里已经比较成熟。开发者只需要写函数，平台负责部署、调度、扩缩容、请求转发和资源管理。

但当 serverless 被放到 edge-cloud continuum 里，问题会复杂很多：

- 计算资源不再是统一的数据中心服务器，而是从 Raspberry Pi、Jetson、Intel NUC 到云服务器的混合资源。
- 网络不再是数据中心内部高速网络，而是 WiFi、移动网络、城市边缘链路、跨区域云链路混在一起。
- 函数请求具有明显的空间和时间特征，比如不同城市、不同区域、不同用户移动轨迹会导致请求位置和速率变化。
- 函数可能依赖数据位置，比如 AI 模型、视频帧、传感器数据、对象存储数据不一定在执行节点附近。
- 平台需要同时处理调度 placement、伸缩 scaling、请求路由 routing，这几个机制之间会互相影响。

传统云计算研究里有成熟 benchmark、testbed、trace 数据，比如 Google Borg 这类大规模集群 trace。但 serverless edge computing 缺少这类标准环境。

所以现在很多研究要么：

- 自己搭一个很小的 testbed，真实但规模有限；
- 用 emulation，较真实但成本较高；
- 用简单 simulator，规模可以大但模型太粗；
- 直接假设函数执行时间、网络延迟、节点性能，结果很难泛化。

作者想解决的是：

**能不能做一个专门面向 serverless edge computing 的仿真框架，让研究者既能模拟函数生命周期和平台自适应策略，又能利用真实 profiling trace 保持结果可信？**

这里的核心不是“再做一个通用边缘模拟器”，而是：

**把 serverless 平台里最关键的函数抽象、调度、伸缩、路由、函数执行时间、资源占用、网络传输都放进同一个可扩展仿真框架里。**

**2. 作者的核心思路**

作者提出的工具叫 `faas-sim`。

它的定位是：

**一个 trace-driven stochastic discrete-event simulation framework，也就是由真实实验 trace 驱动的随机离散事件仿真框架。**

这句话可以拆开理解：

- **trace-driven**：不只靠理论公式估算函数性能，而是先在真实设备上跑函数，采集执行时间、CPU、内存、I/O、GPU 等数据，再把这些数据用于仿真。
- **stochastic**：函数执行时间不是固定常数，而是从分布中采样，因为真实系统里同一个函数每次运行时间也会波动。
- **discrete-event simulation**：基于 SimPy，用事件推进仿真时间，比如函数部署、镜像下载、启动、请求到达、函数执行、网络传输、扩缩容等。
- **serverless edge computing**：仿真对象不是普通任务，而是 FaaS 平台里的函数、函数镜像、函数副本、调度器、负载均衡器、自动伸缩器等。

它大致做了三件事：

1. **建立 serverless 系统模型**  
   把 Function、FunctionImage、FunctionDeployment、FunctionContainer、FunctionReplica、FunctionNode 等概念抽象出来。

2. **用真实 trace 建模函数执行和资源消耗**  
   通过真实设备 profiling 得到不同函数在不同设备上的执行时间和资源占用，再用随机模型或 ML 模型估计仿真中的 FET（Function Execution Time）。

3. **集成 Ether 做网络和拓扑仿真**  
   `faas-sim` 不自己重新发明拓扑生成器，而是使用 `ether` 提供的边缘网络拓扑和 flow-based network simulation，用来模拟镜像下载、函数间数据传输、对象存储到函数副本的数据传输。

因此，`faas-sim` 可以理解为：

**在 `ether` 生成的边缘基础设施地图上，跑 serverless 函数、调度器、负载均衡器和扩缩容逻辑的仿真平台。**

**3. 和 `ether` 论文的关系**

你给的参考文档讲的是 `ether`。那篇工作的核心是：

**如何生成合理可信的边缘基础设施拓扑。**

这篇 `faas-sim` 的核心是：

**在这些拓扑上模拟 serverless edge 平台的运行行为。**

两者关系可以这样理解：

- `ether` 负责回答：边缘-云基础设施长什么样？
- `faas-sim` 负责回答：serverless 平台和函数工作负载跑在这个基础设施上会发生什么？

在 `faas-sim` 里，`ether` 主要承担两个角色：

1. **Topology 输入**  
   `faas-sim` 的仿真场景需要一个网络拓扑。这个拓扑可以用 `ether` 生成，比如工业 IoT、城市感知、多区域云等。

2. **Network simulation**  
   函数镜像下载、存储数据读取、函数间通信都会经过网络。`faas-sim` 使用 `ether` 的 flow-based 网络模型估计传输时间和链路瓶颈。

所以如果说 `ether` 是“地图生成器”，那么 `faas-sim` 就是在地图上放入“车辆、路线规划、交通规则和负载变化”的系统仿真器。

**4. 作者认为 serverless edge 平台有两个核心设计任务**

论文第 2 节先讨论 serverless edge computing 平台设计，而不是直接介绍工具。这是因为作者认为 simulator 必须服务于平台设计任务。

作者把平台设计任务概括成两类。

第一类是 **platform architecture**，也就是平台架构。

它关注：

- 请求入口放在哪里？
- 调度器放在哪里？
- 自动伸缩器放在哪里？
- 负载均衡器集中部署还是分布式部署？
- 函数执行环境是怎样的？

论文举了三种架构：

1. **Centralized Platform Architecture**  
   所有入口、调度、伸缩组件都在云端。这和很多现有 serverless 平台类似，例如 OpenFaaS、Knative、OpenWhisk、AWS Lambda 的云中心式思路。缺点是边缘请求可能先绕到云端，增加延迟。

2. **Hybrid Platform Architecture**  
   路由组件放在边缘，调度可能分成全局和局部两级，伸缩组件仍可能在云端。这比完全中心化更适合边缘，但云端组件仍可能成为瓶颈。

3. **Decentralized Platform Architecture**  
   每个计算集群都有自己的调度、伸缩和路由组件。扩展性更好，但跨集群协调、状态同步和一致性更难。

第二类是 **serverless function adaptation strategies**，也就是函数自适应策略。

主要包括：

- **Placement / Scheduling**：函数副本放在哪个节点？
- **Scaling**：何时增加或减少函数副本？
- **Routing / Load balancing**：请求转发给哪个副本？

在边缘环境里，这些策略比云环境难很多：

- 请求来源有空间分布，执行位置会影响网络延迟。
- 节点能力异构，有些有 GPU，有些只有 ARM CPU。
- 数据位置重要，函数靠近数据执行可能比靠近用户执行更合适。
- 多租户会导致性能干扰，同一节点上多个函数同时运行会拖慢彼此。
- 节点和网络可能不稳定。

因此，`faas-sim` 必须让调度器、负载均衡器、自动伸缩器成为可以替换和扩展的一等组件，而不是写死在仿真器内部。

**5. `faas-sim` 支持哪些仿真用途**

论文总结了四类 use case。

第一类是 **resource planning**。

也就是资源规划。平台设计者可以问：

- 现在这批边缘设备够不够？
- 如果多买 Jetson 或 NUC，系统吞吐会提高多少？
- 某个城市或工厂场景最多能承受多少请求？
- 云、边缘、设备端资源比例该怎么配？

这类问题如果全靠真实购买和部署硬件，成本很高。仿真可以先给出方向。

第二类是 **application performance estimation**。

也就是应用性能估计。它关注：

- 函数平均执行时间是多少？
- 响应时间会不会超过 SLA？
- 成本会不会太高？
- 某个函数部署到边缘还是云端更合适？

因为 `faas-sim` 使用真实 profiling trace，所以它比单纯假设“函数固定执行 100ms”更可信。

第三类是 **serverless adaptation evaluation**。

也就是评估调度、伸缩、路由算法。

比如研究者提出一个新调度算法，可以用 `faas-sim` 在不同拓扑、不同请求模式、不同设备组合下测试：

- 是否减少 FET？
- 是否减少网络传输？
- 是否避免多租户干扰？
- 是否更好地利用 GPU / TPU？
- 是否能应对请求热点变化？

第四类是 **co-simulation driven adaptations**。

这是比较有意思的一点。作者不仅把 simulator 当作离线评估工具，还希望它参与运行时决策。

意思是：真实系统运行时，平台可以把当前状态喂给 simulator，让 simulator 快速模拟几个未来场景，再选择更好的调度或伸缩参数。

这有点像给 serverless edge 平台做一个轻量级数字孪生：

**真实系统负责运行，仿真系统负责试错和预测。**

**6. `faas-sim` 的核心概念模型**

论文第 3 节给出 `faas-sim` 的概念模型。它把函数分成 design time 和 runtime 两层。

几个关键概念如下。

**Function**

表示一个可以被调用的功能，比如 `detect-objects`。它是最高层抽象，只描述“这个函数做什么”。

**FunctionImage**

表示函数在某个平台上的具体实现镜像。比如同一个图像检测函数可以有 CPU 版本、GPU 版本、TPU 版本。

作者特意引入这个概念，是因为边缘环境里“同一个函数”可能需要面向不同硬件准备不同镜像。调度器不仅要决定放在哪个节点，还要决定使用哪个镜像。

**FunctionDeployment**

表示某个 Function 的一次部署配置，包括资源配置、伸缩策略等。

**FunctionContainer**

表示某个 FunctionImage 的运行时配置，比如需要多少 CPU、内存、GPU 显存等。

**FunctionReplica**

表示实际运行的函数副本，类似一个真正跑起来的容器。

**FunctionSimulator**

这是 `faas-sim` 的核心。每个 FunctionReplica 都有一个 FunctionSimulator，用来模拟这个副本的生命周期和执行行为。

**FunctionNode**

表示可以承载函数副本的计算节点，比如 Raspberry Pi、Jetson、Intel NUC、云服务器等。

这些概念的好处是：

**它让仿真模型和真实 FaaS 平台的概念对齐。**

研究者写调度器、伸缩器、负载均衡器时，不是在操作抽象任务编号，而是在操作函数、镜像、副本、节点、资源这些真实系统里也存在的对象。

**7. `faas-sim` 的架构**

论文把 `faas-sim` 的架构概括为三个核心抽象：

1. **FaaSSystem**
2. **Environment**
3. **FunctionSimulator**

**FaaSSystem**

它是用户和平台交互的高层接口，类似一个 serverless 平台前端。

它提供的方法包括：

- `deploy`：部署函数，创建最小数量的函数副本。
- `invoke`：调用函数，通过 LoadBalancer 选择副本，然后执行 invoke 模拟。
- `remove`：移除函数，并关闭所有副本。
- `discover`：发现某个部署下正在运行的副本。
- `scale_up`：增加副本。
- `scale_down`：减少副本。
- `poll_available_replica`：等待可用副本。

这个接口设计很像真实 FaaS 平台，因此适合把真实平台逻辑迁移到仿真里。

**Environment**

它是仿真过程里的全局上下文，保存各种组件引用。

包括：

- ClusterContext：记录节点上的镜像和资源状态。
- FunctionSimulatorFactory：决定某个副本用哪个 FunctionSimulator。
- Topology：网络拓扑，通常来自 Ether。
- Scheduler：决定副本放在哪个节点。
- ResourceState：记录节点和副本资源使用。
- Metrics：记录仿真指标，最后导出为 Pandas DataFrame。
- ContainerRegistry：镜像仓库，也是拓扑中的一个节点，可以模拟镜像下载。
- BackgroundProcesses：后台进程，比如 Autoscaler、ResourceMonitor。
- StorageIndex：建模对象存储和数据位置。

**FunctionSimulator**

它模拟函数副本的生命周期。

一个函数副本通常经历：

1. `deploy`：部署，比如从镜像仓库下载容器镜像。
2. `startup`：启动容器或运行时。
3. `setup`：加载模型、初始化资源。
4. `invoke`：处理请求。
5. `teardown`：清理和关闭。

作者用 AI inference 函数举例：容器启动后会加载 AI 模型到内存，之后每次请求执行推理。仿真中就可以分别模拟镜像下载时间、启动时间、模型加载时间、推理执行时间和资源占用。

这比只写一个“函数执行耗时 X 秒”的模型细得多，也更接近真实 serverless 平台。

**8. Trace-driven performance modeling：为什么不用简单 CPU 指令模型**

很多传统云/边缘仿真器会用类似 CloudSim 的思路：

任务有多少 instructions，CPU 每秒执行多少 instructions，所以执行时间可以算出来。

作者认为这在边缘环境里问题很大：

- 不同 CPU 架构差异很大，ARM、x86、GPU、TPU 都不一样。
- 同样数量的指令在不同架构上耗时不同。
- 函数性能不只取决于 CPU，还取决于内存、I/O、网络、GPU 等。
- 边缘设备的缓存、存储、热状态、并发干扰都会影响运行时间。
- 最后你还是需要真实测量 workload 和 device，和 trace-driven 的成本差不多。

所以作者选择：

**直接在真实设备上跑函数，采集函数执行时间和资源占用，然后用 trace 驱动仿真。**

在仿真时，`faas-sim` 用一个 oracle 来决定某次函数调用的 FET。这个 oracle 可以根据：

- 函数类型；
- 执行节点；
- 当前并发请求数；
- 当前资源使用状态；
- profiling trace 中拟合出的分布；

来采样或预测执行时间。

**9. 单租户和多租户性能退化**

论文中特别强调 performance degradation，也就是性能退化。

在真实边缘节点上，多个函数同时运行时，函数执行时间会变长，波动也会更大。

作者分两种情况建模。

第一种是 **single-tenant performance degradation**。

也就是同一种 workload 在同一个节点上并发运行。作者用 SMT workload 作为例子，拟合出一个执行时间模型：

`FET = 0.068 * r + 0.247 + X`

其中：

- `r` 是并发请求数；
- `X` 是从 log-normal 分布采样的噪声；
- 并发越高，执行时间中位数越大；
- 随机噪声用于模拟真实执行时间波动。

第二种是 **multi-tenant performance degradation**。

也就是不同 workload 混跑，比如 AI inference、CPU-heavy、I/O-heavy 同时在一个节点上执行。

这种情况更难，因为不同函数占用的资源维度不同。

作者使用 resource vector 描述函数资源占用，包括：

- CPU utilization
- block I/O
- network I/O
- GPU utilization
- RAM usage

然后用 ML 模型预测性能退化因子。论文提到他们用 TPOT AutoML 找到了一个 pipeline，验证结果的 mean absolute error 大约在 `0.02` 到 `0.09` 之间。

这说明 `faas-sim` 不只是“套一个固定公式”，而是允许用户把真实 profiling、统计分布、机器学习模型接进仿真过程。

**10. 网络仿真：为什么用 flow-based 模型**

Serverless edge computing 里网络非常关键。典型网络行为包括：

- 节点从镜像仓库下载 FunctionContainer。
- FunctionReplica 从存储节点读取数据。
- 函数之间传输请求和响应数据。
- 边缘节点和云节点之间传输 AI 模型、视频或传感器数据。

`faas-sim` 使用 `ether` 的网络模型，不做 packet-level simulation，而做 flow-based simulation。

也就是说，它不模拟每一个 TCP 包，而是把一次数据传输看成一个 flow：

- 先在拓扑图上找最短路径；
- 找到路径上的瓶颈链路；
- 多个 flow 竞争同一链路时，按 max-min fairness 分配带宽；
- 传输时间大致等于 TCP 建连时间加上数据量除以 goodput。

论文中的传输时间模型可以理解为：

`duration = round_trip_time * 1.5 + bytes_to_transfer / goodput`

这里 `1.5 * RTT` 用来粗略表示 TCP handshake 过程，`goodput` 近似为瓶颈链路可分配带宽乘以 `0.97`，用于扣除 TCP 开销。

这个设计的优点是快，适合大规模系统仿真。

缺点是它没有细致建模：

- TCP 拥塞控制收敛过程；
- 大量并发 TCP flow 下的复杂退化；
- packet loss；
- 更细粒度协议行为；
- 真实设备硬件瓶颈对网络吞吐的影响。

作者很坦诚地说，这个模型不保证适用于所有网络场景。它适合 `faas-sim` 面向的系统级评估，但如果研究问题本身就是 TCP 协议细节，那它不够。

**11. 用户如何定义仿真场景**

`faas-sim` 的仿真场景主要需要两个输入：

1. **Topology**
2. **Benchmark**

**Topology**

拓扑来自 `ether`，包括 nodes、links、cells 和 topology graph。

`faas-sim` 内置了一些典型拓扑：

- Industrial IoT：多个工厂/边缘前提设施加共享云资源。
- Urban sensing：基于 Array of Things 的城市感知场景。
- Multi-region cloud：多个云数据中心通过互联网骨干连接。

这些拓扑可以直接作为 baseline，也可以由用户用代码生成。

**Benchmark**

Benchmark 描述 workload 如何产生。

比如：

- 顺序调用某个函数 N 次；
- 在一段仿真时间内，对多个函数按随机模式产生请求；
- 用多个 workload generator 模拟不同位置的用户；
- 用 sine workload pattern 模拟周期性请求；
- 从已有 inter-arrival time 文件重放真实请求到达序列。

`faas-sim` 的 request generator 可以组合：

- arrival process：请求间隔分布，比如 constant 或 expovariate；
- workload pattern：目标 rps 随时间变化，比如 constant、sine、random walk。

这让它能模拟比较真实的动态 workload，而不是只有固定请求速率。

**12. 论文里的实验与验证**

论文第 4 节评估比较丰富，主要有五部分。

第一部分是 **use case-based evaluation**。

作者展示 `faas-sim` 已经被用于多篇工作，包括：

- 多租户性能退化建模；
- 调度算法评估；
- 负载均衡器放置评估；
- 数据密集型 serverless 应用调度；
- 用 co-simulation 优化调度器参数。

这部分不是单个实验，而是证明 `faas-sim` 确实能覆盖前面提出的四类 use case。

第二部分是 **faas-sim traces**。

作者提供了一批可直接使用的 profiling traces。

设备包括：

- Xeon GPU 机器；
- Intel NUC；
- Raspberry Pi 3；
- Raspberry Pi 4；
- RockPi；
- Coral Dev Board；
- Jetson TX2；
- Jetson Nano；
- Jetson NX。

函数包括：

- Fio I/O workload；
- Mobilenet inference；
- Python Pi；
- Resnet50 inference CPU；
- Resnet50 inference GPU；
- Resnet50 preprocessing；
- Resnet50 training CPU / GPU；
- Speech inference；
- TensorFlow GPU workload。

论文的 Table 2 展示了这些函数在不同设备上的平均 FET。可以看到差异非常大。

例如：

- Mobilenet TFLite inference 在 Jetson NX 上约 `0.33s`，在 RPi4 上约 `1.28s`。
- Resnet50 CPU inference 在 Intel NUC 上约 `0.16s`，在 RPi4 上约 `2.91s`。
- Resnet50 GPU training 在 Xeon GPU 上约 `32.13s`，在 Jetson Nano 上约 `847.17s`。

这说明边缘异构环境里不能简单假设“所有节点执行时间一样”。

第三部分是 **network simulation evaluation**。

作者做了两类网络验证。

第一类是基础 node-to-node 数据传输验证。

实验环境包括：

- 三个 Raspberry Pi 4；
- 两个 Raspberry Pi 3；
- 一个交换机；
- 一个 EdgeRouter X；
- HTTP server 和 curl client；
- 文件大小为 `1MB`、`10MB`、`200MB`。

他们分别在真实 testbed、ns-3、Ether 中运行实验。

结果大致是：

- 顺序下载场景中，Ether 的误差在不同文件大小下保持在 `7%` 以内。
- 并行下载场景中，误差会变大，ns-3 比 Ether 更准确。
- 并行场景误差大的原因之一是 Raspberry Pi 等真实设备本身性能有限，而两个 simulator 都没有完整建模设备硬件对网络吞吐的影响。

第二类是复现真实多区域云实验。

作者复现了 EMMA elastic MQTT middleware 的实验。原实验在三个云区域部署 client 和 broker，观察跨区域 MQTT topic latency。作者用 Ether 和 faas-sim 复现这个场景。

仿真结果在整体趋势上能复现真实系统中的延迟峰谷变化，但更平滑，也无法捕捉 Java VM warmup、buffering 等平台细节。

作者的结论是：

**这个网络模型对系统级趋势分析足够有用，但不能证明所有复杂网络场景都能准确模拟。**

第四部分是 **flexible platform design**。

作者展示如何用 FunctionSimulator 模拟 OpenFaaS 的 `of-watchdog`。

OpenFaaS 有两种执行模式：

- HTTP mode：启动 Flask HTTP server，多个 worker 通过队列处理请求，可以缓存昂贵资源。
- Fork mode：每个请求 fork 一个新的 Python process，开销更高，延迟更大。

`faas-sim` 可以用不同 FunctionSimulator 模拟这两种模式，说明它不是只能模拟一种固定函数运行时，而是能接近真实平台行为。

第五部分是 **faas-sim resource usage**。

作者测试 simulator 自身资源开销。

实验场景是：

- SmartCity topology；
- 15 个 edge cluster；
- 1 个 cloud cluster；
- 每个 cluster 有一个 client；
- 部署 30 个 Resnet50 CPU inference 函数副本；
- 每个 client 发送 `100`、`1000` 或 `2500` 个请求；
- 总请求数分别为 `1500`、`15000`、`37500`。

运行环境是：

- Python 原生运行；
- 主机 32GB RAM；
- i7 7700K 4.2GHz，4 核 8 线程。

结果显示：

- 因为 Python 和 SimPy 是单线程，仿真大致吃满一个 CPU core。
- 长时间运行时内存可能增长到约 `2GB`。
- 内存增长主要来自 Metrics logging。
- 关闭 logging 或使用持续写盘 logger 后，内存增长会明显降低。

这说明 `faas-sim` 的性能可以支持较长场景，但日志系统会影响内存，需要按实验规模调整。

**13. 和其他 simulator 相比，它强在哪里**

论文对比了 SimLess、OpenDC 2.0、DFaaSCloud、SimFaaS 等 serverless simulator。

作者认为 `faas-sim` 的主要差异是：

1. **面向 serverless edge computing，而不是普通云、普通 IoT 或普通边缘计算。**

2. **把 serverless adaptation 作为一等组件。**  
   调度、伸缩、路由都可以替换和扩展。

3. **FunctionSimulator 很灵活。**  
   用户可以模拟函数部署、启动、setup、invoke、teardown，而不是只填一个函数耗时。

4. **性能和资源模型不写死。**  
   可以用统计分布、真实 trace、ML 模型或用户自定义模型。

5. **集成 Ether，支持代码生成拓扑。**  
   这是它和很多只支持 UI 或 JSON 配置的 simulator 的明显区别。

6. **支持 co-simulation。**  
   因为仿真模型和真实 serverless 组件抽象接近，所以仿真结果可以反过来指导真实系统的调度参数。

**14. 这篇论文的贡献**

我觉得这篇论文的贡献可以概括成五点。

第一，**明确提出 serverless edge computing 需要专门的仿真框架**。

它不是普通 serverless，也不是普通 edge。它同时需要建模 FaaS 抽象、异构硬件、网络传输、空间-时间 workload、调度/伸缩/路由策略。

第二，**提出并实现了 `faas-sim`**。

这是一个开源 Python 仿真框架，基于 SimPy，使用真实 trace 驱动，面向 serverless edge 平台评估。

第三，**建立了一套比较完整的 serverless 仿真领域模型**。

包括 Function、FunctionImage、FunctionDeployment、FunctionContainer、FunctionReplica、FunctionNode、FaaSSystem、Environment、FunctionSimulator 等。

第四，**提出灵活的 trace-driven performance/resource modeling 方法**。

它不仅能用真实 FET trace，还能建模单租户、多租户性能退化，并允许接入 ML 模型预测性能退化因子。

第五，**把 `ether` 的拓扑和网络仿真接入 serverless 仿真**。

这让研究者可以在 plausible edge topology 上评估函数调度、镜像下载、数据传输和网络瓶颈。

**15. 局限性**

这篇论文的局限也比较明显，而且作者自己说得很清楚。

第一，**trace-driven 的前提是你要有 trace**。

如果换一个新函数、新设备、新硬件加速器，就需要重新 profiling。作者虽然提供了一批默认 traces，但它们不可能覆盖所有边缘设备和 workload。

第二，**多租户 ML 模型的泛化能力还不充分**。

论文里提到，多租户性能退化模型主要在有限函数集合上训练和验证。它对完全没见过的新函数是否仍然准确，需要重新评估。

第三，**网络模型是 flow-level，不是 packet-level**。

它速度快，但不模拟 TCP 拥塞收敛、packet loss、大量并发 flow 的细节。如果研究问题对网络协议细节敏感，`faas-sim` 不够。

第四，**真实平台细节可能捕捉不到**。

比如 EMMA 实验里的 Java VM warmup 和 buffering，就不是 `faas-sim` 默认能自动模拟的。用户必须显式建模这些平台细节。

第五，**仿真性能受 Python 单线程和日志系统影响**。

大规模仿真时，CPU 基本吃满一个 core；Metrics logging 会导致内存增长，需要换 logger 或减少记录粒度。

第六，**它不是一个标准 benchmark**。

`faas-sim` 是一个框架和工具箱，不是一个固定统一的评测标准。不同用户的 trace、拓扑、模型和 benchmark 可能仍然不同。

**16. 对你的大论文可能有用的理解角度**

如果你的论文主题和 serverless edge / 边缘仿真 / 调度有关，这篇可以从三个角度引用。

第一个角度是 **研究背景**：

边缘 serverless 平台缺少标准 benchmark、reference architecture 和真实 trace，因此需要仿真框架辅助设计与评估。

第二个角度是 **方法借鉴**：

`faas-sim` 把真实 profiling trace、离散事件仿真、拓扑生成、网络 flow 模型和 serverless 平台组件组合起来，是一种“trace-driven + topology-aware + FaaS-aware”的评估方法。

第三个角度是 **与 `ether` 的衔接**：

`ether` 解决基础设施拓扑生成问题，`faas-sim` 在此基础上解决 serverless workload 与平台策略评估问题。两者形成一条完整链路：

**生成边缘基础设施 -> 放入 serverless 平台模型 -> 注入函数工作负载 -> 仿真调度/伸缩/路由/网络传输 -> 输出性能和资源指标。**

**17. 用一句通俗比喻总结**

如果说 `ether` 是一个“边缘计算地图生成器”，能生成城市、工厂、云和边缘节点组成的道路网络，那么 `faas-sim` 就是在这张地图上运行 serverless 平台的“交通仿真系统”：它不仅知道每条路的带宽和延迟，还知道每辆车代表哪个函数、装了多少数据、要去哪台设备执行、路上会不会堵、多个函数同时跑会不会互相拖慢。

它不能保证完全复刻真实世界的每一个细节，但它能让研究者在部署真实系统前，先比较不同平台架构、调度算法、硬件配置和 workload 模式的影响，从而让 serverless edge computing 的实验评估更系统、更可复现、更接近真实场景。
