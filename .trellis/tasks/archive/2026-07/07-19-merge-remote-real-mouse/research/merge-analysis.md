# `origin/rm-actvatation` 与本地真人鼠标变更合并研究

## 结论与依据

- 本地端点：`9c73cc4c52a73d19f6e54dc86801692fdf62f80a`（`完善真人鼠标强制验证配置`）。
- 远端端点：`origin/rm-actvatation` = `7e7b60a42e9f5014c9976a5926255669b965ae64`。
- 共同基点：`e3c1d3620b2ec62f2b7004df7b04383d0ae8b519`。
- 已只读执行 `git merge-base`、`git log`、`git show`、`git diff`、`git merge-tree --name-only`；未执行 rebase、merge、reset 或任何改写 Git 历史的操作。
- `git merge-tree --name-only 9c73cc4 origin/rm-actvatation` 确认 8 个内容冲突；其余 4 个双方改动文件可自动合并，但仍须人工审阅语义。
- 两侧对共同基点均通过 `git diff --check`，没有空白错误。此结果不代表合并结果已验证。

## 远端九个提交摘要

| 提交 | 摘要 | 合并要求 |
| --- | --- | --- |
| `ba54666` `完善` | Redis 锁内远程准入和预建风控日志、WebSocket 日志接管确认、远程滑块真实轨迹改进。 | 保留，避免远程并发在 WebSocket 写日志前越过处理中上限。 |
| `554c468` `优化风控日志` | 管理员可按状态清理风控日志，RiskLogs 加入相应操作。 | 保留。 |
| `01b8b82` `Update risk_control_log_service.py` | 成功率排除“验证链接已过期”的调用方输入失败。 | 保留。 |
| `575c1f5` `优化风控日志` | 按 `call_user` 查询远程调用日志，前后端参数贯通。 | 保留。 |
| `2865d0e` `Update RiskLogs.tsx` | 压缩并折叠远程配置区，保留常用本机滑块开关。 | 保留，与本地强制开关放在展开区。 |
| `ac89e07` `Update Dashboard.tsx` | 广告文本保留换行并折行，避免长链接撑破卡片。 | 无交集，直接保留。 |
| `0553ea1` `账号密码登录新增切换模式` | 新增协议/浏览器登录方式设置和独立保存入口。 | 保留，但须与本地 `force_real_mouse` 的密码登录优先级明确合并。 |
| `0ed47c6` `完善系统设置` | 滑块模式 `captcha.slider_mode`、其运行时缓存、设置页、Token/登录/WS 接入及依赖更新。 | 保留；不能删除本地环境变量和强制开关语义。 |
| `7e7b60a` | 将共同基点 `e3c1d36` 合并回 `rm-actvatation`；相对第二父会带入 launcher 改动，但这些已在本地共同基点中。 | 作为 rebase 目标，不单独挑拣。 |

## 必须保留的本地真人鼠标契约

本地 `9c73cc4` 的下列约束是合并后的不可退让行为：

1. `CAPTCHA_REAL_MOUSE` 是部署级默认能力；`captcha.force_real_mouse` 是管理员对**新开始的本机 Token 刷新和密码登录**的运行时强制覆盖。缺失数据库行按 `false`。
2. `force=false` 时，既有远程优先、环境变量真人鼠标和回退次序不应被强制开关改变。
3. `force=true` 时，本机 Token 刷新和密码登录跳过远程，进入既有 `local` 加权队列；公开 `/api/v1/captcha/slider-solve` 永远传 `force_real_mouse=false`，继续使用 `remote` / `remote_cookie` 队列。
4. 强制任务在真实鼠标导入失败、能力不可用或验证失败时直接失败，不得回退远程、Playwright、DrissionPage 或浏览器登录；`url_expired` 三元组语义不变。
5. 开关在任务开始时取快照，只影响后续任务，不改变正在运行的任务。
6. 管理员配置 API 保持 `GET/PUT /api/v1/captcha/remote-config` 的 `force_real_mouse: boolean` 字段；RiskLogs 仅向管理员展示可保存的无障碍开关。
7. WebSocket 启动时仍记录 `CAPTCHA_REAL_MOUSE` 的原始进程值和解析值；解析失败时先向 `stderr` 写受限诊断再重新抛出。

