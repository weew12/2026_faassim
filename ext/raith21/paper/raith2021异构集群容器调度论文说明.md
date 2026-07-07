# 论文说明

**边缘 serverless 集群里的节点高度异构，函数运行速度和资源争用程度不仅取决于 CPU/内存是否够，还取决于函数本身的资源画像、节点硬件能力、GPU/TPU/磁盘/网络等特征以及同节点容器之间的干扰；作者提出一种基于黑盒 profiling 和机器学习工作负载表征的调度方法，在 Skippy/faas-sim 基础上增加执行时间、资源争用和能力匹配三类 workload-aware priority functions，从而降低函数执行时间和性能退化。**

论文信息：

- 标题：`Container Scheduling on Heterogeneous Clusters using Machine Learning-based Workload Characterization`
- 作者：Philipp Alexander Raith
- 类型：TU Wien 硕士论文 / Diploma Thesis
- 时间：2021 年 2 月 15 日
- 导师：Schahram Dustdar
- 协助：Thomas Rausch
- 关键词：edge, faas, serverless, docker, kubernetes, scheduling, machine-learning, hardware accelerators, workload characterization, resource contention

**1. 这篇论文要解决什么问题**

这篇论文关注的问题是：

**在高度异构的 serverless edge 集群里，如何把函数容器调度到真正适合它的节点上？**

传统 Kubernetes 调度主要依赖 CPU、内存、标签和一些资源均衡启发式规则。这个假设在云数据中心里相对合理，因为云节点往往更同质，资源差异相对可控。

但边缘计算场景完全不同。一个边缘-云连续体可能同时包含：

- 云端 VM；
- Intel NUC 这类 cloudlet；
- Raspberry Pi / RockPi 这类 SBC；
- Jetson Nano / TX2 / Xavier NX 这类边缘 GPU 设备；
- Coral DevBoard 这类 Edge TPU 设备；
- 不同磁盘类型，如 HDD、NVME、eMMC、SD Card；
- 不同 CPU 架构，如 x86、arm32、aarch64。

这会带来几个调度难点：

- 同一个函数在不同节点上的执行时间差异很大。
- 同一个节点对不同函数的适配程度不同。
- GPU/TPU 对某些 AI 推理或训练函数非常重要，但对其他函数可能没有意义。
- 边缘设备资源小，多租户 co-location 容易造成严重性能退化。
- 用户上传函数时通常不知道应该选择哪个节点或能力标签。
- 平台提供方不能假设用户会主动给函数代码加精细 instrumentation。

因此，作者认为默认 Kubernetes / OpenFaaS 调度方式在 serverless edge 中不够用。它可以避免明显的 CPU/内存超限，但不能自动回答：

**这个函数应该运行在什么类型的节点上？这个节点当前是否容易产生资源争用？这个函数在该节点上的执行时间是否真的更短？**

**2. 论文与 Skippy 论文的关系**

参考文档中的 Skippy 论文是 `Optimized container scheduling for data-intensive serverless edge computing`。那篇论文的核心是数据密集型 serverless edge 调度，重点考虑：

- 数据在哪里；
- 镜像在哪里；
- 网络带宽如何；
- 函数是否更适合 edge / cloud；
- 数据移动和计算移动之间如何权衡。

这篇 Philipp Raith 2021 硕士论文是在这个研究链条上的进一步扩展。它仍然使用 Skippy 和 faas-sim，但研究重点从“数据本地性/网络位置”转向：

- workload characterization；
- 异构节点能力建模；
- 函数执行时间建模；
- co-located containers 的性能退化建模；
- 能力匹配型调度。

简单说：

**Skippy 论文主要问“数据密集型函数应该靠近哪些数据和网络位置运行”；这篇论文主要问“异构硬件上，什么样的函数应该跑在哪类节点上，才能更快并减少资源争用”。**

两者是互补关系。论文实验中也比较了四类调度方式：

