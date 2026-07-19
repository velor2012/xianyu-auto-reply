# 实施计划

> 本任务当前处于规划阶段。用户审阅并批准后，才执行 `task.py start` 和产品代码修改。

## 1. 增加 WebSocket 启动配置日志

- 修改 `websocket/_bootstrap.py`：配置解析前保存 `os.getenv("CAPTCHA_REAL_MOUSE")`，日志初始化后记录原始值 `repr` 和最终布尔值。
- 保持现有日志 sink、EXE 重定向和 `.env` 生成逻辑不变。

验证：定向导入/启动检查；Windows EXE 分别以未设置、true、false 启动并检查 `websocket.stdout.log`，另以空字符串启动确认异常重抛前记录 `process_env=''` 与 `parsed_enabled=<parse_failed>`。

## 2. 扩展系统设置与管理员 API

- 在 `backend-web/app/services/system_setting_service.py` 增加 `captcha.force_real_mouse=false` 默认值和免转义键。
- 在 `common/db/init_database.py` 增加相同初始化默认值。
- 扩展 `backend-web/app/api/routes/captcha.py` 的 `RemoteConfigUpdate`、GET 查询/返回和 PUT 批量保存。
- 保持现有管理员鉴权、返回结构和错误处理。

验证：缺键 GET 为 false；PUT true/false 后回显；非管理员仍被拒绝；旧库无需迁移。

## 3. 增加 RiskLogs 开关

- 扩展 `frontend/src/api/admin.ts` 的返回类型、保存参数和载荷。
- 在 `frontend/src/pages/admin/RiskLogs.tsx` 现有管理员验证码配置卡增加 state、加载回显和随保存提交的开关。
- 复用已有 `role="switch"`、loading、disabled 和 Toast 模式。
- 文案明确范围、物理鼠标占用和不可用直接失败。

验证：管理员加载、切换、保存、刷新回显；非管理员不显示管理员配置区；长文案在桌面和移动宽度不溢出。

## 4. 为编排器增加显式强制参数

- 修改 `common/services/captcha/orchestrator.py`，为 `run_slider_verification_with_fallback()` 增加默认 False 的 `force_real_mouse`。
- force=true 时跳过远程分支；`env OR force` 决定是否进入真实鼠标。
- force=true 且引擎不可用时直接失败；force=false 保持现有回退；验证失败和 URL 过期契约不变。
- 核对所有调用方，默认参数不得改变未迁移路径。

验证：覆盖 force/env/remote 组合和不可用失败，不写入非法 `captcha_engine`。

## 5. 接入 Token 刷新

- 扩展 `CookieTokenManager` 的现有异步设置查询，一次读取远程配置和强制键。
- force=true 时生成任务快照、跳过远程配置、进入现有 `local` weighted runner 并传显式强制参数。
- force=false 时保持当前分支和参数。

验证：本机任务按 local 排队；切换开关只影响下一任务；不调用同步 DB 兼容层。

## 6. 接入密码登录服务间调用

- 在 `password_login.py::_decide_mode()` 的异步查询中加入强制键，auto + force=true 选择协议。
- 在 `password_login/flow.py` 每轮滑块前异步读取 force 快照；force=true 时跳过远程并委托 WebSocket。
- 扩展 `WebSocketServiceClient.solve_captcha()` 与 WebSocket `SolveCaptchaRequest`，增加默认 false 的服务间强制字段。
- WebSocket 仅对本机密码登录标记使用 `local` 队列和显式强制参数；公开远程 API 固定不传播该字段，外部请求继续使用 remote/remote_cookie。

验证：密码登录强制时不调用远程；能力不可用时协议任务失败且不回退浏览器；外部接口行为、权重桶和超时保持不变。

## 7. 质量检查

- Python 编译：`python -m py_compile` 覆盖所有修改的 Python 文件。
- 运行新增的最小定向测试，至少覆盖配置 API、编排策略矩阵、Token/密码登录/外部三条入口。
- 前端执行仓库现有 `npm run lint` 和 `npm run build`；不重复已经验证通过且未受影响的用例。
- 执行 `git diff --check`，审查最终差异和公开 API 未传播强制字段。
- 代码修改后执行 `graphify update .`。
- 由 `trellis-check` 复核需求、跨层数据流、异步 DB 边界和回归风险。

## Windows 手工验收

1. 运行 `EXE打包构建.bat`，在有图形桌面、Chrome 和 pyautogui 的 Windows 环境启动发布包。
2. 未设置、true、false 三种环境值分别检查 `websocket.stdout.log` 启动快照。
3. 开启强制开关后，新 Token 刷新和密码登录使用真人鼠标；关闭后恢复原策略。
4. 故意让真实鼠标能力不可用，确认本机两条路径直接失败且不进入远程/Playwright/DrissionPage。
5. 确认外部 `/api/v1/captcha/slider-solve` 在开关开启前后行为一致。

## 回滚点

- 启动日志可独立回滚。
- 前端/API/默认键可一起回滚；数据库遗留键对旧版本无影响。
- 编排器、Token 刷新和密码登录服务间字段作为一个运行策略单元回滚。
- 紧急操作可先将 `captcha.force_real_mouse` 保存为 false，使随后任务立即恢复默认策略。