## 逐文件语义合并

### 8 个内容冲突

| 文件 | 本地语义 | 远端语义 | 推荐合并结果 |
| --- | --- | --- | --- |
| `backend-web/app/api/routes/captcha.py` | 管理员远程验证码配置读写 `captcha.force_real_mouse`；公开远程求解显式传 `force_real_mouse=False`。 | Redis 准入锁内创建 `processing` 风控日志，WebSocket 未接管时标记取消。 | 两者都保留。`RemoteConfigUpdate` 和 GET/PUT 保留强制字段；远程公开调用同时传 `precreated_log_id` 与 `force_real_mouse=False`；保留安全账号 ID、Redis 不可用降级、确认 ID 和未接管清理。 |
| `backend-web/app/api/routes/password_login.py` | `auto + force=true` 选择协议登录；原 `auto` 依据环境真实鼠标或远程能力判断。 | 登录方式只由 `password_login.mode` 决定，默认/非法按浏览器，提供协议/浏览器设置能力。 | `force_real_mouse` 优先于登录方式，以满足强制密码登录契约；其余值保持远端的 `protocol`/`browser` 行为。历史 `auto` 与远端“默认 browser”有不可兼容语义，见“最高风险”；若要求本地 `force=false` 完整旧行为，必须把 `auto` 保留为显式兼容值，而不能悄悄映射为 browser。 |
| `backend-web/app/services/system_setting_service.py` | 默认和免转义键增加 `captcha.force_real_mouse`。 | 默认增加 `captcha.slider_mode`，规范化 `password_login.mode` 和滑块模式。 | 默认集合、`NO_ESCAPE_KEYS` 和 `list_settings()` 同时保留三个键：`captcha.force_real_mouse`、`captcha.slider_mode`、`password_login.mode`。新安装默认 `force=false`、滑块 `browser`；密码默认按最终选择处理。不要让规范化逻辑把仍需兼容的 `auto` 和实际运行值悄悄分离。 |
| `backend-web/app/services/websocket_client.py` | `solve_captcha()` 新增 `force_real_mouse`，透传给服务间 WebSocket。 | 新增 `precreated_log_id`、连接失败/未知状态标志、10 秒 connect 超时。 | 一个方法同时接受两个默认可选参数，JSON 同时发送 `force_real_mouse` 和 `risk_log_id`；保留远端的失败分类，供上游只清理“确定未发送”的预建日志。 |
| `common/services/captcha/orchestrator.py` | `force_real_mouse` 跳过远程；强制不可用直接失败；环境开关仍可启用真人鼠标。 | 以 `slider_mode` 任务快照决定真人鼠标，来源是数据库进程缓存。 | 保留两个显式输入并规定优先级：`force_real_mouse` > `slider_mode == real_mouse` 或环境能力。强制时跳过远程且不可用直接失败；非强制时远端配置仍优先，随后按滑块模式/环境走既有链路。不要以全局改写替代任务参数。 |
| `frontend/src/pages/admin/RiskLogs.tsx` | 强制真人鼠标 state、读取回显、保存参数与管理员开关。 | `call_user` 筛选、仅清理处理中日志、配置折叠和布局压缩。 | 保留全部。导入 `clearProcessingRiskLogs`，查询传 `call_user`，保留二次确认；将强制开关放入展开的远程配置区，复用 `savingConfig`。保存调用参数必须与 API 更新后的顺序一致。 |
| `websocket/app/api/routes/internal.py` | 仅 `call_type=local` 的服务间强制请求进入 local 队列并传递 force。 | 接收 `risk_log_id`、接管预建日志、刷新数据库滑块模式、返回 `_risk_log_id`。 | 请求模型同时包含两个字段。执行优先级为 `force`，否则远端的滑块模式快照；force 走 local 加权队列并传编排器，非 force 保留远端按模式的调度。所有返回分支都带 `_risk_log_id`，以便 backend-web 确认接管。 |
| `websocket/app/services/xianyu/cookie_token_manager.py` | 一次异步读远程配置和 force 快照；force 时丢弃远程配置、local 队列、严格真人鼠标。 | 统一 Token 验证识别，任务前刷新 `captcha.slider_mode`，按数据库滑块模式选择调度。 | `_load_remote_captcha_config()` 返回 `(remote_config, force_real_mouse)`；每任务再取得 `selected_slider_mode`。force 时传 `effective_remote_config=None`、`force_real_mouse=True` 并进 local 队列；否则保留远端配置优先和滑块模式快照。 |

