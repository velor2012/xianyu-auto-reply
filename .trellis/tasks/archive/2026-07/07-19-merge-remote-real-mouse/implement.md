# 实施计划

> 当前只完成合并规划。计划通过门禁后才执行 `task.py start`、rebase、冲突解决和推送。

## 1. 建立安全基线

- `git fetch origin rm-actvatation`，记录最新远端端点和 merge-base。
- 创建仅本地回退引用指向当前 `0c1eaa8`。
- 确认 tracked 工作区干净；保留所有无关未跟踪文件。

## 2. Rebase 与基础配置冲突

- 执行 `git rebase origin/rm-actvatation`。
- 先恢复 `CAPTCHA_REAL_MOUSE` 字段和启动诊断。
- 合并 `captcha.force_real_mouse`、`captcha.slider_mode`、`password_login.mode` 默认值、白名单和规范化。
- 历史 `auto` 统一规范化为 browser。

## 3. 编排与服务间契约冲突

- 合并 orchestrator 的 force 与 slider mode/environment 选择。
- 合并 WebSocket client 的 `force_real_mouse` 与 `precreated_log_id`。
- 合并 internal 请求、队列桶、slider mode 刷新和 `_risk_log_id` 回执。
- 搜索所有调用方，保证新增参数默认值和关键调用显式值正确。

## 4. 本机业务与公开远程入口

- Token 刷新同时保留远程配置、force、slider mode 快照和统一 Token 验证。
- 密码登录采用 browser/protocol；force=true 覆盖并在每轮滑块跳过远程。
- 公开 captcha API 固定 force=false，同时保留 Redis 准入、预建日志、取消/未知状态处理。

## 5. 前端冲突

- 先合并 `frontend/src/api/admin.ts` 的 force 字段、call_user 参数和处理中清理 API。
- 再合并 RiskLogs 的筛选、清理确认、折叠配置区和 force 开关。
- 核对 `saveRemoteCaptchaConfig` 参数顺序与 PUT 载荷。

## 6. 增量验证

不重复合并前已经通过且未被本轮专门修改的基础真人鼠标用例；新增或调整交叉测试只覆盖合并产生的新边界：

- 三源优先级：force、slider_mode、env、remote 组合。
- 密码模式：browser/protocol/历史 auto 与 force 组合。
- 远程准入：risk_log_id + force=false、未发送/未知/正常接管。
- internal：local force、remote/remote_cookie、slider mode 与接管回执。
- RiskLogs/API 类型：force、call_user、处理中清理和折叠配置同时存在。

运行受影响 Python `py_compile`、锁定依赖前端 build、`git diff --check` 和冲突标记搜索。仓库缺 ESLint 配置，记录但不在本任务修复。

## 7. 图谱、检查与推送

- 代码变化后执行 `graphify update .`。
- 由 `trellis-check` 做完整语义和增量验证审查。
- rebase 完成后再次 fetch；若远端前进，重新处理，不强推。
- 确认 `git merge-base --is-ancestor origin/rm-actvatation HEAD`。
- 使用普通 `git push origin rm-actvatation`。

## 回滚点

- 任一冲突无法确定时停止并 `git rebase --abort`。
- 推送前保留本地回退引用。
- 不使用 reset --hard，不删除未跟踪文件，不使用 force push。