- 默认调度器 `vanilla`；
- Rausch 等人提出的 Skippy 数据/位置感知优先级；
- 本文提出的 `ga` workload-aware 优先级；
- 两类优先级组合后的 `all`。

**3. 研究问题**

论文提出三个研究问题。

**RQ1：如何基于黑盒系统指标，在 serverless edge 系统中做工作负载表征？**

平台不能假设用户暴露代码内部逻辑，也不能要求用户手动标注所有资源需求。因此作者选择黑盒 profiling：通过函数执行 trace 和容器/系统级 telemetry 来描述函数行为。

**RQ2：如何把工作负载表征用于 serverless edge 函数调度？**

工作负载表征不是为了单纯分析，而是要变成调度器能用的约束和打分函数。例如某函数在某节点上平均执行时间短，或者某函数会大量使用 GPU/网络/块 I/O，那么调度器应该利用这些信息。

**RQ3：workload-aware 调度器能否提高 serverless edge 函数放置质量？**

论文用 faas-sim 在三类异构集群和两种 workload pattern 下评估，核心指标是 Function Execution Time、性能退化和处理请求数。

**4. 作者的核心思路**

作者的整体方案可以概括为一条 pipeline：

1. **建模异构集群**  
   用一组离散属性描述节点能力，例如架构、加速器、磁盘、位置、连接方式、CPU/GPU 型号、CPU 核数、RAM、VRAM、网络带宽等。

2. **计算集群异构度**  
   用 entropy-based heterogeneity score 描述一个集群的异构程度。完全同质集群得分接近 0，属性分布越丰富、越均匀，异构度越高。

3. **采集真实 profiling 数据**  
   使用 `galileo` 生成函数调用负载，使用 `telemd` 收集容器级和系统级指标。

4. **构造 workload characterization vector**  
   对每个函数在每个节点上的一次调用，提取 CPU、GPU、网络 I/O、块 I/O、RAM、总网络流量、总块 I/O 等资源画像。

5. **对函数做聚类**  
   使用 k-means 把资源行为相似的函数分组，避免为每个函数都单独求解能力匹配优化问题。

6. **训练性能退化模型**  
   通过 co-located workload 实验采集资源争用数据，再用 TPOT/AutoML 训练回归模型，预测多容器共置带来的 FET 放大倍数。

7. **求解 Capability Matching Problem**  
   为每类 workload group 找一组偏好的节点能力分布，例如更偏向 GPU、某种 CPU 架构、某类磁盘或某类位置。

8. **扩展 Skippy/Kubernetes 调度器**  
   增加三个 priority functions：`CapabilityPriority`、`ContentionPriority`、`ExecutionTimePriority`。

一句话概括：

**作者先用 profiling 学到“函数在各种硬件上的行为”，再把这些知识转成调度器打分函数，让调度器从资源容量感知升级为工作负载感知。**

**5. 异构集群建模**

论文把每个节点描述成一组 capability attributes。

主要属性包括：

- `Architecture`：x86、arm32、aarch64；
- `Accelerator`：None、GPU、TPU；
- `Disk`：HDD、SSD、NVME、eMMC、SD Card；
- `Location`：Cloud、MEC、Edge、Mobile；
- `Connection`：Ethernet、WiFi、Mobile；
- `CPU`：i7、Xeon、ARM；
- `GPU`：Turing、Pascal、Maxwell、Volta；
- `Cores / Network / CPU MHz / GPU MHz / RAM / VRAM`：按 Low、Medium、High、Very High 等 bin 离散化。

这种建模方式有两个作用。

第一，给调度器提供可比较的节点能力描述。不同设备虽然硬件细节复杂，但都能被转换成统一属性表。

第二，给后续 Capability Matching Problem 提供输入。优化器不是直接操作具体节点，而是学习某类函数偏好什么能力组合。

论文还提出了 entropy-based heterogeneity score。它把集群中各属性值出现概率与同质基线比较，从而量化集群“有多异构”。作者用这个分数生成和选择评估场景，也把它放进能力匹配优化目标里，避免优化结果只选择极少数同类设备。

