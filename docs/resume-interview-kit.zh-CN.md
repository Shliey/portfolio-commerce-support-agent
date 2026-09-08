# 简历与面试材料

## 当前阶段：源码研究版

**Anthropic Commerce Agents 架构研究与安全机制复现｜Python、Claude API、TypeScript**

- 自底向上分析双角色、多运行时 commerce agent 架构，梳理 Backend 端口、统一 Tool Executor、
  结构化事件与服务端生成 UI 的端到端数据流。
- 重点复现不可信内容 fencing、操作 provenance、配置化工具收缩与人工审批边界，形成安全机制、
  适用范围和失效条件对照文档。
- 对 Messages API、Agent SDK、Managed Agents 三条运行路径进行合同层比较，明确共享业务规则与
  平台 orchestration 的职责边界。

这一版本必须使用“分析、复现、研究”，不能使用“主导开发上游系统”。

## 核心闭环通过全部验证后的工程版

**基于 LangGraph 的可恢复电商售后多 Agent 系统｜Python、FastAPI、SQLite、TypeScript**

- 设计 triage/order/return/policy 四角色 Agent，以显式工具白名单和结构化 handoff 隔离能力，
  通过 SSE 输出带关联 ID 与单调序号的执行事件。
- 将订单所有权、7 天退货资格及人工审批从 LLM 决策下沉至确定性代码，实现
  “草稿—暂停—批准—写入”高风险操作闭环。
- 分离 `user_id`、`thread_id`、`request_id`，在 SQLite 使用 `UNIQUE(request_id)` 保证业务幂等，
  通过 16 线程竞争、Windows 4 进程/8 次竞争、参数冲突和 crash-after-write 恢复验证工单只写一次。
- 构建 FastAPI 与严格模式 TypeScript 演示端，展示角色切换、工具执行、政策引用和审批状态；
  58 个后端测试、3 个前端单元/组件测试与 Playwright 浏览器闭环均通过，默认 CI 不产生模型调用费用。
- 建立 30 条版本化 Policy RAG 集合；离线 Hash stub 与本地 BGE semantic embedding 的 Hit@1、
  Hit@3、MRR、引用合法率和拒答召回均为 1.0，并显式标记未调用生成式 LLM。

以上数字必须与 `artifacts/verification.json` 同步；真实 LLM 延迟/token、Docker 镜像运行和云部署
尚无证据，不写入简历。

## 60 秒介绍

我做的是一个可恢复的电商售后多 Agent 系统。它参考 Anthropic Commerce Agents 的安全思路，
但核心闭环是我在独立仓库里用 LangGraph 和 FastAPI 实现的。系统有 triage、订单、退货和政策四个
角色；模型或路由层只负责理解意图，订单所有权、退货资格、审批和写库全部由确定性代码控制。
我重点解决了两个工程问题：第一，`user_id`、`thread_id` 和 `request_id` 各司其职，避免把会话恢复
误当成业务幂等；第二，批准操作即使断线重试，也依靠数据库唯一约束只生成一张工单。前端消费
结构化 SSE 事件，可以展示 handoff、工具状态和审批卡片。默认测试不用真实模型，真实模型评测会
单独标记，保证结果可复现也不夸大。

## 3 分钟架构讲解提纲

1. 从业务风险开始：售后 Agent 会读取私有订单并可能创建工单，不能只依赖 prompt。
2. API 从 token 得到可信 `user_id`；客户端只能提供 `thread_id/request_id` 和业务输入。
3. triage 将请求路由到显式角色，角色只能使用 allowlist 中的工具。
4. repository 在 SQL 查询中绑定 `user_id`，missing 与 forbidden 对外统一为 not found。
5. return 节点读取权威订单，由纯函数判定 delivered、时间窗和商品属性。
6. 合格请求只写 pending approval；人批准后才进入 ticket transaction。
7. `UNIQUE(request_id)` 抵抗并发、重试和“写成功但 checkpoint 未更新”的崩溃窗口。
8. SSE 用 `run_id + seq` 给前端可观测性；离线和真实模型评测严格分开。

## 高频面试问答

### 为什么需要多 Agent，单 Agent 加很多工具不行吗？

这里的“多 Agent”主要是职责与工具面的隔离，不是启动多个模型互相聊天。角色可以缩小 prompt 和
工具选择空间，并让权限审计更直接。规模很小时单 Agent 完全可行，所以本项目保留确定性 triage，
不为多 Agent 而多 Agent。

### 为什么 checkpoint 不能保证 exactly-once？

checkpoint 保存的是工作流状态。数据库写入成功而 checkpoint 更新前崩溃时，恢复会再次进入写节点。
因此业务表仍需 `UNIQUE(request_id)` 和“已存在则返回原结果”的幂等语义。

### 为什么不用 LLM 判断退货资格？

资格规则来自权威订单状态、时间和商品属性，可被精确定义和单元测试。让 LLM 决定会引入非确定性、
提示注入风险和不可解释的不一致。LLM 可以抽取退货原因并解释结果，但不能决定规则真值。

### Fencing、provenance、authorization 有什么区别？

Fencing 把外部文本限制为数据，缓解 prompt injection；provenance 证明 Agent 最近从可信读取路径见过
某对象；authorization 判断当前主体是否有权操作对象。三者解决不同问题，不能互相替代。

### 为什么 missing 和 forbidden 返回同一错误？

若分别返回 404 和 403，攻击者可枚举订单 ID 并判断订单是否存在。统一外部错误减少对象存在性泄漏，
内部日志仍可保留真实原因供审计。

### SQLite 的上限是什么？

它适合单机作品集和低并发演示。多实例部署应把业务库迁到 PostgreSQL，并使用生产级 LangGraph
checkpointer；接口边界不变，但需要重新验证事务隔离、连接池和并发重试。

### 现在的 RAG 验证到了什么边界？

离线 CI 用明确标注的 Hash stub 验证引用与拒答合同；本机另用 FastEmbed/BGE 在同一 30 条版本化
样本上验证了真实语义检索。两者都没有调用生成式 LLM，所以可以陈述本地 embedding 检索指标，
但不能把它写成真实 LLM 端到端效果。

### 如何证明不是套壳？

展示独立 Git 历史、数据库 schema、幂等冲突测试、断线重试测试、事件协议和设计取舍；同时明确指出
参考了上游哪些思想、没有复制哪些能力。能解释失败窗口和测试证据比功能截图更能证明工程贡献。

## 2–4 周补强顺序

- 第 1 周：核心 schema、认证、所有权、资格规则和 API，建立全绿 CI。
- 第 2 周：LangGraph interrupt/checkpoint 持久化、并发和 crash-after-write 故障注入。
- 第 3 周：真实 semantic embedding、30+ 版本化 RAG eval、前端流式解析与 Playwright E2E。
- 第 4 周：受控真实模型评测、部署、演示录像、性能报告和简历数字定稿。
