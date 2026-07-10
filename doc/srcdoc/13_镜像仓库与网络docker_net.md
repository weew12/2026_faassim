# 镜像仓库与网络：`sim/docker.py`、`sim/net.py`

## 1. 模块定位

容器启动前可能需要拉取镜像。该过程连接镜像元数据、节点缓存、网络路由和仿真时间：

```text
镜像字符串
  -> ContainerRegistry 查找匹配架构条目
  -> 检查 NodeState 镜像缓存
  -> Topology 计算 registry 到节点的路由
  -> SafeFlow 传输镜像字节
  -> 仿真时间推进并记录 flow 指标
```

## 2. `ImageProperties`

这是一个 `NamedTuple`，字段为：

- `name`：仓库/镜像名；
- `size`：镜像字节数；
- `tag`：默认 `latest`；
- `arch`：可选 CPU 架构。

同名同 tag 可以登记多个架构版本。

## 3. `ContainerRegistry`

内部索引结构：

```text
images[repository][tag] -> List[ImageProperties]
```

### `put()` / `put_all()`

登记单个或批量镜像。当前实现允许重复条目，benchmark 应避免无意重复注册。

### `find(image, arch=None)`

先拆分 repository/tag，再按可选架构过滤。传入架构时，同时接受：

- `image.arch == node.arch`；
- `image.arch is None` 的通用镜像。

返回列表而不是单值，因为同一名称和 tag 可能存在多个候选。

## 4. `split_image_name()`

不带冒号的镜像默认 tag 为 `latest`：

```text
python-fn       -> (python-fn, latest)
python-fn:v2    -> (python-fn, v2)
```

当前实现按第一个冒号拆分，不完整支持带端口的 registry 地址，如 `localhost:5000/repo:tag`。若实验使用此类名称，需要改用更稳健的镜像引用解析方法。

## 5. `pull()`

镜像拉取是生成器过程。

### 5.1 架构匹配

按目标节点 `node.arch` 查询镜像。没有候选时抛出 `ValueError`，表示镜像不存在或架构不兼容。

### 5.2 节点缓存

通过 `env.get_node_state(node.name)` 取得节点状态：

- 已有相同 `ImageProperties` 时直接返回，不产生传输；
- 未命中时把镜像加入 `docker_images`，然后模拟拉取。

当前实现先写入缓存再启动网络流。如果流失败，缓存仍可能保留镜像；分析失败路径时应注意这一顺序。

### 5.3 空镜像

`size <= 0` 时不创建网络流，适用于忽略传输成本的简化配置。

### 5.4 网络传输

通过 topology 取得 `DockerRegistry -> node` 路由，创建 `SafeFlow`，等待 `flow.start()` 完成，最后记录 `docker_pull` 流指标。

## 6. `SafeFlow`

`SafeFlow(*args, bw_threshold=0.1, **kwargs)` 是 Ether Flow 的保护包装。它在可用带宽过低时抛出 `LowBandwidthException`，避免产生极大或无意义的传输时间。

`bw_threshold` 的单位必须与 Ether 链路带宽单位一致。

## 7. `LowBandwidthException`

该异常表达路径带宽低于安全阈值。当前继承 `BaseException`，常见的 `except Exception` 不会捕获它。需要容错的调用方必须显式了解该继承关系。

## 8. 网络时间与带宽

理想情况下传输时间近似：

```text
duration = bytes / effective_bandwidth
```

实际 Ether Flow 还会考虑同链路并发流量和带宽共享。不要用静态除法重复增加一次 timeout，否则会重复计算传输耗时。

## 9. 镜像缓存实验设计

比较冷启动时应明确：

- 初始节点缓存是否为空；
- 多架构镜像大小是否一致；
- 第一次拉取失败是否应写缓存；
- 缓存是否有容量和淘汰规则；
- 不同实验是否重用了同一个 Environment/NodeState。

当前缓存是集合，主要表达“存在/不存在”，没有容量和 LRU 淘汰语义。

## 10. 常见误区

- 镜像大小单位与链路带宽单位不匹配；
- 节点架构标签与 registry 的 `arch` 拼写不一致；
- 把镜像 tag 漏掉后意外使用 `latest`；
- 使用含端口 registry 地址但仍按第一个冒号拆分；
- 镜像拉取失败后节点缓存状态不一致；
- 将网络流耗时与额外 timeout 重复累计；
- 以为缓存集合会自动执行容量淘汰。

## 11. 阅读检查点

- 镜像兼容性由哪些字段决定？
- 节点缓存命中为什么不会推进仿真时间？
- registry 元数据和 registry 网络节点分别在哪里？
- `SafeFlow` 保护了哪类异常输入？