### 4 个自动合并文件

| 文件 | 本地语义 | 远端语义 | 自动合并后的必检结果 |
| --- | --- | --- | --- |
| `backend-web/app/services/password_login/flow.py` | 每轮滑块读取 force 快照；force 时跳过远程，向 WebSocket 传 local force 标记。 | 普通路径描述为由 WebSocket 按系统滑块方式决定引擎，删除环境变量判定。 | 保留本地 `_read_remote_config()` 的 force 值和每轮读取时点；force 分支覆盖普通 WebSocket 引擎选择，非 force 保持远端的“WebSocket 统一选择”说明和行为。 |
| `common/db/init_database.py` | 初始化 `captcha.force_real_mouse=false`。 | 初始化 `password_login.mode=browser` 与 `captcha.slider_mode=browser`。 | 三个初始化行都存在，且描述与服务默认值一致；只增键，不迁移或删除旧数据库行。 |
| `frontend/src/api/admin.ts` | 远程配置响应和保存参数新增 `force_real_mouse`。 | 风控日志 `call_user` 请求参数、`clearProcessingRiskLogs()`。 | 返回类型、PUT 载荷、RiskLogs 查询和清理 API 全部同时存在。此处是位置参数 API，前端调用与函数签名必须同步。 |
| `websocket/_bootstrap.py` | 解析配置前取得 `CAPTCHA_REAL_MOUSE` 原值，记录成功/失败启动诊断。 | 数据库连接成功后刷新 `captcha.slider_mode` 缓存。 | 保留 `os`/`stderr` 诊断和 `await refresh_slider_mode_from_database()`。必须先恢复环境变量字段，见下节，否则 `settings.captcha_real_mouse_enabled` 会在启动日志处崩溃。 |

## 非冲突依赖与跨层合并点

远端 `0ed47c6` 修改了直接决定上述 12 个文件能否正确运行的非冲突文件，不能只解决冲突后停止审阅。

- `common/core/config.py`：远端删除 `captcha_real_mouse_enabled`，但本地启动诊断和“环境变量为部署默认能力”仍依赖它。合并必须保留该配置字段及其 Pydantic 解析失败行为；数据库 `captcha.slider_mode` 是新增选择源，不是环境变量的替代品。
- `common/services/captcha/slider_mode.py`：保留远端的线程安全缓存、合法值规范化和数据库刷新；它与环境默认、force 任务参数并列，不能覆盖后两者。
- `backend-web/app/api/routes/system_settings.py`、`frontend/src/api/settings.ts`、`frontend/src/pages/settings/*`、`frontend/src/types/index.ts`：保留滑块方式和协议/浏览器登录方式的校验、独立保存和防止“保存全部设置”误覆盖的过滤逻辑。
- `backend-web/app/services/remote_captcha_admission_service.py`、`risk_control_log_service.py`、`risk_control_logs.py`、`admin.py`：保留 Redis 原子准入、预建日志接管/取消、过期 URL 成功率口径、`call_user` 过滤与只清空 processing 的管理员边界。
- `common/services/captcha/token_response.py`、`websocket/app/services/xianyu/cookie_token_manager.py`：保留统一 Token 滑块识别，不能因合并 force 查询而恢复旧的关键字判断副本。

## API、数据库与前端兼容风险

