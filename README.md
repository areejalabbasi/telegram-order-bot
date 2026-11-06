# telegram-order-bot

Telegram bot for taking coffee shop orders. Customers order from a menu inside the chat, and the shop gets each order with buttons to update its status. The bot replies in Arabic.

### What it does
- `/menu` shows menu items as buttons, and tapping one adds it to the cart
- cart with +/- and total
- checkout asks for the phone number (share contact or type it, Saudi numbers only)
- new orders are sent to the admin chat
- admin can set preparing / ready / done / cancelled, and the customer gets notified each time
- `/orders` (admin only) lists open orders

### Stack
Python + `requests` straight to the Bot API (no framework), SQLite, long polling.

### Setup
1. Get a token from [@BotFather](https://t.me/BotFather)
2. Get your chat id from [@userinfobot](https://t.me/userinfobot)
3.
```
pip install -r requirements.txt
cp .env.example .env    # add token + chat id
python -m bot.main
```

### Tests
```
pytest
```

### Next
- menu from Google Sheets
- payment link (Moyasar / Tap)
