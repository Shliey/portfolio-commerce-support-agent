# 实施状态

## 已实现并在本机验证

- 独立 Python 包、uv 锁文件与 GitHub Actions 配置。
- FastAPI 登录、订单查询、SSE chat、审批列表和审批决定接口。
- triage/order/return/policy 四角色及显式工具白名单。
- LangGraph 路由图；结构化 handoff/tool/approval/completed 事件。
- LangGraph `interrupt()` 与 SQLite Checkpointer；使用新 workflow 实例和新数据库连接恢复审批。
- `active_agent` 按 `(user_id, thread_id)` 持久化；新 Runtime 实例可延续角色且跨用户隔离。
- 业务数据库与 checkpoint 数据库物理分离，并验证双方 schema 不交叉。
- SQL 所有权过滤、确定性 7 天退货规则和人工审批。
- `approvals.request_id` 与 `tickets.request_id` 数据库唯一约束。
- 相同请求重复创建 approval 返回原记录；重复批准返回原 ticket；参数变化返回冲突。
- 使用 SQLite `BEGIN IMMEDIATE` 协调独立 Repository 实例的并发写入；16 次并发批准只产生一张工单。
- Windows `spawn` 模式下 4 个进程执行 8 次竞争批准，最终返回同一 ticket ID 且数据库仅一行。
- 故障注入覆盖“工单已提交、checkpoint 未更新”窗口；新 workflow 实例恢复后仍只有一张工单。
- TypeScript strict 的审批时间线 UI。
- 前端使用 `ReadableStream` 增量解析 SSE，并在每个事件到达时更新执行时间线。
- Playwright 启动隔离的 FastAPI/Vite 进程，验收登录、退货请求、审批和成功提示后自动回收进程。
- RAG 提供真实 LangChain embedding 工厂；生产配置缺失模型名时拒绝启动，不静默降级到 Hash。
- CI 使用明确标记为非语义测试替身的 `HashEmbedding`，运行 30 条版本化检索与拒答评测。
- 本机使用 `fastembed:BAAI/bge-small-en-v1.5` 完成独立真实语义检索评测；30 条样本的
  Hit@1、Hit@3、MRR、引用合法率和拒答召回均为 1.0，且明确标记 `real_model_used=false`。
- 真实 LLM 路由评测 runner 固定 8 条版本化样本并记录 prompt/model、成功率、P50/P95 延迟和 token；
  默认 CI 禁止调用，只有同时显式设置 `RUN_REAL_MODEL_EVAL=1` 和 API key 才会执行。
- 生产应用工厂从环境读取 secret、业务库、checkpoint 库和前端产物路径；同源静态前端、健康检查、
  登录和双数据库已通过真实 Uvicorn 进程级 smoke test。
- 多阶段 Dockerfile、Compose 持久卷与容器健康检查已实现；当前机器没有 Docker CLI，镜像尚未实际构建。
- 后端 31 个测试、前端 1 个单元测试和 1 个浏览器 E2E、lint、format、strict mypy、typecheck、build 和 demo。

具体数字见 `artifacts/verification.json`。

## 下一阶段，不得提前写入简历

- 当前环境没有 LLM API key，因此尚未运行真实 LLM，也没有可声明的真实延迟/token 指标。
- Docker 镜像尚未在装有 Docker 的环境执行构建/运行验收；本机生产进程验收不能替代该结果。
