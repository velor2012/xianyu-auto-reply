# EXE WebSocket 启动配置观测研究

## 结论

最小改动位于 `websocket/_bootstrap.py`：在 `settings = get_settings()` 前读取 `os.getenv("CAPTCHA_REAL_MOUSE")`，在 `setup_logging(...)` 完成后写一条 `logger.info`，同时记录 `repr(raw_value)` 和 `settings.captcha_real_mouse_enabled`。

不需要修改 EXE 打包脚本或 `ServiceManager` 才能使该信息进入 `websocket.stdout.log`。实际 WebSocket Python 子进程的 stderr 已被重定向到该文件，Loguru 的控制台 sink 正是 `sys.stderr`。

推荐日志语义（示例，非实现代码）：

```text
CAPTCHA_REAL_MOUSE 启动配置: process_env='true', parsed_enabled=True
```

`repr` 必须保留：它可区分未设置 (`None`)、空字符串 (`''`) 与字面值（例如 `'true'`）。该日志是启动快照；`get_settings()` 有 LRU 缓存，运行中改环境变量不会刷新最终值。

## 当前链路

```text
父进程环境
  -> ServiceManager.start_python_service(): os.environ.copy()
  -> 冻结 EXE --run-service websocket
  -> service_runner.run_service(): os.environ.copy()
  -> pythonw.exe websocket/main.py
  -> websocket/_bootstrap.py: get_settings()
       -> BaseSettings 读取进程环境/.env
       -> BaseConfig.captcha_real_mouse_enabled
  -> Loguru stderr sink
  -> websocket/logs/websocket.stdout.log
```

1. `ServiceManager.generate_env_files()` 每次启动写入 `websocket/.env`，但目前没有 `CAPTCHA_REAL_MOUSE`。因此 EXE 场景的该变量通常来自启动器自身继承的父进程环境，而不是生成的 `.env`。
2. `start_python_service()` 以 `os.environ.copy()` 构造子进程环境，并将外层 EXE 的 stdout/stderr 合并到 `websocket/logs/websocket.stdout.log`。
3. 冻结模式下外层 EXE 再由 `service_runner` 以 `pythonw.exe` 启动真正的服务；该处再次复制环境，并再次把 Python 子进程 stdout/stderr 合并写入同一 stdout 日志文件。实际服务日志由第二次重定向落盘。
4. WebSocket bootstrap 在模块加载时构造配置，并在之后调用 `setup_logging()`。该函数把 Loguru 控制台 sink 绑定到 `sys.stderr`，故 bootstrap 随后的 `logger.info` 会写入 stdout 日志，同时也会写入 `websocket.log`。

## 最小实现范围

仅修改 `websocket/_bootstrap.py`：

1. 导入 `os`。
2. `get_settings()` 前保存 `raw_captcha_real_mouse = os.getenv("CAPTCHA_REAL_MOUSE")`。
3. `setup_logging(...)` 后记录一次原始值和已解析布尔值。

不要在 `launcher/service_manager.py` 额外打印：它只能确认传给外层 EXE 的环境，不能确认真正 WebSocket 进程使用的 Pydantic 解析结果。不要在 `EXE打包构建.bat` 写死 `CAPTCHA_REAL_MOUSE=true`：这会改变默认行为，并让无桌面/无依赖的机器启动时进入误配置回退。

### 无效值的边界

`get_settings()` 在日志初始化之前执行。若 Pydantic 因无效布尔字面值启动失败，正常的 `logger.info` 无法出现；异常 traceback 仍会进入 `websocket.stdout.log`。若验收要求也必须记录无效原始值，需要在解析前额外 `print(..., flush=True)`，但这会产生两种日志路径，非正常启动场景不建议作为最小方案的一部分。

### `.env` 与进程环境的边界

