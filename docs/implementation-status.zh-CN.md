# 实施状态

## 已实现并在本机验证

- 独立 Python 包、uv 锁文件与 GitHub Actions 配置。
- Typed configuration error 与统一 DI graph 覆盖 chat model、embedding、repository、checkpointer；
  全 fake 构造测试证明默认 CI 不触发网络或真实模型。
- FastAPI 登录、订单与结构化物流查询、SSE chat、审批列表和审批决定接口；演示密码以随机盐 PBKDF2 保存，
  登录校验使用恒定时间比较，未知用户与错误密码返回完全相同的外部响应。
- OpenAPI 为全部公开 endpoint 声明请求/响应模型、SSE media type 和稳定的认证、not-found、
  idempotency-conflict 错误契约，并由 schema 解析测试锁定。
- triage/order/return/policy 四角色及显式工具白名单。
- 每次工具执行前由代码强制校验当前角色白名单；越权调用返回稳定错误并产生拒绝审计，不能靠提示词绕过。
- LangGraph 路由图；结构化 handoff/tool/approval/completed 事件。
- 路由器通过 `IntentRouter` 端口注入，输出 Pydantic `role/order_id/reason` 决策；runtime 消费结构化字段，
  测试可注入 fake，默认关键词实现保持零模型费用。
- 配置 API key 时生产工厂改用 LLM structured-output router；模型调用审计记录 run/user/thread、
  P50 可计算耗时和 input/output token，但不记录原始用户消息。无 key 时仍显式走确定性 router。
- LangGraph `interrupt()` 与 SQLite Checkpointer；使用新 workflow 实例和新数据库连接恢复审批。
- Checkpointer 显式禁用 pickle fallback，并将 JSON/msgpack 反序列化限制为内置安全类型；外部模块对象被拒绝。
- 所有 Session SQLite 连接在 `finally` 显式关闭；Windows 验证可在运行后立即删除 checkpoint 文件。
- Business Repository 同样验证异常事务完整回滚，并在带空格的 Windows 路径反复打开 20 次后可立即重命名删除。
- `active_agent` 按 `(user_id, thread_id)` 持久化；新 Runtime 实例可延续角色且跨用户隔离。
- 业务数据库与 checkpoint 数据库物理分离，并验证双方 schema 不交叉。
- 可独立执行的 migration/seed 入口在干净数据库创建 users、orders、order_items、logistics、
  approvals、tickets、eval_runs，并从结构化物流表读取权威数据。
- SQL 所有权过滤、确定性 7 天退货规则和人工审批。
- 业务逻辑依赖不含 LangChain 的 `BusinessRepository` Protocol；`OrderTools` 统一提供结构化、
  所有权保护的订单/历史/物流读取，SQLite 只是当前适配器。
- `approvals.request_id` 与 `tickets.request_id` 数据库唯一约束。
- 相同请求重复创建 approval 返回原记录；重复批准返回原 ticket；参数变化返回冲突。
- 使用 SQLite `BEGIN IMMEDIATE` 协调独立 Repository 实例的并发写入；16 次并发批准只产生一张工单。
- Windows `spawn` 模式下 4 个进程执行 8 次竞争批准，最终返回同一 ticket ID 且数据库仅一行。
- 故障注入覆盖“工单已提交、checkpoint 未更新”窗口；新 workflow 实例恢复后仍只有一张工单。
- Workflow 自身在 resume 前重查 approval 所有权；跨用户直接调用也稳定拒绝。rejection、未配送、
  缺失配送时间和 DB 原生重复 request_id 均有独立终态/约束测试。
