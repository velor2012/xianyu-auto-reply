import sys
import types
import unittest
from unittest.mock import patch

from common.services.captcha import orchestrator


class RealMouseForceTests(unittest.TestCase):
    def test_force_skips_remote_and_does_not_fallback_after_failure(self):
        module = types.ModuleType("common.services.captcha.real_mouse_slider")
        module.REAL_MOUSE_AVAILABLE = True
        module.run_real_mouse_verification = lambda *args, **kwargs: (False, None)

        with (
            patch.dict(sys.modules, {"common.services.captcha.real_mouse_slider": module}),
            patch.object(orchestrator, "_real_mouse_enabled", return_value=False),
            patch.object(orchestrator, "_call_remote_solve") as remote,
            patch.object(orchestrator, "run_slider_verification") as playwright,
            patch.object(orchestrator, "run_drissionpage_verification") as drissionpage,
        ):
            result = orchestrator.run_slider_verification_with_fallback(
                "account",
                "https://example.test/punish",
                remote_config={"url": "https://remote.test", "secret": "secret"},
                force_real_mouse=True,
            )

        self.assertEqual(result, (False, None, None))
        remote.assert_not_called()
        playwright.assert_not_called()
        drissionpage.assert_not_called()

    def test_force_unavailable_fails_without_playwright(self):
        module = types.ModuleType("common.services.captcha.real_mouse_slider")
        module.REAL_MOUSE_AVAILABLE = False
        module.run_real_mouse_verification = lambda *args, **kwargs: (False, None)

        with (
            patch.dict(sys.modules, {"common.services.captcha.real_mouse_slider": module}),
            patch.object(orchestrator, "_real_mouse_enabled", return_value=False),
            patch.object(orchestrator, "run_slider_verification") as playwright,
        ):
            result = orchestrator.run_slider_verification_with_fallback(
                "account",
                "https://example.test/punish",
                force_real_mouse=True,
            )

        self.assertEqual(result, (False, None, None))
        playwright.assert_not_called()

    def test_environment_real_mouse_keeps_remote_priority(self):
        with (
            patch.object(orchestrator, "_real_mouse_enabled", return_value=True),
            patch.object(
                orchestrator,
                "_call_remote_solve",
                return_value=("ok", {"x5sec": "cookie"}, None),
            ) as remote,
            patch.object(orchestrator, "run_slider_verification") as playwright,
        ):
            result = orchestrator.run_slider_verification_with_fallback(
                "account",
                "https://example.test/punish",
                remote_config={"url": "https://remote.test", "secret": "secret"},
            )

        self.assertEqual(result, (True, {"x5sec": "cookie"}, "remote"))
        remote.assert_called_once()
        playwright.assert_not_called()


if __name__ == "__main__":
    unittest.main()
