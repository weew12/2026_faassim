# 11 · 对象存储 store

对应源码：`simpy/resources/store.py`

## 1. 文件定位

`Store` 系列建模离散对象队列。

- `Store`：FIFO 队列。
- `PriorityStore`：按优先级弹出。
- `FilterStore`：按过滤函数取对象。

## 2. Store

`Store.put(item)` 在容量未满时把对象追加到队尾。

`Store.get()` 在队列非空时取出队首对象。

容量满或队列空时，请求事件会排队等待。

## 3. PriorityStore

`PriorityStore` 用堆维护 `items`，`get()` 返回优先级最小的对象。

建议用 `PriorityItem(priority, item)` 包装业务对象：

```python
yield store.put(PriorityItem(1, 'urgent'))
yield store.put(PriorityItem(5, 'normal'))
item = yield store.get()  # urgent
```

`PriorityItem.__lt__` 只比较 priority，业务对象本身不参与排序。

## 4. FilterStore

`FilterStore.get(filter)` 允许每个 get 请求带一个过滤函数。它会顺序扫描队列，取出第一个满足条件的对象。

```python
req = store.get(lambda item: item.kind == 'gpu')
item = yield req
```

每个等待的 get 请求可以有不同 filter，因此源码没有建立索引，而是逐次扫描。

## 5. 触发特点

`FilterStore._do_get()` 总是返回 `True`，让基类继续检查后续 get 请求。原因是：一个 get 取走某个对象后，其他 get 的 filter 可能还能匹配队列里的其他对象。

普通 `Store._do_get()` 返回 `None`，因为 FIFO 队列空或刚取出队首后，继续检查通常没有额外收益。

## 6. faas-sim 可用场景

- 请求队列
- 调度任务队列
- 按函数名或节点类型过滤的任务池
- 优先级消息队列
- 负载均衡器内部待派发队列

