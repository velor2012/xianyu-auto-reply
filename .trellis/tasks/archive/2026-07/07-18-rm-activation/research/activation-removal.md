# Windows EXE 移除激活认证调研

## 结论

目标“Windows EXE 无需激活即可直接使用”的最小行为改动集中在启动器 GUI：取消首次启动的许可证分流，以及取消运行中每 5 秒的到期复检和停服。`launcher/main.py` 和 `launcher/_bootstrap.py` 只是入口与 GUI 分发，不含认证判断，不应修改。

线上激活码签发网站/API 与 Windows 启动器没有运行时调用关系，可以保持不动。需要注意：当前 EXE 构建会把整个 `frontend/dist` 和 `backend-web` 复制进发布目录，因此“保持线上功能不变”会使这些页面/API 的代码仍出现在 EXE 中，但不会再阻止 EXE 使用。若额外要求 EXE 产物不含任何签发代码，需另做打包配置拆分，不属于最小行为改动。

## 1. 启动拦截链

调用路径：

```text
launcher/main.py:_run_main
  -> launcher/_bootstrap.py:main
  -> LauncherApp()
  -> LauncherApp._check_and_show_page()
  -> load_and_verify_license(machine_id)
  -> _show_config_page() 或 _show_activation_page()
```

证据与建议：

| 文件 | 位置 | 当前行为 | 最小变更 |
| --- | --- | --- | --- |
| `launcher/main.py` | 43-49 | 导入并调用 `_bootstrap.main`。 | 不改。 |
| `launcher/_bootstrap.py` | 10-43 | 无参数时构建 `LauncherApp`；`--run-service` 直接运行子服务。 | 不改。子服务路径从未做许可证检查。 |
| `launcher/gui.py` | 18-25, 72-73, 145-152 | 导入认证函数，生成机器码，`_check_and_show_page()` 决定进入配置页还是激活页。 | 将 `_check_and_show_page()` 固定为 `_show_config_page()`；删除认证相关导入和 `machine_id` 属性。 |
| `launcher/gui.py` | 156-301 | `_show_activation_page()` 和 `_do_activate()` 显示机器码、跳转线上签发页、校验/保存激活码或续期码。 | 删除整个激活页及两个辅助方法。 |

配置页的“保存配置并启动服务”最终调用 `ServiceManager.start_all()`（`launcher/gui.py` 319-362 左右），该路径本身不校验证书。因此取消上述唯一分流后，首次打开 EXE 即到达现有连接配置和服务启动流程。

## 2. 运行中到期检查和停服

调用路径：

```text
show_running_page()
  -> _auto_refresh() 每 5 秒
  -> _check_expire()
  -> load_and_verify_license(machine_id)
  -> ServiceManager.stop_all()
  -> _show_expire_page() -> LauncherApp._show_activation_page()
```

`launcher/gui_running.py` 是运行期唯一的许可证复检点，且也是唯一会因许可证无效停止已启动服务的路径：

| 文件 | 位置 | 当前行为 | 最小变更 |
| --- | --- | --- | --- |
| `launcher/gui_running.py` | 17-21 | 导入许可证读取和到期展示函数。 | 删除这些导入。 |
| `launcher/gui_running.py` | 25-33, 145-146 | 左侧菜单包含“激活码续期”，并动态导入 `gui_renew.render_renew_page`。 | 删除该菜单项和 `renew` 分支。 |
| `launcher/gui_running.py` | 174-191 | 服务状态页读取并显示激活到期时间。 | 删除整个到期信息区及 `_expire_ts` / `_remain_label` 状态。 |
| `launcher/gui_running.py` | 389-422 | `_auto_refresh()` 调用 `_check_expire()`；后者无效/过期时异步 `stop_all()` 并跳转激活页。 | 删除 `_check_expire()`、`_show_expire_page()` 和该调用；`_update_remaining()` 同时删除。 |
| `launcher/service_manager.py` | 473-510 | `stop_all()` 关闭前端 HTTP 服务、终止三个 Python 子服务、按端口清理 8089/8090/8091/9000。 | 不改。保留其窗口关闭、手动停止、更新前退出等正常用途。 |

不存在服务进程内的第二套 EXE 激活校验：`--run-service` 分支直接进入 `launcher/service_runner.py`，三个子服务也没有导入 `launcher.activation`。移除 GUI 复检即可防止因到期自动停服。

## 3. 续期模块和打包关系

### 启动器模块

`launcher/gui_renew.py` 只由 `launcher/gui_running.py` 的 `renew` 菜单分支导入。它读取许可证、提交续期码、打开 `https://xy.zhinianboke.com/renew-activation`，并提供“注销激活”；注销前也会调用 `stop_all()`（15-20, 61-168, 178-194）。删除该菜单分支后，此文件没有其他调用方。

`launcher/activation.py` 的直接调用方为：

| 调用方 | 用途 | 处理建议 |
| --- | --- | --- |
| `launcher/gui.py` | 首次认证和保存 `data/license.dat`。 | 随启动拦截一起删除。 |
| `launcher/gui_running.py` | 到期展示和运行期停服。 | 随运行期检查一起删除。 |
| `launcher/gui_renew.py` | 续期/注销页面。 | 删除该页面后消失。 |
| `launcher/keygen.py` | 本地命令行生成激活码。 | 若删除 `launcher/activation.py`，必须同时删除或改造该开发工具；它仅服务于被废弃的本地签发流程。 |

