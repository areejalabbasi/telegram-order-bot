# minimal telegram bot api client (only what the bot uses)
import requests


class TelegramError(Exception):
    pass


class TelegramAPI:
    def __init__(self, token: str, timeout: int = 35):
        self.base = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout
        self.session = requests.Session()

    def _call(self, method: str, **params):
        resp = self.session.post(f"{self.base}/{method}", json=params, timeout=self.timeout)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', 'unknown error')}")
        return data["result"]

    def get_updates(self, offset=None, timeout=30):
        return self._call("getUpdates", offset=offset, timeout=timeout,
                          allowed_updates=["message", "callback_query"])

    def send_message(self, chat_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self._call("sendMessage", **params)

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self._call("editMessageText", **params)

    def answer_callback(self, callback_id, text=None):
        return self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)
