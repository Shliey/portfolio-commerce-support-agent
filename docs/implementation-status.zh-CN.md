# 实施状态

## 已实现并在本机验证

- 独立 Python 包、uv 锁文件与 GitHub Actions 配置。
- FastAPI 登录、订单查询、SSE chat、审批列表和审批决定接口。
- triage/order/return/policy 四角色及显式工具白名单。
- LangGraph 路由图；结构化 handoff/tool/approval/completed 事件。
- LangGraph `interrupt()` 与 SQLite Checkpointer；使用新 workflow 实例和新数据库连接恢复审批。
- 业务数据库与 checkpoint 数据库物理分离，并验证双方 schema 不交叉。
- SQL 所有权过滤、确定性 7 天退货规则和人工审批。
- `approvals.request_id` 与 `tickets.request_id` 数据库唯一约束。
- 相同请求重复创建 approval 返回原记录；重复批准返回原 ticket；参数变化返回冲突。
- TypeScript strict 的审批时间线 UI。
- 后端 18 个测试、前端 1 个测试、lint、format、strict mypy、typecheck、build 和 demo。

具体数字见 `artifacts/verification.json`。

## 下一阶段，不得提前写入简历

- 当前 RAG 是 lexical offline stub；需接入真实 semantic embedding，并建立 30+ 版本化评测集。
- 当前线程每次请求从 triage 开始；需持久化 `active_agent` 并验证跨轮恢复与跨用户拒绝。
- 当前验证了串行重复调用；需加入多线程/多进程并发和 crash-after-write 故障注入。
- 前端当前解析完整 SSE response；需改为增量 ReadableStream，并加入 Playwright E2E。
- 尚未运行真实模型、测量真实延迟/token 或部署，不得写相应结果。