| 层 | 风险 | 合并约束 |
| --- | --- | --- |
| 配置来源 | 远端删掉环境字段，直接合并会导致 `websocket/_bootstrap.py` 访问不存在属性，且 force=false 时失去部署级真实鼠标能力。 | 环境字段、启动诊断、滑块模式缓存、force 参数三者并存，明确优先级。 |
| 密码登录 | 远端把 `auto` 视为 browser，本地把它作为能力探测并在 force=true 时转协议；已有数据库可能仍有 `auto`。 | 先决定历史 `auto` 的兼容策略，再同步后端校验、服务规范化、前端类型/选项和提示文案；不得显示 browser 却运行 auto。 |
| Backend-Web 到 WebSocket | 新 backend 向旧 WebSocket 发送 `risk_log_id` 时，旧端不会确认 `_risk_log_id`，预建日志会被标为 cancelled，且旧端另建一条日志；新 force 标记在旧端也不会严格生效。 | 两个服务作为同一版本部署；健康检查和回滚都不得混用新旧镜像。 |
| 公开验证码 API | 若把 force 字段暴露到 `/captcha/slider-solve`，外部请求可改变本机队列和严格失败策略。 | 公开路由固定 `force_real_mouse=False`；内部端口仍须只暴露在可信网络，`call_type` 不是独立认证机制。 |
| 远程风控日志 | Redis 可用时预建日志和 WS 接管必须成对；丢失 `_risk_log_id` 会产生 cancelled 日志，Redis 不可用则只能退回旧的非原子数据库计数。 | 保留远端降级与未接管清理；验证 Redis 正常和 WS 回执。不要删除 cancelled 记录来掩盖混合版本。 |
| 数据库 | 三个设置键对旧库均为新增行，无 schema migration；设置初始化尚未运行时，force 缺失必须为 false、滑块模式为 browser。 | 不删除旧键；部署后确认 `SystemSettingService` / 初始化器已写入默认行。 |
| 前端 | `saveRemoteCaptchaConfig` 是位置参数；漏传或错序会把权重/限流值写错。RiskLogs 同时改动状态、筛选和折叠布局，容易在手工解冲突时丢失一侧。 | 让函数签名、载荷和页面调用一次性更新；TypeScript lint/build 必须覆盖这两个页面。 |
| 管理员清理 | “清空处理中日志”可删除仍在执行任务的可观测记录并临时释放远程容量。 | 保留管理员鉴权、状态白名单和不可恢复确认；仅作为人工故障处理，不作为正常收尾路径。 |

## 推荐的 rebase 冲突解决顺序

目标是把本地提交重放到 `origin/rm-actvatation`，不是逐个 cherry-pick 远端提交。实际 rebase 停止后按以下依赖顺序处理，最后一次性 `git add` 并 `git rebase --continue`：

1. 先确认远端端点未移动：`git fetch origin`，复核 `git merge-base 9c73cc4 origin/rm-actvatation`；开始前保存一个仅本地的回退引用。
2. 先处理基础配置：`common/core/config.py`、`common/db/init_database.py`、`backend-web/app/services/system_setting_service.py`、`websocket/_bootstrap.py`，确定环境、滑块模式、force 和密码模式的最终枚举与默认值。
3. 处理编排接口：`common/services/captcha/orchestrator.py`、`backend-web/app/services/websocket_client.py`、`websocket/app/api/routes/internal.py`。先固定 `force_real_mouse`、`slider_mode`、`risk_log_id` 的签名、优先级和回执。
4. 处理本机入口：`websocket/app/services/xianyu/cookie_token_manager.py`、`backend-web/app/services/password_login/flow.py`、`backend-web/app/api/routes/password_login.py`。确认每个任务的快照时点和密码登录模式决策。
5. 处理公开远程入口与风控：`backend-web/app/api/routes/captcha.py`，确认公开调用不能传 force，同时保留 Redis 预建日志链路。
6. 处理前端契约：`frontend/src/api/admin.ts` 后再处理 `frontend/src/pages/admin/RiskLogs.tsx`，保证新增参数、筛选、清理和开关同时存在。
7. 审阅 4 个自动合并文件和所有非冲突依赖，执行 `git diff --check`、搜索冲突标记，并核对所有 `solve_captcha` / `run_slider_verification_with_fallback` 调用点。

不要在解决时接受单侧 “ours/theirs” 整个文件，也不要顺带重构；两侧变更是正交能力，完整保留比压缩差异更小。

## 不重复已通过用例的增量验证矩阵

按任务约束，不重跑本地真人鼠标已通过的专门用例：`tests/test_real_mouse_force.py` 的 3 项，以及 `tests/test_real_mouse_force_cross_layer.py` 中已覆盖的 force 配置回显、Token/password/public 三入口、队列桶、启动日志和 force 快照用例。以下只验证远端引入或双方交叉后的新边界。

