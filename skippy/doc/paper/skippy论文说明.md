# 论文说明

**数据密集型 serverless edge 应用很难调度，因为函数执行位置不仅取决于 CPU/内存，还取决于数据在哪里、容器镜像在哪里、网络上下行瓶颈在哪里、节点有没有 GPU、函数是否应该优先跑在边缘；作者提出 `Skippy`，在 Kubernetes 调度器模型上增加边缘感知的优先级函数，并用仿真自动调优这些优先级权重。**

论文信息：

- 标题：`Optimized container scheduling for data-intensive serverless edge computing`
- 作者：Thomas Rausch, Alexander Rashed, Schahram Dustdar
- 发表：Future Generation Computer Systems, 2021
- DOI：`10.1016/j.future.2020.07.017`
- 关键词：Edge computing, Serverless, Container scheduling, Machine learning

**1. 这篇论文要解决什么问题**

这篇论文关注的是一个很具体但很关键的问题：

**在边缘-云混合环境里，数据密集型 serverless 函数应该被调度到哪里执行？**

传统云环境里，调度器通常主要看：

- 节点是否有足够 CPU；
- 节点是否有足够内存；
- 节点负载是否均衡；
- pod 是否满足 Kubernetes 的资源约束。

但在 serverless edge computing 里，这些远远不够。

因为数据密集型边缘应用往往有几个特点：

- **workload 异构**：一个应用可能由多个函数组成，每个函数对硬件要求不同，比如预处理函数、模型训练函数、模型推理函数。
- **数据位置敏感**：数据可能在边缘传感器、摄像头、工厂网关或本地对象存储里，不一定在云端。
- **延迟敏感**：视频流、城市感知、工业 IoT 等场景通常希望靠近数据源或用户执行。
- **带宽需求高**：视频、图片、模型、训练数据都可能很大。
- **硬件异构**：有些节点是 Raspberry Pi，有些是 Intel NUC，有些是 Jetson TX2，有些是云 VM。
- **上下行网络不对称**：边缘网络内部可能 1Gb/s，但上行到云只有 25Mb/s 或 250Mb/s。

如果调度器只看 CPU 和内存，就会出现很糟糕的放置结果。

比如一个模型训练函数需要读取边缘本地训练数据。如果 Kubernetes 把它调度到云端：

- 它可能有更强 CPU；
- 但训练数据要从边缘上传到云；
- 边缘上行带宽很小；
- 最终函数执行时间可能被数据传输拖垮。

反过来，如果函数镜像只在云端 registry，而数据在边缘，那么把函数放在边缘也需要先从云拉镜像。调度器必须在两种移动之间权衡：

**移动数据到计算节点，还是移动计算到数据附近？**

作者认为，现有 serverless 平台和 Kubernetes 默认调度器没有很好处理这个问题。

**2. 作者的核心思路**

作者提出的系统叫 `Skippy`。

它不是重新做一个完整 serverless 平台，而是：

**在现有 Kubernetes / OpenFaaS 这类平台之上，增加一个边缘感知的容器调度系统。**

它的核心思路是：

1. **保留 Kubernetes 调度器的基本框架**  
   Kubernetes 调度器本质上是在线调度器，每次 pod 到来时，从可行节点里选择一个最合适的节点。

2. **增加边缘场景需要的 metadata**  
   包括节点能力、函数数据依赖、函数硬件需求、节点是 edge 还是 cloud、数据存储节点位置、网络带宽图等。

3. **增加 4 个 edge-friendly priority functions**  
   用来让调度器考虑镜像拉取时间、数据传输时间、硬件能力匹配、边缘/云位置偏好。

4. **用仿真自动调优优先级权重**  
   不同场景下“数据本地性”“镜像本地性”“GPU 能力”“边缘优先”哪个更重要是不一样的。作者用模拟器和 NSGA-II 多目标优化算法自动寻找权重。

一句话概括：

**Skippy 把 Kubernetes 原来“看资源是否够”的调度，扩展成“看资源、数据、镜像、网络、硬件能力和边缘/云位置”的调度。**

**3. 和 `ether`、`faas-sim` 的关系**

这篇论文和你前面看的两篇其实是同一个研究链条里的不同部分。

