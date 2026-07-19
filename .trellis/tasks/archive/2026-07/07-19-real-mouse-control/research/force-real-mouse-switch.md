# 风控日志“强制使用真实鼠标引擎”开关研究

## 推荐最小方案

将开关作为全局 `system_settings` 键 `captcha.force_real_mouse`，默认 `"false"`。复用当前的验证码专用配置 API，而不是新建通用或独立 API：

- 数据模型：`common.models.system_setting.SystemSetting`。
- 持久化服务：`backend-web.app.services.system_setting_service.SystemSettingService.set_settings()`。
- 管理员 API：扩展现有 `GET/PUT /api/v1/captcha/remote-config`。
- 前端 API：扩展 `frontend/src/api/admin.ts` 的 `getRemoteCaptchaConfig()` 与 `saveRemoteCaptchaConfig()`。
- 前端区域：复用 `frontend/src/pages/admin/RiskLogs.tsx` 管理员验证码配置卡，放在已存在的 real_mouse 排队权重附近，随现有“保存”按钮提交。

这样只扩展一条已具备管理员鉴权、批量保存和 WebSocket 动态消费的验证码配置链路；不添加依赖，不新建模型或页面。

不建议复用通用 `PUT /api/v1/system-settings/{key}`：它虽可写入任意键，但当前 RiskLogs 已有面向验证码的专用 API，专用 API 能提供明确布尔类型、同一批次保存、配置语义和最少前端改动。

## 建议的数据契约

```text
system_settings
  captcha.force_real_mouse = "false" | "true"

GET /captcha/remote-config
  ...existing fields..., force_real_mouse: boolean

PUT /captcha/remote-config
  ...existing fields..., force_real_mouse: boolean
```

后端需要同时维护默认键的两个来源：

1. `backend-web/app/services/system_setting_service.py` 的 `DEFAULT_SYSTEM_SETTINGS`，保证 API 首次读取时补齐。
2. `common/db/init_database.py` 的 `DatabaseInitializer.DEFAULT_SETTINGS`，保证初始化数据库时补齐。

并将这个布尔键加入 `NO_ESCAPE_KEYS`，与相邻 `captcha.*` 布尔配置保持一致。

## 当前链路

```text
RiskLogs 管理员卡片
  -> frontend/src/api/admin.ts
  -> PUT /api/v1/captcha/remote-config (管理员)
  -> SystemSettingService.set_settings()
  -> xy_system_settings.captcha.force_real_mouse
  -> WebSocket 的下一次滑块请求
       -> 有效真实鼠标判定
       -> real_mouse_weighted_runner（本地 / 远程公平排队）
       -> run_slider_verification_with_fallback()
       -> run_real_mouse_verification()
```

### 当前真实鼠标开关

现有真实鼠标仅由启动配置 `CAPTCHA_REAL_MOUSE` 决定。`common.services.captcha.orchestrator._real_mouse_enabled()` 同步读取缓存的 `get_settings()`，为真时真实鼠标成为本机唯一引擎：真实鼠标失败不会回退 Playwright/DrissionPage；只有引擎不可用时才回退。

WebSocket 有两个实际滑块入口：

- 本地 Token 刷新：`CookieTokenManager.handle_captcha_verification()`；只有未配置远程服务且环境开关为真时才提前进入 `real_mouse_weighted_runner` 的 `local` 队列。
- 外部远程请求：`/internal/captcha/solve`；环境开关为真时进入 `remote` 或 `remote_cookie` 队列。

前置队列读取数据库中的现有 `captcha.real_mouse_weight_local`、`captcha.real_mouse_weight_remote`，实现本地/远程共享一个物理鼠标时的公平排队。

### 远程优先级是关键事实

`run_slider_verification_with_fallback()` 当前先处理 `remote_config`，仅当远程超时/不可用才落到本机真实鼠标；远程有有效响应但验证失败时不会本机回退。密码登录协议流也先选远程服务。因此仅把新数据库键并入“本机是否启用真实鼠标”的判断，**不能保证**“强制使用真实鼠标”在配置远程服务时真的使用真实鼠标。

## WebSocket 编排的最小正确改动

### 语义建议

把新值定义为“强制启用叠加层”，有效值为：

```text
有效真实鼠标 = CAPTCHA_REAL_MOUSE 已启用 OR captcha.force_real_mouse == true
```

这保留运维环境变量的既有含义：前端关闭“强制”只撤销数据库强制，不会反向关闭已通过环境变量明确启用的真实鼠标。

开关应只影响**新开始**的滑块任务；已运行的物理鼠标操作不能安全地中断或切换引擎。

### 调用方必须共同修改

不能只改 `orchestrator.py`。否则部分调用方会跳过前置加权队列，或登录模式仍判断为“没有真实鼠标能力”。最低限度需要让以下决策共享同一有效值：

