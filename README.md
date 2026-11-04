# netverify

**给它一句话描述，它生成网络验收测试用例；由代码判断这些用例是否可信；可信的用例在真实网络命名空间里执行，执行失败时自动抓包并指出第几个包不对。**

这个项目是给宽带接入设备（CPE / ONU / 光猫）做验收测试的小工具。它不是要替代测试工程师，而是把"写用例"这件重复劳动交出去，同时用代码守住底线——**AI 只出草稿，能不能用由代码判定**。

## 为什么需要它

宽带设备出货前的验收测试，大量工作是重复的：写一条 DHCP 用例、写一条 PPPoE 拨号用例、写一条 VLAN 划分用例。每条都要：

1. 想清楚该发什么包、期待什么响应
2. 写成能跑的脚本
3. 跑失败了去抓包，人工翻几十个包找哪个字段不对

第 1、2 步是重复劳动，第 3 步最费时间。这个工具把 1、2 交给 agent，把 3 交给抓包分析，把"能不能信"交给代码。

## 它是怎么工作的

```
一句话意图
   ↓
agent 生成用例草稿（YAML）
   ↓
代码校验：4 类不变量（不通过就地打回，agent 重写）
   ↓
在 network namespace 里执行（真实发包）
   ↓
失败 → 自动抓包 → 提取字段对比 → 指出第几个包、哪个字段不对
```

**关键设计：agent 不接触执行层。** 它只产出 YAML 草稿，代码先校验草稿，校验通过才执行。这样即使模型胡说，也不会跑出破坏性的测试。

## 快速开始

```bash
git clone https://github.com/<you>/netverify.git
cd netverify
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

运行需要 Linux（用到 `ip netns`）与 `tshark`：

```bash
sudo apt install tshark
```

> 这是 v0.1，还在开发中。下面的命令会随进度逐步可用。

## 用例长什么样

```yaml
id: dhcp-001
title: DHCP 四步握手完整性
intent: 客户端应能在 30 秒内通过 DHCP 获得地址
steps:
  - action: send
    proto: dhcp
    type: DISCOVER
  - action: expect
    proto: dhcp
    type: OFFER
    timeout_s: 5
assertions:
  - field: bootp.option.dhcp
    equals: 2
  - field: bootp.yiaddr
    matches: "^192\\.168\\."
```

## 开发状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| v0.1 | 目录骨架 + 用例 schema | 进行中 |
| v0.2 | agent 生成用例 + 代码校验 | 计划中 |
| v0.3 | netns 执行 + 断言引擎 | 计划中 |
| v0.4 | 失败自动抓包 + 根因定位 | 计划中 |

## 许可

MIT