可以这样理解：

- `ether`：负责生成 plausible edge infrastructure topology，也就是边缘基础设施拓扑。
- `Skippy`：负责在这个拓扑上做 data-intensive serverless function 的调度。
- `faas-sim`：后来发展成更通用的 serverless edge 仿真框架，用来评估调度、伸缩、路由等策略。

在这篇 Skippy 论文里，作者已经用到了两个后来在 `faas-sim` 论文中系统化的思想：

1. **用 Ether 生成网络拓扑和基础设施场景。**

2. **用 trace-driven serverless simulator 做评估和权重优化。**

所以三者关系可以串成一条线：

**Ether 生成边缘地图 -> Skippy 在地图上决定函数放哪里 -> 仿真器评估这些放置决策的执行时间、流量、成本和资源利用率。**

从研究发展顺序上看，Skippy 更像是一个具体调度算法/系统；`faas-sim` 则是后来把这种评估过程抽象成通用仿真框架。

**4. 论文里的应用例子：ML workflow**

作者用一个机器学习工作流来说明数据密集型 serverless edge 应用为什么难调度。

这个 workflow 有三个步骤，每个步骤都作为一个 serverless function：

1. **data preprocessing**  
   读取原始数据，做预处理。

2. **model training**  
   训练模型，通常需要 GPU 加速。

3. **model serving**  
   部署模型并进行推理。

论文中用 MNIST 作为例子，主要是为了可复现。

一个典型训练函数的逻辑是：

- 从 S3 / MinIO 这类对象存储下载训练数据；
- 转换数据格式；
- 训练模型；
- 把训练好的模型上传回对象存储。

这个例子说明一个关键点：

**数据密集型函数的执行时间不只是“计算时间”，还包括大量数据拉取和写回。**

因此，调度器如果不知道函数要读写哪些数据，就无法判断把函数放在哪里更好。

作者之前提出过一个高层 API，让开发者通过注解说明函数的数据依赖和硬件需求。例如：

- `@consumes.data(...)` 表示函数要读取哪些数据；
- `@produces.model(...)` 表示函数会产生哪些模型；
- `@policy.fn(capability='gpu')` 表示函数需要 GPU。

Skippy 会把这些注解转换成 Kubernetes pod labels，供调度器使用。

**5. 关键观察：容器镜像移动 vs 数据移动**

论文第 3 节有一个重要分析：函数启动可能需要拉取容器镜像，函数执行可能需要传输运行时数据。这两者都会耗时。

作者设定了一个典型网络场景：

- 边缘网络内部带宽：`1Gb/s`
- 边缘到互联网下行：`100Mb/s`
- 边缘到互联网上行：`25Mb/s`
- 云内部带宽：`1Gb/s`
- 数据在边缘；
- 容器 registry 在云端。

这时调度器要做权衡：

- 如果把函数放在边缘，需要从云拉镜像到边缘；
- 如果把函数放在云端，需要把边缘数据上传到云。

由于上行带宽通常比下行更小，把数据从边缘上传到云可能非常慢。

论文还观察到 Docker 镜像有分层机制，不同函数镜像可能共享很多 base layers。作者检查自己的应用后发现：

**几乎 90% 的镜像大小是不同镜像之间共享的 layer。**

这意味着：

- 第一次拉镜像很贵；
- 但如果一个节点已经有共享 layer，后续拉其他函数镜像会便宜很多；
- 因此，镜像本地性也是调度器需要考虑的因素。

但在很多数据密集型函数里，一旦共享 layer 已经存在，主要开销就会变成数据传输，而不是镜像拉取。

**6. 边缘-云连续体里的设备异构**

作者的 testbed 和模拟场景包含几类典型设备：

- **VM**：x86，4 核 Core2 3GHz，8GB RAM。
- **SBC**：ARM32，4 核 Cortex-A53 1.4GHz，1GB RAM，类似 Raspberry Pi。
- **NUC**：x86，4 核 i5 2.2GHz，16GB RAM。
- **TX2**：aarch64，Jetson TX2，8GB RAM，带 256-core Pascal GPU。

作者在这些设备上跑 ML workflow，并采集了 `156` 次 warm function executions。

结果说明：

