# 实施计划

> 当前仅为待确认计划。用户确认后才执行 `task.py start` 并进入代码实施。

## 1. 启动流程取消认证拦截

- 修改 `launcher/gui.py`：启动器初始化完成后直接进入现有配置页面。
- 保留本次范围外的认证模块和方法，但确认启动主路径不再调用许可证校验。
- 确认没有 `license.dat`、许可证过期和许可证损坏三种状态均不影响进入配置页。

验证点：启动主路径不读取许可证作为页面分流条件；配置保存和服务启动调用保持原样。

## 2. 运行流程取消到期限制

- 修改 `launcher/gui_running.py`：自动刷新不再执行许可证到期检查。
- 移除许可证无效/过期触发的自动停服和激活页跳转路径。
- 移除运行页中的激活到期信息、倒计时、“激活码续期”菜单和对应菜单分支。
- 保留服务状态刷新、手动停止、关闭窗口及更新流程。

验证点：原许可证过期后服务状态刷新仍继续，且不会调用 `stop_all()`。

## 3. 保持范围外能力不变

- 不修改 `launcher/activation.py`、`launcher/keygen.py`、`launcher/gui_renew.py`。
- 不修改 `frontend/src/pages/auth/RenewActivation.tsx`、`frontend/src/api/activation.ts`。
- 不修改 `backend-web/app/api/routes/activation.py`、激活历史表和路由注册。
- 不修改 `EXE打包构建.bat`。

验证点：最终差异仅包含计划文件及 `launcher/gui.py`、`launcher/gui_running.py` 的行为变更。

## 4. 质量检查

- 静态检查修改文件可正常导入/编译：`python -m py_compile launcher/gui.py launcher/gui_running.py`。
- 使用定向搜索确认启动路径不再调用 `_check_and_show_page()` 的许可证分流，运行刷新不再调用 `_check_expire()`，运行菜单不再出现 `renew`。
- 检查 `git diff --check` 和最终差异，确认没有修改线上签发页面/API或打包脚本。
- 由于仓库没有相关自动化测试，增加一个最小、无需 Tk 主循环和 Windows 图形环境的回归检查；若现有结构无法低成本隔离，则记录为手工验证而不引入测试框架。
- Windows 实机执行 `EXE打包构建.bat`，在无 `data/license.dat` 的新发布目录启动 EXE：应直接进入配置页并可启动服务。
- Windows 实机放置过期/损坏的 `license.dat` 后再次启动：仍应直接进入配置页，运行中不自动停服。
- 检查运行页无激活到期信息和续期菜单。

## 5. 审查与提交

- 由 `trellis-check` 复核需求范围、数据流和回归风险。
- 代码变更后执行 `graphify update .`。
- 用户确认验证结果后，再按 Trellis Phase 3 更新必要规范并提交到 `rm-actvatation` 分支。

## 回滚点

若启动或运行状态刷新受影响，只回滚 `launcher/gui.py` 与 `launcher/gui_running.py`；无需回滚线上页面、API、数据库或构建脚本。