`launcher/hardware_id.py` 只保留对旧 `license.dat` 的兼容说明，没有导入或调用 `activation.py`，不需要为此任务调整。

### Windows EXE 构建

构建脚本是根目录 `EXE打包构建.bat`，使用 Nuitka，不是 PyInstaller：

1. 61-77：在 `frontend/` 执行 `npm ci` 和 `npm run build`，得到 `frontend/dist`。
2. 90-158：以 `launcher/main.py` 为入口，使用 `--include-package=launcher`。因此 `launcher/activation.py`、`launcher/gui_renew.py`、`launcher/keygen.py` 都会随整个 `launcher` 包纳入编译依赖范围，脚本没有这些文件的单独 include/exclude 规则。
3. 169-180：复制 `backend-web`、`websocket`、`scheduler`、`common` 和整个 `frontend/dist` 到发布目录。
4. `launcher/service_manager.py` 379-410 从发布目录中的 `frontend/dist` 启动本地 9000 静态服务。

因此有两种边界：

- **最小行为改动（推荐）**：修改 GUI 启动/运行时检查，删除 `gui_renew.py`（以及若要彻底清理启动器认证实现则删除 `activation.py` 和 `keygen.py`）。无需修改 `EXE打包构建.bat`；重建后 Nuitka 不会再有被删除的模块。
- **EXE 产物零签发代码（非最小）**：构建脚本须为 Windows 创建单独的前端构建产物，并在复制 `backend-web` 前排除 `app/api/routes/activation.py`。这会使同一套构建无法同时承载线上签发站点，需维护独立产物/构建开关，当前需求没有必要。

## 4. `RenewActivation.tsx` 与线上签发边界

`frontend/src/pages/auth/RenewActivation.tsx` 不被 launcher Python 代码导入。它的关系是：

```text
frontend/src/App.tsx
  -> /renew-activation 公共路由
  -> RenewActivation.tsx
  -> frontend/src/api/activation.ts: generateRenewCode()
  -> POST /api/v1/activation/renew
  -> backend-web/app/api/routes/activation.py: generate_renew_activation()
```

`EXE打包构建.bat` 执行完整 Vite 构建并复制全部 `frontend/dist`，所以该页会作为前端静态产物被随包携带；本地导航栏则因 `hideOnLocal: true` 不显示其入口（`frontend/src/components/common/AuthNavbar.tsx` 15-27）。即使不修改前端，网页路由仍可被手动访问，但已没有 Windows 客户端使用其生成的续期码。

以下线上功能可保持不动：

| 文件 | 保持原因 |
| --- | --- |
| `frontend/src/pages/auth/GetActivation.tsx` | 线上公开获取试用激活码页面；不参与 EXE 启动。 |
| `frontend/src/pages/auth/RenewActivation.tsx` | 线上公开生成续期码页面；不参与 EXE 启动。 |
| `frontend/src/api/activation.ts` | 上述两个公开页面的 API 客户端。 |
| `frontend/src/App.tsx` 18-19, 317-318 | 注册两个公开网页路由。 |
| `frontend/src/components/common/AuthNavbar.tsx` 24-27 | 仅在线上域名展示签发入口。 |
| `backend-web/app/api/routes/activation.py` | 提供 `POST /generate`、`POST /renew`、`POST /history`，写入 `xy_activation_logs`。 |
| `backend-web/app/api/routes/_exports.py` 89 | 将该公开路由注册为 `/api/v1/activation`。 |
| `common/db/init_database.py` 1198 起 | 建表 `xy_activation_logs`。 |

保留这些线上组件不影响“EXE 可直接启动”；不要因普通 Web 用户的签发/历史记录而删表或改变线上 API。

## 5. 现有测试覆盖

仓库中存在 `tests/`、`backend-web/tests/`、`scheduler/tests/`、`websocket/tests/` 目录，但当前均无测试文件。对这四个目录以及已跟踪源码检索 `activation`、`license`、`renew-activation`、`launcher.activation`、`gui_renew`、`Nuitka` 均未发现测试引用。

因此当前没有覆盖：

- 未激活或过期时首次启动是否直接进入配置页；
- 服务运行超过原许可到期时间后是否持续运行；
- 续期菜单是否不再出现；
- Windows Nuitka 发布包是否能在不存在 `data/license.dat` 的新目录启动。

实现后应至少手工验证最后一项和前两项；目前没有可复用的现有自动化用例。

## 建议范围

推荐采用“移除 Windows 启动器认证，保留线上签发服务”的范围：修改 `launcher/gui.py` 与 `launcher/gui_running.py`，删除不再可达的 `launcher/gui_renew.py`；若目标包含删除 EXE 内认证实现，再连同 `launcher/activation.py` 和依赖它的 `launcher/keygen.py` 一起删除。不要修改 `launcher/main.py`、`launcher/_bootstrap.py`、`launcher/service_manager.py`，也不要修改线上前端签发页面、API 路由或数据库表。
