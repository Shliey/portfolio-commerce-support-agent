# OpenSpec 逐项完成审计

审计基线：`../openspec/changes/build-ecommerce-support-agent/tasks.md`。`本地通过`表示实现和对应证据已在
Windows 本机复验；`外部待验`表示代码已具备，但当前环境无法产生所要求的外部证据。测试文件采用扁平布局，
与任务示例路径不同，但按相同行为契约验收。

## 1–4：基础、业务与工作流

| 任务 | 状态 | 主要证据 |
|---|---|---|
| 1.1–1.2 工程与依赖 | 本地通过 | `uv sync --frozen`、`uv lock --check`、Python 3.13.9、核心包导入 |
| 1.3 类型模型 | 本地通过 | `models.py`；strict mypy 全绿 |
| 1.4 Repository 生命周期 | 本地通过 | `ports.py`、显式 `close()`/context manager、Windows 重命名/删除与回滚测试 |
| 1.5 配置与 DI | 本地通过 | typed `ConfigurationError`、全 fake 依赖图测试 |
| 1.6 migration/seed | 本地通过 | 干净 DB seed、完整 schema、`UNIQUE(request_id)` 数据库约束测试 |
| 2.1 认证 | 本地通过 | PBKDF2 凭据；随机 nonce + HMAC 服务端 token；过期、篡改、伪造与等价错误测试 |
| 2.2 订单与物流 | 本地通过 | 所有权过滤、结构化响应与稳定错误码测试 |
| 2.3 基础 API | 本地通过 | TestClient、OpenAPI schema 和真实 Uvicorn 进程 smoke |
| 3.1 四角色路由 | 本地通过 | Pydantic structured router、fake 注入、角色工具白名单与越权拒绝 |
| 3.2 handoff 状态 | 本地通过 | 重启后 `active_agent` 延续、typed handoff 与关联 id 测试 |
| 3.3 checkpoint scope | 本地通过 | `user_id:thread_id:request_id` key 与跨用户拒绝测试 |
| 4.1 确定性资格 | 本地通过 | owner/delivered/returnable/7-day 组合单测 |
| 4.2 审批图 | 本地通过 | interrupt、批准、拒绝、冲突、外来订单测试 |
| 4.3 crash recovery | 本地通过 | business commit 后故障注入，恢复后仍为一张 ticket |
| 4.4 restart recovery | 本地通过 | 新 workflow/SQLite 连接恢复 pending approval |

## 5–8：RAG、API、持久化与安全

| 任务 | 状态 | 主要证据 |
|---|---|---|
| 5.1 Policy corpus | 本地通过 | 四主题与 source/title/section/position/topic 元数据测试 |
| 5.2 可替换检索 | 本地通过 | embedding/vector-store ports；Hash stub 与 FastEmbed 生产配置边界 |
| 5.3 evidence-only | 本地通过 | 越界问题拒答、引用子集和无证据零引用测试 |
| 5.4 30-case eval | 本地通过 | 两份 v1 JSON 报告；两项零容忍安全计数均为 0 |
| 5.5 real-model gate | 本地通过（无真实调用） | 默认关闭、缺 key 拒绝、开关打开后的 8-case fake CLI 全路径测试 |
| 6.1 streaming API | 本地通过 | 完整事件 taxonomy、因果顺序、同 run_id、单调 seq、净化错误测试 |
| 6.2 审批幂等 | 本地通过 | 断线重试同 ticket、参数冲突 SSE、跨用户 approval 无写入 |
| 6.3 OpenAPI | 本地通过 | 全公开 endpoint、模型、media type 与错误描述 schema 测试 |
| 7.1 Windows SQLite | 本地通过 | 反复打开、关闭、跨进程竞争与立即移动/删除测试 |
| 7.2 双数据库边界 | 本地通过 | 独立路径、独立 schema、fake checkpointer/repository 独立替换 |
| 7.3 安全反序列化 | 本地通过 | 仅放行 `langgraph.types.Interrupt`；伪造 `os.system` 在导入前拒绝且无 marker |
| 7.4 写入恢复 | 本地通过 | 与 4.3 共用故障注入证据 |
| 8.1 审计与脱敏 | 本地通过 | model/tool 的关联字段、耗时、token/attempt；prompt、secret 和错误文本不入日志 |
| 8.2 重试与限额 | 本地通过 | 模型/工具有界指数退避、持续失败错误、step/tool limit 事件 |
| 8.3 人工审批门禁 | 本地通过 | 无公开直接建单路径；缺失/跨用户 approval 均不能写 ticket |
| 8.4 统一错误 | 本地通过 | API/SSE 无 traceback、SQL、prompt；稳定 code 测试 |

## 9–10：UI、CI 与作品集材料

| 任务 | 状态 | 主要证据 |
|---|---|---|
| 9.1 严格 TypeScript | 本地通过 | `npm run typecheck -- --strict`、build |
| 9.2 UI 状态 | 本地通过 | 登录、订单、流式事件、角色/工具、引用、批准/拒绝与错误态组件测试 |
| 9.3 浏览器无密钥 | 本地通过 | 每次 production build 后扫描 dist |
| 9.4 浏览器 E2E | 本地通过 | Playwright：登录→订单→退货→批准→唯一 ticket |
| 10.1 CI | 外部待验 | workflow 已覆盖全部命令并显式 `RUN_REAL_MODEL_EVAL=0`；仓库无 remote，GitHub 登录已失效，不能声称远端 green run |
| 10.2 README/架构/截图 | 本地通过 | README contract test、架构说明、已目视验收的 Playwright 截图 |
| 10.3 one-shot demo | 本地通过 | fresh DB 完整闭环退出 0 |
| 10.4 结果总结 | 本地通过 | 本文、evidence matrix、implementation status、resume/interview kit 与 verification JSON |

## 当前外部边界

- 没有 LLM API key：真实 LLM 路由成功率、延迟、token 成本不存在；不可引用 fake runner 数字冒充。
- Docker Desktop 4.90.0 已安装，Engine 29.7.2 与 Compose 5.5.1 完成本机 build/run/health；无云部署证据。
- 独立仓库没有 Git remote，且本机 GitHub CLI token 失效：无法产生 OpenSpec 10.1 要求的远端绿色 CI run。

因此，本地实现 issue 已清零；真实模型和远端 CI 仍需相应外部凭据。