- Raspberry Pi 这类 SBC 甚至跑不了 model training，因为内存不够。
- Jetson TX2 虽然 CPU 不如 Intel NUC，但因为有 GPU，model training 表现更好。
- 不同函数对不同硬件的适配差异很大。

这进一步说明，调度器不能只看“节点剩余 CPU/内存”，还要看：

**这个函数需要什么能力，而这个节点是否真的具备这种能力。**

**7. 三个基础设施场景**

为了评估 Skippy，作者没有只在小 testbed 上跑实验，而是使用 Edge Topology Synthesizer / Ether 生成了三类 plausible scenario。

**S1：Urban sensing**

城市感知场景，参考 Chicago Array of Things。

主要设定：

- 约 200 个传感器节点；
- 每个 sensor node 有两个 SBC；
- 城市中有 cloudlet；
- 每个摄像头附近配置 Intel NUC 和两个 Jetson TX2；
- 另有 30 个云 VM 作为 fallback；
- 每个 edge network 内部 LAN 为 `1Gb/s`；
- edge 到互联网为 `100/25Mb/s` 下行/上行；
- cloud 内部为 `10Gb/s`，到互联网为 `1Gb/s`。

总节点数为 `1170`，设备比例大致是：

- VM：3%
- SBC：39%
- NUC：19%
- TX2：39%

这是一个典型“边缘资源多、云资源少、数据在边缘”的场景。

**S2：Industry 4.0**

工业 IoT / 智能制造场景。

主要设定：

- 10 个工厂位置；
- 每个工厂有 4 个 SBC 作为 IoT gateway；
- 1 个 Intel NUC；
- 1 个 Jetson TX2；
- 4 个 on-premises cloud VM；
- edge 和 on-prem cloud 都有 datastore；
- SBC 通过 `300Mb/s` WiFi 到 AP；
- AP 到 edge resources 是 `10Gb/s`；
- AP 到 on-prem cloud 是 `1Gb/s`；
- 工厂之间通过 `500/250Mb/s` 下行/上行互联网连接。

总节点数为 `110`，设备比例大致是：

- VM：40%
- SBC：40%
- NUC：10%
- TX2：10%

这是一个 edge 和 on-prem cloud 混合更均衡的场景。

**S3：Cloud federation**

云联邦场景，用作非边缘对照。

主要设定：

- 3 个云区域；
- 每个区域平均 150 个 VM；
- 总节点数 `450`；
- 全部是 VM，没有 edge 设备；
- 区域内带宽 `10Gb/s`；
- 跨区域带宽 `1Gb/s`；
- 每个区域本地访问 container registry。

这是一个相对同构的云环境，用来观察 Skippy 在非边缘场景中是否仍然有效。

**8. Kubernetes 调度器的基本机制**

理解 Skippy 之前，需要先理解 Kubernetes scheduler。

Kubernetes 调度器是一个 online scheduler，也就是 pod 一个个到来，调度器通常不知道未来还有哪些 pod。

它大致分两步：

1. **Predicate functions**  
   硬约束过滤。比如节点 CPU/内存不够，就直接淘汰。

2. **Priority functions**  
   软约束打分。对每个可行节点计算多个优先级分数，再按权重求和，选择最高分节点。

形式上可以理解为：

`score(pod, node) = Σ wi * Si(pod, node)`

其中：

- `Si` 是第 i 个 priority function；
- `wi` 是它的权重；
- 得分最高的 node 被选中。

Kubernetes 默认调度器的问题是：

**它的默认 priority functions 主要面向云数据中心，不理解边缘网络、数据位置、容器镜像位置、GPU 能力和 edge/cloud locality。**

Skippy 就是在这个框架里增加新的 priority functions。

**9. Skippy 的系统组成**

Skippy 主要由几类组件组成。

**metadata schema**

Skippy 大量使用容器和节点 labels。所有 Skippy 相关 label 都带有 `*.skippy.io` 前缀。

这些 metadata 用来告诉调度器：

- 函数要读哪些数据；
- 函数会写哪些数据；
- 函数需要 GPU 吗；
- 节点有 GPU 吗；
- 节点属于 edge 还是 cloud；
- 节点是否运行 storage pod。

**skippy-daemon**

