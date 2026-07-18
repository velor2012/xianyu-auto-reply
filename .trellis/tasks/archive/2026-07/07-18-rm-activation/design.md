# 技术设计

## 目标边界

只改变 Windows 启动器的行为，不改变线上 Web 激活码签发能力，也不删除现有认证模块。认证代码可以继续随 Nuitka 的 `launcher` 包进入发布物，但不得再参与启动、运行期停服或 Windows 端续期入口展示。

## 现状数据流

```text
launcher/main.py
  -> launcher/_bootstrap.py
  -> LauncherApp
  -> _check_and_show_page()
  -> load_and_verify_license()
  -> 配置页 / 激活页

运行页自动刷新
  -> _check_expire()
  -> load_and_verify_license()
  -> stop_all() + 激活页
```

线上签发链路独立存在：

```text
RenewActivation.tsx
  -> frontend/src/api/activation.ts
  -> POST /api/v1/activation/renew
  -> backend-web/app/api/routes/activation.py
```

## 设计方案

### 启动阶段

在 `launcher/gui.py` 中保留现有 GUI 初始化、机器码字段和认证模块，但将首次页面选择固定到现有配置页面。这样不需要激活文件也可以进入数据库/Redis 配置流程，且不改服务启动逻辑。

激活页相关方法可以保留但不再从首次启动路径进入，以控制本次差异；实施时应确认没有其他入口误跳转到激活页。

### 运行阶段

在 `launcher/gui_running.py` 中移除许可证到期复检对运行状态的影响：

- 自动刷新不再调用 `_check_expire()`。
- 不再因许可证状态调用 `ServiceManager.stop_all()` 或跳转激活页。
- 删除运行页的“激活码续期”菜单项和 `renew` 分支，避免 Windows 端继续暴露认证入口。
- 删除或停用仅用于显示许可证到期倒计时的 UI，避免向用户展示无意义的认证状态。
- 保留服务状态刷新、手动停止、窗口关闭、更新退出等非认证逻辑。

### 打包与线上能力

不修改 `EXE打包构建.bat`，因为其编译入口、资源复制和服务启动方式与认证拦截解耦。保持 `frontend/dist`、`backend-web/app/api/routes/activation.py` 和线上路由不变，线上页面仍可签发续期码。

## 兼容与风险

- 旧用户的 `data/license.dat` 不删除，也不再作为进入系统的前置条件。
- 认证模块保留意味着发布包可能仍包含相关代码，但这是已确认的“仅改行为”范围。
- 运行期取消到期停服后，许可证到期不会再限制业务功能；这是本次需求的预期行为。
- 需要重点防止删除/调整自动刷新逻辑时误伤服务状态更新或手动停止流程。

## 回滚

若验证发现启动器流程异常，可回滚 `launcher/gui.py` 和 `launcher/gui_running.py` 的本次变更；线上前端、后端 API、数据库和打包脚本无需回滚。