- TypeScript strict 的审批时间线 UI。
- UI 登录后展示所有权保护的订单历史，并在通用事件卡中展示角色、工具、RAG 引用和审批状态。
- React Testing Library + jsdom 使用 fake backend 验证订单、流式审批、批准结果和稳定登录错误状态。
- 前端使用 `ReadableStream` 增量解析 SSE，并在每个事件到达时更新执行时间线。
- SSE 事件按用户、线程、run 和 seq 持久化在 checkpoint 边界；支持用户隔离的线程快照与断线 replay。
- 运行异常统一转换为带完整 run/user/thread/seq 的稳定错误事件，不暴露 SQL/堆栈且同样支持 replay。
- 工具执行边界记录 run/user/thread、调用名、耗时、尝试次数和状态；敏感字段递归脱敏，
  瞬时故障使用有界指数退避，每轮工具数超限即停止。
- Runtime 同时限制每轮工具调用数和每 run 事件步数；超限产生完整关联并持久化的
  `limit_exceeded` 终止事件，且步数耗尽前不会进入后续工具。
- 本地 TestClient/no-LLM load smoke 对 `GET /orders` 执行 100 次全部成功，P50 1.727 ms、
  P95 2.194 ms、max 3.308 ms；仅代表当前机器的 fake 本地路径，不代表网络或模型延迟。
- Playwright 启动隔离的 FastAPI/Vite 进程，验收登录、退货请求、审批和成功提示后自动回收进程。
- Playwright E2E 同时断言订单历史、退货审批和唯一成功结果；Windows teardown 后 8010/5174 无监听残留。
- README 内嵌由同一 Playwright 通过路径显式生成并经人工视觉检查的完整页面截图；刷新命令可复现。
- 前端生产构建自动扫描 API key、provider token 与硬编码 Bearer 凭据模式，发现即失败。
- RAG 提供真实 LangChain embedding 工厂；生产配置缺失模型名时拒绝启动，不静默降级到 Hash。
- Embedding 与 VectorStore 分别通过协议替换；内存向量库是默认实现，fake store 合同测试验证替换后
  引用与拒答语义保持不变。
- 生产应用工厂将配置的 semantic retriever 注入 runtime；真实 Uvicorn smoke 已用 BGE 回答电子保修问题并返回合法来源。
- Policy 语料从业务代码迁至独立版本化文件，覆盖退货、电子保修、物流异常/赔付和促销退款；
  每个 chunk 保存 source、title、section、position 与 topic 元数据。
- CI 使用明确标记为非语义测试替身的 `HashEmbedding`，运行 30 条版本化检索与拒答评测。
- 两套 RAG 报告直接输出零容忍安全计数：`cited_source_not_retrieved=0`、
  `policy_fabricated_without_evidence=0`，不再依赖从聚合比例反推。
- 本机使用 `fastembed:BAAI/bge-small-en-v1.5` 完成独立真实语义检索评测；30 条样本的
  Hit@1、Hit@3、MRR、引用合法率和拒答召回均为 1.0，且明确标记 `real_model_used=false`。
- 真实 LLM 路由评测 runner 固定 8 条版本化样本并记录 prompt/model、成功率、P50/P95 延迟和 token；
  默认 CI 禁止调用，只有同时显式设置 `RUN_REAL_MODEL_EVAL=1` 和 API key 才会执行。
- 生产应用工厂从环境读取 secret、业务库、checkpoint 库和前端产物路径；同源静态前端、健康检查、
  登录和双数据库已通过真实 Uvicorn 进程级 smoke test。
- 多阶段 Dockerfile、Compose 持久卷与容器健康检查已实现；当前机器没有 Docker CLI，镜像尚未实际构建。
- 后端 63 个测试、前端 3 个单元/组件测试和 1 个浏览器 E2E、lint、format、strict mypy、typecheck、build 和 demo。
- CI 已覆盖后端静态检查/测试/RAG 报告、前端单测/typecheck/build/密钥扫描/E2E；README 必备章节由测试门禁。

具体数字见 `artifacts/verification.json`。

## 下一阶段，不得提前写入简历

- 当前环境没有 LLM API key，因此尚未运行真实 LLM，也没有可声明的真实延迟/token 指标。
- Docker 镜像尚未在装有 Docker 的环境执行构建/运行验收；本机生产进程验收不能替代该结果。