这是一个运行在每个集群节点上的 daemon。

它负责探测节点能力，例如：

- 是否有 NVIDIA GPU；
- CUDA 版本；
- 是否运行 MinIO storage pod；
- 节点 locality 是 edge 还是 cloud。

它会把这些信息写成 Kubernetes node labels。

作者提到这个 daemon 开销较小：

- 约 `120MB` 磁盘空间；
- 约 `25-40MB` RAM，取决于 CPU 架构。

**skippy-scheduler**

这是 Skippy 的核心调度器。

它基于 Kubernetes 的 MCDM 调度逻辑，但加入 edge-aware priority functions。

**data index & bandwidth graph**

这是 Skippy 相比普通调度器很关键的两个结构：

- data index：记录某个数据 item 存在哪些 storage nodes 上；
- bandwidth graph：记录节点之间理论或估计带宽。

这两个结构让调度器可以估计：

- 函数在某节点执行时，从数据存储拉数据要多久；
- 从 container registry 拉镜像到某节点要多久。

**OpenFaaS integration**

作者用 OpenFaaS 作为 serverless 平台原型。

OpenFaaS 在 Kubernetes 上通过 `faas-netes` 把函数部署成 Kubernetes pods。作者修改 `faas-netes`，给这些 pods 加 label，让它们由 Skippy 而不是默认 Kubernetes scheduler 调度。

除此之外，Skippy 主要还是通过 Kubernetes API 工作，没有深度侵入 OpenFaaS。

**10. Skippy 的四个 edge-friendly priority functions**

这是论文最核心的技术部分。

**1. LatencyAwareImageLocalityPriority**

作用：

**偏好那些能更快拉取容器镜像的节点。**

它会估算：

- pod 需要哪些 container images；
- node 上是否已经有这些 images；
- 如果没有，需要从 registry 拉多少数据；
- registry 到 node 的带宽是多少；
- 下载大概需要多久。

如果镜像已经在节点上，或者共享 layer 已经存在，部署会更快。

它解决的是：

**计算移动到边缘时，函数代码/镜像本身也要移动。**

**2. DataLocalityPriority**

作用：

**偏好那些离函数所需数据更近、数据传输更快的节点。**

它会读取函数的 metadata，例如：

- `data.skippy.io/recv`：函数要读取的数据；
- `data.skippy.io/send`：函数会写入的数据。

然后通过 storage index 找到数据所在 storage nodes，再用 bandwidth graph 估算数据传输时间。

它解决的是：

**数据移动到计算节点的代价。**

这也是数据密集型 serverless edge 调度中最重要的 priority function 之一。

**3. CapabilityPriority**

作用：

**偏好具备函数所需硬件能力的节点。**

比如函数 label 表示它需要 GPU：

`capability.skippy.io/gpu`

调度器就会优先选择带 GPU 的节点。

这解决的是：

**边缘设备异构和硬件加速器利用问题。**

**4. LocalityTypePriority**

作用：

**偏好某类 locality 的节点，比如 edge 或 cloud。**

例如某些函数因为隐私、延迟或业务要求，希望优先运行在 edge，而不是 cloud。

它通过 `locality.skippy.io/type` 这类 label 来匹配 pod 和 node。

这解决的是：

**函数的高层位置偏好。**

**11. 为什么还要自动调权重**

增加 priority functions 之后，另一个问题出现了：

**这些 priority functions 的权重怎么设？**

如果 DataLocalityPriority 权重太高，调度器可能总是追着数据跑，忽视 GPU 能力。

如果 CapabilityPriority 权重太高，调度器可能总是追着 GPU 跑，导致大量数据跨网络传输。

如果 LocalityTypePriority 权重太高，调度器可能过度使用 edge，导致边缘资源拥塞。

不同场景下权重应该不同：

- 城市感知场景中，云资源少，locality 可能更重要。
- 工业场景中，数据分布在 edge 和 on-prem cloud，data locality 和 GPU capability 都重要。
- 云联邦场景中，节点同构，capability 和 edge/cloud locality 可能不重要。

靠人工调参会很困难，需要大量系统经验和生产环境试错。

所以作者提出：

**用仿真和多目标优化算法自动找到一组比较好的 priority function weights。**