**6. workload characterization：黑盒函数画像**

论文的 workload characterization 基于两类数据。

第一类是 invocation trace，用来计算 Function Execution Time。

作者对 FET 的定义比较明确：FET 指用户函数代码真正执行的时间，不包含完整客户端往返，也不同于端到端 HTTP latency。论文图 4.3 把一次调用拆成：

- client 发送请求；
- function 接收请求；
- watchdog 转发请求；
- function starts；
- function returns；
- client 收到响应。

FET 关注中间用户代码执行区间。

第二类是 telemetry，用来描述资源使用。论文记录的指标包括：

- CPU usage；
- GPU usage；
- Network I/O；
- Block I/O；
- RAM。

这些指标每秒采样一次，主要来自 `telemd` 和 cgroup 监控。

最终作者把一次函数调用的 time-series telemetry 转换成固定长度向量。向量包含：

- 平均 CPU 使用；
- 平均 GPU 使用；
- block I/O 数据速率；
- network I/O 数据速率；
- block I/O 总量；
- network I/O 总量；
- 平均内存使用，并按设备容量归一化。

这么做的关键价值是：

**把不定长的运行时监控数据，变成调度器和机器学习模型可以处理的固定长度资源画像。**

**7. 函数聚类**

如果每个函数都独立求解一次能力匹配优化问题，函数数量一多就不可扩展。作者因此用 k-means 对函数做聚类。

聚类输入来自 workload characterization vector。由于 k-means 使用欧氏距离，作者对 I/O 总量做 min-max scaling，避免大数量级字段支配距离计算。

论文评估了 4 到 10 个 cluster，并用 silhouette score 做客观选择，同时也保留了一个人工直觉选择的聚类方案。

聚类大致能把函数分成：

- I/O heavy 函数；
- CPU oriented 函数；
- GPU oriented 函数；
- training 函数；
- inference 函数。

这个步骤的意义是：

**让“未知或新增函数”可以先归入已有 workload group，再复用该 group 的能力偏好，而不是重新完整优化。**

**8. 性能退化模型**

边缘节点资源有限，多容器共置时性能退化非常明显。论文特别强调，云 VM 通常更能承受共置，而 Raspberry Pi 这类资源受限设备可能出现极高性能退化。

作者把性能退化建模为回归问题：

- 输入：当前节点上所有运行中函数的资源画像统计；
- 输出：相对于 baseline FET 的退化因子。

退化因子为 1 表示没有退化，2 表示 FET 增加 100%。

输入不是简单资源总和，而是统计特征。对 CPU、GPU、network、block I/O 等资源，作者计算：

- mean；
- standard deviation；
- minimum；
- maximum；
- 25%、50%、75% percentile；
- running containers 数量；
- 各资源总和；
- 平均内存使用。

最终输入向量长度为 34。

模型训练方面，作者专门设计 CPU、GPU、block I/O 等干扰函数，并在不同设备上制造 co-location 场景。然后用 TPOT 自动搜索回归 pipeline。论文报告 TPOT 评估了 101000 个 pipeline，运行 340 小时，最后选择了包含 ExtraTreesRegressor、DecisionTreeRegressor、AdaBoostRegressor、PCA 等组件的 pipeline。

这个模型随后被接入 faas-sim，用于模拟同节点容器干扰导致的 FET 放大。

**9. OpenFaaSExt：多计算平台函数部署**

原始 OpenFaaS 的 FunctionDefinition 通常对应一个容器镜像。但在异构边缘环境中，一个函数可能有多个实现：

- CPU 版本；
- GPU 版本；
- TPU/TFLite 版本；
- 不同架构镜像版本。

因此作者提出 `OpenFaaSExt` 的概念，引入 `FunctionDeployment`。它可以包含多个 FunctionDefinition，并把伸缩配置上提到 FunctionDeployment 层。

