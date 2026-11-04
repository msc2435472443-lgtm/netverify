# 为什么 CI 里不跑网络命名空间

这是这个仓库最容易被问到的一个设计决定，写清楚比藏着好。

## 结论

CI 只跑「不需要构造网络环境」的部分：用例 schema 校验、断言比较逻辑、报告渲染。
真实发包（`ip netns` + veth + tcpdump）在本地 Kali 上跑，结果录屏。

## 三个具体原因

1. **权限**：GitHub Actions 的 `ubuntu-latest`（未加 sudo 的 runner）建 netns 需要
   `CAP_NET_ADMIN`。虽然 `sudo ip netns add` 通常能用，但 sudo 在这些镜像里的可用性
   随 runner 版本变化，属于「今天能跑明天挂」的依赖。

2. **镜像限制**：部分镜像（以及容器化 runner）禁用了 namespace 创建。表现是
   `RTNETLINK answers: Operation not permitted`——这个错误的根因不在我们的代码里，
   但会让 CI 红，逼人加 `continue-on-error`，等于把 CI 变成装饰品。

3. **抓包**：`tshark` 需要 `CAP_NET_RAW`。在 CI 里装它 + 提权 + 抓包，成本高于收益，
   而且抓到的包要不要入库又是一个问题（体积 + 隐私）。

## 这不是偷懒

分工是清楚的：

| 在哪跑 | 跑什么 | 证明什么 |
|---|---|---|
| CI（每次 push） | schema 校验、断言逻辑、报告渲染 | 逻辑没写错 |
| 本地（交付前） | netns 仿真 + 真实抓包 + 端到端 | 真的能跑 |

面试时如果被问「你的 CI 覆盖率多少」，诚实回答是：

> 单元层面 100% 在 CI 里跑；端到端不进 CI，因为需要 `CAP_NET_ADMIN`，
> 在托管 runner 上不稳定。所以我用「本地一条命令 + 录屏」来证明端到端可用。
> 如果这个项目是给公司用的，我会改成自建 runner 或 docker-in-docker 里跑特权容器。

## 如果以后要进 CI

真有需要时的两条路：

- 自建 runner（`--privileged` 容器里跑），成本是维护机器
- `unshare --net` 加用户命名空间（不需要 root），但 veth 跨命名空间仍要权限

两条都比「在托管 runner 上加 sudo」可靠。
