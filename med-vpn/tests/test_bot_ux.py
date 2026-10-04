import asyncio
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:FAKE_TOKEN_FOR_OFFLINE_TESTS")
os.environ.setdefault("HYSTERIA_SERVER_ENDPOINT", "127.0.0.1:443")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))
import bot
import ux
import keyboards as kb
from aiogram.types import Message, Chat, User

def client(expiry=None):
    return SimpleNamespace(is_active=True, expires_at=expiry, username="test", password="fake")

class StateTests(unittest.TestCase):
    def test_expired_malformed_and_revoked_access_is_not_active(self):
        now = datetime.now(timezone.utc)
        for expiry in [(now-timedelta(seconds=1)).isoformat(), "broken", "2026-01-01"]:
            self.assertFalse(ux.has_access(client(expiry),now))
        self.assertTrue(ux.has_access(client((now+timedelta(days=1)).isoformat()),now))
        self.assertTrue(ux.has_access(client(),now))
        revoked = client(); revoked.is_active = False
        self.assertFalse(ux.has_access(revoked,now))

    def test_navigation_and_copy_limits(self):
        buttons = [b for row in kb.main_menu(False,True).inline_keyboard for b in row]
        self.assertTrue(any(b.callback_data == "myconfig" for b in buttons))
        self.assertFalse(any(b.callback_data == "admin_menu" for b in buttons))
        self.assertTrue(any("Продлить" in b.text for b in buttons))
        self.assertIsNotNone(kb.connection_menu("x"*256).inline_keyboard[0][0].copy_text)
        self.assertTrue(all(b.copy_text is None for row in kb.connection_menu("x"*257).inline_keyboard for b in row))
        self.assertIsNone(ux.guide("arbitrary"))
        for platform in ux.PLATFORMS:
            self.assertIn("Happ",ux.guide(platform))

class HandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_chat_gate_prevents_group_credentials(self):
        for kind,allowed in [("private",True),("group",False),("supergroup",False)]:
            message = Message(message_id=1,date=datetime.now(timezone.utc),
                chat=Chat(id=1,type=kind),from_user=User(id=1,is_bot=False,first_name="Test"),
                text="/myconfig")
            result,_ = await bot.router.message.check_root_filters(message)
            self.assertEqual(bool(result),allowed)

    async def test_expired_client_is_not_reissued_or_provisioned(self):
        api = SimpleNamespace(send_message=AsyncMock())
        expired = client((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())
        with patch.object(bot.db,"get_active_client",return_value=expired), \
             patch.object(bot.hysteria,"generate_credentials") as generate, \
             patch.object(bot,"_send_config",new_callable=AsyncMock) as send:
            await bot._handle_myconfig(api,1,1,None)
            generate.assert_not_called()
            send.assert_not_awaited()
        self.assertIn("истёк",api.send_message.call_args.args[1])

    async def test_config_html_and_qr_navigation(self):
        api = SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock())
        uri = "hysteria2://test:fake@127.0.0.1/?sni=a&pinSHA256=00#test"
        with patch.object(bot.hysteria,"build_hysteria_uri",return_value=uri), \
             patch.object(bot,"config_to_qr_png",return_value=io.BytesIO(b"fixture")):
            await bot._send_config(api,1,client())
        kwargs = api.send_message.call_args.kwargs
        self.assertEqual(kwargs["parse_mode"],"HTML")
        self.assertIn("&amp;",api.send_message.call_args.args[1])
        self.assertIsNotNone(kwargs["reply_markup"])
        api.send_photo.assert_awaited_once()

    async def test_navigation_edits_in_place(self):
        message = SimpleNamespace(text="Menu",photo=[],edit_text=AsyncMock(),answer=AsyncMock())
        await bot._screen(SimpleNamespace(message=message),"Menu",kb.main_menu(False))
        message.edit_text.assert_awaited_once()
        message.answer.assert_not_awaited()

if __name__ == "__main__":
    unittest.main()

class CredentialNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_keeps_the_previously_delivered_link(self):
        message = SimpleNamespace(text="hysteria2://test:fake@127.0.0.1",photo=[],
                                  edit_text=AsyncMock(),answer=AsyncMock())
        await bot._screen(SimpleNamespace(message=message),"Help",kb.platforms_menu())
        message.edit_text.assert_not_awaited()
        message.answer.assert_awaited_once()
