import ast
import asyncio
import io
import importlib.util
import inspect
import os
import sys
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import params as fastapi_params

from common.services.captcha import orchestrator


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str, modules: dict[str, types.ModuleType] | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with patch.dict(sys.modules, modules or {}):
        spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, rows=(), scalar=None):
        self.rows = list(rows)
        self.scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)

    def scalar_one_or_none(self):
        return self.scalar


class FakeSettingsSession:
    def __init__(self, records=()):
        self.records = {record.key: record for record in records}
        self.commits = 0
        self.executed_statements = []

    async def execute(self, statement):
        self.executed_statements.append(statement)
        return FakeResult(self.records.values())

    def add(self, record):
        self.records[record.key] = record

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def statement_sql(statement):
    try:
        return str(statement.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        return str(statement)


def assert_query_contains(test_case, session, key):
    test_case.assertTrue(
        any(key in statement_sql(statement) for statement in session.executed_statements),
        f"database query did not contain {key!r}",
    )


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def load_captcha_route():
    deps = types.ModuleType("app.api.deps")
    deps.get_current_admin_user = lambda: None
    deps.get_db_session = lambda: None

    api_package = types.ModuleType("app.api")
    api_package.deps = deps
    services_package = types.ModuleType("app.services")

    admission = types.ModuleType("app.services.remote_captcha_admission_service")
    admission.DEFAULT_REMOTE_COOLDOWN_SECONDS = 600
    admission.DEFAULT_REMOTE_PROCESSING_MAX = 20
    admission.REMOTE_COOLDOWN_SECONDS_KEY = "captcha.remote_cooldown_seconds"
    admission.REMOTE_PROCESSING_MAX_KEY = "captcha.remote_processing_max"
    admission.sanitize_nonnegative_int = lambda value, default: default

    class AdmissionService:
        def __init__(self, _db):
            pass

        async def check_admission(self):
            return True, None

    admission.RemoteCaptchaAdmissionService = AdmissionService

    websocket_client_module = types.ModuleType("app.services.websocket_client")
    websocket_client_module.websocket_client = SimpleNamespace(
        solve_captcha=AsyncMock(return_value={"success": False, "message": "failed"})
    )

    system_setting_service = load_module(
        ROOT / "backend-web/app/services/system_setting_service.py",
        "system_setting_service_for_captcha_test",
    )

    app_package = types.ModuleType("app")
    app_package.__path__ = []
    services_package.__path__ = []
    api_package.__path__ = []
    app_package.api = api_package
    app_package.services = services_package

    modules = {
        "app": app_package,
        "app.api": api_package,
        "app.api.deps": deps,
        "app.services": services_package,
        "app.services.remote_captcha_admission_service": admission,
        "app.services.system_setting_service": system_setting_service,
        "app.services.websocket_client": websocket_client_module,
    }
    return load_module(
        ROOT / "backend-web/app/api/routes/captcha.py",
        "captcha_route_for_force_test",
        modules,
    )


def load_password_flow():
    app_package = types.ModuleType("app")
    app_package.__path__ = []
    core_package = types.ModuleType("app.core")
    core_package.__path__ = []
    services_package = types.ModuleType("app.services")
    services_package.__path__ = []

    config = types.ModuleType("app.core.config")
    config.get_settings = lambda: SimpleNamespace(captcha_real_mouse_enabled=False)
    http_client = types.ModuleType("app.core.http_client")
    http_client.get_http_client = lambda: None
    account_service = types.ModuleType("app.services.account_service")
    account_service.AccountService = object
    websocket_client = types.ModuleType("app.services.websocket_client")
    websocket_client.websocket_client = SimpleNamespace(solve_captcha=AsyncMock())

    remote_solver = types.ModuleType("common.services.captcha.remote_solver")
    remote_solver.solve_remote = AsyncMock()
    face_verification = types.ModuleType("common.services.xianyu_login.face_verification")
    face_verification.FaceVerificationError = RuntimeError
    face_verification.run_face_verification_flow = AsyncMock()
    login_do = types.ModuleType("common.services.xianyu_login.login_do")
    login_do.LoginBranch = SimpleNamespace(SLIDER="slider")
    login_do.build_login_form = lambda *args, **kwargs: None
    login_do.classify_login_response = lambda *args, **kwargs: None
    login_do.post_login_do = AsyncMock()
    xianyu_utils = types.ModuleType("common.utils.xianyu_utils")
    xianyu_utils.trans_cookies = lambda value: {"unb": value}

    app_package.core = core_package
    app_package.services = services_package
    database_session = types.ModuleType("common.db.session")
    database_session.async_session_maker = lambda: None
    modules = {
        "app": app_package,
        "app.core": core_package,
        "app.core.config": config,
        "app.core.http_client": http_client,
        "app.services": services_package,
        "app.services.account_service": account_service,
        "app.services.websocket_client": websocket_client,
        "common.db.session": database_session,
        "common.services.captcha.remote_solver": remote_solver,
        "common.services.xianyu_login.face_verification": face_verification,
        "common.services.xianyu_login.login_do": login_do,
        "common.utils.xianyu_utils": xianyu_utils,
    }
    return load_module(
        ROOT / "backend-web/app/services/password_login/flow.py",
        "password_login_flow_for_force_test",
        modules,
    )


def load_password_route():
    app_package = types.ModuleType("app")
    app_package.__path__ = []
    api_package = types.ModuleType("app.api")
    api_package.__path__ = []
    core_package = types.ModuleType("app.core")
    core_package.__path__ = []
    services_package = types.ModuleType("app.services")
    services_package.__path__ = []

    deps = types.ModuleType("app.api.deps")
    deps.get_current_active_user = lambda: None
    deps.get_account_service = lambda: None
    config = types.ModuleType("app.core.config")
    config.get_settings = lambda: SimpleNamespace(
        captcha_real_mouse_enabled=False,
        websocket_service_url="http://127.0.0.1:8001",
    )
    account_service = types.ModuleType("app.services.account_service")
    account_service.AccountService = object
    password_login_package = types.ModuleType("app.services.password_login")
    password_login_package.password_login_manager = SimpleNamespace()
    password_login_manager = types.ModuleType("app.services.password_login.manager")
    password_login_manager.SESSION_PREFIX = "pl_"
    account_limit = types.ModuleType("common.services.account_limit_service")
    account_limit.AccountLimitExceededError = RuntimeError
    account_limit.AccountLimitService = object

    app_package.api = api_package
    app_package.core = core_package
    app_package.services = services_package
    api_package.deps = deps
    core_package.config = config
    services_package.account_service = account_service
    services_package.password_login = password_login_package
    modules = {
        "app": app_package,
        "app.api": api_package,
        "app.api.deps": deps,
        "app.core": core_package,
        "app.core.config": config,
        "app.services": services_package,
        "app.services.account_service": account_service,
        "app.services.password_login": password_login_package,
        "app.services.password_login.manager": password_login_manager,
        "common.services.account_limit_service": account_limit,
    }
    return load_module(
        ROOT / "backend-web/app/api/routes/password_login.py",
        "password_login_route_for_force_test",
        modules,
    )


def load_cookie_manager(name="cookie_token_manager_force_test"):
    if name in sys.modules:
        return sys.modules[name]
    database_session = types.ModuleType("common.db.session")
    database_session.async_session_maker = lambda: None
    return load_module(
        ROOT / "websocket/app/services/xianyu/cookie_token_manager.py",
        name,
        {"common.db.session": database_session},
    )


def load_internal_route():
    return load_module(
        ROOT / "websocket/app/api/routes/internal.py",
        "websocket_internal_route_for_force_test",
    )


def load_bootstrap_snapshot(raw_value):
    class RecordingLogger:
        def __init__(self):
            self.calls = []

        def info(self, message):
            self.calls.append(("logger.info", message))

        def error(self, message):
            self.calls.append(("logger.error", message))

    logger = RecordingLogger()
    websocket_config = load_module(
        ROOT / "websocket/app/core/config.py",
        f"websocket_config_for_bootstrap_{raw_value!r}",
    )
    logging_utils = types.ModuleType("common.utils.logging_utils")
    events = []
    stderr = io.StringIO()
    error = None

    def setup_logging(*args, **kwargs):
        events.append(("setup_logging", args, kwargs))

    logging_utils.setup_logging = setup_logging
    network_utils = types.ModuleType("common.utils.network_utils")
    network_utils.resolve_listen_host = lambda host, port: host
    config = types.ModuleType("app.core.config")
    config.get_settings = lambda: websocket_config.WebSocketConfig(_env_file=None)
    error_handlers = types.ModuleType("app.core.error_handlers")
    error_handlers.setup_error_handlers = lambda app: None
    routes = types.ModuleType("app.api.routes")
    routes.__path__ = []
    for route_name in ("cookies_refresh", "internal", "password_login"):
        route = types.ModuleType(f"app.api.routes.{route_name}")
        route.router = __import__("fastapi").APIRouter()
        setattr(routes, route_name, route)
    app_package = types.ModuleType("app")
    app_package.__path__ = []
    app_core = types.ModuleType("app.core")
    app_core.__path__ = []
    app_api = types.ModuleType("app.api")
    app_api.__path__ = []
    app_package.core = app_core
    app_package.api = app_api
    app_core.config = config
    app_api.routes = routes
    cookie_renew = types.ModuleType("common.services.cookie_renew_browser_service")
    cookie_renew.enable_local_browser_renew = lambda: None
    loguru_module = types.ModuleType("loguru")
    loguru_module.logger = logger
    modules = {
        "app": app_package,
        "app.core": app_core,
        "app.core.config": config,
        "app.core.error_handlers": error_handlers,
        "app.api": app_api,
        "app.api.routes": routes,
        "app.api.routes.cookies_refresh": routes.cookies_refresh,
        "app.api.routes.internal": routes.internal,
        "app.api.routes.password_login": routes.password_login,
        "common.utils.logging_utils": logging_utils,
        "common.utils.network_utils": network_utils,
        "common.services.cookie_renew_browser_service": cookie_renew,
        "loguru": loguru_module,
    }
    module_name = f"bootstrap_snapshot_{raw_value!r}"
    with patch.dict(sys.modules, modules):
        sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / "websocket/_bootstrap.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            with patch("faulthandler.enable"), redirect_stderr(stderr):
                spec.loader.exec_module(module)
        except Exception as exc:
            error = exc
        finally:
            sys.modules.pop(module_name, None)
    return events, logger.calls, stderr.getvalue(), error


class CaptchaConfigApiTests(unittest.TestCase):
    def test_force_setting_round_trips_and_admin_dependency_remains(self):
        captcha = load_captcha_route()
        from common.models.system_setting import SystemSetting

        session = FakeSettingsSession(
            [SystemSetting(key="captcha.block_remote_calls", value="false")]
        )
        admin = SimpleNamespace(is_admin=True)

        initial = asyncio.run(captcha.get_remote_config(current_user=admin, db=session))
        self.assertTrue(initial.success)
        self.assertFalse(initial.data["force_real_mouse"])
        assert_query_contains(self, session, "captcha.force_real_mouse")

        for enabled in (True, False):
            response = asyncio.run(
                captcha.update_remote_config(
                    captcha.RemoteConfigUpdate(force_real_mouse=enabled),
                    current_user=admin,
                    db=session,
                )
            )
            self.assertTrue(response.success)
            self.assertEqual(session.records["captcha.force_real_mouse"].value, str(enabled).lower())
            assert_query_contains(self, session, "captcha.force_real_mouse")
            loaded = asyncio.run(captcha.get_remote_config(current_user=admin, db=session))
            self.assertEqual(loaded.data["force_real_mouse"], enabled)
            assert_query_contains(self, session, "captcha.force_real_mouse")

        for endpoint in (captcha.get_remote_config, captcha.update_remote_config):
            parameter = inspect.signature(endpoint).parameters["current_user"]
            self.assertIsInstance(parameter.default, fastapi_params.Depends)
            self.assertIs(parameter.default.dependency, captcha.deps.get_current_admin_user)


class TokenRefreshForceTests(unittest.TestCase):
    def test_force_true_uses_local_runner_and_drops_remote_config(self):
        manager_module = load_cookie_manager()
        remote_rows = [
            SimpleNamespace(key="captcha.remote_service_url", value="https://remote.test"),
            SimpleNamespace(key="captcha.remote_secret_key", value="secret"),
            SimpleNamespace(key="captcha.force_real_mouse", value="true"),
        ]
        session = FakeSettingsSession(remote_rows)
        parent = SimpleNamespace(
            cookie_id="account",
            cookies_str="sid=1",
            cookies={"sid": "1"},
            device_id="device",
            last_message_received_time=0,
            message_cookie_refresh_cooldown=300,
            _safe_str=str,
        )
        manager = manager_module.CookieTokenManager(parent)
        runner = AsyncMock(return_value=(False, None, None))
        browser = AsyncMock(side_effect=AssertionError("force mode must not use browser runner"))
        fake_db = types.ModuleType("common.db.compat")
        fake_db.db_manager = SimpleNamespace(add_risk_control_log=lambda **_: None)
        slider_module = types.ModuleType("app.services.captcha.slider_stealth")
        slider_module.CAPTCHA_NOT_REQUIRED = object()
        slider_module.run_slider_verification_with_fallback = lambda *args, **kwargs: None

        with (
            patch.object(manager_module, "async_session_maker", lambda: FakeSessionContext(session)),
            patch.object(manager_module, "real_mouse_weighted_runner", SimpleNamespace(submit=runner)),
            patch.object(manager_module, "run_browser_task", browser),
            patch.object(manager_module, "is_real_mouse_enabled", return_value=False),
            patch.dict(
                sys.modules,
                {
                    "common.db.compat": fake_db,
                    "app.services.captcha.slider_stealth": slider_module,
                },
            ),
        ):
            asyncio.run(manager.handle_captcha_verification({"data": {"url": "https://slider.test"}}))

        runner.assert_awaited_once()
        args, kwargs = runner.await_args.args, runner.await_args.kwargs
        self.assertEqual(args[0], "local")
        self.assertIsNone(args[-1])
        self.assertEqual(kwargs["weight_class"], "local")
        self.assertTrue(kwargs["force_real_mouse"])
        browser.assert_not_awaited()

    def test_force_false_keeps_remote_config_on_original_browser_branch(self):
        manager_module = load_cookie_manager()
        manager = manager_module.CookieTokenManager(
            SimpleNamespace(
                cookie_id="account",
                cookies_str="sid=1",
                cookies={"sid": "1"},
                device_id="device",
                last_message_received_time=0,
                message_cookie_refresh_cooldown=300,
                _safe_str=str,
            )
        )
        remote_config = {"url": "https://remote.test", "secret": "secret"}
        runner = AsyncMock(side_effect=AssertionError("remote config should use original branch"))
        browser = AsyncMock(return_value=(False, None, None))
        fake_db = types.ModuleType("common.db.compat")
        fake_db.db_manager = SimpleNamespace(add_risk_control_log=lambda **_: None)
        slider_module = types.ModuleType("app.services.captcha.slider_stealth")
        slider_module.CAPTCHA_NOT_REQUIRED = object()
        slider_module.run_slider_verification_with_fallback = lambda *args, **kwargs: None

        with (
            patch.object(manager, "_load_remote_captcha_config", AsyncMock(return_value=(remote_config, False))),
            patch.object(manager_module, "real_mouse_weighted_runner", SimpleNamespace(submit=runner)),
            patch.object(manager_module, "run_browser_task", browser),
            patch.dict(
                sys.modules,
                {
                    "common.db.compat": fake_db,
                    "app.services.captcha.slider_stealth": slider_module,
                },
            ),
        ):
            asyncio.run(manager.handle_captcha_verification({"data": {"url": "https://slider.test"}}))

        browser.assert_awaited_once()
        self.assertIs(browser.await_args.args[-1], remote_config)
        self.assertFalse(browser.await_args.kwargs["force_real_mouse"])
        runner.assert_not_awaited()

    def test_force_true_local_entry_fails_when_real_mouse_is_unavailable(self):
        manager_module = load_cookie_manager()
        manager = manager_module.CookieTokenManager(
            SimpleNamespace(
                cookie_id="account",
                cookies_str="sid=1",
                cookies={"sid": "1"},
                device_id="device",
                last_message_received_time=0,
                message_cookie_refresh_cooldown=300,
                _safe_str=str,
            )
        )
        fake_db = types.ModuleType("common.db.compat")
        fake_db.db_manager = SimpleNamespace(
            add_risk_control_log=lambda **_: 1,
            update_risk_control_log=lambda **_: None,
        )
        unavailable = types.ModuleType("common.services.captcha.real_mouse_slider")
        unavailable.REAL_MOUSE_AVAILABLE = False
        slider_module = types.ModuleType("app.services.captcha.slider_stealth")
        slider_module.CAPTCHA_NOT_REQUIRED = object()
        slider_module.run_slider_verification_with_fallback = (
            orchestrator.run_slider_verification_with_fallback
        )
        submitted = []

        async def submit(weight, function, *args, **kwargs):
            submitted.append((weight, kwargs.copy()))
            return function(*args, **kwargs)

        with (
            patch.object(
                manager,
                "_load_remote_captcha_config",
                AsyncMock(return_value=(
                    {"url": "https://remote.test", "secret": "secret"},
                    True,
                )),
            ),
            patch.object(manager_module, "real_mouse_weighted_runner", SimpleNamespace(submit=submit)),
            patch.object(manager_module, "run_browser_task", AsyncMock()) as browser,
            patch.object(manager_module, "is_real_mouse_enabled", return_value=False),
            patch.object(orchestrator, "_call_remote_solve") as remote,
            patch.object(orchestrator, "run_slider_verification") as playwright,
            patch.object(orchestrator, "run_drissionpage_verification") as drissionpage,
            patch.dict(
                sys.modules,
                {
                    "common.db.compat": fake_db,
                    "app.services.captcha.slider_stealth": slider_module,
                    "common.services.captcha.real_mouse_slider": unavailable,
                },
            ),
        ):
            result = asyncio.run(
                manager.handle_captcha_verification({"data": {"url": "https://slider.test"}})
            )

        self.assertIsNone(result)
        self.assertEqual(submitted[0][0], "local")
        self.assertTrue(submitted[0][1]["force_real_mouse"])
        browser.assert_not_awaited()
        remote.assert_not_called()
        playwright.assert_not_called()
        drissionpage.assert_not_called()

    def test_force_snapshot_only_changes_the_next_token_task(self):
        manager_module = load_cookie_manager()
        manager = manager_module.CookieTokenManager(
            SimpleNamespace(
                cookie_id="account",
                cookies_str="sid=1",
                cookies={"sid": "1"},
                device_id="device",
                last_message_received_time=0,
                message_cookie_refresh_cooldown=300,
                _safe_str=str,
            )
        )
        setting = {"value": True}
        runner = AsyncMock(return_value=(False, None, None))
        browser = AsyncMock(return_value=(False, None, None))
        fake_db = types.ModuleType("common.db.compat")
        fake_db.db_manager = SimpleNamespace(add_risk_control_log=lambda **_: None)
        slider_module = types.ModuleType("app.services.captcha.slider_stealth")
        slider_module.CAPTCHA_NOT_REQUIRED = object()
        slider_module.run_slider_verification_with_fallback = lambda *args, **kwargs: None

        async def read_config():
            snapshot = setting["value"]
            if snapshot:
                setting["value"] = False
            return ({"url": "https://remote.test", "secret": "secret"}, snapshot)

        with (
            patch.object(manager, "_load_remote_captcha_config", AsyncMock(side_effect=read_config)),
            patch.object(manager_module, "real_mouse_weighted_runner", SimpleNamespace(submit=runner)),
            patch.object(manager_module, "run_browser_task", browser),
            patch.object(manager_module, "is_real_mouse_enabled", return_value=False),
            patch.dict(
                sys.modules,
                {
                    "common.db.compat": fake_db,
                    "app.services.captcha.slider_stealth": slider_module,
                },
            ),
        ):
            asyncio.run(manager.handle_captcha_verification({"data": {"url": "https://one.test"}}))
            asyncio.run(manager.handle_captcha_verification({"data": {"url": "https://two.test"}}))

        runner.assert_awaited_once()
        self.assertTrue(runner.await_args.kwargs["force_real_mouse"])
        browser.assert_awaited_once()
        self.assertFalse(browser.await_args.kwargs["force_real_mouse"])


class PasswordLoginForceTests(unittest.TestCase):
    def test_force_true_skips_remote_and_marks_local_websocket_call(self):
        flow = load_password_flow()
        flow.websocket_client.solve_captcha = AsyncMock(
            return_value={"success": True, "data": {"cookies": {"x5sec": "cookie"}}}
        )
        flow.solve_remote = AsyncMock(side_effect=AssertionError("force mode must skip remote"))

        result = asyncio.run(
            flow._solve_slider(
                "account",
                "https://slider.test",
                {"url": "https://remote.test", "secret": "secret", "force_real_mouse": True},
            )
        )

        self.assertEqual(result, ("ok", {"x5sec": "cookie"}, None))
        flow.solve_remote.assert_not_awaited()
        flow.websocket_client.solve_captcha.assert_awaited_once_with(
            account_id="account",
            url="https://slider.test",
            call_type="local",
            force_real_mouse=True,
        )

    def test_force_false_keeps_remote_priority(self):
        flow = load_password_flow()
        flow.solve_remote = AsyncMock(
            return_value=("ok", {"x5sec": "remote-cookie"}, None)
        )
        flow.websocket_client.solve_captcha = AsyncMock(
            side_effect=AssertionError("remote config should not call websocket")
        )

        result = asyncio.run(
            flow._solve_slider(
                "account",
                "https://slider.test",
                {"url": "https://remote.test", "secret": "secret", "force_real_mouse": False},
            )
        )

        self.assertEqual(result, ("ok", {"x5sec": "remote-cookie"}, None))
        flow.solve_remote.assert_awaited_once()
        flow.websocket_client.solve_captcha.assert_not_awaited()

    def test_force_failure_response_stays_local_without_remote_fallback(self):
        flow = load_password_flow()
        flow.websocket_client.solve_captcha = AsyncMock(
            return_value={"success": False, "message": "real mouse unavailable"}
        )
        flow.solve_remote = AsyncMock(side_effect=AssertionError("force mode must skip remote"))

        result = asyncio.run(
            flow._solve_slider(
                "account",
                "https://slider.test",
                {"url": "https://remote.test", "secret": "secret", "force_real_mouse": True},
            )
        )

        self.assertEqual(result, ("fail", None, "real mouse unavailable"))
        flow.solve_remote.assert_not_awaited()
        flow.websocket_client.solve_captcha.assert_awaited_once_with(
            account_id="account",
            url="https://slider.test",
            call_type="local",
            force_real_mouse=True,
        )

    def test_read_remote_config_reads_force_setting_from_async_db(self):
        flow = load_password_flow()
        from common.models.system_setting import SystemSetting

        session = FakeSettingsSession(
            [
                SystemSetting(key="captcha.remote_service_url", value="https://remote.test"),
                SystemSetting(key="captcha.remote_secret_key", value="secret"),
                SystemSetting(key="captcha.force_real_mouse", value="true"),
            ]
        )
        with patch.object(flow, "async_session_maker", lambda: FakeSessionContext(session)):
            config = asyncio.run(flow._read_remote_config())

        self.assertEqual(config["url"], "https://remote.test")
        self.assertEqual(config["secret"], "secret")
        self.assertTrue(config["force_real_mouse"])
        assert_query_contains(self, session, "captcha.force_real_mouse")

    def test_decide_mode_auto_force_true_uses_protocol(self):
        route = load_password_route()
        from common.models.system_setting import SystemSetting

        session = FakeSettingsSession(
            [SystemSetting(key="password_login.mode", value="auto"),
             SystemSetting(key="captcha.force_real_mouse", value="true")]
        )

        self.assertTrue(asyncio.run(route._decide_mode(session)))
        assert_query_contains(self, session, "captcha.force_real_mouse")


class ExternalCaptchaBoundaryTests(unittest.TestCase):
    def test_empty_url_preserves_precreated_risk_log_id(self):
        internal = load_internal_route()

        response = asyncio.run(
            internal.solve_captcha(
                internal.SolveCaptchaRequest(url=" ", risk_log_id=123)
            )
        )

        self.assertEqual(response["code"], 400)
        self.assertEqual(response["_risk_log_id"], 123)

    def test_public_backend_route_always_sends_remote_without_force(self):
        captcha = load_captcha_route()
        from common.models.user import User

        user = SimpleNamespace(username="admin")

        class UserSession(FakeSettingsSession):
            async def execute(self, _statement):
                return FakeResult(scalar=user)

        session = UserSession()
        captcha.websocket_client.solve_captcha = AsyncMock(
            return_value={"success": False, "message": "failed"}
        )
        request = captcha.SliderSolveRequest(
            secret_key="secret",
            account_id="external",
            url="https://slider.test",
        )

        with patch.object(captcha, "_is_remote_slider_blocked", AsyncMock(return_value=False)):
            asyncio.run(captcha.slider_solve(request, db=session))

        captcha.websocket_client.solve_captcha.assert_awaited_once()
        call = captcha.websocket_client.solve_captcha.await_args.kwargs
        self.assertEqual(call["call_type"], "remote")
        self.assertFalse(call["force_real_mouse"])
        self.assertIs(User, captcha.User)

    def test_websocket_external_calls_keep_remote_weight_buckets(self):
        internal = load_internal_route()
        fake_db = types.ModuleType("common.db.compat")
        fake_db.db_manager = SimpleNamespace(add_risk_control_log=lambda **_: None)
        slider_module = types.ModuleType("app.services.captcha.slider_stealth")
        slider_module.CAPTCHA_NOT_REQUIRED = object()
        slider_module.run_slider_verification_with_fallback = lambda *args, **kwargs: None
        browser = AsyncMock(return_value=(False, None, None))

        with (
            patch.object(internal, "is_real_mouse_enabled", return_value=False),
            patch.object(internal, "run_browser_task", browser),
            patch.dict(
                sys.modules,
                {
                    "common.db.compat": fake_db,
                    "app.services.captcha.slider_stealth": slider_module,
                },
            ),
        ):
            asyncio.run(
                internal.solve_captcha(
                    internal.SolveCaptchaRequest(
                        url="https://slider.test",
                        call_type="remote",
                        force_real_mouse=True,
                    )
                )
            )
            asyncio.run(
                internal.solve_captcha(
                    internal.SolveCaptchaRequest(
                        url="https://slider.test",
                        call_type="remote",
                        cookies="sid=1",
                        force_real_mouse=True,
                    )
                )
            )

        self.assertEqual(browser.await_count, 2)
        first_kwargs = browser.await_args_list[0].kwargs
        second_kwargs = browser.await_args_list[1].kwargs
        self.assertEqual(first_kwargs["weight_class"], "remote")
        self.assertEqual(second_kwargs["weight_class"], "remote_cookie")
        self.assertFalse(first_kwargs["force_real_mouse"])
        self.assertFalse(second_kwargs["force_real_mouse"])


class StartupLogContractTests(unittest.TestCase):
    def test_bootstrap_runtime_logs_process_value_and_parsed_value_after_setup(self):
        cases = ((None, False), ("true", True), ("false", False))
        for raw_value, parsed_value in cases:
            with self.subTest(raw_value=raw_value):
                if raw_value is None:
                    with patch.dict(os.environ, {}, clear=False):
                        os.environ.pop("CAPTCHA_REAL_MOUSE", None)
                        events, logger_calls, stderr, error = load_bootstrap_snapshot(raw_value)
                else:
                    with patch.dict(os.environ, {"CAPTCHA_REAL_MOUSE": raw_value}):
                        events, logger_calls, stderr, error = load_bootstrap_snapshot(raw_value)

                self.assertIsNone(error)
                self.assertEqual(stderr, "")
                self.assertEqual([event[0] for event in events], ["setup_logging"])
                self.assertEqual([call[0] for call in logger_calls], ["logger.info"])
                self.assertEqual(len(events), 1)
                self.assertEqual(len(logger_calls), 1)
                self.assertIn(f"process_env={raw_value!r}", logger_calls[0][1])
                self.assertIn(f"parsed_enabled={parsed_value}", logger_calls[0][1])

    def test_bootstrap_reports_raw_empty_value_before_reraising_parse_error(self):
        with patch.dict(os.environ, {"CAPTCHA_REAL_MOUSE": ""}):
            events, logger_calls, stderr, error = load_bootstrap_snapshot("")

        self.assertIsNotNone(error)
        self.assertIn("ValidationError", type(error).__name__)
        self.assertEqual(events, [])
        self.assertEqual(logger_calls, [])
        self.assertEqual(
            stderr,
            "CAPTCHA_REAL_MOUSE 启动配置: process_env='', parsed_enabled=<parse_failed>\n",
        )

    def test_startup_snapshot_fields_and_order_are_preserved(self):
        path = ROOT / "websocket/_bootstrap.py"
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))

        def call_line(function_name):
            lines = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name) and node.func.id == function_name:
                    lines.append(node.lineno)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == function_name:
                    lines.append(node.lineno)
            return min(lines)

        raw_assignment = next(
            node.lineno
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "raw_captcha_real_mouse" for target in node.targets)
        )
        get_settings_line = call_line("get_settings")
        setup_logging_line = call_line("setup_logging")
        logger_info_line = next(
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "info"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        )

        self.assertLess(raw_assignment, get_settings_line)
        self.assertLess(get_settings_line, setup_logging_line)
        self.assertLess(setup_logging_line, logger_info_line)
        self.assertIn("os.getenv(\"CAPTCHA_REAL_MOUSE\")", source)
        self.assertIn("process_env={raw_captcha_real_mouse!r}", source)
        self.assertIn("parsed_enabled={settings.captcha_real_mouse_enabled}", source)


if __name__ == "__main__":
    unittest.main()
