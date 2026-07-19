# 真人鼠标运行配置与强制开关

## Goal

让 Windows EXE 的 WebSocket 启动日志明确显示 `CAPTCHA_REAL_MOUSE` 的进程环境原值与最终解析结果，并允许管理员在风控日志页面动态强制本机业务滑块使用真实鼠标引擎。

## Background / Confirmed Facts

- `EXE打包构建.bat` 会删除发布目录中的服务 `.env`；启动器每次启动服务时由 `ServiceManager.generate_env_files()` 覆盖生成新 `.env`。
- EXE 子服务通过 `os.environ.copy()` 继承启动器环境；`BaseConfig.captcha_real_mouse_enabled` 从 `CAPTCHA_REAL_MOUSE` 解析布尔值，默认 `false`。
- WebSocket 的 Loguru 控制台 sink 写入 `stderr`，冻结启动链路将其重定向到 `websocket/logs/websocket.stdout.log`。
- 风控日志页面已有仅管理员可见的验证码配置区、`system_settings` 持久化和 `GET/PUT /api/v1/captcha/remote-config`，本任务复用该链路。
- 当前默认顺序为远程服务优先，再按环境变量决定真实鼠标，最后使用 Playwright/DrissionPage；默认行为必须保持兼容。

## Requirements

### R1. 输出启动配置

WebSocket 每次启动时，在日志初始化后记录一次 `CAPTCHA_REAL_MOUSE` 的进程环境原值和 Pydantic 最终解析值。原始值使用可区分 `None`、空字符串和字面值的表示方式；不得记录其他配置或敏感信息。

### R2. 增加强制开关

风控日志页面的管理员验证码配置区新增“强制使用真实鼠标引擎”开关。状态使用 `system_settings` 键 `captcha.force_real_mouse` 持久化，默认关闭，随现有验证码配置保存并在刷新页面后正确回显。

### R3. 采用叠加语义

- 开关关闭：完全保持现有调用方式；`CAPTCHA_REAL_MOUSE=true` 时仍按当前逻辑使用真实鼠标，页面开关不得反向关闭环境变量能力。
- 开关开启：只对新开始的本机 Token 刷新和密码登录滑块强制使用真实鼠标，并跳过这两条路径上的远程优先逻辑。
- 外部系统调用本机过滑块接口不读取、不传递、也不应用该数据库开关，继续保持当前环境变量、远程队列和权重语义。
- 已运行任务不因开关变化被中断或切换引擎。

### R4. 强制失败契约

开关开启后，真实鼠标模块导入失败、运行能力不可用或验证失败时，本次任务直接失败，不回退远程服务、Playwright、DrissionPage 或浏览器登录模式。开关关闭时保留当前不可用回退行为。

### R5. 保持最小范围

复用现有配置 API、数据表、前端配置卡、真实鼠标加权队列和失败响应，不新增依赖、数据表、独立页面或独立配置服务。

## Acceptance Criteria

- [ ] Windows EXE 启动 WebSocket 后，`websocket/logs/websocket.stdout.log` 含 `CAPTCHA_REAL_MOUSE` 原始进程值与最终解析值。
- [ ] 未设置、设置为 `true`、设置为 `false` 时，启动日志分别显示正确快照；设置为空字符串时启动失败，并在 `websocket.stdout.log` 中记录 `process_env=''` 与解析失败标记。
- [ ] 管理员可加载、保存并回显强制开关；非管理员继续由现有鉴权拒绝访问配置接口。
- [ ] 旧数据库缺少 `captcha.force_real_mouse` 时 GET 返回 `false`，无需数据库迁移。
- [ ] `force=false, env=false` 时，Token 刷新、密码登录和外部调用保持当前策略。
- [ ] `force=false, env=true` 时，仍保留当前环境变量与远程优先级行为。
- [ ] `force=true` 时，新 Token 刷新与密码登录跳过远程并通过既有 `local` 加权队列使用真实鼠标。
- [ ] `force=true` 且真实鼠标不可用或失败时，本机业务任务直接失败且不进入其他引擎。
- [ ] 外部过滑块调用在 `force=true` 时仍保持 `remote` / `remote_cookie` 队列及当前引擎选择。
- [ ] 开关切换只影响随后开始的任务，不改变正在执行任务和现有队列权重。

## Out of Scope

- 不改变 `CAPTCHA_REAL_MOUSE` 默认值或启动器生成 `.env` 的字段集合。
- 不新增真实鼠标就绪探针、运行状态页面或 `pyautogui` 自动安装。
- 不修改历史风控日志。
