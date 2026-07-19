# 真人鼠标强制开关：确认范围与集成研究

## 研究结论

已确认的产品决定如下，原 PRD 中“强制模式下真实鼠标能力不可用时怎么办”的问题已解决：

1. 数据库强制开关关闭时，必须逐字保持当前策略；特别是 `CAPTCHA_REAL_MOUSE=true` 仍照现有规则生效，不能被页面开关反向关闭。
2. 数据库强制开关开启时，只覆盖本机 Token 刷新和密码登录的后续新滑块任务。
3. 外部系统经 `POST /api/v1/captcha/slider-solve` 调用本机的路径不读取、不传递、也不应用该开关，继续只遵循当前环境变量和远程队列语义。
4. 强制模式下，真实鼠标模块导入失败或 `REAL_MOUSE_AVAILABLE` 为假时，本次任务立即失败，绝不改走远程、Playwright 或 DrissionPage；真实鼠标实际验证失败也保持现有“失败不回退”规则。
5. 不新增依赖、数据表、独立 API 或配置服务。使用已有 `system_settings`、`GET/PUT /api/v1/captcha/remote-config` 和 RiskLogs 管理员卡片。

## 启动日志契约

实现位置应为 `websocket/_bootstrap.py`，并严格按顺序执行：

1. 在 `get_settings()` 前用 `os.getenv("CAPTCHA_REAL_MOUSE")` 保存真实进程环境值。
2. 完成 `setup_logging(...)` 后，仅写一条 `logger.info`，字段至少为 `process_env={raw_value!r}` 与 `parsed_enabled={settings.captcha_real_mouse_enabled}`。
3. 不记录 `.env` 内容、数据库值、密钥或其他配置。

`repr` 是契约的一部分：未设置为 `None`，空字符串为 `''`，字面值保留引号，例如 `'true'`。`BaseConfig` 以 Pydantic 从 `CAPTCHA_REAL_MOUSE` 解析布尔值，默认 `false`，`get_settings()` 带 LRU 缓存；该记录是进程启动快照。

日志会进入 `websocket/logs/websocket.stdout.log` 的原因是：`setup_logging()` 将 Loguru 控制台 sink 写入 `sys.stderr`，`ServiceManager.start_python_service()` 和冻结模式的 `service_runner.run_service()` 都将子服务 `stderr` 合并重定向至该 stdout 文件。日志也会进入轮转的 `websocket/logs/websocket.log`。不要在启动器或打包脚本记录此项，因为那里不能证明 WebSocket 进程最终的 Pydantic 解析结果。

无效布尔字面值会在日志初始化前令 `get_settings()` 失败；本任务验收只要求未设置、`true`、`false`，不应为了未要求的无效值观测额外引入 `print` 路径。

## 设置和 API 契约

持久化键固定为：

```text
captcha.force_real_mouse = "false" | "true"
```

默认值为 `"false"`，并需同时出现在以下两个既有默认值源中，以兼容新库和旧库：

- `backend-web/app/services/system_setting_service.py` 的 `DEFAULT_SYSTEM_SETTINGS` 和 `NO_ESCAPE_KEYS`。
- `common/db/init_database.py` 的 `DatabaseInitializer.DEFAULT_SETTINGS`。

扩展现有、仅管理员可访问的验证码配置接口，不新建接口：

```text
GET /api/v1/captcha/remote-config
  -> 保留既有字段，新增 force_real_mouse: boolean

PUT /api/v1/captcha/remote-config
  -> 保留既有字段，新增 force_real_mouse: boolean
  -> 以 "true" / "false" 写入 captcha.force_real_mouse
```

后端扩展 `RemoteConfigUpdate`、查询键列表和批量保存字典；GET 缺少该行时必须返回 `false`。前端同步扩展 `getRemoteCaptchaConfig()` 返回类型及 `saveRemoteCaptchaConfig()` 载荷，在 `RiskLogs.tsx` 的现有管理员卡内增加本地 state、加载回显、随“保存”按钮提交的 `role="switch"`。该卡已由 `user?.is_admin` 整体保护，API 也使用 `get_current_admin_user`，不应新增第二套权限逻辑或即时保存 API。

页面开关文案必须说明它会占用本机物理鼠标、只影响新开始的本机 Token 刷新和密码登录；不应宣称影响外部远程调用。开关可以沿用同卡已有的 `button[role=switch]` 可访问性模式和 loading 禁用状态。

## 运行期策略矩阵

`env` 表示缓存后的 `CAPTCHA_REAL_MOUSE` 解析结果，`force` 表示本次任务开始时异步读取的 `captcha.force_real_mouse`。

