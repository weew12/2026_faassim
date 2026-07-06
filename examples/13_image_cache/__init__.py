"""
image_cache 样例包。

本包用于演示 faas-sim 中节点级镜像缓存机制，重点覆盖：
- docker.pull() 如何检查 node_state.docker_images；
- 同一节点重复部署相同镜像时如何命中缓存；
- 不同节点首次部署相同镜像时为什么仍需拉取；
- 镜像缓存命中与 flow.csv 中 docker_pull 网络流的关系；
- same_node_cache_reuse 与 different_node_cold_pull 两组场景对比。

运行入口：
    python -u examples/13_image_cache/main.py
"""