1. `common/services/captcha/orchestrator.py`：决定实际引擎。
2. `websocket/app/services/xianyu/cookie_token_manager.py`：决定本地请求是否进入前置 `local` 加权队列。
3. `websocket/app/api/routes/internal.py`：决定远程请求是否进入 `remote` / `remote_cookie` 加权队列。
4. `backend-web/app/api/routes/password_login.py`：auto 模式决定协议登录还是浏览器登录。
5. `backend-web/app/services/password_login/flow.py`：登录滑块决定远程还是委托 WebSocket。

数据库读取不要直接塞入现有同步 `is_real_mouse_enabled()` 并在 FastAPI 事件循环中阻塞调用 `db_manager.get_system_setting()`：该兼容方法会创建线程、等待查询完成，单次最长等待 30 秒。应在异步入口用现有 async session 一次性读取该键，再把已解析的有效布尔值传给同步编排函数；或者引入一个小型、可 await 的共用读取函数。读取发生在每个滑块任务启动时即可，和现有“本机滑块不处理”实时查库模式一致。

### “强制”若必须胜过远程

如果产品含义是“无论远程配置是否存在，所有滑块都必须使用本机真实鼠标”，则必须在两处改变优先级：

- `common/services/captcha/orchestrator.py`：真实鼠标分支必须早于远程 `remote_config` 分支，或强制时不向其传入远程配置。
- `backend-web/app/services/password_login/flow.py`：强制时不得先调用 `solve_remote()`，而应委托 WebSocket。

这是行为改动，不应悄悄混入一个普通布尔开关。若产品只想表达“本机处理时使用真实鼠标”，更准确的文案应是“本机滑块优先使用真实鼠标”，并保留远程优先级。

## 前端实施范围

1. 在 `RiskLogs.tsx` 增加 `forceRealMouse` state。
2. `loadRemoteConfig()` 回填 API 返回值。
3. `handleSaveRemoteConfig()` 将值传给扩展后的 `saveRemoteCaptchaConfig()`。
4. 在现有管理员验证码卡、real_mouse 权重说明附近放一个可访问的 `role="switch"` 控件；当前页面已有相同开关样式和 loading 状态可直接沿用。
5. 默认 false。文案必须说明会占用桌面物理光标，且仅新任务生效。

无需改 `frontend/src/api/settings.ts`：该通用系统设置层没有该验证码专用状态，也未将该键加入布尔转换表。

## 产品语义待确认

1. **“强制”是否覆盖远程服务？** 现状是远程优先；两种含义会产生不同编排顺序和风险。
2. **false 的含义是什么？** 推荐为“撤销数据库强制，仍尊重 `CAPTCHA_REAL_MOUSE` 环境变量”，而不是全局关闭。
3. **无桌面/依赖缺失时怎么办？** 现有引擎会记录不可用并回退原逻辑。若 UI 仍称“强制”，用户会得到与文案不一致的结果；可接受回退、后端拒绝保存，或增加运行状态检测，三者需产品选择。
4. **是否包含密码登录滑块？** 若包含，必须同步处理 backend-web 的协议模式和其远程优先级；若仅 Token 刷新/外部接口，需要在 UI 明确范围。
5. **保存方式：** 复用远程配置卡意味着随“保存”提交；若要求点击即生效，应改用 RiskLogs 已有本机开关的独立 GET/PUT 模式，但会增加 API 表面。

## 风险

- 真实鼠标物理上只能单任务执行；强制扩大使用范围会增加队列等待和 API 超时风险。保留并接入现有 `real_mouse_weighted_runner` 是必要条件。
- 真实鼠标成功率依赖 Windows 图形桌面、可见 Chrome、轨迹样本和 `pyautogui`。数据库开关不能让不具备能力的节点获得能力。
- 若“强制”覆盖远程，已配置的远程 Cookie 传递、链接重取和远程容量控制将被绕开；这应视作明确的运行策略切换。
- `SystemSettingService` 与数据库初始化器维护两套默认列表；漏改其一会造成新库与已升级库默认值不一致。
- 远程配置 API 当前同时承载 URL、密钥、Cookie 传递、远程拒绝、容量、冷却和权重。扩展一个布尔字段是最小变更；不要把此开关拆成多个模型/接口。

## 建议测试

