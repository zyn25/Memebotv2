"""
Live Price Feed + Smart Alerts
"""
import asyncio
import aiohttp
from typing import Dict
from config import config
from utils.logger import logger


class PriceFeed:
    def __init__(self):
        self.session = None
        self.running = False
        self.bot_instance = None
        self.tg_bot = None
        self.prices: Dict[str, float] = {}
        self.sol_price = 150.0
        self.update_interval = 10

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        self.running = False
        if self.session:
            await self.session.close()

    async def start(self, bot_instance, tg_bot=None):
        self.running = True
        self.bot_instance = bot_instance
        self.tg_bot = tg_bot
        logger.info("Price Feed started")

        while self.running:
            try:
                await self._update_sol_price()
                await self._update_position_prices()
                await self._check_alerts()
            except Exception as e:
                logger.debug("Price feed error: " + str(e)[:50])
            await asyncio.sleep(self.update_interval)

    async def _update_sol_price(self):
        try:
            async with self.session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    p = d.get("solana", {}).get("usd", 0)
                    if p > 0:
                        self.sol_price = p
        except:
            pass

    async def _update_position_prices(self):
        if not self.bot_instance:
            return
        rm = self.bot_instance.risk_manager
        for addr, pos in rm.positions.items():
            if pos.status != "open":
                continue
            try:
                price = await self.bot_instance.executor.get_token_price(addr)
                if price and price > 0:
                    self.prices[addr] = price
            except:
                pass

    async def _check_alerts(self):
        if not self.bot_instance or not self.tg_bot:
            return

        rm = self.bot_instance.risk_manager
        for addr, pos in rm.positions.items():
            if pos.status != "open":
                continue

            cp = self.prices.get(addr, 0)
            if cp <= 0 or pos.entry_price <= 0:
                continue

            pnl = ((cp - pos.entry_price) / pos.entry_price) * 100
            pnl_sol = (cp / pos.entry_price - 1) * pos.entry_sol

            # Alert: 2x profit
            if pnl >= 100 and not getattr(pos, "_alert_2x", False):
                pos._alert_2x = True
                await self.tg_bot._send(
                    "\U0001f680 <b>2X! " + pos.symbol + "</b>\n\n"
                    + "PnL: +" + str(round(pnl, 1)) + "%\n"
                    + "Profit: " + str(round(pnl_sol, 4)) + " SOL\n"
                    + "Duration: " + pos.hold_duration()
                )

            # Alert: 5x profit
            if pnl >= 400 and not getattr(pos, "_alert_5x", False):
                pos._alert_5x = True
                await self.tg_bot._send(
                    "\U0001f525 <b>5X! " + pos.symbol + "</b>\n\n"
                    + "PnL: +" + str(round(pnl, 1)) + "%\n"
                    + "Profit: " + str(round(pnl_sol, 4)) + " SOL"
                )

            # Alert: 10x profit
            if pnl >= 900 and not getattr(pos, "_alert_10x", False):
                pos._alert_10x = True
                await self.tg_bot._send(
                    "\U0001f4a5 <b>10X!!! " + pos.symbol + "</b>\n\n"
                    + "PnL: +" + str(round(pnl, 1)) + "%\n"
                    + "Profit: " + str(round(pnl_sol, 4)) + " SOL\n"
                    + "CONSIDER SELLING!"
                )

            # Alert: approaching stop loss
            if pnl <= -25 and not getattr(pos, "_alert_sl_warn", False):
                pos._alert_sl_warn = True
                await self.tg_bot._send(
                    "\u26a0\ufe0f <b>SL WARNING: " + pos.symbol + "</b>\n\n"
                    + "PnL: " + str(round(pnl, 1)) + "%\n"
                    + "Close to stop loss!"
                )

            # Alert: big dump
            if pnl <= -50 and not getattr(pos, "_alert_dump", False):
                pos._alert_dump = True
                await self.tg_bot._send(
                    "\U0001f534 <b>DUMP: " + pos.symbol + "</b>\n\n"
                    + "PnL: " + str(round(pnl, 1)) + "%\n"
                    + "Consider selling!"
                )

    def get_price(self, addr):
        return self.prices.get(addr, 0)

    def get_sol_price(self):
        return self.sol_price