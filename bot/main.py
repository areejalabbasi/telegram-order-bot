# run: python -m bot.main
import logging
import os
import time

from dotenv import load_dotenv

from .handlers import Bot
from .store import Store
from .telegram_api import TelegramAPI, TelegramError

log = logging.getLogger("order-bot")


def run():
    load_dotenv()
    token = os.environ["BOT_TOKEN"]
    admin_chat_id = int(os.environ["ADMIN_CHAT_ID"])
    db_path = os.environ.get("DB_PATH", "orders.db")

    api = TelegramAPI(token)
    bot = Bot(api, Store(db_path), admin_chat_id)
    offset = None
    log.info("bot started, polling for updates")

    while True:
        try:
            updates = api.get_updates(offset=offset)
        except (TelegramError, OSError) as exc:
            log.warning("polling failed: %s, retrying in 5s", exc)
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                bot.handle(update)
            except Exception:
                log.exception("failed to handle update %s", update.get("update_id"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