这样用户可以为同一个逻辑函数提交多个计算平台版本，系统再根据 ranking 和调度策略选择具体部署哪一个版本。

不过这里有一个重要限制：

**论文实现仍然使用静态 deployment ranking。**

也就是说，平台不是动态判断“当前是否应该用 GPU 版本还是 CPU 版本”，而是按用户给定顺序先尝试某个平台，资源不足或超过限制后再使用下一个平台。

这个限制在实验结果里也造成了一些反直觉现象。例如某些训练函数在 `ga` 调度下优先使用 GPU 设备，但由于具体 GPU 节点性能并不一定优于 Intel NUC，处理请求数反而低于 vanilla 的某些放置。

**10. Capability Matching Problem**

Capability Matching Problem 是论文中比较核心的抽象。

目标是：

**给某个 workload group 找到一组节点能力偏好，使调度器能判断哪些节点更适合这个函数组。**

优化输入包括：

- 函数集合；
- 函数聚类结果；
- 函数到 group 的映射；
- 节点集合；
- 节点能力描述；
- 各函数在各节点上的 FET。

优化输出是 requirements，也就是一组属性-取值的偏好概率。例如：

```json
{
  "architecture": {
    "x86": 0.5,
    "aarch64": 0.5
  },
  "cores": {
    "MEDIUM": 1
  },
  "accelerator": {
    "None": 0.1,
    "GPU": 0.9
  },
  "gpu_model": {
    "TURING": 0.8,
    "VOLTA": 0.1,
    "MAXWELL": 0.1
  }
}
```

这表示该 workload group 明显偏好 GPU，尤其偏好 Turing GPU。

优化目标在性能和多样性之间折中：

- performance：选择节点上的平均 FET；
- device ratio：选择节点数量占总节点比例；
- variety：选择节点集合的异构程度；
- score：综合 performance 和 variety。

论文把这个问题类比为 0/1 Knapsack，并使用遗传算法求解。作者实现了两种表示：

- 1:1 device representation：每个具体设备都是优化变量；
- device type representation：按设备类型枚举，规模更小。

这个优化结果最终喂给 `CapabilityPriority`。

**11. 三个 workload-aware priority functions**

论文最直接落到调度器中的贡献，是三个 priority functions。

**1. CapabilityPriority**

作用：

**偏好那些能力属性更符合函数组 requirements 的节点。**

它的逻辑是遍历节点能力属性，如果 pod requirements 中存在该属性，就把对应取值的偏好概率累加为得分。

例如某函数组偏好 `accelerator=GPU`，那么 GPU 节点会比无加速器节点获得更高分。

这个 priority function 解决的是：

**函数需求和节点能力的匹配问题。**

**2. ContentionPriority**

作用：

**偏好当前资源利用更低、预计更不容易产生资源争用的节点。**

它使用 workload characterization 中的 CPU、GPU、network、block I/O 数据率。对于某个候选节点，它会：

- 读取新 pod 的资源画像；
- 遍历节点上已有 running pods；
- 累加已有 pod 的 CPU/GPU/network/block I/O 使用；
- 用节点网络速度和磁盘速度对 I/O 影响做粗略归一；
- 返回一个与当前资源压力相关的分数。

论文中磁盘速度估计为：

- NVME：2.5 GB/s；
- SSD：500 MB/s；
- HDD：250 MB/s；
- eMMC：150 MB/s；
- SD：50 MB/s。

这个 priority function 解决的是：

**不要把资源画像相互冲突的函数堆到同一台弱边缘设备上。**

**3. ExecutionTimePriority**

作用：

**偏好该函数 baseline FET 更短的节点。**

实现非常直接：读取 pod 在 node 上的 mean FET，并取负值作为得分，因为调度器通常选择更高分，而 FET 越低越好。

这个 priority function 解决的是：

**让调度器直接利用真实 profiling 得到的函数-节点性能差异。**

**12. 实验设备**

