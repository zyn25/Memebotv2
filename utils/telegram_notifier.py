"""
Telegram notifications
"""
import httpx
from config import config
from utils.logger import logger

class TelegramNotifier:
    def __init__(self):
        self.token = config.notification.telegram_token
        self.chat_id = config.notification.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.enabled = bool(self.token and self.chat_id)

    async def send_message(self, msg, parse_mode="HTML"):
        if not self.enabled: return
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post(f"{self.base_url}/sendMessage",
                    json={"chat_id":self.chat_id,"text":msg,"parse_mode":parse_mode,
                          "disable_web_page_preview":True}, timeout=10)
                if r.status_code != 200:
                    logger.warning(f"Telegram error: {r.text}")
        except Exception as e:
            logger.error(f"Telegram failed: {e}")

    async def notify_scan(self, td):
        if not config.notification.notify_on_scan: return
        await self.send_message(
            f"NEW TOKEN\n\n"
            f"Name: {td.get('name','?')}\n"
            f"Symbol: {td.get('symbol','???')}\n"
            f"Liq: {td.get('liquidity_sol',0):.1f} SOL\n"
            f"Holders: {td.get('holder_count',0)}\n"
            f"Rug: {td.get('rugpull_score','?')}/100\n"
            f"Addr: {td.get('address','')}")

    async def notify_buy(self, td):
        if not config.notification.notify_on_buy: return
        await self.send_message(
            f"BUY EXECUTED\n\n"
            f"Token: {td.get('symbol','???')}\n"
            f"Amount: {td.get('amount_sol',0):.4f} SOL\n"
            f"Price: ${td.get('price',0):.10f}\n"
            f"Tokens: {td.get('tokens_received',0):,.0f}\n"
            f"Rug Score: {td.get('rug_score','?')}/100")

    async def notify_sell(self, td):
        if not config.notification.notify_on_sell: return
        pnl = td.get("pnl_percent", 0)
        e = "WIN" if pnl >= 0 else "LOSS"
        await self.send_message(
            f"SELL EXECUTED ({e})\n\n"
            f"Token: {td.get('symbol','???')}\n"
            f"SOL: {td.get('sol_received',0):.4f}\n"
            f"PnL: {pnl:+.2f}%\n"
            f"Duration: {td.get('hold_time','N/A')}\n"
            f"Reason: {td.get('reason','N/A')}")

    async def notify_alert(self, msg):
        await self.send_message(f"ALERT\n\n{msg}")

notifier = TelegramNotifier()