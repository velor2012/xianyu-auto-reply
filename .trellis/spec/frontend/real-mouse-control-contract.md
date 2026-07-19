# Real-Mouse Slider Control Contract

## 1. Scope / Trigger

Use this contract when changing the Risk Logs captcha settings, `CAPTCHA_REAL_MOUSE`, local token-refresh captcha handling, password-login captcha handling, or the backend-to-WebSocket captcha request.

The environment flag is the deployment default. The database force switch is an administrator runtime override for new local business tasks only. It must not change public remote captcha behavior.

## 2. Signatures

```text
Environment:
  CAPTCHA_REAL_MOUSE: boolean, default false

System setting:
  captcha.force_real_mouse: "true" | "false", default "false"

GET /api/v1/captcha/remote-config
  response.data.force_real_mouse: boolean

PUT /api/v1/captcha/remote-config
  request.force_real_mouse: boolean

WebSocketServiceClient.solve_captcha(...)
  call_type: "local" | "remote"
  force_real_mouse: boolean = false

run_slider_verification_with_fallback(...)
  force_real_mouse: boolean = false
```

## 3. Contracts

- `force=false` preserves the existing order exactly. In particular, configured remote solving remains ahead of environment-enabled real mouse.
- `force=true` affects only new local token-refresh and password-login captcha tasks. Those tasks skip remote solving and enter the existing `local` real-mouse weighted queue.
- Public remote captcha calls always pass `force_real_mouse=false` and remain in `remote` or `remote_cookie` queues.
- A force-switch change is sampled once when a new task starts. It must not switch or cancel a running task.
- Forced real mouse is strict: import failure, unavailable runtime capability, or verification failure returns failure without Playwright, DrissionPage, remote, or browser-login fallback.
- Environment-only real mouse keeps its existing unavailable-engine fallback behavior.
- Startup logging records `CAPTCHA_REAL_MOUSE` as `process_env=<repr>` plus `parsed_enabled=<bool>` after logging initialization.
- If configuration parsing fails before logging initialization, write only `process_env=<repr>` and `parsed_enabled=<parse_failed>` to `stderr`, flush, then re-raise. The EXE redirects this to `websocket/logs/websocket.stdout.log`.

## 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Setting row missing | API returns `force_real_mouse=false` |
| Non-admin reads or writes config | Existing admin dependency rejects the request |
| `force=false`, env false | Existing remote/Playwright/DrissionPage flow |
| `force=false`, env true | Existing remote-first, then real-mouse flow |
| `force=true`, local token refresh | Skip remote, use `local` queue and real mouse |
| `force=true`, password login | Select protocol mode, skip remote, use WebSocket `local` queue |
| `force=true`, external captcha call | Ignore database force; preserve remote behavior |
| Forced engine unavailable or fails | Return failure; no fallback engine |
| Invalid environment boolean, including empty string | Log restricted parse-failure diagnostic to `stderr`, then preserve the Pydantic failure |

## 5. Good / Base / Bad Cases

- Good: an administrator enables force mode; the next token refresh snapshots `true`, enters the local weighted queue, and records `captcha_engine=real_mouse` on success.
- Base: force mode is off; `CAPTCHA_REAL_MOUSE=true` and a configured remote service continue using the existing remote-first policy.
- Bad: reading `captcha.force_real_mouse` through synchronous `db_manager` inside an async FastAPI path. Read it with the existing async session together with neighboring captcha settings.
- Bad: exposing `force_real_mouse` from the public slider API. Only the existing service-to-service password-login call may send the local force marker.
- Bad: treating `CAPTCHA_REAL_MOUSE=''` as false. It is an invalid Pydantic boolean and must remain a startup error with a restricted diagnostic.

## 6. Tests Required

- Startup contract: real configuration parsing for unset, `true`, `false`, and empty-string failure; assert logger ordering and pre-logger `stderr` failure diagnostics.
- Config API: queried key list includes `captcha.force_real_mouse`; missing row returns false; PUT stores both boolean values; admin dependency remains attached.
- Orchestrator matrix: remote priority when force is false, strict real mouse when force is true, unavailable-engine fallback only for environment-only mode.
- Token refresh: async setting snapshot, local queue under force, and a changed setting affects only the next task.
- Password login: `auto + force=true` selects protocol mode, refreshes settings per slider round, skips remote, and sends the local force marker.
- Public remote boundary: backend never propagates force; WebSocket retains `remote` / `remote_cookie` classification.
- Frontend: locked TypeScript build passes; administrator load/save payload contains `force_real_mouse` and the switch uses the existing accessible switch pattern.
- Windows acceptance: verify the compiled EXE log path and a controlled visible-desktop real-mouse run.

## 7. Wrong vs Correct

### Wrong

```python
# This changes public remote behavior and blocks the event loop.
force = db_manager.get_system_setting("captcha.force_real_mouse") == "true"
if force or is_real_mouse_enabled():
    use_real_mouse_everywhere()
```

### Correct

```python
# Async entry point snapshots the database override for this local task.
force = settings_map.get("captcha.force_real_mouse", "false") == "true"
await local_runner.submit(
    run_slider_verification_with_fallback,
    force_real_mouse=force,
)
```

The orchestrator receives an explicit per-task force value; environment behavior and public remote behavior remain separate.
