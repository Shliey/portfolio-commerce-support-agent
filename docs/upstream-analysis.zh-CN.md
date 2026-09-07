# Anthropic Commerce Agents：自底向上的源码剖析

## 1. 先判断它究竟是什么

上游不是一个单体聊天机器人，而是一个 commerce agent 参考架构：shopping agent 服务消费者，
merchant agent 服务运营人员；同一套核心契约分别运行在 Messages API、Claude Agent SDK 和
Managed Agents 上；retail、travel、telecom、entertainment 四个 vertical 负责证明核心层可以
被行业化扩展。

它最有价值的不是“接了多少工具”，而是将概率性的语言模型限制在确定性的业务护栏里面。
官方仓库的 Git 远端、版权头和提交记录都表明源码归 Anthropic。个人项目只能写“研究、复现、
借鉴并独立实现”，不能写成自己从零完成了上游系统。

## 2. 第一层：类型和协议是系统地基

`commerce_common.streaming.AgentEvent` 把模型执行过程变成宿主可消费的事件；
`ToolOutcome` 同时携带给模型看的结果、给 UI 的事件以及 blocked/refused 状态。shopping 和
merchant 的 `types.py` 再定义会话上下文与会话状态。由此形成两个重要边界：

1. 模型消息不是 UI 协议；UI 消费结构化事件。
2. 请求上下文不是长期状态；状态由宿主按 session 保存。

代价是所有 runtime 都必须严格保持事件语义一致，否则“共享核心”只停留在代码复用层面。

## 3. 第二层：Backend 接口隔离真实业务系统

`StorefrontBackend` 和 `MerchantBackend` 是面向部署方的端口。核心 executor 只依赖这些接口，
不直接依赖 Shopify、ERP、支付或仓库 SDK。这样测试可以注入 fake backend，vertical 可以注入
内存/JSON demo backend，生产部署可以实现数据库或服务适配器。

这是典型的依赖倒置：Agent core 定义自己需要的能力，外部系统适配这个契约。其局限也很清楚：
接口隔离不会自动提供鉴权、事务和审计，这些仍由部署方负责。

## 4. 第三层：安全不是一句 system prompt

### 4.1 Fencing

`commerce_common/fencing.py` 将目录、商品描述、订单文本等第三方内容视作数据。它进行 NFKC
归一化，移除零宽字符、双向文本控制符、伪造角色边界、工具/转录标签和 fence 自身的闭合标记，
再把结果放进固定标签中并限制长度。

它缓解的是“外部数据伪装成指令”和上下文污染，不是身份认证。攻击者即使无法逃逸 fence，仍然
可能请求别人的订单；所有权必须由后端依据可信 session 判断。

### 4.2 Provenance gate

shopping agent 只有在当前 session 已通过搜索、详情或订单记录看到某商品后，才允许把其加入购物车；
merchant agent 只有读取过 listing/campaign 后，才允许暂存相应变更。这个机制阻止模型凭空构造 ID
执行动作，也迫使写操作建立在近期权威读取上。

provenance 也不是授权：它证明“Agent 从可信读取路径见过这个 ID”，不证明当前人有权操作它。

### 4.3 审批与上限

merchant 变更先 staging，再由 host approval surface 批准，最后 apply。数量、调用次数和变更范围
在代码里设置 cap。安全不变量位于 executor/gate/backend 路径，因此三种 runtime 不能因 prompt
差异绕过它。

## 5. 第四层：BaseToolExecutor 是核心控制平面

`commerce_common.execution.BaseToolExecutor` 集中完成：

- 工具名到 handler 的映射与分派；
- Pydantic 参数验证和稳定错误文本；
- 配置关闭工具后的拒绝；
- skill、presentation extension、delegate 和 memory 的统一接入；
- 后端异常降级，避免一次工具故障直接终止整轮对话；
- 对返回模型的业务数据统一 fencing。

这比每个 tool 自己处理异常和安全规则更易审计。风险是基类职责很重；新增机制若继续塞入基类，
会逐渐形成“框架内部框架”。

## 6. 第五层：Prompt、Skill 和 Grounding 分工

静态 system prompt 描述始终成立的身份与规则，skill 按请求加载具体流程，动态 context 携带品牌、
session 和当次业务信息。`prompt_assembly.py` 对静态前缀和 tools 加 cache control，要求每轮保持相同
字节，从而提高 prompt cache 命中。

grounding rule 在特定问题上强制首先执行权威读取，例如订单问题先读订单，经营分析先读 snapshot。
这不是普通 RAG：它是运行时级工具选择约束，防止模型在应该查实时数据时直接凭语言先验回答。

## 7. 第六层：一次请求的完整调用链

```text
React/宿主应用
  → API 根据 X-Session-Id 恢复 session/state
  → runtime 组装静态 prompt + fenced 动态上下文 + tools
  → grounding rule 可强制首个读取工具
  → Claude 返回文本块或 tool_use
  → role executor 校验参数、provenance、cap、approval
  → Backend 执行权威读取或暂存动作
  → ToolOutcome 将 fenced result 送回模型，并将 UI/event 送给宿主
  → runtime 继续模型轮次，直到自然结束或 presentation clean-end
  → 前端按 text_delta/tool_call/ui/cart_update/turn_complete 渲染
```

“一个模型拥有对话”避免多个 Agent 争夺最终回复；delegate 只完成受限分析并返回结构化结果。

## 8. 第七层：三种运行时共享什么

- Messages API：仓库自己实现 turn loop，控制最细，也承担最多循环和状态管理责任。
- Agent SDK：SDK 管理 loop，核心通过同一工具执行器暴露能力；宿主预取 grounding。
- Managed Agents：以 manifest、system prompt 和 MCP server 部署；平台负责托管，服务端 gate 仍保留。

真正共享的是 prompt/skills/tool contracts/gates/executor，而不是强行共享每一行 orchestration 代码。
优点是业务规则只定义一次；成本是要持续做跨 runtime 合同测试。

## 9. 第八层：前端不是聊天气泡附属品

presentation tool call 由服务端验证、补全并转换为 UI event。模型只表达“展示什么”，不能直接提供
任意 HTML，也不能决定可信价格或 checkout URL。前端共享 `web-shared` 中的 transcript、composer、
inspector 和 generative component 机制，各 vertical 只添加领域组件。

这是“生成式 UI + 服务端权威数据”的折中：比纯文本更可用，比模型生成任意 UI 更可控。

## 10. 工程化与可验证边界

上游用七个 Python 包明确模块边界，Next.js 应用组成 npm workspace。CI 检查 Python lint/format/test、
八个 web build、生成 manifest 一致性以及包名抢注风险。测试覆盖跨 runtime 的行为合同，而不仅是函数。

但 README 已明确：demo API 没有生产认证；checkout 不收费；merchant write 必须经 host apply；
没有随仓库交付真实 connector；这是 reference implementation 且不维护。因此简历上不能把 demo backend
说成真实生产集成，也不能把默认测试说成真实模型质量验证。

## 11. 面试中的核心结论

项目的主线可以压缩为一句话：**LLM 负责理解意图和组织解释，代码负责权限、数据来源、风险上限、
审批与副作用。** 个人实现进一步用数据库唯一约束和故障注入证明：checkpoint 恢复不能替代业务幂等。

