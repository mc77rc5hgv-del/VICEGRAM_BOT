import base64
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
os.environ.setdefault("BOT_TOKEN", "123456:FAKE_TOKEN_FOR_OFFLINE_TESTS")
os.environ.setdefault("HYSTERIA_SERVER_ENDPOINT", "127.0.0.1:443")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))
import bot
import routing_profiles as routing
from qr import config_to_qr_png

class ProfileTests(unittest.TestCase):
    def test_roundtrip_qr_and_proxy_default(self):
        for mode in ("universal", "full"):
            uri = routing.routing_uri(mode)
            decoded = json.loads(base64.b64decode(uri.removeprefix("happ://routing/onadd/")))
            self.assertEqual(decoded, routing.profile(mode))
            self.assertEqual(decoded["GlobalProxy"], "true")
            self.assertNotIn("geoip:ru", decoded["DirectIp"])
            self.assertLess(len(uri), 3000)
            self.assertTrue(config_to_qr_png(uri).read().startswith(b"\x89PNG"))
        with self.assertRaises(ValueError):
            routing.profile("bad")

    def test_full_removes_public_exceptions_in_same_profile(self):
        universal, full = routing.profile("universal"), routing.profile("full")
        self.assertEqual(universal["Name"], full["Name"])
        self.assertEqual(full["DirectSites"], [])
        self.assertIn("domain:ru", universal["DirectSites"])
        self.assertIn("domain:xn--p1ai", universal["DirectSites"])
        self.assertNotIn("domain:com", universal["DirectSites"])
        self.assertEqual(full["DomesticDNSType"], "DoH")
        self.assertEqual(full["DirectIp"], list(routing.LOCAL_NETWORKS))

class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def callback(self, mode="universal", chat=1):
        return SimpleNamespace(answer=AsyncMock(), data="routing:" + mode,
            from_user=SimpleNamespace(id=1), message=SimpleNamespace(chat=SimpleNamespace(id=chat)),
            bot=SimpleNamespace(send_message=AsyncMock(), send_document=AsyncMock(), send_photo=AsyncMock()))

    async def test_unpaid_and_wrong_owner_denied(self):
        for paid,chat in ((None,1),(object(),2)):
            cb = self.callback(chat=chat)
            with patch.object(bot.db, "get_paid_client", return_value=paid):
                await bot.cb_routing_profile(cb)
            cb.bot.send_document.assert_not_awaited()
            cb.bot.send_photo.assert_not_awaited()

    async def test_paid_gets_import_not_credentials(self):
        cb = self.callback()
        with patch.object(bot.db, "get_paid_client", return_value=object()):
            await bot.cb_routing_profile(cb)
        cb.bot.send_document.assert_awaited_once()
        cb.bot.send_photo.assert_awaited_once()
        text = cb.bot.send_message.call_args.args[1]
        self.assertIn("happ://routing/onadd/", text)
        self.assertNotIn("hysteria2://", text)
        self.assertLess(len(text),4096)

    async def test_unknown_mode_is_ignored(self):
        cb = self.callback("bad")
        await bot.cb_routing_profile(cb)
        cb.bot.send_message.assert_not_awaited()
