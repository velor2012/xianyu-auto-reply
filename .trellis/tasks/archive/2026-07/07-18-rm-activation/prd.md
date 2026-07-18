# 移除 Windows 激活码认证

## Goal

让 Windows Nuitka EXE 启动后无需输入激活码或续期码即可进入现有配置和业务功能；已启动服务不再因许可证到期自动停止。

## Background / Confirmed Facts

- 当前分支为 `rm-actvatation`，基于 `main`，本轮只规划，不执行业务代码修改。
- Windows EXE 入口为 `launcher/main.py`，最终创建 `LauncherApp`。
- `launcher/gui.py` 首次启动通过 `load_and_verify_license()` 在配置页和激活页之间分流；激活页还负责激活码/续期码输入。
- `launcher/gui_running.py` 每 5 秒复查许可证，到期或无效时停止服务并返回激活页；运行页还提供启动器内的续期菜单。
- `EXE打包构建.bat` 使用 Nuitka 编译整个 `launcher` 包，并复制完整 `frontend/dist`、`backend-web` 等目录。
- `frontend/src/pages/auth/RenewActivation.tsx` 及 `backend-web/app/api/routes/activation.py` 是线上公开的续期码签发页面/API，不是 Windows EXE 的运行时认证调用方。
- 仓库当前没有覆盖激活认证或 Windows EXE 启动行为的自动化测试。

## Requirements

### R1. Windows EXE 可直接进入配置流程

取消启动器首次运行时的许可证认证分流，使没有 `data/license.dat`、许可证过期或许可证无效时，仍直接进入现有配置页面。

### R2. Windows EXE 不因许可证到期停服

移除运行期许可证复检导致的自动停止服务和跳转激活页；保留窗口关闭、手动停止、更新退出等与许可证无关的服务管理行为。

### R3. 隐藏 Windows 启动器认证入口

移除 Windows 启动器中可见的激活/续期入口及运行路径，避免用户继续进入这些页面；按已确认范围保留底层认证模块文件。

### R4. 保持线上签发能力

保留线上 `RenewActivation.tsx`、`GetActivation.tsx`、激活 API、历史记录和数据库日志，不改变普通 Web 用户生成激活码/续期码的能力。

### R5. 保持打包可用

`EXE打包构建.bat` 完成构建后，发布包应可在无激活文件的新目录中启动，并正常进入现有配置、服务启动和业务功能流程。

## Acceptance Criteria

- [ ] 新 Windows EXE 在不存在 `data/license.dat` 时不显示激活页，直接显示配置页。
- [ ] 启动器配置完成后可以按现有流程启动服务，不依赖激活文件。
- [ ] 许可证到期/无效不会触发自动停服或跳回激活页。
- [ ] Windows 启动器运行页面不再提供激活码续期/注销入口。
- [ ] 线上 `/renew-activation` 页面和 `/api/v1/activation/renew` 行为保持不变。
- [ ] `EXE打包构建.bat` 无需引入额外构建步骤，发布包构建成功。
- [ ] 现有非许可证相关的启动、停止、更新和服务管理行为未被改变。

## Scope Decision

- 已确认采用“仅改行为”：不删除 `launcher/activation.py`、`launcher/keygen.py`、`launcher/gui_renew.py`，不删除线上签发页面/API。
- 修改启动器 GUI 的启动分流、运行期到期处理和续期菜单可见性，使 Windows EXE 不再强制认证；保留认证模块作为未调用代码，降低本次改动范围。
