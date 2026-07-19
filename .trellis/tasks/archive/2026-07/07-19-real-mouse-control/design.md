# 技术设计

## 边界

本任务只增加启动可观测性和一个数据库强制策略。环境变量继续表示部署级默认能力，数据库键只对本机业务入口提供运行时强制覆盖。外部过滑块接口保持现状。

不新增表、依赖或独立 API。复用 `SystemSetting`、验证码配置 API、RiskLogs 管理员配置卡、`WeightedTaskRunner` 和现有编排返回值。

## 配置契约

```text
环境变量：CAPTCHA_REAL_MOUSE -> bool，默认 false
数据库键：captcha.force_real_mouse -> "true" | "false"，默认 "false"

GET /api/v1/captcha/remote-config
  新增 force_real_mouse: boolean

PUT /api/v1/captcha/remote-config
  新增 force_real_mouse: boolean
```

`captcha.force_real_mouse` 同时加入 `SystemSettingService.DEFAULT_SYSTEM_SETTINGS`、`NO_ESCAPE_KEYS` 和 `DatabaseInitializer.DEFAULT_SETTINGS`。GET 缺键时返回 `false`，兼容旧数据库。

## 启动日志

`websocket/_bootstrap.py` 在 `get_settings()` 前读取：

```text
raw = os.getenv("CAPTCHA_REAL_MOUSE")
```

完成 `setup_logging()` 后记录一条启动快照：

```text
CAPTCHA_REAL_MOUSE 启动配置: process_env=<repr>, parsed_enabled=<bool>
```

该日志通过 Loguru `stderr` sink 和现有 EXE 子进程重定向进入 `websocket.stdout.log`，同时进入轮转的 `websocket.log`。不修改打包脚本或启动器日志。若 Pydantic 解析失败，bootstrap 在重新抛出异常前直接向 `sys.stderr` 输出一次仅含 `CAPTCHA_REAL_MOUSE` 原始值和 `parsed_enabled=<parse_failed>` 的诊断，并使用 `flush=True`；不得吞异常或记录其他配置。

## 策略矩阵

| 入口 | `force=false` | `force=true` |
| --- | --- | --- |
| Token 刷新 | 完全保持现有远程优先、env 和兜底顺序 | 跳过远程，进入 `local` 加权队列，强制真实鼠标 |
| 密码登录 | 保持当前 auto/browser/protocol 与远程优先逻辑 | auto 视为协议能力；登录滑块跳过远程，经 WebSocket `local` 队列强制真实鼠标 |
| 外部过滑块 | 保持当前 `remote` / `remote_cookie` 及 env 行为 | 不读取也不应用数据库开关，行为不变 |

有效选择不是全局改写 `_real_mouse_enabled()`，而是本次任务显式传入：

```text
use_real_mouse = env_enabled OR force_real_mouse
```

只有 `force_real_mouse=true` 才跳过本机业务路径上的远程分支。这样 `force=false + env=true` 仍保留当前“远程优先于真实鼠标”行为。

## 数据流

### Token 刷新

`CookieTokenManager` 在现有异步设置查询中同时读取远程配置和 `captcha.force_real_mouse`，形成任务开始快照。

- false：沿用当前参数和线程池分支。
- true：不传远程配置，给编排器传 `force_real_mouse=True`，通过 `real_mouse_weighted_runner.submit("local", ...)` 执行。

禁止在事件循环中调用同步 `db_manager.get_system_setting()`。

### 密码登录

`password_login._decide_mode()` 将新键加入现有异步查询；auto 模式下 force=true 选择协议登录。

`password_login.flow` 在每次登录滑块开始前异步读取远程配置和 force 快照：

- false：有远程仍先远程。
- true：不调用远程，使用 `WebSocketServiceClient.solve_captcha(..., call_type="local", force_real_mouse=True)`。

扩展既有服务间 `SolveCaptchaRequest`，增加默认 `False` 的 `force_real_mouse` 字段。公开 `/api/v1/captcha/slider-solve` 不接受也不传播该字段。WebSocket 内部处理仅在服务间本机调用标记为真时进入 `local` 队列；现有外部请求继续硬编码为 `remote` / `remote_cookie`，不能用请求字段改变远程权重桶。

内部 WebSocket 路由当前没有独立服务鉴权，因此实现和审查必须确保该标记不从公开 backend API 暴露。此任务不扩展现有信任边界；后续若开放 WebSocket 内部端口给不受信网络，应单独增加服务间认证。

### 外部调用

公开过滑块 API 始终调用 WebSocket 时传 `force_real_mouse=False`。WebSocket 不为该路径查询数据库强制键，继续按环境变量决定真实鼠标并保持远程队列、Cookie 重取、容量限制和超时语义。

## 编排与失败

`run_slider_verification_with_fallback()` 增加默认 `False` 的显式参数。

1. force=false：执行现有远程分支。
2. force=true：跳过远程分支。
3. `env OR force` 为真：加载真实鼠标引擎。
4. force=true 且导入失败或 `REAL_MOUSE_AVAILABLE=False`：记录明确错误并直接返回现有失败三元组。
5. force=false + env=true 且引擎不可用：保持当前回退普通引擎行为。
6. 引擎可用但验证失败：保持当前失败不回退；`URL_EXPIRED` 契约不变。

不新增错误枚举，避免污染 `captcha_engine` 字段。日志和现有失败状态承担诊断信息。

## 前端

在 RiskLogs 现有管理员验证码配置卡中：

- 增加 `forceRealMouse` state；
- 加载时读取 `force_real_mouse`；
- 随现有保存按钮提交；
- 复用当前 `role="switch"`、loading 和 disabled 模式；
- 文案说明仅影响新开始的 Token 刷新和密码登录，会占用本机物理鼠标，能力不可用时任务直接失败。

## 兼容与回滚

数据库键缺失默认 false；旧版本会忽略新键。页面关闭开关即可让新任务恢复原策略，正在执行的任务自然完成。代码可按启动日志、配置/UI、运行编排三个单元回滚，无数据库迁移回滚。
