# 合并远端真人鼠标相关变更

## Goal

将本地 3 个未推送提交安全重放到 `origin/rm-actvatation` 新增的 9 个提交之上，语义合并远端系统设置、密码登录、RiskLogs 和风控日志能力与本地真人鼠标强制策略，完成增量验证后使用普通 push 推送，不覆盖共享历史。

## Background / Confirmed Facts

- 共同基点为 `e3c1d36`；本地端点为 `0c1eaa8`，远端端点为 `7e7b60a`。
- 本地领先 3 个提交、落后远端 9 个提交；首次 rebase 在 8 个核心文件发生内容冲突，随后已安全执行 `git rebase --abort`。
- 远端新增 Redis 原子准入、预建风控日志接管、`call_user` 筛选、处理中日志清理、折叠式 RiskLogs 配置区、显式密码登录模式和 `captcha.slider_mode`。
- 本地新增 `CAPTCHA_REAL_MOUSE` 启动诊断、`captcha.force_real_mouse`、本机 Token/密码登录强制真人鼠标和严格失败契约。
- 两侧能力均需保留，不能对冲突文件整块选择 ours 或 theirs。

## Requirements

### R1. 保留远端新增能力

合并后必须保留远端 9 个提交中的系统设置、显式密码登录模式、滑块模式缓存、Redis 远程准入、预建风险日志接管/取消、`call_user` 筛选、处理中日志清理和 RiskLogs 折叠布局。

### R2. 保留本地真人鼠标契约

- `CAPTCHA_REAL_MOUSE` 继续作为部署级启用来源并保留启动成功/解析失败诊断。
- `captcha.force_real_mouse` 缺失时默认 false。
- 强制开关只影响新开始的本机 Token 刷新和密码登录，跳过远程并进入 `local` 队列。
- 强制任务不可用或失败时直接失败，不回退其他引擎。
- 公开远程过滑块固定 `force_real_mouse=false`，继续使用 `remote` / `remote_cookie`。

### R3. 明确三源优先级

- 本机任务 `force_real_mouse=true`：最高优先级，跳过远程，严格真人鼠标。
- 非强制任务：保持远程配置优先；远程未接管时，`CAPTCHA_REAL_MOUSE=true` 或 `captcha.slider_mode=real_mouse` 均可选择真人鼠标。
- `captcha.slider_mode=browser` 不反向关闭已经由环境变量启用的真人鼠标能力。
- 设置在任务开始时形成快照，不切换正在执行的任务。

### R4. 采用远端密码登录语义

- 登录模式以远端显式 `browser` / `protocol` 为准。
- 历史或非法 `auto` 值规范化为 `browser`，前端展示和后端行为一致。
- `captcha.force_real_mouse=true` 时覆盖登录模式并进入协议登录的本机真人鼠标链路。
- force=false 时不恢复旧的隐式能力探测 `auto` 行为。

### R5. 保持跨服务契约

`WebSocketServiceClient.solve_captcha()` 同时保留本地 `force_real_mouse` 和远端 `precreated_log_id/risk_log_id` 契约；所有 WebSocket 返回分支保留风险日志接管 ID。公开 backend API 不暴露服务间 force 字段。

### R6. 安全重放与推送

- 以最新 `origin/rm-actvatation` 为目标执行 rebase，冲突按依赖顺序进行语义合并。
- 不使用 `git push --force` 或 `--force-with-lease`。
- 验证期间远端若前进，重新 fetch 并基于新端点处理。
- 现有未跟踪 `.pi`、Trellis 脚手架、`graphify-out` 等不得纳入合并提交。

## Acceptance Criteria

- [ ] 本地 3 个提交成功重放到最新 `origin/rm-actvatation`，且远端是本地 HEAD 的祖先。
- [ ] 8 个冲突文件和 4 个自动合并文件均保留双方约定语义，无冲突标记。
- [ ] 环境变量、`captcha.slider_mode`、每任务 force 三源优先级符合 R3。
- [ ] 密码模式只保留 `browser/protocol`，历史 `auto` 实际运行和页面展示均归一为 browser；force=true 仍进入协议真人鼠标。
- [ ] 公开远程调用同时保留预建风险日志链路并固定 `force_real_mouse=false`。
- [ ] Token 刷新、密码登录、WebSocket internal 路由保持正确快照、队列桶和风险日志回执。
- [ ] RiskLogs 同时保留 call_user 筛选、处理中清理、折叠布局和强制真人鼠标开关。
- [ ] 增量测试、受影响 Python 编译、前端锁定依赖 build 和 `git diff --check` 通过。
- [ ] `graphify update .` 完成。
- [ ] 使用普通 `git push origin rm-actvatation` 成功。

## Out of Scope

- 不重构验证码编排、设置服务或 RiskLogs 页面。
- 不新增内部 WebSocket 服务鉴权；继续沿用现有可信网络边界。
- 不修复仓库既有 ESLint 配置缺失。
- 不删除或整理无关未跟踪文件。
