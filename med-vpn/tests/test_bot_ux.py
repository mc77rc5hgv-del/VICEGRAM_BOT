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
    return SimpleNamespace(telegram_id=1,is_active=True, expires_at=expiry, username="test", password="fake")

class StateTests(unittest.TestCase):
    def test_expired_malformed_and_revoked_access_is_not_active(self):
        now = datetime.now(timezone.utc)
        for expiry in [(now-timedelta(seconds=1)).isoformat(), "broken", "2026-01-01"]:
            self.assertFalse(ux.has_access(client(expiry),now))
        self.assertTrue(ux.has_access(client((now+timedelta(days=1)).isoformat()),now))
        self.assertFalse(ux.has_access(client(),now))
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
        with patch.object(bot.db,"get_paid_client",return_value=None), \
             patch.object(bot.hysteria,"generate_credentials") as generate, \
             patch.object(bot,"_send_config",new_callable=AsyncMock) as send:
            await bot._handle_myconfig(api,1,1,None)
            generate.assert_not_called()
            send.assert_not_awaited()
        self.assertIn("оплаченная",api.send_message.call_args.args[1])

    async def test_config_html_and_qr_navigation(self):
        api = SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock())
        uri = "hysteria2://test:fake@127.0.0.1/?sni=a&pinSHA256=00#test"
        with patch.object(bot.db,"get_paid_client",return_value=client()), patch.object(bot.hysteria,"build_hysteria_uri",return_value=uri), \
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

class PaidConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_starts_with_instructions_not_credentials(self):
        api = SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock())
        with patch.object(bot.db,"get_paid_client",return_value=client()), \
             patch.object(bot,"_send_config",new_callable=AsyncMock) as send:
            await bot._handle_myconfig(api,1,1,None)
            send.assert_not_awaited()
        self.assertIn("шаг 1",api.send_message.call_args.args[1])
        api.send_photo.assert_not_awaited()

    async def test_final_sender_rechecks_payment_and_owner(self):
        for paid,chat in [(None,1),(client(),2)]:
            api = SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock())
            with patch.object(bot.db,"get_paid_client",return_value=paid), \
                 patch.object(bot.hysteria,"build_hysteria_uri") as uri:
                await bot._send_config(api,chat,client())
                uri.assert_not_called()
                api.send_photo.assert_not_awaited()

    async def test_stale_final_button_after_expiry_cannot_deliver(self):
        callback = SimpleNamespace(answer=AsyncMock(),data="config:android",
            from_user=SimpleNamespace(id=1,username=None),
            message=SimpleNamespace(chat=SimpleNamespace(id=1)),
            bot=SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock()))
        with patch.object(bot.db,"get_paid_client",return_value=None), \
             patch.object(bot,"_send_config",new_callable=AsyncMock) as send:
            await bot.cb_final_config(callback)
            send.assert_not_awaited()
        self.assertIn("оплаченная",callback.bot.send_message.call_args.args[1])

    def test_unified_menu_and_final_step(self):
        labels = [button.text for row in kb.main_menu(False).inline_keyboard for button in row]
        self.assertFalse(any("Как подключиться" in label for label in labels))
        for platform in ux.PLATFORMS:
            callbacks = [button.callback_data for row in kb.guide_menu(platform).inline_keyboard for button in row]
            self.assertIn("config:" + platform,callbacks)

    def test_invoice_owner_currency_and_amount_are_validated(self):
        self.assertIsNotNone(bot._payment_plan("sub:1m:1",1,"XTR",150))
        for payload,owner,currency,amount in [
            ("sub:1m:2",1,"XTR",150),("sub:1m:1",1,"RUB",150),
            ("sub:1m:1",1,"XTR",1),("bad",1,"XTR",150)]:
            self.assertIsNone(bot._payment_plan(payload,owner,currency,amount))

class PaidDatabaseTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.settings = patch.object(bot.db,"settings",SimpleNamespace(
            db_path=str(Path(self.temp.name)/"test.db"),referral_commission_rate=0.1))
        self.settings.start()
        bot.db.init_db()

    def tearDown(self):
        self.settings.stop()
        self.temp.cleanup()

    def test_free_expired_revoked_and_unpaid_cannot_get_config(self):
        bot.db.create_client(1,None,"test","fake")
        self.assertIsNone(bot.db.get_paid_client(1))
        bot.db.extend_expiry(1,1)
        self.assertIsNone(bot.db.get_paid_client(1))
        bot.db.record_purchase(1,149,"RUB")
        self.assertIsNotNone(bot.db.get_paid_client(1))
        with bot.db._connect() as conn:
            conn.execute("UPDATE clients SET expires_at = ? WHERE telegram_id = 1",
                ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
        self.assertIsNone(bot.db.get_paid_client(1))
        bot.db.extend_expiry(1,1)
        bot.db.revoke_client(1)
        self.assertIsNone(bot.db.get_paid_client(1))

    def test_payment_history_is_scoped_and_referrals_count_unique_payers(self):
        bot.db.get_or_create_user(2,None,1)
        bot.db.record_purchase(2,149,"RUB")
        bot.db.record_purchase(2,150,"XTR")
        self.assertEqual(bot.db.paying_referrals(1),1)
        self.assertEqual(len(bot.db.purchase_history(2)),2)
        self.assertEqual(bot.db.purchase_history(1),[])