| 增量范围 | 最小验证 | 通过条件 |
| --- | --- | --- |
| 配置三源优先级 | 新增/调整一个定向 mock 用例：`force=true + slider_mode=browser/real_mouse + 已配置远程`。 | force 仍跳过远程、走 local、不可用直接失败；`force=false` 时 slider_mode 与环境默认都不被丢弃。 |
| 密码方式交叉 | 用 settings 行覆盖 `protocol`、`browser`、历史 `auto`（若保留）各与 force true/false 的组合。 | 最终选定的 legacy 策略在 API 校验、列表返回、页面展示和 `_decide_mode()` 完全一致；force=true 必进协议。 |
| 远程准入和日志接管 | mock Redis 锁和 WebSocket 回执，验证 `precreated_log_id` + `force_real_mouse=False` 同时发出；覆盖连接未发送、未知超时、正常回执。 | 正常请求只使用预建日志；确定未发送才取消；未知状态不提前取消；公开路径没有 force。 |
| WebSocket 任务选择 | 定向调用 internal route：外部远程请求、服务间 local force 请求、滑块模式 real_mouse 的普通请求。 | remote/remote_cookie、local force、`_risk_log_id` 回执和调度器选择均正确。 |
| RiskLogs 前端 | 仅跑受影响前端的 lint/type/build 命令（以 `frontend/package.json` 脚本为准）。 | `saveRemoteCaptchaConfig` 调用和类型匹配；`call_user` 查询、清理 processing、折叠区和 force 开关均可编译。 |
| Python 静态边界 | 对合并后的 Python 触及模块执行定向 `py_compile`，再做 `git diff --check`。 | 不存在旧环境属性缺失、导入循环、语法错误或冲突标记。 |
| Windows 实机 | 不重做已验证的基础 force 矩阵，只做“数据库滑块模式 + force + 远程配置”交叉的一次可见桌面验证。 | force 开启后 Token 和密码登录严格真人鼠标；关闭后远端/滑块模式按最终规则运行；外部远程 API 不受 force 影响。 |

## 正常 push 条件与回滚

### 正常 push 条件

1. rebase 前后再次 `git fetch origin`；`origin/rm-actvatation` 必须是本地 HEAD 的祖先。远端若在验证期间前进，重新基于新端点 rebase，不使用 force push。
2. 8 个冲突和 4 个自动合并文件均按本文的双侧语义核对，且没有 `<<<<<<<` / `=======` / `>>>>>>>` 标记。
3. 增量验证矩阵通过，特别是三源优先级、远程日志接管、密码模式和前端类型构建；已通过的本地 force 用例不重复执行。
4. `git diff --check` 无输出，待提交内容仅包含预期的远端能力、本地真人鼠标契约和本任务研究产物；未把工作区无关的未跟踪 `.trellis` / `.pi` 内容带入提交。
5. 满足以上条件后使用普通 `git push origin rm-actvatation`。rebase 后远端是祖先时该推送是快进，不需要 `--force` 或 `--force-with-lease`。

### 回滚

- rebase 尚未完成：使用 `git rebase --abort`，恢复到 rebase 前本地提交，不触及远端。
- rebase 已完成但未推送：回到开始前创建的本地回退引用；操作前核对引用指向，避免误丢用户未提交工作。
- 已正常推送：以新的 revert 提交撤销重放后的本地真人鼠标提交，不改写共享历史；远端九个提交保持原样。新增的 `system_settings` 键是可忽略的加性数据，无需删除。
- 运行时紧急降级：先由管理员把 `captcha.force_real_mouse` 保存为 `false`，它只影响新任务；若问题来自远端全局滑块选择，再将 `captcha.slider_mode` 设为 `browser`。不要靠清空 processing 日志替代任务收尾。

## 最高风险

远端将 `CAPTCHA_REAL_MOUSE` 从 `common/core/config.py` 和编排器中移除，同时引入数据库 `captcha.slider_mode`；本地强制契约仍以该环境字段作为部署级默认并在 bootstrap 读取其属性。若按任一侧整块解冲突，轻则 WebSocket 启动时属性错误，重则 force=false 的既有环境真人鼠标策略静默失效。必须先落实“环境默认 + 全局 slider_mode + 每任务 force”的三源优先级，再解决密码登录历史 `auto` 的兼容策略。
