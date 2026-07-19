# 技术设计

## 合并方式

以 `origin/rm-actvatation` 为新基线，rebase 本地三个提交。开始前创建本地回退引用，不修改远端。冲突只对停止中的本地功能提交做语义解决；两个 Trellis 归档提交按新父提交重放。

## 最终配置模型

```text
CAPTCHA_REAL_MOUSE                 部署级启用来源，bool
captcha.slider_mode               数据库全局模式：browser | real_mouse
captcha.force_real_mouse          本机业务每任务强制：bool
password_login.mode               browser | protocol；auto/非法值 -> browser
```

本机验证码有效选择：

```text
force=true:
  skip remote -> strict real_mouse -> unavailable/failure returns failure

force=false:
  configured remote first
  then real_mouse when env=true OR slider_mode=real_mouse
  otherwise browser/Playwright/DrissionPage
```

公开远程调用永远 `force=false`，但继续遵循远端已有 slider mode/environment 行为和 `remote` / `remote_cookie` 队列。

## 冲突解决顺序

1. 基础配置：恢复 `common/core/config.py` 的环境字段；合并 `SystemSettingService`、数据库初始化、slider mode 缓存和 bootstrap 日志。
2. 编排签名：合并 `force_real_mouse`、`slider_mode`、`risk_log_id` 和 `_risk_log_id` 回执。
3. 本机入口：合并 Token 设置快照、密码模式与每轮密码滑块配置刷新。
4. 公开远程入口：同时保留 Redis 准入/预建日志与固定 force=false。
5. 前端契约：先合并 API 类型，再合并 RiskLogs 筛选、清理、折叠和开关。
6. 审阅自动合并文件和 `0ed47c6` 引入的非冲突依赖。

禁止对冲突文件整块选择 ours/theirs。

## 关键文件决议

- `captcha.py`：保留 force 配置 GET/PUT；公开调用同时发送 `risk_log_id` 和 `force_real_mouse=false`；保留 Redis 降级和未接管清理。
- `password_login.py`：采用 browser/protocol；auto 归一 browser；force=true 优先 protocol。
- `system_setting_service.py`：同时保留 force、slider_mode、password mode 默认值和规范化。
- `websocket_client.py`：一个请求同时承载 force 与 precreated log ID，并保留连接失败分类。
- `orchestrator.py`：force 参数最高；非强制保留远程优先，再由 env OR slider_mode 选择真人鼠标。
- `RiskLogs.tsx`：保留 call_user、处理中清理、折叠 UI、force state/回显/保存；位置参数与 API 签名同步。
- `internal.py`：请求模型同时含 force/risk_log_id；local force 进入 local 队列；外部继续 remote；所有响应带接管 ID。
- `cookie_token_manager.py`：同次异步设置读取 remote+force，另取 slider mode 快照；force 时 remote=None，其他情况维持远程优先。

## 兼容与风险

- 环境字段不能被远端删除，否则 bootstrap 属性访问失败且部署级真人鼠标静默失效。
- `saveRemoteCaptchaConfig` 使用位置参数，手工冲突解决必须同步签名和调用。
- backend-web/WebSocket 新旧版本不能混部，否则风险日志接管和 force 字段无法形成完整契约。
- internal 路由仍依赖可信网络；公开 backend API 不传播 force。
- Redis 不可用时保留远端非原子降级，不通过删除日志掩盖未知执行状态。

## 回滚

- rebase 中：`git rebase --abort`。
- rebase 完成未推送：回到预先创建的本地回退引用。
- 推送后：通过新 revert 提交撤销本地真人鼠标重放提交，不改写共享历史。
- 运行时：先关闭 `captcha.force_real_mouse`；需要时将 `captcha.slider_mode` 设为 browser。
