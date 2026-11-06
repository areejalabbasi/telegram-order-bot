import pytest

from bot.handlers import Bot, normalize_phone
from bot.store import Store

ADMIN = 999
CUSTOMER = {"id": 1, "first_name": "Sara"}


class FakeAPI:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.answered = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append((chat_id, message_id, text, reply_markup))

    def answer_callback(self, callback_id, text=None):
        self.answered.append(text)


@pytest.fixture
def bot():
    return Bot(FakeAPI(), Store(":memory:"), ADMIN)


def message(text=None, user=CUSTOMER, chat_id=1, contact=None):
    msg = {"chat": {"id": chat_id}, "from": user}
    if text is not None:
        msg["text"] = text
    if contact:
        msg["contact"] = {"phone_number": contact}
    return {"message": msg}


def press(data, user=CUSTOMER, chat_id=1, text=""):
    return {"callback_query": {
        "id": "cb", "data": data, "from": user,
        "message": {"chat": {"id": chat_id}, "message_id": 10, "text": text},
    }}


@pytest.mark.parametrize("raw,expected", [
    ("0551234567", "0551234567"),
    ("+966551234567", "0551234567"),
    ("966 55 123 4567", "0551234567"),
    ("055-123-4567", "0551234567"),
    ("12345", None),
    ("0451234567", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_start_shows_menu(bot):
    bot.handle(message("/start"))
    chat_id, text, kb = bot.api.sent[-1]
    assert "Sara" in text
    assert any(b["callback_data"] == "add:latte" for row in kb["inline_keyboard"] for b in row)


def test_add_and_remove_items(bot):
    bot.handle(press("add:latte"))
    bot.handle(press("add:latte"))
    bot.handle(press("add:cookie"))
    assert bot.store.get_cart(1) == {"latte": 2, "cookie": 1}

    bot.handle(press("crm:latte"))
    bot.handle(press("crm:cookie"))
    assert bot.store.get_cart(1) == {"latte": 1}


def test_cart_shows_total(bot):
    bot.handle(press("add:latte"))
    bot.handle(press("add:cookie"))
    bot.handle(press("cart"))
    text = bot.api.edited[-1][2]
    assert "33 ر.س" in text  # 21 + 12


def test_unknown_item_is_rejected(bot):
    bot.handle(press("add:pizza"))
    assert bot.store.get_cart(1) == {}
    assert bot.api.answered[-1] == "الصنف غير متوفر"


def test_checkout_with_empty_cart(bot):
    bot.handle(press("checkout"))
    assert "فاضية" in bot.api.sent[-1][1]
    assert bot.store.get_state(1) is None


def test_full_order_flow(bot):
    bot.handle(press("add:v60"))
    bot.handle(press("add:basbousa"))
    bot.handle(press("checkout"))
    assert bot.store.get_state(1) == "awaiting_phone"

    bot.handle(message("123"))  # bad number
    assert "غير صحيح" in bot.api.sent[-1][1]

    bot.handle(message(contact="+966551234567"))

    customer_msg, admin_msg = bot.api.sent[-2], bot.api.sent[-1]
    assert customer_msg[0] == 1 and "#1" in customer_msg[1]
    assert admin_msg[0] == ADMIN and "0551234567" in admin_msg[1] and "38 ر.س" in admin_msg[1]

    order = bot.store.get_order(1)
    assert order["items"] == {"v60": 1, "basbousa": 1}
    assert order["total"] == 38
    assert bot.store.get_cart(1) == {}
    assert bot.store.get_state(1) is None


def test_admin_updates_status_and_customer_is_notified(bot):
    bot.handle(press("add:latte"))
    bot.handle(press("checkout"))
    bot.handle(message("0551234567"))

    bot.handle(press("st:1:ready", user={"id": ADMIN}, chat_id=ADMIN, text="طلب جديد #1"))
    assert bot.store.get_order(1)["status"] == "ready"
    assert bot.api.sent[-1][0] == 1
    assert "جاهز" in bot.api.sent[-1][1]


def test_customer_cannot_change_status(bot):
    bot.handle(press("add:latte"))
    bot.handle(press("checkout"))
    bot.handle(message("0551234567"))

    bot.handle(press("st:1:done"))
    assert bot.store.get_order(1)["status"] == "new"
    assert bot.api.answered[-1] == "غير مسموح"


def test_admin_can_list_open_orders(bot):
    for _ in range(2):
        bot.handle(press("add:latte"))
        bot.handle(press("checkout"))
        bot.handle(message("0551234567"))
    bot.handle(press("st:1:done", user={"id": ADMIN}, chat_id=ADMIN))

    bot.api.sent.clear()
    bot.handle(message("/orders", user={"id": ADMIN}, chat_id=ADMIN))
    assert len(bot.api.sent) == 1 and "#2" in bot.api.sent[0][1]