论文 testbed 包含 9 类设备：

- XeonGpu：x86，Xeon E-2224，8GB RAM，Turing GPU，HDD；
- XeonCpu：x86，Xeon E-2224，8GB RAM，无加速器，HDD；
- Intel NUC：x86，Intel i5，16GB RAM，无加速器，NVME；
- Raspberry Pi 3：arm32，1GB RAM，SD Card；
- Raspberry Pi 4：arm32，1GB RAM，SD Card；
- RockPi：aarch64，2GB RAM，SD Card；
- Coral DevBoard：aarch64，1GB RAM，Edge TPU，eMMC；
- Nvidia TX2：aarch64，8GB RAM，Pascal GPU，eMMC；
- Nvidia Nano：aarch64，4GB RAM，Maxwell GPU，SD Card；
- Nvidia Xavier NX：aarch64，8GB RAM，Volta GPU + tensor cores，SD Card。

这些设备覆盖了云 VM、cloudlet、SBC、边缘 GPU、Edge TPU 等典型异构节点。

**13. 实验场景**

论文基于 Urban Sensing / Smart City 场景，参考 Chicago Array of Things，并使用 Ether 生成三类合成基础设施。

**1. cloud**

云中心化场景。XeonCpu 占比高，边缘设备少，只有少量 GPU VM。该场景代表“刚开始采用 edge computing”的系统。

设备比例大致为：

- XeonCpu：69.0%；
- XeonGpu：8.2%；
- RPI3：5.4%；
- RPI4：4.6%；
- Nano：4.4%；
- 其他设备占比较低。

异构度：5.95。

**2. edge cloudlet**

边缘 cloudlet 比例高，Intel NUC 占比非常高，但 GPU/TPU 设备比例较低。它代表 edge-centric computing 中 cloudlet 较强、但加速器较稀缺的场景。

设备比例大致为：

- Intel NUC：38.8%；
- RPI3：16.0%；
- RPI4：14.0%；
- Nano：9.8%；
- XeonCpu：9.6%；
- XeonGpu：1.6%。

异构度：6.92。

**3. hybrid**

混合场景，更均衡地包含 SBC、AI 加速设备、cloudlet 和云 VM。

设备比例大致为：

- RPI3：21.4%；
- RPI4：18.6%；
- Intel NUC：14.8%；
- RockPi：10.6%；
- Nano：8.4%；
- Coral：8.0%；
- XeonGpu：6.0%。

异构度：7.38。

**14. 实验函数**

论文使用的函数分为 AI pipeline 函数和干扰/画像函数。

AI pipeline 函数包括：

- `resnet50-preprocessing`：图片缩放和预处理，CPU；
- `resnet50-training`：ResNet50 fine-tuning，CPU/GPU；
- `resnet50-inference`：目标分类，CPU/GPU；
- `mobilenet-inference`：轻量目标分类，CPU/TPU；
- `speech-inference`：DeepSpeech 语音转文字，CPU/GPU。

辅助 profiling / degradation 函数包括：

- `tf-gpu`：GPU 矩阵乘；
- `python-pi`：CPU 圆周率计算；
- `fio`：随机块 I/O 读写。

这些函数与论文目标高度一致：既有完整 AI pipeline，也有专门制造 CPU/GPU/I/O 干扰的基准函数。

**15. workload pattern 和 autoscaling 设置**

论文模拟两类请求模式：

- constant workload；
- sine workload。

训练和预处理请求频率较低，因为这些任务真实场景中不会像推理一样高频调用；推理请求频率较高，模拟 AR、认知辅助、视频分析等场景。

每个实验运行 5 次，每次模拟 33 分钟。

自动伸缩方面，作者没有提出新的复杂 autoscaler，而是实现了一个基于队列长度的策略：

- 周期性检查函数队列长度；
- 目标队列长度为 75；
- 每 50 秒检查一次；
- 同时设置每个函数的最小和最大副本数。