| 入口 | force=false | force=true |
| --- | --- | --- |
| 本机 Token 刷新 | 完全保留当前顺序：有远程配置先远程；远程可用但失败不回退；远程不可用才落本机；无远程时 env=true 使用真实鼠标，否则 Playwright/DrissionPage。 | 跳过远程配置，进入现有 `local` 加权队列，强制真实鼠标。模块不可用或验证失败均不回退。 |
| 密码登录 | 完全保留当前模式选择与协议链路：`auto` 仅 env=true 或已配置远程服务时走协议；协议滑块有远程时先远程。 | `auto` 必须视为具备协议能力而走协议；每次新登录滑块跳过远程，委托 WebSocket 的 `local` 队列强制真实鼠标。不可用或失败保持协议失败/重试，不回退浏览器模式。 |
| 外部远程调用 | 保留当前实现：不读数据库开关；env=true 时走 `remote` 或 `remote_cookie` 队列，否则默认本机引擎。 | 不适用，行为与左列完全相同。 |

特别地，`force=false + env=true` 必须保留“远程配置优先于真实鼠标”的当前行为。只有数据库强制本机任务时，远程优先级才被压过；这不能通过改动全局 `_real_mouse_enabled()` 实现。

## 三条数据流与异步读取边界

### 1. 本机 Token 刷新

`CookieTokenManager.handle_captcha_verification()` 已在异步上下文通过 `async_session_maker()` 读取远程配置。将 `captcha.force_real_mouse` 加入同一次查询并在开始本次滑块前解析为布尔快照；不要在该热路径调用同步 `common.db.compat.db_manager.get_system_setting()`。

当快照为真时：不给 `run_slider_verification_with_fallback()` 传远程配置，传入显式 `force_real_mouse=True`，并经既有 `real_mouse_weighted_runner.submit("local", ...)` 提交。否则传递当前远程配置和默认 `False`，保留原分支。队列外不应再次读取该设置，配置改变只对随后开始的任务生效。

### 2. 密码登录

`backend-web/app/api/routes/password_login.py` 的 `_decide_mode()` 已使用注入的 `AsyncSession` 查询模式与远程配置。把新键加入同一次查询，以便 `auto + force=true` 选择协议登录，避免浏览器代理路径绕过强制策略。

`backend-web/app/services/password_login/flow.py` 必须使用 `async_session_maker()` 异步读取远程配置和强制值；读取时点应在每次识别到新的 `LoginBranch.SLIDER`、委托 WebSocket 前，作为该滑块任务的快照。强制值为真时不调用 `solve_remote()`，而是通过现有 `WebSocketServiceClient.solve_captcha()` 传递一个仅服务间使用的可选 `force_real_mouse=True` 标记；为假时维持现有远程优先逻辑。

为承载密码登录的本机意图，可在既有 `SolveCaptchaRequest` 和 `WebSocketServiceClient.solve_captcha()` 上增加同名、默认 `False` 的字段，不创建新端点。WebSocket 内部接口仅在该标记为真且调用来源为本机 `local` 路径时进入 `local` 队列并将标记传给编排器；后台公开远程 API 固定传 `False`。这是同一服务间调用契约的最小扩展，不能让公开的 `/api/v1/captcha/slider-solve` 传播此值。

### 3. 外部远程调用

公开入口 `POST /api/v1/captcha/slider-solve` 调用 `WebSocketServiceClient.solve_captcha(..., call_type="remote")`，WebSocket 的 `/internal/captcha/solve` 将其固定分流至 `remote` / `remote_cookie`。该路径不得查询 `captcha.force_real_mouse`，不得设置服务间强制标记，也不得把数据库强制值传入 `run_slider_verification_with_fallback()`。

因此现有外部容量限制、Cookie 链接重取、延长队列超时，以及本地/远程权重语义均不受开关影响。

## 编排器和失败契约

给 `common/services/captcha/orchestrator.py` 的 `run_slider_verification_with_fallback()` 增加默认 `False` 的显式参数 `force_real_mouse`，而非让同步 `_real_mouse_enabled()` 查询数据库。其有效状态为：

```text
use_real_mouse = CAPTCHA_REAL_MOUSE 已启用 OR force_real_mouse
```

优先级规则为：

1. 仅 `force_real_mouse=False` 时执行当前的远程配置分支。
2. 之后若 `use_real_mouse=True`，执行真实鼠标导入与可用性检查。
3. `force_real_mouse=True` 且模块导入失败或 `REAL_MOUSE_AVAILABLE=False` 时，记录明确错误后直接返回失败，不调用任何兜底引擎。
4. `force_real_mouse=False + env=true` 且真实鼠标不可用时，保留当前兼容行为：记录错误并回退原 Playwright/DrissionPage 链路。
5. 真实鼠标已可用但验证未通过时，无论来源为环境变量还是强制开关，都直接返回失败；现有 `URL_EXPIRED` 返回语义不变。

无需为了“引擎不可用”新增异常类型或一套响应协议。编排器返回现有失败三元组，调用方把风险日志/协议会话标记为失败；日志必须包含“强制真实鼠标引擎不可用”和运行条件。这样可避免把非成功引擎字符串写入既有 `captcha_engine` 枚举字段，同时满足“不回退”的失败契约。