1. API：管理员 GET 在键缺失时返回 `false`；PUT `true/false` 后 GET 回显，并在 `xy_system_settings` 写入正确字符串；非管理员被拒绝。
2. 初始化：新数据库和已存在数据库经 `SystemSettingService.ensure_default_settings()` 后均有 `captcha.force_real_mouse=false`。
3. WebSocket 单元测试：mock 数据库设置和真实鼠标函数，验证环境 false + DB true 进入真实鼠标；环境 false + DB false 不进入；环境 true + DB false 仍进入。
4. 队列回归：本地和远程请求在强制 DB 值为 true 时仍分别进入 `local`、`remote`/`remote_cookie` 前置队列，并继续使用现有权重。
5. 优先级测试：根据确认的产品语义，断言“强制”是否跳过 remote_config；同时覆盖远程超时、远程明确失败和真实鼠标失败不回退。
6. 密码登录：auto 模式在强制值为 true 时选择协议，并确认登录滑块的远程优先级符合产品决定。
7. 前端：管理员加载回显、切换后保存载荷、刷新页面后状态一致；非管理员不渲染控件。
8. Windows 手工冒烟：在具备图形桌面和 Chrome 的发布包中启用开关，确认新风控日志的 `captcha_engine=real_mouse`；关闭后确认恢复确认后的默认策略。不要在用户正在操作的桌面执行。

未发现覆盖 `CAPTCHA_REAL_MOUSE`、远程配置 API 或真实鼠标权重的现有自动化测试；本次是只读研究，未运行任何测试，避免重复已验证用例。

## 证据

- `common/models/system_setting.py:19` 至 `common/models/system_setting.py:33`：`xy_system_settings` 键值模型。
- `backend-web/app/services/system_setting_service.py:65` 至 `backend-web/app/services/system_setting_service.py:74`：现有 captcha 默认键；`backend-web/app/services/system_setting_service.py:117` 至 `backend-web/app/services/system_setting_service.py:131`：免转义白名单；`backend-web/app/services/system_setting_service.py:188` 至 `backend-web/app/services/system_setting_service.py:220`：批量保存。
- `common/db/init_database.py:153` 至 `common/db/init_database.py:175`、`common/db/init_database.py:3309` 至 `common/db/init_database.py:3328`：第二套初始化默认值。
- `backend-web/app/api/routes/captcha.py:75` 至 `backend-web/app/api/routes/captcha.py:104`：远程配置请求模型和 key；`backend-web/app/api/routes/captcha.py:631` 至 `backend-web/app/api/routes/captcha.py:723`：管理员 GET/PUT 与批量保存。
- `frontend/src/api/admin.ts:152` 至 `frontend/src/api/admin.ts:187`：现有前端远程配置契约；`frontend/src/pages/admin/RiskLogs.tsx:56` 至 `frontend/src/pages/admin/RiskLogs.tsx:70`、`frontend/src/pages/admin/RiskLogs.tsx:127` 至 `frontend/src/pages/admin/RiskLogs.tsx:241`、`frontend/src/pages/admin/RiskLogs.tsx:481` 至 `frontend/src/pages/admin/RiskLogs.tsx:511`：同一配置区与保存流。
- `backend-web/app/api/routes/risk_control_logs.py:73` 至 `backend-web/app/api/routes/risk_control_logs.py:122`、`frontend/src/api/admin.ts:261` 至 `frontend/src/api/admin.ts:273`：现有即时保存的“本机滑块不处理”开关，可作 UX 对照但不建议复用为新接口。
- `common/services/captcha/orchestrator.py:59` 至 `common/services/captcha/orchestrator.py:78`：当前仅环境开关；`common/services/captcha/orchestrator.py:180` 至 `common/services/captcha/orchestrator.py:279`：远程优先及真实鼠标失败策略。
- `websocket/app/services/xianyu/cookie_token_manager.py:495` 至 `websocket/app/services/xianyu/cookie_token_manager.py:613`：本地 Token 刷新、远程配置与前置 local 队列。
- `websocket/app/api/routes/internal.py:421` 至 `websocket/app/api/routes/internal.py:440`：远程入口分流到 remote 队列。
- `common/services/captcha/weighted_runner.py:42` 至 `common/services/captcha/weighted_runner.py:191`、`common/services/captcha/weighted_scheduler.py:26` 至 `common/services/captcha/weighted_scheduler.py:34`：前置队列和现有数据库权重键。
- `backend-web/app/api/routes/password_login.py:50` 至 `backend-web/app/api/routes/password_login.py:86`、`backend-web/app/services/password_login/flow.py:78` 至 `backend-web/app/services/password_login/flow.py:117`：密码登录的独立能力判定和远程优先级。
- `common/db/compat.py:79` 至 `common/db/compat.py:130`、`common/db/compat.py:371` 至 `common/db/compat.py:387`：同步兼容读取会创建线程并同步等待，不适合直接放进 async 热路径。
- `common/services/captcha/real_mouse_slider.py:1071` 至 `common/services/captcha/real_mouse_slider.py:1111`：真实鼠标最终串行锁和执行入口。