作者明确说明，论文重点不是 autoscaling，而是调度 placement。因此 autoscaler 主要用于产生合理的动态副本行为。

**16. 实验结果：baseline profiling**

baseline profiling 显示，同一函数在不同设备上的 FET 差异很大。

主要观察：

- Raspberry Pi 3 在很多函数上最慢，因此综合性能排名最低。
- GPU workload 在不同 GPU 设备之间差异更明显。
- Fio 的差异主要来自磁盘类型，SD Card 和 NVME 的差距非常大。
- ResNet50 training 使用 GPU 后 CPU 使用显著下降，说明硬件加速改变了资源瓶颈。
- 小音频输入使 speech inference 的网络资源较低。
- Jetson 设备上 VRAM 和 RAM 共享，导致某些 GPU workload 的 RAM 指标较高。

这部分证明了论文基本前提：

**异构边缘集群中，函数执行性能不能靠 CPU/内存容量简单推断，必须通过 workload-aware profiling 学习。**

**17. 实验结果：性能退化**

性能退化实验显示，不同设备对 co-location 的敏感程度差异巨大。

论文中特别提到：

- Coral DevBoard 难以稳定运行多个服务，因此实验中用 RPI4 模型替代；
- 低性能设备如 RPI3 在某些实验中退化可达到非常高的水平；
- 云 VM 更稳定，但也并非完全没有资源争用；
- TPOT 训练出的模型在各设备上取得可接受 RMSE/MAE。

这说明：

**在边缘 serverless 中，调度器不能只问“节点还有没有资源”，还要问“把这个函数和已有函数放一起会不会让执行时间恶化”。**

**18. 实验结果：workload clustering**

作者比较了不同聚类数量下的 silhouette score，结果显示 5 个 cluster 的平均 silhouette score 最高，为 0.386039。

但作者也保留了 7 个 cluster 的主观方案，因为它能把 Fio 这类 I/O heavy 函数单独分出来，更符合领域直觉。

这个结果说明两点：

- 资源画像确实能把函数粗略分成 CPU/GPU/I/O/training/inference 等行为类别；
- 但当前函数数量偏少，聚类质量还有提升空间。

作者在讨论中也承认，后续应增加更多同类函数来验证泛化能力。

**19. 实验结果：Capability Matching 优化**

Capability Matching 的优化结果说明，不同 workload group 偏好的节点能力不同。

例如：

- 某些 inference workload 偏好轻量加速器或特定架构；
- training workload 往往偏好 GPU；
- I/O heavy workload 更受磁盘类型影响；
- 性能权重和多样性权重会显著改变 requirements。

作者比较了遗传算法和枚举式 device type representation。最后实际调度实验中选择更适合的设置，用于 `CapabilityPriority`。

这里最重要的理解是：

**论文不是直接说“所有 AI 函数都应该去 GPU”，而是通过 profiling 和优化让不同函数组得到不同能力偏好。**

**20. 实验结果：调度性能**

论文最终比较四类调度 pipeline：

- `vanilla`：默认调度；
- `skippy`：Rausch 等人的数据/位置感知优先级；
- `ga`：本文提出的 workload-aware 优先级；
- `all`：组合 Skippy 和本文所有 custom priorities。

核心结果是：

**相对于 vanilla，ga 在各场景中平均 FET 降低 33% 到 68%，性能退化降低 25% 到 57%。**

论文表 6.7 给出的详细结果如下：

| Scenario | Workload | FET 降低 | 性能退化降低 |
|---|---:|---:|---:|
| cloud | constant | 56% | 33% |
| cloud | sine | 44% | 26% |
| edge cloudlet | constant | 68% | 57% |
| edge cloudlet | sine | 59% | 52% |
| hybrid | constant | 47% | 46% |
| hybrid | sine | 33% | 45% |

这说明 workload-aware 调度在 edge/cloudlet 场景里收益尤其明显。原因是这些场景节点更异构，默认调度更容易把函数放到不合适的节点上。

