import unittest
from unittest.mock import patch, MagicMock
from api.telegram_antispam import is_spam_message, check_and_handle_spam


class TestTelegramAntiSpam(unittest.TestCase):
    def test_is_spam_message_arabic_and_english(self):
        self.assertFalse(is_spam_message("صباح الخير يا شباب سهم فوري اخباره ايه؟"))
        self.assertFalse(is_spam_message("What do you think of COMI stock?"))
        self.assertFalse(is_spam_message("/start"))
        self.assertFalse(is_spam_message("https://egxbots.com/scanner"))
        self.assertFalse(is_spam_message(""))
        self.assertFalse(is_spam_message("   "))

    def test_is_spam_message_cyrillic_russian(self):
        self.assertTrue(is_spam_message("Ребята, всем привет, у нас запара на заводе кирпича"))
        self.assertTrue(is_spam_message("Нужны курьеры на подработку"))
        self.assertTrue(is_spam_message("Водительская служба в поиске новых сотрудников"))
        self.assertTrue(is_spam_message("", caption="Заходите в наш канал"))

    @patch("requests.post")
    def test_check_and_handle_spam_in_group(self, mock_post):
        mock_post.return_value.json.return_value = {"ok": True}

        msg = {
            "message_id": 9999,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "from": {"id": 12345678, "first_name": "Ivan", "last_name": "Spammer", "username": "spambot"},
            "text": "Нужны курьеры на подработку пишите в личку",
        }

        handled = check_and_handle_spam(msg, bot_token="TEST_BOT_TOKEN")
        self.assertTrue(handled)

        # Ensure deleteMessage, banChatMember, and sendMessage were called
        urls_called = [call.args[0] for call in mock_post.call_args_list]
        self.assertTrue(any("deleteMessage" in u for u in urls_called))
        self.assertTrue(any("banChatMember" in u for u in urls_called))
        self.assertTrue(any("sendMessage" in u for u in urls_called))

    @patch("requests.post")
    def test_check_and_handle_spam_ignores_clean_message(self, mock_post):
        msg = {
            "message_id": 1000,
            "chat": {"id": -1002083067817, "type": "supergroup"},
            "from": {"id": 8888, "first_name": "Ahmed"},
            "text": "تحليل سهم مصر للأسمنت ايه؟",
        }
        handled = check_and_handle_spam(msg, bot_token="TEST_BOT_TOKEN")
        self.assertFalse(handled)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_check_and_handle_spam_ignores_private_chat(self, mock_post):
        msg = {
            "message_id": 1001,
            "chat": {"id": 8888, "type": "private"},
            "from": {"id": 8888, "first_name": "Ivan"},
            "text": "Привет",
        }
        handled = check_and_handle_spam(msg, bot_token="TEST_BOT_TOKEN")
        self.assertFalse(handled)
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
