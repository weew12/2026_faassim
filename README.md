# faas-sim:基于 trace 驱动的 Function-as-a-Service 仿真器

官方地址： <https://github.com/edgerun/faas-sim>
github commit: 6bebc51247d484a3dc65e3930a6cd0de3e24afd5

## 简介

faas-sim 是一个功能强大的、基于 trace 驱动的仿真框架,用于模拟基于容器的 Function-as-a-Service(FaaS)平台。
它可以用于开发和评估此类系统的运维策略性能,例如**调度(Scheduling)**、**自动扩缩容(Autoscaling)**、**负载均衡(Load Balancing)** 等。
faas-sim 由 [维也纳技术大学分布式系统组](https://dsg.tuwien.ac.at) 开发,是围绕无服务器边缘计算系统开展更广泛研究工作的一部分。

## 整体架构

faas-sim 基于 [SimPy](https://simpy.readthedocs.io) 离散事件仿真框架构建。
它使用 [Ether](https://github.com/edgerun/ether) 作为网络仿真层,用于创建集群配置和网络拓扑。
默认情况下,它使用 [Skippy](https://github.com/edgerun/skippy-core) 调度系统进行资源调度,
但用户也可以自行接入其他调度器、自动扩缩容器和负载均衡器。
faas-sim 是 trace 驱动的,依赖于来自工作负载和设备的 profiling 数据来模拟函数执行。
它预装了多种常见计算设备和代表性集群工作负载的 trace。
下图给出了整体概览:

<img alt="architecture-overview" width="700px" src="https://raw.github.com/edgerun/faas-sim/master/doc/figures/architecture-overview.png">

## 运行示例(Examples)

你可以通过先创建虚拟环境并安装所需依赖,来运行我们在 <https://github.com/edgerun/faas-sim/tree/master/examples> 中提供的示例。

```bash
make venv
source .venv/bin/activate
python -m examples.<example>.main
```

其中 `<example>` 对应具体的示例包。
更多细节请参阅示例 [README](https://github.com/edgerun/faas-sim/tree/master/examples/README.md)。

## 运行 Notebooks

Notebook 文件位于 `notebooks` 目录。
你需要以 editable 模式安装 `faas-sim` 才能运行这些 notebook。
在 `notebooks` 内可以直接从 `sim` 包中导入所需模块。

安装项目(假设你已通过 `make venv` 创建并激活了虚拟环境):

```bash
pip install -e .
jupyter notebook
```

## 文档

完整文档请访问:<https://edgerun.github.io/faas-sim/>

## 维护者

* [Thomas Rausch](https://github.com/thrau)
* [Philipp Raith](https://github.com/phip123)

## 开发说明

仿真器在 `/feature/adapt-to-galileo-faas` 分支上经历了一次较大规模的重构,
目标是与其他 galileo 项目保持兼容。
**只有这个分支处于活跃开发状态。**

## 相关论文

1. Raith, P., Rausch, T., Furutanpey, A., & Dustdar, S. (2023).
   **faas‐sim: A trace‐driven simulation framework for serverless edge computing platforms.**
   发表于 *Software: Practice and Experience*。Wiley Online Library。
   [[论文 PDF](https://onlinelibrary.wiley.com/doi/pdf/10.1002/spe.3277)]
2. Raith, P. (2021)
   Container Scheduling on Heterogeneous Clusters using Machine Learning-based Workload Characterization.
   *硕士学位论文*。维也纳技术大学。
   [[论文](https://repositum.tuwien.at/handle/20.500.12708/16871)]
3. Rausch, T., Lachner, C., Frangoudis, P. A., Raith, P., & Dustdar, S. (2020).
   Synthesizing Plausible Infrastructure Configurations for Evaluating Edge Computing Systems.
   发表于 *第 3 届 USENIX 边缘计算热门话题研讨会(HotEdge 20)*。USENIX Association。
   [[论文](https://www.usenix.org/conference/hotedge20/presentation/rausch)]
4. Rausch, T., Rashed, A., & Dustdar, S. (2020)
   Optimized container scheduling for data-intensive serverless edge computing.
   发表于 *Future Generation Computer Systems*。
   [[论文](https://www.sciencedirect.com/science/article/pii/S0167739X2030399X)]
5. Rashed, A. (2020)
   Optimized Container Scheduling for Serverless Edge Computing.
   *硕士学位论文*。维也纳技术大学。
   [[论文](http://repositum.tuwien.ac.at/obvutwhs/content/titleinfo/4671607)]