**21. 一个重要反例：静态 deployment ranking 的副作用**

论文没有只报平均提升，也分析了不理想案例。

在 edge cloudlet + sine workload 中，`ga` 对 `resnet50-preprocessing` 的放置更好，主要把它放到 Intel NUC，避免了 vanilla 把它分散到 RockPi/RPI4 等不适合节点上，因此处理更多 preprocessing 请求。

但对 `resnet50-training`，`ga` 反而处理请求数更少。原因是：

- deployment ranking 规定 training 先用 GPU 版本；
- ga 更积极使用 GPU 节点；
- vanilla 在 GPU 节点被占用后更多使用 Intel NUC CPU 版本；
- 某些情况下 Intel NUC 对该 workload 的实际表现优于部分边缘 GPU 节点。

这个现象揭示了一个关键局限：

**如果函数计算平台选择是静态 ranking，调度器再聪明也只能在既定版本选择下优化；真正理想的系统应该动态决定当前使用 CPU/GPU/TPU 哪个版本。**

这对你的论文很有价值，因为它说明“缓存/调度/伸缩/版本选择”不能完全割裂。

**22. 这篇论文的贡献**

我认为这篇论文的贡献主要有六点。

第一，**把 serverless edge 调度问题从数据本地性扩展到 workload-awareness。**

它不是否定 Skippy 的数据/网络感知，而是补上另一类重要因素：函数在不同硬件上的性能差异和资源干扰。

第二，**提出系统化异构节点建模方法。**

用架构、加速器、磁盘、位置、连接、CPU/GPU 型号、资源 bin 等属性描述节点，并用 entropy score 量化集群异构度。

第三，**提出黑盒 workload characterization 方法。**

不依赖用户代码 instrumentation，只通过 FET trace 和 telemetry，把函数行为转成固定长度资源画像。

第四，**把工作负载聚类用于调度可扩展性。**

通过 k-means 把函数分组，避免为每个函数单独求解能力匹配问题。

第五，**提出性能退化预测模型。**

通过干扰实验和回归模型，把 co-located containers 造成的性能退化接入 faas-sim。

第六，**实现三类 workload-aware priority functions。**

包括执行时间优先、资源争用规避和能力匹配，并在仿真中显示显著降低 FET 和性能退化。

**23. 局限性**

这篇论文的局限也比较明显。

第一，**profiling 成本较高。**

作者需要在每类设备上运行每个函数，采集 baseline FET 和 telemetry。随着函数和设备类型增加，数据采集成本会上升。

第二，**对未知函数泛化能力有限。**

虽然作者用聚类支持新函数归类，但讨论中承认并未充分测试未知函数。

第三，**性能退化模型没有区分目标服务。**

模型主要基于资源使用预测退化，但同样资源画像下，不同函数对干扰的敏感性可能不同。作者建议未来把具体 service 或 workload cluster 作为输入。

第四，**函数输入数据变化可能改变资源画像。**

论文每个函数主要使用一种输入。更大图片、更长音频、不同 batch size 都可能改变 CPU/GPU/I/O/网络行为。

第五，**OpenFaaSExt 仍使用静态计算平台 ranking。**

这会导致某些场景下 GPU 优先并不一定最优。动态平台选择是重要未来方向。

第六，**只模拟了一类 OpenFaaS watchdog。**

论文主要使用 HTTP watchdog，而 Forking / process-per-request 等模式可能更适合长任务。

第七，**priority weights 没有深入优化。**

论文未来工作明确提出，尤其是把 Skippy 的数据/位置优先级和本文 workload-aware 优先级组合后，权重仍值得进一步优化。

**24. 和当前 faas-sim 源码的对应关系**

你当前项目中的许多模块都能对应到这篇论文。

`ext/raith21/` 基本就是这篇论文实验扩展层：

