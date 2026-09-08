# 能力、归属与验证证据矩阵

| 能力 | Anthropic 上游 | 本项目个人实现 | 当前可引用证据 | 简历边界 |
|---|---|---|---|---|
| 双角色 commerce 架构 | 已实现 | 不复制 | 上游 README 与源码 | 只能写源码研究 |
| 三种 Claude runtime | 已实现 | 仅实现 LangGraph/FastAPI | 上游三个 runtime 目录 | 不写成个人实现 |
| Fencing/provenance | 已实现 | 采用所有权和工具白名单，后续可扩展 fence | 上游 fencing/gates 测试 | 可写“借鉴设计” |
| 四角色路由 | 无此实现 | 已实现 LangGraph triage、持久角色与代码强制 allowlist | runtime 与 41+ 测试 | 可写个人实现 |
| 所有权保护 | 部署方责任 | 已实现仓库查询约束 | API/仓库测试 | 可写个人实现 |
| 人工审批 | merchant 上游已实现 | return workflow 独立实现 | SSE + approval API 测试 | 可写个人实现 |
| 业务幂等 | 非上游主线 | `UNIQUE(request_id)` + 重试返回原 ticket | repository 测试 | 测试通过后量化 |
| LangGraph | 上游不使用 | 路由图已接入 | runtime graph + 测试 | 可写个人实现 |
| Policy RAG | 上游以 backend policy read 为主 | 独立语料、Hash 测试替身与 FastEmbed 语义检索 | 两份 30 样本报告 | 可写本地语义检索，不写真实 LLM |
| 严格 TS 前端 | 上游完整八应用 | 订单历史、增量 SSE、引用与审批时间线 | unit/typecheck/build/Playwright | 可写个人实现 |
| 真实模型评测 | 可运行 smoke，需 key | 严格门禁 runner 已实现，当前无 key | runner 合同测试 | 不得宣称真实模型指标 |
| 生产启动 | 文档级多平台说明 | 环境工厂、Dockerfile、Compose | Uvicorn smoke；无 Docker CLI | 可写容器化，不得宣称镜像/云部署通过 |

## 使用规则

只有“本项目个人实现”且“当前可引用证据”通过本机或 CI 验证的内容，才能进入工程版简历。
文件数量、测试数量和性能数字都必须由脚本生成，不能人工估算后长期保留。
