"""
image_pull_network 样例包。

本包用于演示 faas-sim 中镜像拉取与网络传输之间的关系，重点覆盖：
- docker.pull() 如何触发网络 Flow；
- 首次部署镜像时的冷拉取开销；
- 同一节点已有镜像时的缓存复用；
- 不同镜像大小对拉取耗时的影响；
- flow、image_pull_probe、replica_deployment 等指标导出。

运行入口：
    python -u examples/05_image_pull_network/main.py
"""
