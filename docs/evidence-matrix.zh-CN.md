# 能力、归属与验证证据矩阵

| 能力 | Anthropic 上游 | 本项目个人实现 | 当前可引用证据 | 简历边界 |
|---|---|---|---|---|
| 双角色 commerce 架构 | 已实现 | 不复制 | 上游 README 与源码 | 只能写源码研究 |
| 三种 Claude runtime | 已实现 | 仅实现 LangGraph/FastAPI | 上游三个 runtime 目录 | 不写成个人实现 |
| Fencing/provenance | 已实现 | 采用所有权和工具白名单，后续可扩展 fence | 上游 fencing/gates 测试 | 可写“借鉴设计” |
| 四角色路由 | 无此实现 | 已实现确定性 triage 与 allowlist | `runtime.py` 与测试 | 可写个人实现 |
| 所有权保护 | 部署方责任 | 已实现仓库查询约束 | API/仓库测试 | 可写个人实现 |
| 人工审批 | merchant 上游已实现 | return workflow 独立实现 | SSE + approval API 测试 | 可写个人实现 |
| 业务幂等 | 非上游主线 | `UNIQUE(request_id)` + 重试返回原 ticket | repository 测试 | 测试通过后量化 |
| LangGraph | 上游不使用 | 路由图已接入 | runtime graph + 测试 | 可写个人实现 |
| Policy RAG | 上游以 backend policy read 为主 | 当前仅离线 lexical stub | RAG 单测 | 不宣称语义检索效果 |
| 严格 TS 前端 | 上游完整八应用 | 本项目有独立审批时间线 UI | typecheck/build | 构建通过后写入 |
| 真实模型评测 | 可运行 smoke，需 key | 尚未实现 | 无 | 当前不得宣称 |
| 生产部署 | 文档级多平台说明 | 尚未部署 | 无 | 当前不得宣称上线 |

## 使用规则

只有“本项目个人实现”且“当前可引用证据”通过本机或 CI 验证的内容，才能进入工程版简历。
文件数量、测试数量和性能数字都必须由脚本生成，不能人工估算后长期保留。