**12. 优化目标**

作者定义了 4 个高层 operational goals。

**f1：average function execution time**

所有函数的平均执行时间。目标是最小化。

**f2：up/downlink usage**

edge 和 cloud 网络之间传输的字节数。目标是最小化。

这反映了上下行链路压力。

**f3：edge resource utilization**

分配在 edge 节点上的资源占比。目标是最大化。

这反映是否有效利用边缘资源。

**f4：cloud execution costs**

云端函数执行时间和流量带来的成本。目标是最小化。

作者用 AWS Lambda 的定价模型来估计成本。

所以优化问题是：

- 最小化 `f1`
- 最小化 `f2`
- 最大化 `f3`
- 最小化 `f4`

作者用 Platypus 框架里的 NSGA-II 遗传算法进行多目标优化。

具体做法是：

- 给定拓扑 `T`；
- 给定 workload profile `W`；
- 给定一组权重 `w`；
- 运行模拟器 `sim(T, W, w)`；
- 从 trace 计算 f1-f4；
- NSGA-II 迭代 `10000` 代；
- 得到 Pareto frontier 上的 `100` 个解；
- 从中选一个较均衡的权重方案。

这个过程说明：

**Skippy 的调度逻辑是在线贪心的，但它的参数可以通过离线仿真优化。**

**13. Serverless simulator 在论文中的作用**

这篇论文里的 simulator 是后来 `faas-sim` 思路的早期形态。

它有两个作用：

1. **评估大规模场景**  
   作者的小 testbed 不可能真实部署 1170 个节点的城市感知场景，所以需要仿真。

2. **给优化算法提供目标函数值**  
   NSGA-II 每次尝试一组权重，都需要知道这组权重会带来什么 FET、网络流量、成本和边缘资源利用率。真实系统上反复跑太贵，所以用仿真。

这个 simulator：

- 基于 SimPy；
- 直接调用 Skippy scheduler 代码；
- 使用 Ether 生成网络拓扑；
- 使用 testbed profiling data 模拟函数执行；
- 使用 flow-based network model 模拟数据传输；
- 模拟 OpenFaaS 的 scale-to-zero 行为；
- 如果函数 idle 超过 `5min`，副本会被停止，后续调用会触发 cold start。

需要注意的是，作者也承认模拟器不是完美 Docker pull 模拟器。真实 Docker pull 会涉及镜像 layer、host 上已有 layer、解压时间等；论文中为了简化，采用了“共享 layer 约 90%”这类经验假设。

**14. 实验设置**

作者比较了三种调度器：

1. **默认 Kubernetes scheduler**
2. **Skippy，所有新增权重设为 1**
3. **Skippy，使用优化后的 priority function weights**

实验流程大致是：

- 随机生成 ML workflow pipeline；
- 每个 pipeline 包含 3 个 ML functions；
- 把函数部署注入 scheduler queue；
- 根据 workload profile 生成请求；
- 运行模拟直到达到指定 invocation 数；
- 比较执行时间、网络流量、边缘资源利用率和成本。

在 S2 场景中，每次实验到 `30000` 次 function invocations 后结束。

工作负载假设包括：

- model serving 请求约 `40 requests/s`；
- data preprocessing 请求每隔几分钟触发一次；
- 容器镜像和 pod 实例之间采用 Pareto 分布；
- 假设 80% pods 使用 20% images；
- 数据 items 在 datastores 和 workflows 之间均匀分布；
- 不同 scheduler 对比使用相同 random seed，保证可比性。

**15. 实验结果：运行时性能**

论文第 6.3.1 节观察了三类场景下的运行时表现。

核心结果是：

**默认 Kubernetes scheduler 在边缘场景中会产生大量跨网络流量，导致函数执行时间变长，甚至出现队列积压。**

在 S1 Urban Sensing 中：

- Kubernetes placement 很快导致网络排队问题；
- 函数执行时间持续上升；
- 原因是调度结果让网络无法及时传输函数所需数据。

在 S2 Industry 4.0 中：

- 没有像 S1 那样严重排队；
- 但 Kubernetes 的放置仍导致整体 FET 更高；
- Skippy 能更好地在数据位置、GPU 能力、边缘/云资源之间权衡。