`os.getenv()` 只观测真实进程环境，不会读 `.env` 文件。当前 Launcher 生成的 websocket `.env` 不含此键，因而这正好对应 EXE 的实际输入。若未来把该键写入 `.env`，日志应明确字段名为 `process_env`，避免把 `None` 误解为“没有任何配置来源”。若产品要求记录 `.env` 原文来源，需要单独定义优先级与脱敏规则。

## 风险

- **打包依赖风险：** `websocket/pyproject.toml` 将 `pyautogui` 声明为 Windows 可选依赖；`EXE打包构建.bat` 没有显式 `--include-package=pyautogui`。真实鼠标模块又是惰性导入。必须在 Windows release 包内实际验证该依赖及其子依赖可导入，不能仅凭构建成功判断。
- **运行环境风险：** 真实鼠标引擎要求有图形桌面的 Windows、可用的 `pyautogui`，还以 `channel="chrome"` 启动可见本机 Chrome。它会接管物理光标，且与 Launcher 写入的 `BROWSER_HEADLESS=true` 是不同路径；真实鼠标会强制 `headless=False`。
- **日志截断行为：** 两层启动都以 `"w"` 打开同一个 stdout 日志。实际 Python 服务的 stderr 会落入文件，但每次重启会覆盖旧 stdout 内容；长期诊断应同时检查带轮转的 `websocket/logs/websocket.log`。

## 建议验证

1. Windows EXE 在命令提示符中以 `CAPTCHA_REAL_MOUSE=true` 启动，确认 `websocket/logs/websocket.stdout.log` 有一条 `process_env='true', parsed_enabled=True`。
2. 不设置该变量重新启动，确认同一行显示 `process_env=None, parsed_enabled=False`。
3. 设置非法值并启动，确认 stdout 日志至少有 Pydantic 启动异常；若验收要求必须含原始值，再决定是否加入解析前 `print`。
4. 从 release 目录使用实际子服务解释器导入 `pyautogui`，并执行一次受控、可见桌面的真实鼠标滑块冒烟验证。不得在无人值守或用户正在使用鼠标的桌面执行。

## 证据

- `EXE打包构建.bat:93` 至 `EXE打包构建.bat:164`：Nuitka standalone 构建参数；`common` 被打包但无显式 `pyautogui` include。
- `EXE打包构建.bat:171` 至 `EXE打包构建.bat:242`：复制服务源码、清除原有 `.env` 和日志目录。
- `launcher/service_manager.py:217` 至 `launcher/service_manager.py:237`：每次生成 websocket `.env`，未写入 `CAPTCHA_REAL_MOUSE`。
- `launcher/service_manager.py:300` 至 `launcher/service_manager.py:355`：复制父环境并把外层服务 stdout/stderr 重定向到 `<service>/logs/<name>.stdout.log`。
- `launcher/service_runner.py:220` 至 `launcher/service_runner.py:265`：冻结模式再次复制环境，并将实际 Python 子服务 stdout/stderr 写入相同 stdout 日志。
- `common/core/config.py:27` 至 `common/core/config.py:31`：`BaseSettings` 配置 `.env`；`common/core/config.py:94` 至 `common/core/config.py:99`：`CAPTCHA_REAL_MOUSE` 映射到布尔字段。
- `websocket/_bootstrap.py:26` 至 `websocket/_bootstrap.py:39`：配置先加载，随后设置 Loguru。
- `common/utils/logging_utils.py:80` 至 `common/utils/logging_utils.py:100`：控制台 sink 为 `sys.stderr`，文件 sink 为 websocket.log。
- `websocket/pyproject.toml:36` 至 `websocket/pyproject.toml:38`：Windows 条件 `pyautogui` 依赖。
- `common/services/captcha/real_mouse_slider.py:11` 至 `common/services/captcha/real_mouse_slider.py:15`、`common/services/captcha/real_mouse_slider.py:52` 至 `common/services/captcha/real_mouse_slider.py:62`、`common/services/captcha/real_mouse_slider.py:337` 至 `common/services/captcha/real_mouse_slider.py:348`：桌面、依赖、可见 Chrome 的运行条件。
