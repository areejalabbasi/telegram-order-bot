import html
import re

from .menu import MENU

PHONE_RE = re.compile(r"^(?:\+?966|0)5\d{8}$")

STATUS_LABELS = {
    "preparing": "قيد التحضير ☕",
    "ready": "جاهز للاستلام ✅",
    "done": "تم الاستلام",
    "cancelled": "ملغي",
}


def money(n):
    return f"{n} ر.س"


def cart_total(cart: dict) -> int:
    return sum(MENU[i]["price"] * q for i, q in cart.items())


def cart_lines(cart: dict) -> str:
    lines = [f"• {MENU[i]['name']} × {q}: {money(MENU[i]['price'] * q)}" for i, q in cart.items()]
    return "\n".join(lines)


def normalize_phone(raw: str):
    phone = re.sub(r"[\s\-()]", "", raw or "")
    if not PHONE_RE.match(phone):
        return None
    if phone.startswith("+966"):
        phone = "0" + phone[4:]
    elif phone.startswith("966"):
        phone = "0" + phone[3:]
    return phone


class Bot:
    def __init__(self, api, store, admin_chat_id: int):
        self.api = api
        self.store = store
        self.admin_chat_id = admin_chat_id

    def handle(self, update: dict):
        if "callback_query" in update:
            self._on_callback(update["callback_query"])
        elif "message" in update:
            self._on_message(update["message"])

    def _menu_keyboard(self, user_id):
        cart = self.store.get_cart(user_id)
        rows = []
        for item_id, it in MENU.items():
            qty = cart.get(item_id, 0)
            label = f"{it['name']}: {money(it['price'])}" + (f"  ({qty})" if qty else "")
            rows.append([{"text": label, "callback_data": f"add:{item_id}"}])
        count = sum(cart.values())
        rows.append([{"text": f"🛒 السلة ({count})", "callback_data": "cart"}])
        return {"inline_keyboard": rows}

    def _cart_keyboard(self, cart):
        # cadd/crm = pressed from the cart screen
        rows = [[
            {"text": f"➖ {MENU[i]['name']}", "callback_data": f"crm:{i}"},
            {"text": "➕", "callback_data": f"cadd:{i}"},
        ] for i in cart]
        rows.append([{"text": "↩️ رجوع للمنيو", "callback_data": "menu"},
                     {"text": "🗑 تفريغ", "callback_data": "clear"}])
        rows.append([{"text": "✅ إتمام الطلب", "callback_data": "checkout"}])
        return {"inline_keyboard": rows}

    @staticmethod
    def _admin_keyboard(order_id):
        return {"inline_keyboard": [[
            {"text": "بدأ التحضير", "callback_data": f"st:{order_id}:preparing"},
            {"text": "جاهز", "callback_data": f"st:{order_id}:ready"},
        ], [
            {"text": "تم الاستلام", "callback_data": f"st:{order_id}:done"},
            {"text": "إلغاء", "callback_data": f"st:{order_id}:cancelled"},
        ]]}

    def _on_message(self, msg):
        chat_id = msg["chat"]["id"]
        user = msg["from"]
        user_id = user["id"]
        text = (msg.get("text") or "").strip()

        if text in ("/start", "/menu"):
            name = html.escape(user.get("first_name", ""))
            self.api.send_message(chat_id, f"أهلًا {name} 👋\nاختر من المنيو واضغط على أي صنف لإضافته للسلة:",
                                  self._menu_keyboard(user_id))
            return

        if text == "/orders" and chat_id == self.admin_chat_id:
            self._send_open_orders()
            return

        if self.store.get_state(user_id) == "awaiting_phone":
            raw = msg["contact"]["phone_number"] if "contact" in msg else text
            phone = normalize_phone(raw)
            if not phone:
                self.api.send_message(chat_id, "الرقم غير صحيح. اكتب رقم جوال سعودي مثل 0551234567، أو اضغط زر مشاركة الرقم.")
                return
            self._place_order(chat_id, user, phone)
            return

        self.api.send_message(chat_id, "اكتب /menu عشان تشوف المنيو.")

    def _on_callback(self, cq):
        data = cq.get("data", "")
        user_id = cq["from"]["id"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]

        if data.startswith("st:"):
            self._on_admin_status(cq, data)
            return

        action, _, item_id = data.partition(":")
        if action in ("add", "cadd", "crm"):
            if item_id not in MENU:
                self.api.answer_callback(cq["id"], "الصنف غير متوفر")
                return
            delta = -1 if action == "crm" else 1
            self.store.add_to_cart(user_id, item_id, delta)
            self.api.answer_callback(cq["id"], "تم الحذف" if delta < 0 else "تمت الإضافة")
            if action == "add":
                self.api.edit_message(chat_id, message_id, cq["message"].get("text", "المنيو"),
                                      self._menu_keyboard(user_id))
            else:
                self._show_cart(chat_id, message_id, user_id)
            return

        self.api.answer_callback(cq["id"])

        if data == "menu":
            self.api.edit_message(chat_id, message_id, "المنيو: اضغط على أي صنف لإضافته:",
                                  self._menu_keyboard(user_id))
        elif data == "cart":
            self._show_cart(chat_id, message_id, user_id)
        elif data == "clear":
            self.store.clear_cart(user_id)
            self.api.edit_message(chat_id, message_id, "تم تفريغ السلة.", self._menu_keyboard(user_id))
        elif data == "checkout":
            if not self.store.get_cart(user_id):
                self.api.send_message(chat_id, "السلة فاضية، أضف شي من المنيو أول.")
                return
            self.store.set_state(user_id, "awaiting_phone", cq["from"].get("first_name"))
            self.api.send_message(chat_id, "آخر خطوة: شاركنا رقم جوالك عشان نتواصل معك لما يجهز الطلب.", {
                "keyboard": [[{"text": "📱 مشاركة رقمي", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            })

    def _show_cart(self, chat_id, message_id, user_id):
        cart = self.store.get_cart(user_id)
        if not cart:
            self.api.edit_message(chat_id, message_id, "السلة فاضية.", self._menu_keyboard(user_id))
            return
        text = f"🛒 السلة\n\n{cart_lines(cart)}\n\n<b>المجموع: {money(cart_total(cart))}</b>"
        self.api.edit_message(chat_id, message_id, text, self._cart_keyboard(cart))

    def _place_order(self, chat_id, user, phone):
        user_id = user["id"]
        cart = self.store.get_cart(user_id)
        if not cart:
            self.store.set_state(user_id, None)
            self.api.send_message(chat_id, "السلة فاضية، اكتب /menu وابدأ من جديد.",
                                  {"remove_keyboard": True})
            return

        total = cart_total(cart)
        name = user.get("first_name", "")
        order_id = self.store.create_order(user_id, chat_id, name, phone, cart, total)
        self.store.clear_cart(user_id)
        self.store.set_state(user_id, None)

        self.api.send_message(
            chat_id,
            f"تم استلام طلبك رقم <b>#{order_id}</b> 🎉\n\n{cart_lines(cart)}\n\n"
            f"<b>المجموع: {money(total)}</b>\nبنرسل لك هنا أول ما يجهز.",
            {"remove_keyboard": True},
        )
        self.api.send_message(
            self.admin_chat_id,
            f"🔔 طلب جديد #{order_id}\nالعميل: {html.escape(name)}\nالجوال: {phone}\n\n"
            f"{cart_lines(cart)}\n\n<b>المجموع: {money(total)}</b>",
            self._admin_keyboard(order_id),
        )

    def _on_admin_status(self, cq, data):
        chat_id = cq["message"]["chat"]["id"]
        if chat_id != self.admin_chat_id:
            self.api.answer_callback(cq["id"], "غير مسموح")
            return
        _, order_id, status = data.split(":")
        order = self.store.get_order(int(order_id))
        if order is None:
            self.api.answer_callback(cq["id"], "الطلب غير موجود")
            return

        self.store.set_status(order["id"], status)
        self.api.answer_callback(cq["id"], STATUS_LABELS[status])
        self.api.send_message(order["chat_id"], f"تحديث طلبك #{order['id']}: {STATUS_LABELS[status]}")

        keyboard = None if status in ("done", "cancelled") else self._admin_keyboard(order["id"])
        self.api.edit_message(chat_id, cq["message"]["message_id"],
                              cq["message"].get("text", "") + f"\n\nالحالة: {STATUS_LABELS[status]}",
                              keyboard)

    def _send_open_orders(self):
        orders = self.store.open_orders()
        if not orders:
            self.api.send_message(self.admin_chat_id, "ما فيه طلبات مفتوحة.")
            return
        for o in orders:
            self.api.send_message(
                self.admin_chat_id,
                f"#{o['id']} · {html.escape(o['name'] or '')} · {o['phone']}\n"
                f"{cart_lines(o['items'])}\nالمجموع: {money(o['total'])} · الحالة: {o['status']}",
                self._admin_keyboard(o["id"]),
            )