在 S3 Cloud Regions 中：

- 各节点都是云 VM，相对同构；
- 因此三种调度器在函数执行时间上差别不大；
- 但如果跨区域调度不当，仍会产生额外数据移动成本。

作者还观察到：

**在很多场景里，成本主要来自数据移动，尤其是 data egress，而不是纯计算时间。**

这对 serverless pricing 很重要，因为很多人直觉上只关注函数运行时间，但数据跨区域/出云流量可能才是主要成本。

**16. 实验结果：系统可扩展性**

作者进一步研究 placement 对系统可扩展性的影响。

他们发现，在这些数据密集型场景中，最先成为瓶颈的往往不是 CPU 或内存，而是网络。

他们把不可行 placement 定义为：

**仿真过程中出现网络瓶颈，使某个 flow 分配到的带宽低于 `0.1Mb/s`。**

实验从每个节点 `0.1` 个 deployment 增加到每个节点 `2` 个 deployment。

主要发现：

- Skippy 的 placement 能维持更高的数据吞吐。
- 默认 Kubernetes scheduler 在某些场景中很早就产生不可行 placement。
- 在 S3 中，跨区域带宽很快被打满。
- 如果启用 OpenFaaS scale-to-zero，默认 scheduler 在 S1 中甚至无法产生可行 placement，因为函数不断被重新调度，导致网络迅速被跨网络流量拥塞。

这说明：

**好的函数放置不是局部优化，而会直接影响系统能不能扩展。**

**17. 实验结果：优化权重有什么意义**

论文 Fig. 9 展示了不同场景下优化得到的 priority function weights。

结论比较符合直觉：

在 S1 Urban Sensing 中：

- GPU 节点比例较高，没有很快饱和；
- capability priority 没那么重要；
- locality 更重要，因为云资源少，要避免不必要地使用云。

在 S2 Industry 4.0 中：

- GPU 节点较少；
- 数据也分布在 edge 和 on-prem cloud；
- 所以 data locality 和 capability priority 更重要。

在 S3 Cloud Federation 中：

- 资源比较同构；
- 没有 edge 设备；
- locality、capability、resource balance 权重都没那么关键。

这个结果说明，权重不是一套固定参数可以通吃所有场景。

**Skippy 的调度框架需要结合具体基础设施和 workload，用仿真来调参。**

**18. 调度器吞吐和代价**

Skippy 提高 placement 质量，但不是免费的。

Kubernetes 调度器为了提高吞吐，会使用 sampling heuristic：集群很大时不评估所有节点，只抽样一部分节点打分。

当集群节点数达到 `6500` 以上时，Kubernetes 只考虑约 `5%` 的可用节点进行 scoring。

这个假设在云数据中心里可能合理，因为节点和网络比较同构。

但在边缘环境里，节点差异极大。如果只抽样，可能刚好错过最适合的边缘节点、GPU 节点或数据附近节点。

所以 Skippy 默认关闭这种 aggressive sampling，考虑所有节点。

代价是调度吞吐下降。

论文结果显示：

- 默认 Kubernetes scheduler 使用 2 个 priority functions 和 sampling，在 `10000` 节点集群中约 `170 pods/s`。
- Skippy 默认使用 5 个 priority functions 并评估所有节点，在 `10000` 节点集群中约 `15 pods/s`。

作者认为在他们的场景中这不是主要问题，因为调度延迟只占总 round-trip time 很小一部分。

但它确实说明：

**更智能的边缘调度会牺牲调度器吞吐，未来可能需要 Omega、Firmament 这类更分散或更高效的调度架构。**

**19. 这篇论文的贡献**

我觉得这篇论文的贡献主要有四点。

第一，**明确指出默认 Kubernetes / serverless 调度器不适合数据密集型边缘函数。**

原因不是 Kubernetes 做得差，而是它默认不理解边缘场景里的数据位置、网络上下行、镜像移动、GPU 能力和 edge/cloud locality。

第二，**提出 Skippy 调度系统。**

Skippy 保留 Kubernetes 的在线 MCDM 调度框架，但增加了边缘感知 metadata、data index、bandwidth graph 和新的 priority functions。