## 队列不变量

不修改 `common/services/captcha/weighted_runner.py`、`weighted_scheduler.py` 或 `real_mouse_slider.py` 的调度算法。强制任务只复用已有入口：

- Token 刷新使用 `local`。
- 密码登录经 WebSocket 使用 `local`。
- 外部请求继续使用 `remote` 或 `remote_cookie`。

现有前置 `WeightedTaskRunner`、真实鼠标串行执行器和权重读取保持原样。已被选中并正在执行的任务不检查数据库新值，不能因管理员切换开关而取消、切换引擎或改变其权重；数据库值只在开始新滑块任务前生成快照。

## 最小验证与回滚

当前仓库未发现覆盖验证码配置、编排优先级或 RiskLogs 配置卡的自动化测试，也没有声明 pytest/vitest 测试脚本。后续实现应补充最小、聚焦的 Python 标准库测试或项目已可运行的等价测试，不引入测试依赖，至少覆盖：

1. `force=true` 跳过远程并在真实鼠标不可用时失败；`force=false + env=true` 保留远程优先；`force=false + env=false` 保留普通链路。
2. Token 刷新和密码登录只在 `force=true` 时以 `local` 进入既有加权 runner；公开远程调用不传强制值且保持 `remote` / `remote_cookie`。
3. 管理员 GET 缺键返回 `false`，PUT 后可回显；非管理员被现有鉴权拒绝。

常规验证至少执行受影响 Python 文件的编译检查，以及前端 `npm run lint` 和 `npm run build`。Windows EXE 手工验证应在有图形桌面、Chrome 和真实鼠标依赖的隔离机器上完成：

1. 分别以未设置、`CAPTCHA_REAL_MOUSE=true`、`CAPTCHA_REAL_MOUSE=false` 启动 EXE，检查 `websocket/logs/websocket.stdout.log` 的一次性启动快照。
2. 管理员开启开关并保存，刷新 RiskLogs 确认回显；新 Token 刷新和密码登录应记录真实鼠标，关闭后恢复确认前的策略。
3. 在故意缺少真实鼠标能力的环境开启开关，确认本机两条路径失败且未使用远程/Playwright/DrissionPage；确认外部 `/api/v1/captcha/slider-solve` 行为不变。
4. 不在有人正在操作的 Windows 桌面执行真实鼠标验证，因为它会接管物理光标。

回滚首先将页面开关保存为 `false`，立即恢复新任务的原有策略；已运行任务自然完成。若需要部署回退，旧版本安全忽略新增的 `system_settings` 键，不需要数据库迁移或数据删除。代码回滚点应保持为：启动日志独立小改动、配置/API/前端契约改动、本机两条编排改动三个可独立审查的提交单元。

## 后续规划产物的输入

规划代理应据此：从 PRD 删除已解决 Open Question；在 `design.md` 固化上述三个流、策略矩阵、失败契约和日志落盘链路；在 `implement.md` 以默认值/API/前端、Token、密码登录/WebSocket、编排器、验证的顺序列出操作。`implement.jsonl` 与 `check.jsonl` 至少应引用本研究文件和相关前端规范文件，且删除 `_example`。

## 证据

- `websocket/_bootstrap.py:26-39`、`common/core/config.py:94-125`、`common/utils/logging_utils.py:57-100`：WebSocket 解析配置及 Loguru stderr sink。
- `launcher/service_manager.py:217-355`、`launcher/service_runner.py:220-265`：EXE 两层环境继承和 stdout/stderr 重定向。
- `backend-web/app/services/system_setting_service.py:41-135`、`common/db/init_database.py:91-175`：两套默认设置与免转义白名单。
- `backend-web/app/api/routes/captcha.py:75-104,631-723`、`frontend/src/api/admin.ts:152-187`、`frontend/src/pages/admin/RiskLogs.tsx:204-320,390-535`：管理员 API、前端契约及现有开关/保存模式。
- `common/services/captcha/orchestrator.py:59-78,149-348`：环境变量真实鼠标、远程优先、不可用回退和失败不回退。
- `websocket/app/services/xianyu/cookie_token_manager.py:495-613`：Token 刷新的异步远程配置读取和 local 队列入口。
- `backend-web/app/api/routes/password_login.py:50-86`、`backend-web/app/services/password_login/flow.py:46-117,213-280`：密码登录模式选择、远程优先和 WebSocket 委托。
- `backend-web/app/services/websocket_client.py:245-310`、`websocket/app/api/routes/internal.py:80-88,336-455`、`backend-web/app/api/routes/captcha.py:500-565`：服务间滑块调用和公开远程调用路径。
- `common/services/captcha/weighted_runner.py:42-304`、`common/services/captcha/real_mouse_slider.py:1063-1111`：现有加权队列、不可取消语义与物理鼠标串行执行。
- `common/db/compat.py:79-130,371-387`：同步兼容层使用新线程并最多等待 30 秒，不能放入事件循环中的设置读取路径。