- `ext/raith21/functionsim.py`：函数执行模拟器，体现 FET、资源使用和干扰建模；
- `ext/raith21/oracles.py`：Raith21 专用 FET Oracle 和 Resource Oracle；
- `ext/raith21/resources.py`：不同函数在不同设备上的资源画像；
- `ext/raith21/fet.py`：函数执行时间画像；
- `ext/raith21/device.py`、`etherdevices.py`：异构设备建模；
- `ext/raith21/generator.py`：异构设备生成；
- `ext/raith21/predicates.py`：内存、架构、加速器、GPU/TPU 独占等硬约束；
- `ext/raith21/priorities.py`：`CapabilityMatchingPriority`、`ExecutionTimePriority`、`ContentionPriority`。

核心仿真链路仍然走：

- `sim/faassim.py`：装配 Environment、FaaS 系统、调度器和 Benchmark；
- `sim/faas/system.py`：部署副本、进入 scheduler queue、启动生命周期；
- `sim/skippy.py`：把 FunctionReplica 转成 Skippy Pod；
- `skippy/core/scheduler.py`：执行谓词过滤和优先级打分；
- `sim/resource.py`：资源状态和资源监控；
- `sim/core.py`：NodeState 中的 performance degradation 支持；
- `sim/benchmark.py`：加载 degradation model 并注入环境。

因此，读这篇论文时可以直接把它理解为：

**`ext/raith21` 这一整套扩展为什么存在、它的实验假设是什么、调度优先级为什么这样设计。**

**25. 对你大论文可能有用的角度**

如果你的大论文研究边缘 serverless、缓存、冷启动、调度或 autoscaling，这篇论文至少有五个可借鉴点。

第一，**工作负载画像可以作为调度依据。**

不要只用函数名称或平均耗时，可以引入 CPU/GPU/I/O/网络/RAM 资源向量，刻画函数行为。

第二，**异构节点不能只抽象为 CPU/内存。**

边缘环境中磁盘、架构、加速器、位置、连接方式都会影响调度质量。

第三，**资源争用是边缘 FaaS 的重要问题。**

如果你的研究涉及缓存保活或 warm replica 保留，就更需要考虑保留实例对节点资源和后续请求的干扰。

第四，**仿真可以承载复杂策略评估。**

真实部署 1000 个异构节点成本高，faas-sim 的价值就在于把 profiling 数据、调度策略和网络/资源模型结合起来。

第五，**策略耦合很关键。**

论文中的静态 deployment ranking 反例说明：调度、函数版本选择、缓存、扩缩容并不是独立模块。一个模块的固定假设可能限制另一个模块的优化效果。

**26. 和缓存/冷启动研究的衔接**

这篇论文没有直接把重点放在 cold start cache 上，但它对缓存类研究有启发。

如果你的系统需要做缓存感知调度或实例保留策略，可以把本文思想迁移过来：

- `ExecutionTimePriority` 可以扩展为 warm execution time / cold execution time 差异；
- `ContentionPriority` 可以用于判断保留 warm replica 是否会挤压节点；
- `CapabilityPriority` 可以用于选择更适合长期缓存某类函数的节点；
- workload clustering 可以把相似函数归组，共享缓存策略参数；
- performance degradation model 可以估计“缓存命中收益”与“资源占用代价”之间的权衡。

换句话说：

**缓存策略不应该只问“这个函数未来会不会再来”，还应该问“把它留在哪个节点上，是否会影响其他函数，是否真的适合该节点能力”。**

**27. 用一句通俗比喻总结**

如果默认 Kubernetes 调度器像是在看“哪间教室还有座位”，那么这篇论文提出的 workload-aware 调度更像是在看“这门课需要实验室、投影仪还是钢琴；这个教室现在吵不吵；这位老师在哪间教室讲得最快”。它把容器调度从简单容量匹配，推进到结合函数画像、硬件能力和资源干扰的综合决策问题。

这篇论文的核心价值在于：

**它证明了在异构边缘 serverless 环境中，只有理解函数工作负载本身，调度器才能真正做出高质量放置决策。**