第三，**提出四个 edge-friendly priority functions。**

包括：

- LatencyAwareImageLocalityPriority
- DataLocalityPriority
- CapabilityPriority
- LocalityTypePriority

它们共同解决了数据移动、计算移动、硬件匹配和边缘/云位置偏好的问题。

第四，**用仿真和多目标优化自动调权重。**

作者不是手工拍脑袋设置权重，而是通过 serverless simulator + NSGA-II 优化 FET、上下行流量、边缘资源利用和云成本。

第五，**提供 trace 和多场景评估。**

作者在真实 testbed 上采集 ML workflow profiling traces，并在城市感知、工业 IoT、云联邦三类场景中评估调度效果。

**20. 局限性**

这篇论文的局限也比较清楚。

第一，**没有充分处理边缘系统的动态性。**

论文主要关注函数部署时的 placement。真实边缘系统中，用户会移动、节点会变化、网络状态会变化、函数副本可能需要迁移。

第二，**没有解决 client proximity 问题。**

对于静态内容服务、图像分类等请求响应类函数，用户到函数副本的 RTT 可能比数据位置更重要。Skippy 当前主要关注数据和节点之间的关系，没有充分建模客户端位置。

第三，**OpenFaaS / Kubernetes 的中心化 API gateway 架构不适合某些边缘场景。**

如果所有请求都经过中心入口，边缘低延迟优势会被削弱。作者提到可以复制 API gateway，但如何细粒度定位到城市街区级别仍是开放问题。

第四，**节点资源模型仍然比较粗。**

Kubernetes 主要建模 CPU、内存和 pod 数量。GPU 这类稀缺、离散、可能不可共享的资源很难简单表示。

第五，**多租户和 workload interference 没有深入研究。**

容器共享节点时，不同函数之间会有性能干扰。论文没有系统评估多租户场景下 Skippy 的行为。

第六，**假设函数代码通过容器镜像分发。**

这适合 OpenFaaS 这类平台，但 OpenWhisk 等平台可能通过平台层机制分发函数代码，不一定适用 LatencyAwareImageLocalityPriority。

第七，**调度吞吐下降。**

Skippy 为了提升 placement 质量，需要评估更多 priority functions 和更多节点，在大集群中吞吐明显低于默认 Kubernetes scheduler。

**21. 对你的大论文可能有用的理解角度**

如果你的大论文涉及边缘 serverless、调度、仿真或资源管理，这篇论文可以从几个角度使用。

第一个角度是 **问题定义**：

数据密集型 serverless edge 应用的调度核心，不是单纯资源匹配，而是 data movement 和 computation movement 的权衡。

第二个角度是 **调度指标设计**：

调度器应该考虑：

- 数据本地性；
- 镜像本地性；
- 网络带宽；
- 节点硬件能力；
- edge/cloud locality；
- 云成本；
- 边缘资源利用率。

第三个角度是 **系统实现路径**：

不一定要重写 serverless 平台，可以像 Skippy 一样扩展 Kubernetes 调度器和 OpenFaaS 部署流程，通过 labels、daemon、data index、bandwidth graph 接入边缘感知信息。

第四个角度是 **仿真辅助优化**：

边缘调度参数很难人工设定，可以用仿真器在不同拓扑和 workload 下自动调优调度器权重。

第五个角度是 **和前两篇论文衔接**：

这篇论文可以作为 `ether` 和 `faas-sim` 之间的桥：

- `ether` 负责生成评估拓扑；
- `Skippy` 是被评估和优化的调度系统；
- `faas-sim` 则把这类评估进一步泛化成完整 serverless edge 仿真框架。

**22. 用一句通俗比喻总结**

如果说默认 Kubernetes 调度器像是在普通云数据中心里“找一台空机器运行函数”，那么 Skippy 更像是在复杂城市交通里“给任务选路线和目的地”：它不仅看哪台机器有空，还看数据在哪、镜像从哪来、路上堵不堵、目标机器有没有 GPU、任务应不应该留在边缘、去云端会不会产生昂贵流量。

这篇论文的核心价值在于，它把 serverless edge 调度从单纯的资源匹配问题，推进到一个同时考虑数据、网络、硬件和成本的多目标权衡问题。
