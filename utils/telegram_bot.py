import asyncio
import time as time_mod
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.enums import ParseMode
from config import config
from utils.logger import logger
from utils.config_commands import register_config_commands



class TelegramBot:
    def __init__(self):
        self.token = config.notification.telegram_token
        self.chat_id = str(config.notification.telegram_chat_id)
        self.enabled = bool(self.token and self.chat_id)
        self.bot = None
        self.dp = None
        self.router = None
        self.bot_instance = None
        self.running = False
        self.addr_cache = {}
        self.muted = False
        self.start_time = time_mod.time()

    def set_bot(self, bi):
        self.bot_instance = bi

    async def start(self):
        if not self.enabled:
            logger.warning("TG not configured")
            return
        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        self._register_handlers()
        self._register_callbacks()
        self.running = True
        logger.info("TG started (aiogram)")
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
            logger.info("TG webhook deleted")
        except Exception as e:
            logger.warning("Webhook: " + str(e))
        try:
            await self.bot.session.close()
            logger.info("TG old session closed")
            self.bot = Bot(token=self.token)
        except:
            pass
        await asyncio.sleep(5)
        asyncio.create_task(self._poll())
        await asyncio.sleep(10)
        try:
            await self._send("Bot Online!\n\nKetik /help", kb=self._main_kb())
        except Exception as e:
            logger.error("TG send failed: " + str(e))

    async def _poll(self):
        mr = 3
        rt = 0
        while rt < mr and self.running:
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(5)
                logger.info("TG polling attempt " + str(rt + 1))
                await self.dp.start_polling(
                    self.bot,
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"],
                )
                break
            except Exception as e:
                err = str(e)
                rt += 1
                if "Conflict" in err or "conflict" in err:
                    w = 60 * rt
                    logger.warning("TG conflict, wait " + str(w) + "s")
                    try:
                        await self.bot.session.close()
                        self.bot = Bot(token=self.token)
                    except:
                        pass
                    await asyncio.sleep(w)
                elif "Forbidden" in err or "401" in err:
                    logger.error("TG token INVALID!")
                    return
                else:
                    logger.error("TG error: " + err[:200])
                    await asyncio.sleep(30)
        if rt >= mr:
            logger.error("TG failed after " + str(mr) + " attempts")

    async def stop(self):
        if self.bot and self.running:
            self.running = False
            try:
                await self._send("Bot Offline")
            except Exception:
                pass
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                await self.dp.stop_polling()
                await asyncio.sleep(3)
                await self.bot.session.close()
            except Exception as e:
                logger.warning("TG stop: " + str(e))

    async def _send(self, text, pm=ParseMode.HTML, kb=None):
        if not self.enabled or not self.bot:
            return
        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode=pm, reply_markup=kb
            )
        except Exception as e:
            logger.error("TG send: " + str(e))

    def _auth(self, msg):
        cid = msg.chat.id if hasattr(msg, "chat") else msg.message.chat.id
        return str(cid) == self.chat_id

    def _main_kb(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="\U0001f4ca Stats"), KeyboardButton(text="\U0001f4cb Status")],
                [KeyboardButton(text="\U0001f4b0 Balance"), KeyboardButton(text="\U0001f4c8 Positions")],
                [KeyboardButton(text="\U0001f4dc History"), KeyboardButton(text="\U0001f4e1 Scanner")],
                [KeyboardButton(text="\u2699\ufe0f Config"), KeyboardButton(text="\U0001f3af Sniper")],
                [KeyboardButton(text="\U0001f514 Alerts"), KeyboardButton(text="\U0001f4c8 Chart")],
                [KeyboardButton(text="\u23f8\ufe0f Pause"), KeyboardButton(text="\u25b6\ufe0f Resume")],
                [KeyboardButton(text="\U0001f6d1 Sell All"), KeyboardButton(text="\U0001f4f4 Stop")],
            ],
            resize_keyboard=True,
            input_field_placeholder="Ketik command atau paste address...",
        )

    def _back_kb(self):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="menu_main")]
            ]
        )

    def _confirm_kb(self, a, t=""):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="\u2705 Confirm", callback_data="confirm_" + a + "_" + t),
                    InlineKeyboardButton(text="\u274c Cancel", callback_data="cancel"),
                ]
            ]
        )

    def _pos_kb(self, ps):
        btns = []
        for a, p in ps.items():
            lb = "\U0001f4b0 " + p.symbol + " | " + str(round(p.entry_sol, 3)) + " SOL | " + p.hold_duration()
            btns.append([InlineKeyboardButton(text=lb, callback_data="posdetail_" + a[:16])])
        if ps:
            btns.append([InlineKeyboardButton(text="\U0001f6d1 Sell All", callback_data="confirm_sellall_")])
        btns.append([InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="menu_main")])
        return InlineKeyboardMarkup(inline_keyboard=btns)

    def _settings_kb(self):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="SL: " + str(config.trading.stop_loss_percent) + "%", callback_data="set_sl"),
                    InlineKeyboardButton(text="TP: " + str(config.trading.take_profit_percent) + "%", callback_data="set_tp"),
                ],
                [
                    InlineKeyboardButton(text="Size: " + str(config.trading.max_sol_per_trade) + " SOL", callback_data="set_size"),
                    InlineKeyboardButton(text="Conc: " + str(config.trading.max_concurrent), callback_data="set_concurrent"),
                ],
                [InlineKeyboardButton(text="Slippage: " + str(config.trading.slippage_bps) + " bps", callback_data="set_slippage")],
                [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="menu_main")],
            ]
        )

    def _bar(self, v, mx, l=10):
        p = min(100, max(0, (v / mx) * 100))
        f = int(l * p / 100)
        e = l - f
        if p >= 70: c = "\U0001f7e2"
        elif p >= 40: c = "\U0001f7e1"
        else: c = "\U0001f534"
        return c + " " + "\u2588" * f + "\u2591" * e + " " + str(round(p)) + "%"

    def _rbar(self, s, l=10):
        f = int(l * s / 100)
        e = l - f
        if s <= 20: c = "\U0001f7e2"
        elif s <= 40: c = "\U0001f7e1"
        elif s <= 60: c = "\U0001f7e0"
        else: c = "\U0001f534"
        return c + " " + "\u2588" * f + "\u2591" * e + " " + str(s) + "/100"

    def _abar(self, s, l=10):
        f = int(l * s / 100)
        e = l - f
        if s >= 75: c = "\U0001f7e2"
        elif s >= 55: c = "\U0001f7e1"
        elif s >= 40: c = "\U0001f7e0"
        else: c = "\U0001f534"
        return c + " " + "\u2588" * f + "\u2591" * e + " " + str(s) + "/100"

    def _register_handlers(self):
        r = self.router
        register_config_commands(r, self._auth, self._settings_kb)

        @r.message(Command("start"))
            async def h_start(msg: Message):
            if not self._auth(msg):
                return
            await msg.answer("\U0001f3af <b>Auto Sniper Bot</b>\n\nBot aktif!\nKetik /help", parse_mode="HTML", reply_markup=self._main_kb())

        @r.message(Command("help"))
        async def h_help(msg: Message):
            if not self._auth(msg):
                return
            await msg.answer(
                "\U0001f916 <b>AUTO SNIPER BOT</b>\n" + "=" * 28 + "\n\n"
                + "\U0001f4ca <b>Monitoring</b>\n"
                + "/stats /balance /positions /history\n"
                + "/scanner /config /portfolio\n\n"
                + "\u23f8\ufe0f <b>Control</b>\n"
                + "/pause /resume /stop\n\n"
                + "\U0001f4b0 <b>Trading</b>\n"
                + "/buy ADDRESS SOL\n/sell TOKEN\n/sellall\n\n"
                + "\U0001f6e1\ufe0f <b>Risk</b>\n"
                + "/setsl N /settp N /setsize N\n\n"
                + "\U0001f50d <b>Analysis</b>\n"
                + "/rugcheck ADDRESS\n/ai ADDRESS\n\n"
                + "\U0001f43b <b>Whale</b>\n"
                + "/whales /whaletrades /copytrades\n"
                + "/track ADDRESS /whalestats\n\n"
                + "\U0001f4c8 <b>Reports</b>\n"
                + "/daily /weekly /journal /pnl\n\n"
                + "\U0001f4cb <b>Token List</b>\n"
                + "/blacklist /whitelist\n\n"
                + "\U0001f4c8 <b>Chart</b>\n/chart ADDRESS\n\n"
                + "\U0001f514 <b>Alerts</b>\n/alerts\n\n"
                + "\U0001f3af <b>Sniper</b>\n/sniper\n\n"
                + "\U0001f4ca <b>Analytics</b>\n"
                + "/top /worst /streak /roi\n"
                + "/risk /speed /status\n\n"
                + "\U0001f50d <b>Market</b>\n"
                + "/trending /gas\n\n"
                + "\U0001f4b0 <b>Finance</b>\n"
                + "/withdraw\n\n"
                + "\U0001f507 <b>Settings</b>\n"
                + "/mute /unmute /version\n\n"
                + "\u2022 Paste address = auto rugcheck\n"
                + "\u2022 /buy ADDRESS = default amount\n\n"
                + "\u26a0\ufe0f <b>DISCLAIMER</b>\n"
                + "Bot ini bukan penasihat keuangan.\n"
                + "Crypto berisiko tinggi.\n"
                + "Hanya pakai dana yang siap hilang.\n"
                + "Selalu DYOR dan pakai stop loss.",
                parse_mode="HTML", reply_markup=self._main_kb())

        @r.message(F.text == "\U0001f4ca Stats")
        @r.message(Command("stats"))
        async def h_stats(msg: Message):
            if not self._auth(msg):
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            s = self.bot_instance.risk_manager.get_stats()
            bs = self.bot_instance.stats
            up = time_mod.time() - self.bot_instance.start_time
            h = int(up // 3600)
            m = int((up % 3600) // 60)
            pe = "\U0001f4b0" if s["total_pnl_sol"] >= 0 else "\U0001f4b8"
            await msg.answer(
                "\U0001f4ca <b>STATS</b>\n" + "=" * 28 + "\n\n"
                + "\u23f1\ufe0f Uptime: <b>" + str(h) + "h " + str(m) + "m</b>\n\n"
                + "<b>Scanning</b>\n  Scanned: <b>" + str(bs["tokens_scanned"]) + "</b>\n  Passed: <b>" + str(bs["tokens_passed_screening"]) + "</b>\n  Rugs: <b>" + str(bs["rugpulls_blocked"]) + "</b>\n\n"
                + "<b>Trading</b>\n  Trades: <b>" + str(s["total_trades"]) + "</b>\n  Win Rate: <b>" + str(round(s["win_rate"], 1)) + "%</b>\n  " + self._bar(s["win_rate"], 100) + "\n  " + pe + " PnL: <b>" + str(round(s["total_pnl_sol"], 4)) + " SOL</b>\n  Active: <b>" + str(s["active_positions"]) + "</b>\n  Max DD: <b>" + str(round(s["max_drawdown"], 4)) + " SOL</b>\n\n"
                + "\u26a0\ufe0f Errors: <b>" + str(bs["errors"]) + "</b>\n"
                + "\U0001f6e1\ufe0f CB: <b>" + ("BREAK" if self.bot_instance.circuit_breaker_active else "OK") + "</b>",
                parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\U0001f4b0 Balance")
        @r.message(Command("balance"))
        async def h_balance(msg: Message):
            if not self._auth(msg):
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            bal = await self.bot_instance.executor.get_sol_balance()
            s = self.bot_instance.risk_manager.get_stats()
            pe = "\U0001f4b0" if s["total_pnl_sol"] >= 0 else "\U0001f4b8"
            de = "\U0001f4b0" if s["daily_pnl"] >= 0 else "\U0001f4b8"
            await msg.answer(
                "\U0001f4b0 <b>WALLET</b>\n" + "=" * 28 + "\n\n"
                + "SOL: <b>" + str(round(bal, 4)) + "</b>\nPositions: <b>" + str(s["active_positions"]) + "</b>\n\n"
                + de + " Daily: <b>" + str(round(s["daily_pnl"], 4)) + " SOL</b>\n"
                + pe + " Total: <b>" + str(round(s["total_pnl_sol"], 4)) + " SOL</b>\n\n"
                + "Mode: <b>" + ("DRY RUN" if config.dry_run else "LIVE") + "</b>",
                parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\U0001f4c8 Positions")
        @r.message(Command("positions"))
        async def h_positions(msg: Message):
            if not self._auth(msg):
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            rm = self.bot_instance.risk_manager
            pos = {a: p for a, p in rm.positions.items() if p.status == "open"}
            if not pos:
                await msg.answer("\U0001f4ca <b>No positions</b>", parse_mode="HTML", reply_markup=self._back_kb())
                return
            sol_usd = 150.0
            try:
                sol_usd = await self.bot_instance.executor._get_sol_usd_price()
            except:
                pass
            total_pnl = 0.0
            total_inv = 0.0
            text = "\U0001f4c8 <b>POSITIONS (" + str(len(pos)) + ")</b>\n" + "=" * 28 + "\n\n"
            text += "\U0001f4b1 SOL: ~$" + str(round(sol_usd, 2)) + "\n\n"
            for addr, p in pos.items():
                cp = 0.0
                try:
                    res = await self.bot_instance.executor.get_token_price(addr)
                    if res and res > 0:
                        cp = res
                except Exception:
                    pass
                if p.entry_price > 0 and cp > 0:
                    pnl_pct = ((cp - p.entry_price) / p.entry_price) * 100
                    pnl_sol = (cp / p.entry_price - 1) * p.entry_sol
                else:
                    pnl_pct = 0.0
                    pnl_sol = 0.0
                pnl_usd = pnl_sol * sol_usd
                inv_usd = p.entry_sol * sol_usd
                total_pnl += pnl_sol
                total_inv += p.entry_sol
                if pnl_pct >= 100: e = "\U0001f680"
                elif pnl_pct >= 0: e = "\U0001f7e2"
                elif pnl_pct >= -30: e = "\U0001f7e1"
                else: e = "\U0001f534"
                bp = min(100, max(0, (pnl_pct + 100) / 2))
                bf = int(10 * bp / 100)
                bar = "\u2588" * bf + "\u2591" * (10 - bf)
                tps = ""
                if p.tp1_hit: tps += " TP1:OK"
                if p.tp2_hit: tps += " TP2:OK"
                text += (
                    e + " <b>" + p.symbol + "</b>\n   Invested: " + str(round(p.entry_sol, 4)) + " SOL ($" + str(round(inv_usd, 2)) + ")\n   Entry: $" + str(p.entry_price) + "\n   Current: $" + str(cp)
                    + "\n   PnL: <b>" + ("+" if pnl_pct >= 0 else "") + str(round(pnl_pct, 1)) + "%</b> | <b>" + ("+" if pnl_sol >= 0 else "") + str(round(pnl_sol, 4)) + " SOL</b> | <b>" + ("+" if pnl_usd >= 0 else "") + "$" + str(round(pnl_usd, 2)) + "</b>\n   " + bar
                    + "\n   SL: $" + str(p.stop_loss_price) + " | TP1: $" + str(round(p.tp1_price, 10)) + " | TP2: $" + str(round(p.tp2_price, 10))
                    + "\n   Duration: <b>" + p.hold_duration() + "</b> | Remaining: <b>" + str(round(p.remaining_pct * 100)) + "%</b> | DCA: <b>" + str(p.dca_count) + "</b>" + tps + "\n   <code>" + addr[:20] + "...</code>\n\n"
                )
            te = "\U0001f4b0" if total_pnl >= 0 else "\U0001f4b8"
            tpct = (total_pnl / total_inv * 100) if total_inv > 0 else 0
            tusd = total_pnl * sol_usd
            text += ("=" * 28 + "\n" + te + " <b>Float PnL</b>\n   " + ("+" if total_pnl >= 0 else "") + str(round(total_pnl, 4)) + " SOL | " + ("+" if tusd >= 0 else "") + "$" + str(round(tusd, 2)) + "\n   " + ("+" if tpct >= 0 else "") + str(round(tpct, 1)) + "%\n\n" + "\U0001f4b0 Invested: " + str(round(total_inv, 4)) + " SOL\n" + "\U0001f4c8 Active: " + str(len(pos)))
            await msg.answer(text, parse_mode="HTML", reply_markup=self._pos_kb(pos))

        @r.message(F.text == "\U0001f4dc History")
        @r.message(Command("history"))
        async def h_history(msg: Message):
            if not self._auth(msg):
                return
            await self._send_history_page(msg, 1)

        @r.message(F.text == "\U0001f4e1 Scanner")
        @r.message(Command("scanner"))
        async def h_scanner(msg: Message):
            if not self._auth(msg):
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            bs = self.bot_instance.stats
            sc = max(bs["tokens_scanned"], 1)
            pr = (bs["tokens_passed_screening"] / sc) * 100
            await msg.answer(
                "\U0001f4e1 <b>SCANNER</b>\n" + "=" * 28 + "\n\n"
                + "Running: <b>" + ("YES" if self.bot_instance.running else "NO") + "</b>\n\n"
                + "Scanned: <b>" + str(bs["tokens_scanned"]) + "</b>\nPassed: <b>" + str(bs["tokens_passed_screening"]) + "</b>\nFailed: <b>" + str(bs["tokens_failed_screening"]) + "</b>\nRugs: <b>" + str(bs["rugpulls_blocked"]) + "</b>\n\n"
                + "Pass Rate: <b>" + str(round(pr, 1)) + "%</b>\n" + self._bar(pr, 100) + "\n\n"
                + "Seen: <b>" + str(len(self.bot_instance.scanner.seen_tokens)) + "</b>\nErrors: <b>" + str(bs["errors"]) + "</b>\nCB: <b>" + ("ON" if self.bot_instance.circuit_breaker_active else "OFF") + "</b>",
                parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\u2699\ufe0f Config")
        @r.message(Command("config"))
        async def h_config(msg: Message):
            if not self._auth(msg):
                return
            await msg.answer(
                "\u2699\ufe0f <b>CONFIG</b>\n" + "=" * 28 + "\n\n"
                + "Mode: <b>" + ("DRY RUN" if config.dry_run else "LIVE") + "</b>\n\n"
                + "Max/Trade: <b>" + str(config.trading.max_sol_per_trade) + " SOL</b>\nStop Loss: <b>" + str(config.trading.stop_loss_percent) + "%</b>\nTake Profit: <b>" + str(config.trading.take_profit_percent) + "%</b>\nConcurrent: <b>" + str(config.trading.max_concurrent) + "</b>\nSlippage: <b>" + str(config.trading.slippage_bps) + " bps</b>\n\n"
                + "Max Rug: <b>" + str(config.screening.max_rugpull_score) + "/100</b>\nMin Holders: <b>" + str(config.screening.min_unique_holders) + "</b>\nMin Liq: <b>" + str(config.screening.min_initial_liquidity) + " SOL</b>",
                parse_mode="HTML", reply_markup=self._settings_kb())

        @r.message(F.text == "\u23f8\ufe0f Pause")
        @r.message(Command("pause"))
        async def h_pause(msg: Message):
            if not self._auth(msg):
                return
            if self.bot_instance:
                self.bot_instance.circuit_breaker_active = True
            await msg.answer("\u23f8\ufe0f <b>PAUSED</b>", parse_mode="HTML")

        @r.message(F.text == "\u25b6\ufe0f Resume")
        @r.message(Command("resume"))
        async def h_resume(msg: Message):
            if not self._auth(msg):
                return
            if self.bot_instance:
                self.bot_instance.circuit_breaker_active = False
                self.bot_instance.consecutive_errors = 0
                self.bot_instance.risk_manager.paused_by_drawdown = False
                self.bot_instance.risk_manager.paused_by_profit_target = False
                self.bot_instance.risk_manager.consecutive_losses = 0
            await msg.answer("\u25b6\ufe0f <b>RESUMED</b>", parse_mode="HTML")

        @r.message(F.text == "\U0001f6d1 Sell All")
        async def h_sellall_btn(msg: Message):
            if not self._auth(msg):
                return
            await msg.answer("\u26a0\ufe0f <b>Sell ALL?</b>", parse_mode="HTML", reply_markup=self._confirm_kb("sellall"))

        @r.message(F.text == "\U0001f4f4 Stop")
        async def h_stop_btn(msg: Message):
            if not self._auth(msg):
                return
            await msg.answer("\u26a0\ufe0f <b>STOP BOT?</b>\n\nKetik /resume untuk mengaktifkan kembali", parse_mode="HTML", reply_markup=self._confirm_kb("stop"))

        @r.message(Command("buy"))
        async def h_buy(msg: Message):
            if not self._auth(msg):
                return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("\U0001f4b0 <b>BUY TOKEN</b>\n" + "=" * 28 + "\n\nUsage:\n/buy ADDRESS SOL\n/buy ADDRESS (default " + str(config.trading.max_sol_per_trade) + " SOL)\n\nContoh:\n/buy 262o7x...kvpump 0.5", parse_mode="HTML")
                return
            if len(parts) == 2:
                parts.append(str(config.trading.max_sol_per_trade))
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            addr = parts[1]
            try:
                amt = float(parts[2])
            except ValueError:
                await msg.answer("Invalid amount")
                return
            await msg.answer("Buying " + str(amt) + " SOL...")
            try:
                buy = await self.bot_instance.executor.buy_token(token_address=addr, sol_amount=amt)
                if buy and buy.get("success"):
                    self.bot_instance.risk_manager.open_position(
                        token_address=addr, symbol="MANUAL", entry_price=buy.get("price", 0),
                        sol_amount=amt, tokens_received=buy.get("tokens_received", 0),
                        screener_score=50, rug_score=0)
                    dr = "DRY" if buy.get("dry_run") else "LIVE"
                    await msg.answer(dr + " BUY OK\n\nSpent: " + str(round(amt, 4)) + " SOL\nTokens: " + str(buy.get("tokens_received", 0)) + "\nTX: " + str(buy.get("tx_hash", "N/A"))[:24], parse_mode="HTML", reply_markup=self._back_kb())
                else:
                    await msg.answer("Buy failed!")
            except Exception as e:
                await msg.answer("Error: " + str(e)[:100])

        @r.message(Command("sell"))
        async def h_sell(msg: Message):
            if not self._auth(msg):
                return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /sell TOKEN")
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            target = parts[1]
            rm = self.bot_instance.risk_manager
            pos = None
            for a, p in rm.positions.items():
                if p.status == "open" and (a == target or p.symbol.lower() == target.lower()):
                    pos = p
                    break
            if not pos:
                await msg.answer("Not found: " + target)
                return
            await msg.answer("Sell " + pos.symbol + "?\nEntry: " + str(round(pos.entry_sol, 4)) + " SOL", parse_mode="HTML", reply_markup=self._confirm_kb("sell", pos.token_address[:16]))

        @r.message(Command("sellall"))
        async def h_sellall(msg: Message):
            if not self._auth(msg):
                return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            rm = self.bot_instance.risk_manager
            ps = {a: p for a, p in rm.positions.items() if p.status == "open"}
            if not ps:
                await msg.answer("No positions")
                return
            await msg.answer("Selling " + str(len(ps)) + "...")
            res = []
            for a, p in list(ps.items()):
                try:
                    r = await self.bot_instance.executor.sell_token(p.token_address, int(p.tokens_held))
                    if r and r.get("success"):
                        sr = r.get("sol_received", 0)
                        pnl = sr - p.total_invested
                        rm.close_position(a, 0, sr)
                        e = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                        res.append(e + " " + p.symbol + ": " + str(round(pnl, 4)) + " SOL")
                    else:
                        res.append("\u274c " + p.symbol)
                except Exception:
                    res.append("\u274c " + p.symbol)
            await msg.answer("<b>Results</b>\n\n" + "\n".join(res), parse_mode="HTML")

        @r.message(Command("setsl"))
        async def h_setsl(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /setsl 30")
                return
            try:
                config.trading.stop_loss_percent = float(parts[1])
                await msg.answer("SL: " + parts[1] + "%", reply_markup=self._settings_kb())
            except ValueError:
                await msg.answer("Invalid")

        @r.message(Command("settp"))
        async def h_settp(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /settp 200")
                return
            try:
                config.trading.take_profit_percent = float(parts[1])
                await msg.answer("TP: " + parts[1] + "%", reply_markup=self._settings_kb())
            except ValueError:
                await msg.answer("Invalid")

        @r.message(Command("setsize"))
        async def h_setsize(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /setsize 0.5")
                return
            try:
                config.trading.max_sol_per_trade = float(parts[1])
                await msg.answer("Size: " + parts[1] + " SOL", reply_markup=self._settings_kb())
            except ValueError:
                await msg.answer("Invalid")

        @r.message(Command("portfolio"))
        async def h_portfolio(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            bal = await self.bot_instance.executor.get_sol_balance()
            rm = self.bot_instance.risk_manager
            st = rm.get_stats()
            pv = 0
            pt = ""
            for a, p in rm.positions.items():
                if p.status == "open":
                    pr = await self.bot_instance.executor.get_token_price(a)
                    if pr:
                        v = pr * p.tokens_held
                        pv += v
                        pnl = p.pnl_percent(pr)
                        pt += "  " + p.symbol + " | " + str(round(v, 4)) + " SOL | " + ("+" if pnl >= 0 else "") + str(round(pnl, 1)) + "%\n"
            t = bal + pv
            pe = "+" if st["total_pnl_sol"] >= 0 else ""
            text = "PORTFOLIO\n" + "=" * 28 + "\n\nCash: " + str(round(bal, 4)) + " SOL\nPositions: " + str(round(pv, 4)) + " SOL\nTotal: " + str(round(t, 4)) + " SOL\n\nPnL: " + pe + str(round(st["total_pnl_sol"], 4)) + " SOL\nActive: " + str(st["active_positions"]) + "\n\n"
            if pt: text += "Positions:\n" + pt
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("daily"))
        async def h_daily(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            r2 = self.bot_instance.risk_manager.get_daily_report()
            pe = "+" if r2["total_pnl"] >= 0 else ""
            text = "DAILY REPORT\n" + "=" * 28 + "\n\nTrades: " + str(r2["trades"]) + "\nWin/Loss: " + str(r2["wins"]) + "/" + str(r2["losses"]) + "\nWin Rate: " + str(round(r2["win_rate"], 1)) + "%\nPnL: " + pe + str(round(r2["total_pnl"], 4)) + " SOL\n"
            if r2.get("best_trade"): text += "\nBest: " + str(r2["best_trade"].get("symbol", "?")) + " +" + str(round(r2["best_trade"].get("pnl_percent", 0), 1)) + "%"
            if r2.get("worst_trade"): text += "\nWorst: " + str(r2["worst_trade"].get("symbol", "?")) + " " + str(round(r2["worst_trade"].get("pnl_percent", 0), 1)) + "%"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("weekly"))
        async def h_weekly(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            r2 = self.bot_instance.risk_manager.get_weekly_report()
            pe = "+" if r2["total_pnl"] >= 0 else ""
            await msg.answer("WEEKLY REPORT\n" + "=" * 28 + "\n\nTrades: " + str(r2["trades"]) + "\nWin/Loss: " + str(r2["wins"]) + "/" + str(r2["losses"]) + "\nWin Rate: " + str(round(r2["win_rate"], 1)) + "%\nPnL: " + pe + str(round(r2["total_pnl"], 4)) + " SOL\nAvg: " + str(round(r2["avg_pnl"], 4)) + " SOL/trade\n", parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("rugcheck"))
        @r.message(Command("rug"))
        async def h_rugcheck(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /rugcheck ADDRESS")
                return
            addr = parts[1]
            await msg.answer("\U0001f50d Checking <code>" + addr[:20] + "...</code>", parse_mode="HTML")
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            try:
                meta = await self.bot_instance.scanner._fetch_meta(addr)
                if not meta: meta = {"address": addr}
                report = await self.bot_instance.screener.rug_checker.analyze(meta)
                checks = ""
                for n, d in report.details.items():
                    e = "\u2705" if d["passed"] else "\u274c"
                    checks += "  " + e + " " + n + ": " + d["detail"] + "\n"
                sl = getattr(report, 'safety_level', 'UNKNOWN')
                labels = {"DANGER": "\u26d4 DANGER - JANGAN BELI!", "HIGH_RISK": "\U0001f534 HIGH RISK - Hindari!", "MEDIUM_RISK": "\U0001f7e0 MEDIUM RISK - Hati-hati!", "LOW_RISK": "\U0001f7e1 LOW RISK - Cek manual", "SAFE": "\u2705 SAFE - Relatif aman", "UNKNOWN": "\u2753 UNKNOWN"}
                safe = labels.get(sl, "\u2753 UNKNOWN")
                crit_text = ""
                crit = getattr(report, 'critical_failures', [])
                if crit:
                    crit_text = "\n\n\u26d4 <b>CRITICAL:</b>\n"
                    for c in crit:
                        crit_text += "  \U0001f534 " + c.replace("_", " ").upper() + "\n"
                text = ("\U0001f6e1\ufe0f <b>RUG CHECK</b>\n" + "=" * 28 + "\n\n<code>" + addr[:20] + "...</code>\n\nScore: <b>" + str(report.score) + "/100</b>\n" + self._rbar(report.score) + "\n\n" + safe + "\n\u2705 Passed: <b>" + str(report.checks_passed) + "</b>\n\u274c Failed: <b>" + str(report.checks_failed) + "</b>\n\n<b>Details</b>\n" + checks + crit_text + "\n<b>Risks</b>\n")
                text += "\n".join(report.reasons) if report.reasons else "None"
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="\U0001f916 AI Analysis", callback_data="ai_" + addr)], [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="menu_main")]])
                await msg.answer(text, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                await msg.answer("Error: " + str(e)[:100])

        @r.message(Command("ai"))
        async def h_ai(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /ai ADDRESS", parse_mode="HTML")
                return
            addr = parts[1]
            await msg.answer("\U0001f916 AI Analyzing...", parse_mode="HTML")
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            try:
                meta = await self.bot_instance.scanner._fetch_meta(addr)
                if not meta:
                    meta = {"address": addr, "symbol": "???", "name": "Unknown", "price_usd": 0, "market_cap": 0, "volume_24h": 0, "liquidity": 0, "holder_count": 0, "website": "", "twitter": "", "telegram": "", "buys_1h": 0, "sells_1h": 0, "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0}
                report = await self.bot_instance.screener.rug_checker.analyze(meta)
                meta = self._fix_h(meta, report)
                ai = self._ai_analyze(report, meta)
                await msg.answer(self._build_ai(ai, report, meta, addr), parse_mode="HTML", reply_markup=self._back_kb())
            except Exception as e:
                await msg.answer("AI error: " + str(e)[:100])

        @r.message(Command("whales"))
        async def h_whales(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance or not self.bot_instance.whale_tracker:
                await msg.answer("Whale tracker N/A")
                return
            await msg.answer(self.bot_instance.whale_tracker.format_whale_list(), parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("whaletrades"))
        async def h_whaletrades(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance or not self.bot_instance.whale_tracker:
                await msg.answer("Whale tracker N/A")
                return
            await msg.answer(self.bot_instance.whale_tracker.format_recent_trades(), parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("copytrades"))
        async def h_copytrades(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance or not self.bot_instance.whale_tracker:
                await msg.answer("Whale tracker N/A")
                return
            await msg.answer(self.bot_instance.whale_tracker.format_copy_history(), parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("track"))
        async def h_track(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage: /track WALLET")
                return
            if not self.bot_instance or not self.bot_instance.whale_tracker:
                await msg.answer("Whale tracker N/A")
                return
            addr = parts[1]
            wt = self.bot_instance.whale_tracker
            await msg.answer("Analyzing...")
            await wt._verify_whale(addr)
            if addr in wt.whales:
                p = wt.whales[addr]
                await msg.answer("Whale Found!\n\nTier: " + p.tier + "\nScore: " + str(round(p.whale_score)) + "/100\nBalance: " + str(round(p.sol_balance, 2)) + " SOL\nAge: " + str(p.wallet_age_days) + "d\nTags: " + ", ".join(p.tags), parse_mode="HTML", reply_markup=self._back_kb())
            else:
                await msg.answer("Wallet not qualified")

        @r.message(Command("whalestats"))
        async def h_whalestats(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance or not self.bot_instance.whale_tracker:
                await msg.answer("Whale tracker N/A")
                return
            ws = self.bot_instance.whale_tracker.get_stats()
            await msg.answer("WHALE STATS\n" + "=" * 28 + "\n\nDiscovered: " + str(ws["discovered"]) + "\nVerified: " + str(ws["verified"]) + "\nRejected scam: " + str(ws["rejected_scam"]) + "\nRejected low: " + str(ws["rejected_low"]) + "\nTracked: " + str(ws["whales_tracked"]) + "\nWatched: " + str(ws["wallets_watched"]) + "\nTrades: " + str(ws["trades_detected"]) + "\nCopied: " + str(ws["trades_copied"]) + "\nBlacklisted: " + str(ws["blacklisted"]) + "\n", parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("blacklist"))
        async def h_blacklist(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage:\n/blacklist add ADDR\n/blacklist remove ADDR\n/blacklist list")
                return
            act = parts[1]
            if act == "list":
                bl = self.bot_instance.token_blacklist
                if not bl:
                    await msg.answer("Empty")
                    return
                t = "Blacklist\n\n"
                for a in list(bl)[-20:]: t += "  " + a[:20] + "...\n"
                await msg.answer(t, parse_mode="HTML")
            elif act == "add" and len(parts) >= 3:
                self.bot_instance.token_blacklist.add(parts[2])
                await msg.answer("Added: " + parts[2][:20])
            elif act == "remove" and len(parts) >= 3:
                self.bot_instance.token_blacklist.discard(parts[2])
                await msg.answer("Removed: " + parts[2][:20])

        @r.message(Command("whitelist"))
        async def h_whitelist(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("Usage:\n/whitelist add ADDR\n/whitelist remove ADDR\n/whitelist list")
                return
            act = parts[1]
            if act == "list":
                wl = self.bot_instance.token_whitelist
                if not wl:
                    await msg.answer("Empty")
                    return
                t = "Whitelist\n\n"
                for a in list(wl)[-20:]: t += "  " + a[:20] + "...\n"
                await msg.answer(t, parse_mode="HTML")
            elif act == "add" and len(parts) >= 3:
                self.bot_instance.token_whitelist.add(parts[2])
                await msg.answer("Added: " + parts[2][:20])
            elif act == "remove" and len(parts) >= 3:
                self.bot_instance.token_whitelist.discard(parts[2])
                await msg.answer("Removed: " + parts[2][:20])

        @r.message(F.text == "\U0001f4c8 Chart")
        @r.message(Command("chart"))
        async def h_chart(msg: Message):
            if not self._auth(msg): return
            parts = msg.text.split()
            if len(parts) < 2:
                await msg.answer("\U0001f4c8 <b>CHART</b>\n\nPaste dulu address token, lalu tekan tombol Chart lagi.\n\nAtau ketik:\n<code>/chart ADDRESS</code>", parse_mode="HTML")
                return
            addr = parts[1]
            await msg.answer("\U0001f4c8 <b>Chart: " + addr[:16] + "...</b>\n\nhttps://dexscreener.com/solana/" + addr, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\U0001f514 Alerts")
        @r.message(Command("alerts"))
        async def h_alerts(msg: Message):
            if not self._auth(msg): return
            pf = self.bot_instance.price_feed if self.bot_instance else None
            sol_p = pf.get_sol_price() if pf else 150.0
            await msg.answer("\U0001f514 <b>ALERTS</b>\n" + "=" * 28 + "\n\nSOL: <b>$" + str(round(sol_p, 2)) + "</b>\n\n2X Alert: <b>ON</b>\n5X Alert: <b>ON</b>\n10X Alert: <b>ON</b>\nSL Warning: <b>ON</b>\nDump Alert: <b>ON</b>\n\nAlerts sent automatically via Telegram", parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\U0001f3af Sniper")
        @r.message(Command("sniper"))
        async def h_sniper(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            bs = self.bot_instance.stats
            await msg.answer("\U0001f3af <b>SNIPER STATUS</b>\n" + "=" * 28 + "\n\nMode: <b>" + ("DRY RUN" if config.dry_run else "LIVE") + "</b>\n\nSources:\n  Raydium WS: <b>ACTIVE</b>\n  DexScreener: <b>ACTIVE</b>\n  Jupiter: <b>ACTIVE</b>\n  Pump.fun: <b>ACTIVE</b>\n\nScanned: <b>" + str(bs["tokens_scanned"]) + "</b>\nPassed: <b>" + str(bs["tokens_passed_screening"]) + "</b>\nTrades: <b>" + str(bs["trades_executed"]) + "</b>\n\nPrice Feed: <b>ACTIVE</b>\nMulti TP: <b>30%/30%/40%</b>\nDCA: <b>30%/50% drops</b>\nTrailing SL: <b>Dynamic</b>", parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(F.text == "\U0001f4cb Status")
        @r.message(Command("status"))
        async def h_status(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            bal = await self.bot_instance.executor.get_sol_balance()
            rm = self.bot_instance.risk_manager
            st = rm.get_stats()
            bs = self.bot_instance.stats
            mode = "\U0001f7e2 DRY RUN" if config.dry_run else "\U0001f534 LIVE"
            active = st["active_positions"]
            paused = "YES" if (rm.paused_by_drawdown or rm.paused_by_profit_target) else "NO"
            consec = rm.consecutive_losses
            text = "\U0001f4cb <b>STATUS</b>\n" + "=" * 28 + "\n\n"
            text += "Mode: <b>" + mode + "</b>\n"
            text += "Balance: <b>" + str(round(bal, 4)) + " SOL</b>\n"
            text += "Active: <b>" + str(active) + "</b> positions\n"
            text += "Daily PnL: <b>" + ("+" if rm.daily_pnl >= 0 else "") + str(round(rm.daily_pnl, 4)) + " SOL</b>\n"
            text += "Win Rate: <b>" + str(round(st["win_rate"], 1)) + "%</b>\n"
            text += "Total PnL: <b>" + ("+" if st["total_pnl_sol"] >= 0 else "") + str(round(st["total_pnl_sol"], 4)) + " SOL</b>\n\n"
            text += "\U0001f6e1\ufe0f <b>Protection</b>\n"
            text += "Paused: <b>" + paused + "</b>\n"
            text += "Consec Loss: <b>" + str(consec) + "/" + str(rm.max_consecutive_losses) + "</b>\n"
            text += "Max DD: <b>" + str(round(rm.max_drawdown, 4)) + " SOL</b>\n\n"
            text += "\U0001f4e1 <b>Scanner</b>\n"
            text += "Running: <b>" + ("YES" if self.bot_instance.running else "NO") + "</b>\n"
            text += "Scanned: <b>" + str(bs["tokens_scanned"]) + "</b>\n"
            text += "Passed: <b>" + str(bs["tokens_passed_screening"]) + "</b>\n\n"
            text += "\U0001f43b <b>Whale</b>\n"
            if self.bot_instance.whale_tracker:
                ws = self.bot_instance.whale_tracker.get_stats()
                text += "Tracked: <b>" + str(ws["whales_tracked"]) + "</b>\nCopied: <b>" + str(ws["trades_copied"]) + "</b>\n"
            else:
                text += "N/A\n"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        # ============================================
        # BATCH 1: ANALYTICS COMMANDS
        # ============================================

        @r.message(Command("top"))
        async def h_top(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            trades = self.bot_instance.risk_manager.closed_positions
            if not trades:
                await msg.answer("\U0001f4ca <b>No trades yet</b>", parse_mode="HTML")
                return
            wins = sorted([t for t in trades if t.get("pnl_sol", 0) > 0], key=lambda t: t.get("pnl_percent", 0), reverse=True)[:5]
            if not wins:
                await msg.answer("\U0001f4ca <b>No winning trades yet</b>", parse_mode="HTML")
                return
            sol_usd = 62.0
            try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
            except: pass
            text = "\U0001f48e <b>TOP 5 TRADES</b>\n" + "=" * 28 + "\n\n"
            for i, t in enumerate(wins, start=1):
                ps = t.get("pnl_sol", 0)
                pp = t.get("pnl_percent", 0)
                text += ("#" + str(i) + " \U0001f7e2 <b>" + t.get("symbol", "???") + "</b>\n   PnL: <b>+" + str(round(pp, 2)) + "%</b> (+" + str(round(ps, 4)) + " SOL ~$" + str(round(ps * sol_usd, 2)) + ")\n   \u23f1\ufe0f " + t.get("hold_time", "-") + " | \u2699\ufe0f " + t.get("reason", "").replace("_", " ").upper() + "\n\n")
            total = sum(t.get("pnl_sol", 0) for t in wins)
            text += "=" * 28 + "\n\U0001f4b0 Total: <b>+" + str(round(total, 4)) + " SOL</b> (~$" + str(round(total * sol_usd, 2)) + ")"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("worst"))
        async def h_worst(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            trades = self.bot_instance.risk_manager.closed_positions
            if not trades:
                await msg.answer("\U0001f4ca <b>No trades yet</b>", parse_mode="HTML")
                return
            losses = sorted([t for t in trades if t.get("pnl_sol", 0) < 0], key=lambda t: t.get("pnl_percent", 0))[:5]
            if not losses:
                await msg.answer("\U0001f389 <b>No losing trades!</b>", parse_mode="HTML")
                return
            sol_usd = 62.0
            try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
            except: pass
            text = "\U0001f4c9 <b>WORST 5 TRADES</b>\n" + "=" * 28 + "\n\n"
            for i, t in enumerate(losses, start=1):
                ps = t.get("pnl_sol", 0)
                pp = t.get("pnl_percent", 0)
                text += ("#" + str(i) + " \U0001f534 <b>" + t.get("symbol", "???") + "</b>\n   PnL: <b>" + str(round(pp, 2)) + "%</b> (" + str(round(ps, 4)) + " SOL ~$" + str(round(ps * sol_usd, 2)) + ")\n   \u23f1\ufe0f " + t.get("hold_time", "-") + " | \u2699\ufe0f " + t.get("reason", "").replace("_", " ").upper() + "\n\n")
            total = sum(t.get("pnl_sol", 0) for t in losses)
            text += "=" * 28 + "\n\U0001f4b8 Total: <b>" + str(round(total, 4)) + " SOL</b>\n\n\u26a0\ufe0f Pelajari kesalahan ini!"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("streak"))
        async def h_streak(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            trades = self.bot_instance.risk_manager.closed_positions
            if not trades:
                await msg.answer("\U0001f4ca <b>No trades yet</b>", parse_mode="HTML")
                return
            current_streak = 0
            streak_type = ""
            for t in reversed(trades):
                pnl = t.get("pnl_sol", 0)
                if current_streak == 0:
                    streak_type = "WIN" if pnl >= 0 else "LOSS"
                    current_streak = 1
                elif (streak_type == "WIN" and pnl >= 0) or (streak_type == "LOSS" and pnl < 0):
                    current_streak += 1
                else: break
            best_win = 0
            best_loss = 0
            temp_win = 0
            temp_loss = 0
            for t in trades:
                if t.get("pnl_sol", 0) >= 0:
                    temp_win += 1
                    temp_loss = 0
                    best_win = max(best_win, temp_win)
                else:
                    temp_loss += 1
                    temp_win = 0
                    best_loss = max(best_loss, temp_loss)
            if streak_type == "WIN": emoji = "\U0001f525"
            else: emoji = "\U0001f9ca"
            color = "\U0001f7e2" if streak_type == "WIN" else "\U0001f534"
            text = emoji + " <b>STREAK</b>\n" + "=" * 28 + "\n\n"
            text += "Current: " + color + " <b>" + str(current_streak) + " " + streak_type + "</b>\n\n"
            text += "\U0001f3c6 Best Win: <b>" + str(best_win) + "</b>\n"
            text += "\U0001f4c9 Best Loss: <b>" + str(best_loss) + "</b>\n\n"
            if streak_type == "WIN" and current_streak >= 3: text += "\U0001f525 On fire!"
            elif streak_type == "LOSS" and current_streak >= 3: text += "\u26a0\ufe0f Loss streak! Auto pause di 3x."
            else: text += "\U0001f4aa Keep going!"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("roi"))
        async def h_roi(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            rm = self.bot_instance.risk_manager
            bal = await self.bot_instance.executor.get_sol_balance()
            st = rm.get_stats()
            sol_usd = 62.0
            try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
            except: pass
            estimated_initial = bal - st["total_pnl_sol"]
            if estimated_initial <= 0: estimated_initial = bal
            roi_pct = (st["total_pnl_sol"] / estimated_initial * 100) if estimated_initial > 0 else 0
            roi_usd = st["total_pnl_sol"] * sol_usd
            daily_avg = st["total_pnl_sol"] / max(1, st["total_trades"])
            text = "\U0001f4c8 <b>ROI</b>\n" + "=" * 28 + "\n\n"
            text += "Balance: <b>" + str(round(bal, 4)) + " SOL</b> (~$" + str(round(bal * sol_usd, 2)) + ")\n"
            text += "Est. Initial: <b>" + str(round(estimated_initial, 4)) + " SOL</b>\n\n"
            text += "Total PnL: <b>" + ("+" if st["total_pnl_sol"] >= 0 else "") + str(round(st["total_pnl_sol"], 4)) + " SOL</b> (~$" + ("+" if roi_usd >= 0 else "") + str(round(roi_usd, 2)) + ")\n"
            text += "ROI: <b>" + ("+" if roi_pct >= 0 else "") + str(round(roi_pct, 1)) + "%</b>\n"
            text += "Avg/Trade: <b>" + ("+" if daily_avg >= 0 else "") + str(round(daily_avg, 4)) + " SOL</b>\n\n"
            text += "Trades: <b>" + str(st["total_trades"]) + "</b>\n"
            text += "Win Rate: <b>" + str(round(st["win_rate"], 1)) + "%</b>\n"
            text += "PF: <b>" + str(round(st["profit_factor"], 2)) + "x</b>\n"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("mute"))
        async def h_mute(msg: Message):
            if not self._auth(msg): return
            self.muted = True
            await msg.answer("\U0001f507 <b>NOTIFICATIONS MUTED</b>\n\nBot tetap jalan, notifikasi dimatikan.\n\n/unmute untuk hidupkan lagi.", parse_mode="HTML")

        @r.message(Command("unmute"))
        async def h_unmute(msg: Message):
            if not self._auth(msg): return
            self.muted = False
            await msg.answer("\U0001f50a <b>NOTIFICATIONS ON</b>\n\nNotifikasi dihidupkan kembali.", parse_mode="HTML")

        @r.message(Command("version"))
        async def h_version(msg: Message):
            if not self._auth(msg): return
            mode = "\U0001f7e2 DRY RUN" if config.dry_run else "\U0001f534 LIVE"
            uptime = time_mod.time() - self.start_time
            h = int(uptime // 3600)
            m = int((uptime % 3600) // 60)
            await msg.answer(
                "\U0001f916 <b>AUTO SNIPER BOT</b>\n" + "=" * 28 + "\n\n"
                + "Version: <b>2.0 ULTIMATE</b>\n"
                + "Mode: <b>" + mode + "</b>\n"
                + "Uptime: <b>" + str(h) + "h " + str(m) + "m</b>\n\n"
                + "\U0001f4ca <b>Features</b>\n  Commands: <b>46+</b>\n  Auto Features: <b>20+</b>\n  Protection Layers: <b>16</b>\n\n"
                + "\U0001f6e1\ufe0f <b>Protection</b>\n  Dynamic Trailing: ON\n  Early Exit: ON\n  Consecutive Loss: ON\n  Max Drawdown: ON\n  Auto Blacklist: ON\n  Anti-FOMO: ON\n  Anti-Scam: ON\n\n"
                + "\U0001f916 <b>Tech</b>\n  Python + aiogram\n  Jupiter + DexScreener\n  Helius RPC\n  12-Layer Rugcheck",
                parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("trending"))
        async def h_trending(msg: Message):
            if not self._auth(msg): return
            await msg.answer("\U0001f50d <b>Loading trending...</b>", parse_mode="HTML")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.dexscreener.com/latest/dex/search?q=solana%20trending", timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200:
                            await msg.answer("Error fetching data")
                            return
                        data = await r.json()
                pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"][:8]
                if not pairs:
                    await msg.answer("No trending tokens found")
                    return
                text = "\U0001f525 <b>TRENDING SOLANA</b>\n" + "=" * 28 + "\n\n"
                for i, pair in enumerate(pairs, start=1):
                    base = pair.get("baseToken", {})
                    sym = base.get("symbol", "???")
                    addr = base.get("address", "")
                    price = pair.get("priceUsd", "0")
                    vol = pair.get("volume", {}).get("h24", 0) or 0
                    pc = pair.get("priceChange", {}).get("h1", 0) or 0
                    liq = pair.get("liquidity", {}).get("usd", 0) or 0
                    pc_emoji = "\U0001f7e2" if pc >= 0 else "\U0001f534"
                    text += ("#" + str(i) + " <b>" + sym + "</b>\n   $" + str(price) + " | " + pc_emoji + " " + ("+" if pc >= 0 else "") + str(round(pc, 1)) + "%\n   Vol: $" + str(round(vol)) + " | Liq: $" + str(round(liq)) + "\n   <code>" + addr[:20] + "...</code>\n\n")
                await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())
            except Exception as e:
                await msg.answer("Trending error: " + str(e)[:100])

        @r.message(Command("gas"))
        async def h_gas(msg: Message):
            if not self._auth(msg): return
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"jsonrpc": "2.0", "id": 1, "method": "getRecentPrioritizationFees", "params": []}
                    async with session.post(config.rpc.solana_rpc, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        data = await r.json()
                        fees = data.get("result", [])
                        if fees:
                            avg_fee = sum(f.get("prioritizationFee", 0) for f in fees[:20]) / min(20, len(fees))
                            max_fee = max(f.get("prioritizationFee", 0) for f in fees[:20])
                        else:
                            avg_fee = max_fee = 0
                sol_usd = 62.0
                try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
                except: pass
                avg_sol = avg_fee / 1e9
                text = "\u26fd\ufe0f <b>GAS FEE</b>\n" + "=" * 28 + "\n\n"
                text += "Avg: <b>" + str(round(avg_fee)) + " lamports</b> (" + str(round(avg_sol, 6)) + " SOL ~$" + str(round(avg_sol * sol_usd, 4)) + ")\n"
                text += "Max: <b>" + str(round(max_fee)) + " lamports</b>\n\n"
                text += "Bot Priority: <b>100,000 lamports</b> (" + str(round(100000 / 1e9, 6)) + " SOL)"
                await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())
            except Exception as e:
                await msg.answer("Gas error: " + str(e)[:100])

        @r.message(Command("speed"))
        async def h_speed(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            start = time_mod.time()
            await self.bot_instance.executor.get_sol_balance()
            latency = (time_mod.time() - start) * 1000
            st = self.bot_instance.risk_manager.get_stats()
            ms = self.bot_instance.monitor
            uptime = time_mod.time() - self.start_time
            tph = (st["total_trades"] / (uptime / 3600)) if uptime > 3600 else st["total_trades"]
            text = "\u26a1 <b>BOT SPEED</b>\n" + "=" * 28 + "\n\n"
            text += "RPC Latency: <b>" + str(round(latency)) + "ms</b>\n"
            text += "Check Interval: <b>3s</b>\n"
            text += "Trades/Hour: <b>" + str(round(tph, 1)) + "</b>\n"
            text += "Monitor Checks: <b>" + str(ms.total_checks) + "</b>\n"
            text += "Total Exits: <b>" + str(ms.total_exits) + "</b>\n"
            text += "Exit Errors: <b>" + str(ms.total_exit_errors) + "</b>\n"
            text += "DCA Count: <b>" + str(ms.total_dca) + "</b>\n\n"
            if latency < 100: text += "\U0001f7e2 Speed: EXCELLENT"
            elif latency < 300: text += "\U0001f7e1 Speed: GOOD"
            elif latency < 500: text += "\U0001f7e0 Speed: AVERAGE"
            else: text += "\U0001f534 Speed: SLOW"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        # ============================================
        # FINANCE COMMANDS
        # ============================================

        @r.message(Command("journal"))
        async def h_journal(msg: Message):
            if not self._auth(msg): return
            try:
                from utils.trading_journal import get_journal_summary, get_daily_summary, get_weekly_summary
                summary = get_journal_summary()
                daily = get_daily_summary()
                weekly = get_weekly_summary()
                if not summary:
                    await msg.answer("\U0001f4ca <b>No journal data yet</b>", parse_mode="HTML")
                    return
                sol_usd = 62.0
                try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
                except: pass
                text = "\U0001f4ca <b>TRADING JOURNAL</b>\n" + "=" * 28 + "\n\n"
                text += "\U0001f4c8 <b>ALL TIME</b>\n"
                text += "Trades: <b>" + str(summary["total_trades"]) + "</b>\n"
                text += "Win/Loss: <b>" + str(summary["wins"]) + "</b>/<b>" + str(summary["losses"]) + "</b>\n"
                text += "Win Rate: <b>" + str(summary["win_rate"]) + "%</b>\n"
                text += "PnL: <b>" + ("+" if summary["total_pnl_sol"] >= 0 else "") + str(summary["total_pnl_sol"]) + " SOL</b> (~$" + ("+" if summary["total_pnl_sol"] * sol_usd >= 0 else "") + str(round(summary["total_pnl_sol"] * sol_usd, 2)) + ")\n"
                text += "Avg Win: <b>+" + str(summary["avg_win_percent"]) + "%</b>\nAvg Loss: <b>" + str(summary["avg_loss_percent"]) + "%</b>\nPF: <b>" + str(summary["profit_factor"]) + "x</b>\n"
                text += "Multi TP: <b>" + str(summary["multi_tp_count"]) + "</b>\n"
                text += "Best: <b>" + summary["best_trade"]["symbol"] + " +" + str(summary["best_trade"]["pnl_percent"]) + "%</b>\n"
                text += "Worst: <b>" + summary["worst_trade"]["symbol"] + " " + str(summary["worst_trade"]["pnl_percent"]) + "%</b>\n\n"
                if daily:
                    text += "\U0001f4c5 <b>TODAY</b>\nTrades: <b>" + str(daily["trades"]) + "</b> | WR: <b>" + str(daily["win_rate"]) + "%</b>\nPnL: <b>" + ("+" if daily["total_pnl_sol"] >= 0 else "") + str(daily["total_pnl_sol"]) + " SOL</b>\n\n"
                if weekly:
                    text += "\U0001f4c6 <b>WEEKLY (" + str(weekly["days"]) + "d)</b>\nTrades: <b>" + str(weekly["total_trades"]) + "</b> | WR: <b>" + str(weekly["win_rate"]) + "%</b>\nPnL: <b>" + ("+" if weekly["total_pnl_sol"] >= 0 else "") + str(weekly["total_pnl_sol"]) + " SOL</b>\n"
                await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())
            except Exception as e:
                await msg.answer("Journal error: " + str(e)[:100])

        @r.message(Command("pnl"))
        async def h_pnl(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            rm = self.bot_instance.risk_manager
            bal = await self.bot_instance.executor.get_sol_balance()
            st = rm.get_stats()
            sol_usd = 62.0
            try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
            except: pass
            total_usd = st["total_pnl_sol"] * sol_usd
            daily_usd = rm.daily_pnl * sol_usd
            text = "\U0001f4b0 <b>PnL OVERVIEW</b>\n" + "=" * 28 + "\n\n"
            text += "Balance: <b>" + str(round(bal, 4)) + " SOL</b> (~$" + str(round(bal * sol_usd, 2)) + ")\n\n"
            text += "Daily: <b>" + ("+" if rm.daily_pnl >= 0 else "") + str(round(rm.daily_pnl, 4)) + " SOL</b> (~$" + ("+" if daily_usd >= 0 else "") + str(round(daily_usd, 2)) + ")\n"
            text += "Total: <b>" + ("+" if st["total_pnl_sol"] >= 0 else "") + str(round(st["total_pnl_sol"], 4)) + " SOL</b> (~$" + ("+" if total_usd >= 0 else "") + str(round(total_usd, 2)) + ")\n\n"
            text += "Win Rate: <b>" + str(round(st["win_rate"], 1)) + "%</b>\nTrades: <b>" + str(st["total_trades"]) + "</b>\nActive: <b>" + str(st["active_positions"]) + "</b>\nMax DD: <b>" + str(round(st["max_drawdown"], 4)) + " SOL</b>\nPF: <b>" + str(round(st["profit_factor"], 2)) + "x</b>\n"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("risk"))
        async def h_risk(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            rm = self.bot_instance.risk_manager
            bal = await self.bot_instance.executor.get_sol_balance()
            st = rm.get_stats()
            active = st["active_positions"]
            exposure = sum(p.total_invested for p in rm.positions.values() if p.status == "open")
            exposure_pct = (exposure / bal * 100) if bal > 0 else 0
            text = "\U0001f6e1\ufe0f <b>RISK ANALYSIS</b>\n" + "=" * 28 + "\n\n"
            text += "Balance: <b>" + str(round(bal, 4)) + " SOL</b>\n"
            text += "Active: <b>" + str(active) + "</b> positions\n"
            text += "Exposure: <b>" + str(round(exposure, 4)) + " SOL</b> (" + str(round(exposure_pct, 1)) + "%)\n\n"
            text += "\U0001f4ca <b>Risk Level</b>\n"
            if exposure_pct > 50: text += "\U0001f534 HIGH RISK\n"
            elif exposure_pct > 25: text += "\U0001f7e0 MEDIUM\n"
            else: text += "\U0001f7e2 LOW\n"
            text += "\n\U0001f6e1\ufe0f <b>Protection</b>\n"
            text += "Daily PnL: <b>" + str(round(rm.daily_pnl, 4)) + " SOL</b>\n"
            text += "Max DD: <b>" + str(round(rm.max_drawdown, 4)) + " SOL</b>\n"
            text += "Consec Loss: <b>" + str(rm.consecutive_losses) + "/3</b>\n"
            text += "Paused: <b>" + ("YES" if (rm.paused_by_drawdown or rm.paused_by_profit_target) else "NO") + "</b>\n"
            await msg.answer(text, parse_mode="HTML", reply_markup=self._back_kb())

        @r.message(Command("withdraw"))
        async def h_withdraw(msg: Message):
            if not self._auth(msg): return
            if not self.bot_instance:
                await msg.answer("Bot not initialized")
                return
            parts = msg.text.split()
            aw = self.bot_instance.auto_withdraw
            if not aw:
                await msg.answer("Auto withdraw not available")
                return
            stats = aw.get_stats()
            if len(parts) < 2:
                bal = await self.bot_instance.executor.get_sol_balance()
                profit = bal - stats["initial_balance"] if stats["initial_balance"] > 0 else 0
                await msg.answer(
                    "\U0001f4b8 <b>WITHDRAW</b>\n" + "=" * 28 + "\n\n"
                    + "Status: <b>" + ("ON" if stats["enabled"] else "OFF") + "</b>\n"
                    + "Wallet: <code>" + stats["wallet"] + "</code>\n"
                    + "Initial: <b>" + str(round(stats["initial_balance"], 4)) + " SOL</b>\n"
                    + "Balance: <b>" + str(round(bal, 4)) + " SOL</b>\n"
                    + "Profit: <b>" + ("+" if profit >= 0 else "") + str(round(profit, 4)) + " SOL</b>\n\n"
                    + "Min Profit: <b>" + str(stats["min_profit"]) + " SOL</b>\n"
                    + "Percentage: <b>" + str(stats["percentage"]) + "%</b>\n"
                    + "Total Withdrawn: <b>" + str(round(stats["total_withdrawn"], 4)) + " SOL</b>\n"
                    + "Count: <b>" + str(stats["withdraw_count"]) + "</b>\n\n"
                    + "/withdraw now | /withdraw set WALLET\n/withdraw pct 50 | /withdraw min 0.05",
                    parse_mode="HTML", reply_markup=self._back_kb())
                return
            action = parts[1]
            if action == "now":
                await msg.answer("\u23f3 Processing...")
                await aw.check_and_withdraw(self.bot_instance)
                await msg.answer("\u2705 Done!")
            elif action == "set" and len(parts) >= 3:
                aw.withdraw_wallet = parts[2]
                aw.enabled = bool(parts[2] and aw.initial_balance > 0)
                await msg.answer("\u2705 Wallet set: <code>" + parts[2] + "</code>", parse_mode="HTML")
            elif action == "pct" and len(parts) >= 3:
                try: aw.withdraw_percentage = int(parts[2]); await msg.answer("\u2705 Percentage: " + parts[2] + "%")
                except: await msg.answer("Invalid")
            elif action == "min" and len(parts) >= 3:
                try: aw.min_profit_to_withdraw = float(parts[2]); await msg.answer("\u2705 Min profit: " + parts[2] + " SOL")
                except: await msg.answer("Invalid")
            else:
                await msg.answer("Usage:\n/withdraw\n/withdraw now\n/withdraw set WALLET\n/withdraw pct 50\n/withdraw min 0.05")
        # ============================================
        # AUTO RUGCHECK (Paste address)
        # ============================================

        @r.message(F.text & ~F.command)
        async def h_auto(msg: Message):
            if not self._auth(msg):
                return
            text = msg.text.strip()
            kbs = ["\U0001f4ca Stats", "\U0001f4cb Status", "\U0001f4b0 Balance", "\U0001f4c8 Positions", "\U0001f4dc History", "\u23f8\ufe0f Pause", "\u25b6\ufe0f Resume", "\U0001f4e1 Scanner", "\u2699\ufe0f Config", "\U0001f3af Sniper", "\U0001f514 Alerts", "\U0001f4c8 Chart", "\U0001f6d1 Sell All", "\U0001f4f4 Stop"]
            if text in kbs:
                return
            from utils.helpers import is_valid_solana_address
            if is_valid_solana_address(text) and len(text) >= 32:
                await msg.answer("\U0001f50d Auto rugcheck...", parse_mode="HTML")
                if not self.bot_instance:
                    await msg.answer("Bot not initialized")
                    return
                try:
                    meta = await self.bot_instance.scanner._fetch_meta(text)
                    if not meta: meta = {"address": text}
                    report = await self.bot_instance.screener.rug_checker.analyze(meta)
                    checks = ""
                    for n, d in report.details.items():
                        e = "\u2705" if d["passed"] else "\u274c"
                        checks += "  " + e + " " + n + ": " + d["detail"] + "\n"
                    sl = getattr(report, 'safety_level', 'UNKNOWN')
                    labels = {"DANGER": "\u26d4 DANGER - JANGAN BELI!", "HIGH_RISK": "\U0001f534 HIGH RISK - Hindari!", "MEDIUM_RISK": "\U0001f7e0 MEDIUM RISK - Hati-hati!", "LOW_RISK": "\U0001f7e1 LOW RISK - Cek manual", "SAFE": "\u2705 SAFE - Relatif aman", "UNKNOWN": "\u2753 UNKNOWN"}
                    safe = labels.get(sl, "\u2753 UNKNOWN")
                    crit_text = ""
                    crit = getattr(report, 'critical_failures', [])
                    if crit:
                        crit_text = "\n\n\u26d4 <b>CRITICAL:</b>\n"
                        for c in crit:
                            crit_text += "  \U0001f534 " + c.replace("_", " ").upper() + "\n"
                    out = ("\U0001f6e1\ufe0f <b>AUTO RUG CHECK</b>\n" + "=" * 28 + "\n\n<code>" + text[:20] + "...</code>\n\nScore: <b>" + str(report.score) + "/100</b>\n" + self._rbar(report.score) + "\n\n" + safe + "\n\u2705 Passed: <b>" + str(report.checks_passed) + "</b>\n\u274c Failed: <b>" + str(report.checks_failed) + "</b>\n\n<b>Details</b>\n" + checks + crit_text + "\n<b>Risks</b>\n")
                    out += "\n".join(report.reasons) if report.reasons else "None"
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="\U0001f916 AI Analysis", callback_data="ai_" + text)], [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="menu_main")]])
                    await msg.answer(out, parse_mode="HTML", reply_markup=kb)
                except Exception as e:
                    await msg.answer("Error: " + str(e)[:100])

    # ============================================
    # HISTORY PAGE (Class level)
    # ============================================

    async def _send_history_page(self, msg, page):
        if not self.bot_instance:
            await msg.answer("Bot not initialized")
            return
        per_page = 5
        all_trades = list(reversed(self.bot_instance.risk_manager.closed_positions))
        total = len(all_trades)
        if total == 0:
            await msg.answer("\U0001f4dc <b>No trades</b>", parse_mode="HTML", reply_markup=self._back_kb())
            return
        max_page = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, max_page))
        start = (page - 1) * per_page
        end = start + per_page
        trades = all_trades[start:end]
        sol_usd = 62.0
        try: sol_usd = await self.bot_instance.executor._get_sol_usd_price()
        except: pass
        text = "\U0001f4dc <b>TRADE HISTORY</b> (Page " + str(page) + "/" + str(max_page) + ")\n" + "=" * 30 + "\n\n"
        for i, t in enumerate(trades, start=start + 1):
            p = t.get("pnl_percent", 0)
            ps = t.get("pnl_sol", 0)
            dur = t.get("hold_time", "-")
            reason = t.get("reason", "unknown").replace("_", " ").upper()
            symbol = t.get("symbol", "???")
            entry = t.get("entry_sol", 0)
            exit_sol = t.get("exit_sol", 0)
            multi_tp = t.get("multi_tp", False)
            dca = t.get("dca_count", 0)
            pnl_usd = ps * sol_usd
            if ps >= 0: emoji = "\U0001f7e2"; result = "WIN"
            else: emoji = "\U0001f534"; result = "LOSS"
            tp_text = " | TP" if multi_tp else ""
            dca_text = " | DCA:" + str(dca) if dca > 0 else ""
            text += ("#" + str(i) + " " + emoji + " <b>" + symbol + "</b> - " + result + "\n   In: " + str(round(entry, 4)) + " SOL | Out: " + str(round(exit_sol, 4)) + " SOL\n   PnL: <b>" + ("+" if ps >= 0 else "") + str(round(ps, 4)) + " SOL</b> (~$" + ("+" if pnl_usd >= 0 else "") + str(round(pnl_usd, 2)) + ") | <b>" + ("+" if p >= 0 else "") + str(round(p, 2)) + "%</b>\n   \u23f1\ufe0f " + dur + " | \u2699\ufe0f " + reason + tp_text + dca_text + "\n\n")
        total_wins = len([t for t in all_trades if t.get("pnl_sol", 0) >= 0])
        total_losses = len([t for t in all_trades if t.get("pnl_sol", 0) < 0])
        wr = (total_wins / total * 100) if total > 0 else 0
        total_pnl = sum(t.get("pnl_sol", 0) for t in all_trades)
        total_pnl_usd = total_pnl * sol_usd
        filled = int(wr / 10)
        empty = 10 - filled
        if wr >= 60: bar_emoji = "\U0001f7e2"
        elif wr >= 40: bar_emoji = "\U0001f7e1"
        else: bar_emoji = "\U0001f534"
        bar = bar_emoji + " " + "\u2588" * filled + "\u2591" * empty + " " + str(round(wr, 1)) + "%"
        pnl_emoji = "\U0001f4b0" if total_pnl >= 0 else "\U0001f4b8"
        text += "=" * 30 + "\n\U0001f4ca <b>ALL TIME</b>\n"
        text += "Trades: <b>" + str(total) + "</b> | \U0001f7e2 <b>" + str(total_wins) + "</b> | \U0001f534 <b>" + str(total_losses) + "</b>\n"
        text += bar + "\n"
        text += pnl_emoji + " PnL: <b>" + ("+" if total_pnl >= 0 else "") + str(round(total_pnl, 4)) + " SOL</b> (~$" + ("+" if total_pnl_usd >= 0 else "") + str(round(total_pnl_usd, 2)) + ")\n"
        buttons = []
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="\u2b05\ufe0f Prev", callback_data="history_" + str(page - 1)))
        nav.append(InlineKeyboardButton(text=str(page) + "/" + str(max_page), callback_data="noop"))
        if page < max_page:
            nav.append(InlineKeyboardButton(text="Next \u27a1\ufe0f", callback_data="history_" + str(page + 1)))
        buttons.append(nav)
        buttons.append([InlineKeyboardButton(text="\u2b05\ufe0f Menu", callback_data="menu_main")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)

    # ============================================
    # AI HELPER (Class level)
    # ============================================

    def _fix_h(self, meta, report):
        hd = report.details.get("holder_distribution", {})
        ht = hd.get("detail", "")
        if meta.get("holder_count", 0) == 0 and "~" in ht:
            try: meta["holder_count"] = int(ht.split("~")[1].split(" ")[0])
            except: pass
        if meta.get("holder_count", 0) == 0:
            mc = meta.get("market_cap", 0)
            if mc > 100000000: meta["holder_count"] = 50000
            elif mc > 10000000: meta["holder_count"] = 10000
            elif mc > 1000000: meta["holder_count"] = 1000
            elif mc > 100000: meta["holder_count"] = 100
        return meta

    def _build_ai(self, ai, report, meta, addr):
        sym = meta.get("symbol", "???")
        nm = meta.get("name", "Unknown")
        pr = meta.get("price_usd", 0)
        mc = meta.get("market_cap", 0)
        lq = meta.get("liquidity", 0)
        vl = meta.get("volume_24h", 0)
        hc = meta.get("holder_count", 0)
        ch = ""
        for n, d in report.details.items():
            e = "\u2705" if d["passed"] else "\u274c"
            ch += "  " + e + " " + n + ": " + d["detail"] + "\n"
        rm = {"STRONG BUY": "\U0001f7e2 STRONG BUY", "BUY": "\U0001f7e2 BUY", "HOLD": "\U0001f7e1 HOLD", "AVOID": "\U0001f7e0 AVOID", "DANGER": "\U0001f534 DANGER"}
        rc = rm.get(ai["action"], ai["action"])
        nn = "\n".join(["  \u2022 " + nt for nt in ai["notes"]])
        sb = self._abar(ai["total"])
        safe_label = getattr(report, 'safety_level', 'UNKNOWN')
        return ("\U0001f9e0 <b>AI: " + sym + "</b>\n" + nm + "\n" + "=" * 28 + "\n\n"
            + "<b>Market</b>\n  Price: <code>$" + str(pr) + "</code>\n  MCap: <code>$" + str(round(mc)) + "</code>\n  Liq: <code>$" + str(round(lq)) + "</code>\n  Vol: <code>$" + str(round(vl)) + "</code>\n  Holders: <b>" + str(hc) + "</b>\n\n"
            + "<b>Rug</b>\n  Score: <b>" + str(report.score) + "/100</b>\n  Safe: <b>" + safe_label + "</b>\n" + ch + "\n"
            + "<b>AI Score</b>\n  " + sb + "\n  Total: <b>" + str(ai["total"]) + "/100</b>\n  Rec: <b>" + rc + "</b>\n\n"
            + "<b>Breakdown</b>\n  Safety: <b>" + str(ai["safety"]) + "/30</b>\n  Liq: <b>" + str(ai["liquidity"]) + "/25</b>\n  Momentum: <b>" + str(ai["momentum"]) + "/20</b>\n  Holders: <b>" + str(ai["holders"]) + "/15</b>\n  Social: <b>" + str(ai["social"]) + "/10</b>\n\n"
            + "<b>Notes</b>\n" + nn + "\n\n<code>" + addr + "</code>")

    def _ai_analyze(self, report, meta):
        notes = []
        safety = max(0, 30 - (report.score * 0.3))
        if report.is_safe: notes.append("Rug check PASSED")
        else: notes.append("Rug check FAILED (" + str(report.score) + "/100)"); safety = max(0, safety - 10)
        if report.checks_passed >= 10: safety = min(30, safety + 5); notes.append("Most checks passed")
        if report.checks_failed >= 5: safety = max(0, safety - 10); notes.append("Many checks failed")
        safety = round(min(30, max(0, safety)))
        liquidity = 0
        liq = meta.get("liquidity", 0)
        mcap = meta.get("market_cap", 0)
        vol = meta.get("volume_24h", 0)
        if liq >= 100000: liquidity += 15; notes.append("Strong liq: $" + str(round(liq)))
        elif liq >= 50000: liquidity += 12; notes.append("Good liq: $" + str(round(liq)))
        elif liq >= 10000: liquidity += 8; notes.append("Medium liq: $" + str(round(liq)))
        elif liq >= 5000: liquidity += 4; notes.append("Low liq: $" + str(round(liq)))
        else: notes.append("Very low liq: $" + str(round(liq)))
        if mcap > 0 and liq > 0:
            lm = liq / mcap
            if lm >= 0.3: liquidity += 10; notes.append("Excellent liq/mcap")
            elif lm >= 0.1: liquidity += 6
            elif lm >= 0.05: liquidity += 3
        liquidity = round(min(25, max(0, liquidity)))
        momentum = 0
        if vol > 0 and mcap > 0:
            vm = vol / mcap
            if vm >= 1.0: momentum += 15; notes.append("Insane vol: " + str(round(vm, 2)) + "x")
            elif vm >= 0.5: momentum += 12; notes.append("High vol: " + str(round(vm, 2)) + "x")
            elif vm >= 0.1: momentum += 8
            elif vm >= 0.01: momentum += 4
        if meta.get("price_usd", 0) > 0: momentum += 3; notes.append("Has price")
        buys = meta.get("buys_1h", 0); sells = meta.get("sells_1h", 0)
        if buys > sells: momentum += 5; notes.append("Buy pressure: " + str(round(buys / max(1, sells), 1)) + "x")
        elif sells > buys * 2: momentum = max(0, momentum - 5); notes.append("Heavy selling")
        momentum = round(min(20, max(0, momentum)))
        hs = 0; hc = meta.get("holder_count", 0)
        if hc >= 1000: hs += 15; notes.append("Strong holders: " + str(hc))
        elif hc >= 500: hs += 12; notes.append("Good holders: " + str(hc))
        elif hc >= 100: hs += 8; notes.append("Growing holders: " + str(hc))
        elif hc >= 30: hs += 4; notes.append("Few holders: " + str(hc))
        else: notes.append("Very few holders: " + str(hc))
        hs = round(min(15, max(0, hs)))
        social = 0
        if meta.get("website"): social += 3; notes.append("Has website")
        if meta.get("twitter"): social += 3; notes.append("Has Twitter")
        if meta.get("telegram"): social += 4; notes.append("Has Telegram")
        if not any([meta.get("website"), meta.get("twitter"), meta.get("telegram")]): notes.append("No social")
        social = round(min(10, max(0, social)))
        total = min(100, max(0, safety + liquidity + momentum + hs + social))
        if total >= 75 and report.is_safe: action = "STRONG BUY"
        elif total >= 55 and report.is_safe: action = "BUY"
        elif total >= 40: action = "HOLD"
        elif total >= 25: action = "AVOID"
        else: action = "DANGER"
        return {"total": total, "safety": safety, "liquidity": liquidity, "momentum": momentum, "holders": hs, "social": social, "action": action, "notes": notes}

    # ============================================
    # CALLBACKS
    # ============================================

    def _register_callbacks(self):
        r = self.router

        @r.callback_query(F.data.startswith("history_"))
        async def cb_history(cb: CallbackQuery):
            if not self._auth(cb): return
            page = int(cb.data.replace("history_", ""))
            await cb.message.delete()
            await self._send_history_page(cb.message, page)
            await cb.answer()

        @r.callback_query(F.data == "noop")
        async def cb_noop(cb: CallbackQuery):
            await cb.answer()

        @r.callback_query(F.data == "menu_main")
        async def cb_main(cb: CallbackQuery):
            if not self._auth(cb): return
            await cb.message.edit_text("Menu")
            await cb.message.answer("Gunakan menu:", reply_markup=self._main_kb())
            await cb.answer()

        @r.callback_query(F.data == "cancel")
        async def cb_cancel(cb: CallbackQuery):
            if not self._auth(cb): return
            await cb.message.edit_text("Cancelled")
            await cb.answer()

        @r.callback_query(F.data.startswith("confirm_sellall"))
        async def cb_sellall(cb: CallbackQuery):
            if not self._auth(cb): return
            if not self.bot_instance:
                await cb.answer("Not ready")
                return
            rm = self.bot_instance.risk_manager
            ps = {a: p for a, p in rm.positions.items() if p.status == "open"}
            if not ps:
                await cb.message.edit_text("No positions")
                await cb.answer()
                return
            await cb.message.edit_text("Selling " + str(len(ps)) + "...")
            res = []
            for a, p in list(ps.items()):
                try:
                    r = await self.bot_instance.executor.sell_token(p.token_address, int(p.tokens_held))
                    if r and r.get("success"):
                        sr = r.get("sol_received", 0)
                        pn = sr - p.total_invested
                        rm.close_position(a, 0, sr)
                        e = "\U0001f7e2" if pn >= 0 else "\U0001f534"
                        res.append(e + " " + p.symbol + ": " + str(round(pn, 4)) + " SOL")
                    else: res.append("\u274c " + p.symbol)
                except: res.append("\u274c " + p.symbol)
            await cb.message.edit_text("<b>Results</b>\n\n" + "\n".join(res), parse_mode="HTML")
            await cb.answer("Done!")

        @r.callback_query(F.data.startswith("confirm_stop"))
        async def cb_stop(cb: CallbackQuery):
            if not self._auth(cb): return
            await cb.message.edit_text("\u23f9\ufe0f <b>BOT DIHENTIKAN</b>\n\nKetik /resume untuk mengaktifkan kembali", parse_mode="HTML")
            if self.bot_instance:
                self.bot_instance.circuit_breaker_active = True
            await cb.answer()

        @r.callback_query(F.data.startswith("confirm_sell_"))
        async def cb_sell_confirm(cb: CallbackQuery):
            if not self._auth(cb): return
            if not self.bot_instance:
                await cb.answer("Not ready")
                return
            target = cb.data.replace("confirm_sell_", "")
            rm = self.bot_instance.risk_manager
            pos = None
            fa = ""
            for a, p in rm.positions.items():
                if p.status == "open" and a[:16] == target:
                    pos = p
                    fa = a
                    break
            if not pos:
                await cb.message.edit_text("Not found")
                await cb.answer()
                return
            await cb.message.edit_text("Selling " + pos.symbol + "...")
            try:
                r = await self.bot_instance.executor.sell_token(pos.token_address, int(pos.tokens_held))
                if r and r.get("success"):
                    sr = r.get("sol_received", 0)
                    pn = sr - pos.total_invested
                    rm.close_position(fa, 0, sr)
                    e = "WIN" if pn >= 0 else "LOSS"
                    await cb.message.edit_text(e + ": " + pos.symbol + "\n\nReturned: " + str(round(sr, 4)) + " SOL\nPnL: " + str(round(pn, 4)) + " SOL", parse_mode="HTML")
                else: await cb.message.edit_text("Sell failed")
            except Exception as e: await cb.message.edit_text("Error: " + str(e)[:80])
            await cb.answer()

        @r.callback_query(F.data.startswith("posdetail_"))
        async def cb_posdetail(cb: CallbackQuery):
            if not self._auth(cb): return
            target = cb.data.replace("posdetail_", "")
            rm = self.bot_instance.risk_manager if self.bot_instance else None
            if not rm:
                await cb.answer("Not ready")
                return
            pos = None
            fa = ""
            for a, p in rm.positions.items():
                if p.status == "open" and a[:16] == target:
                    pos = p
                    fa = a
                    break
            if not pos:
                await cb.answer("Not found")
                return
            text = ("\U0001f4cb <b>" + pos.symbol + "</b>\n" + "=" * 28 + "\n\nEntry: " + str(round(pos.entry_sol, 4)) + " SOL\nPrice: $" + str(pos.entry_price) + "\nSL: $" + str(pos.stop_loss_price) + "\nTP1: $" + str(round(pos.tp1_price, 10)) + "\nTP2: $" + str(round(pos.tp2_price, 10)) + "\nHigh: $" + str(pos.highest_price) + "\nTokens: " + str(round(pos.tokens_held)) + "\nDuration: " + pos.hold_duration() + "\nRemaining: " + str(round(pos.remaining_pct * 100)) + "%\nDCA: " + str(pos.dca_count) + "/" + str(pos.dca_max) + "\n\n<code>" + fa + "</code>")
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Sell", callback_data="confirm_sell_" + fa[:16])], [InlineKeyboardButton(text="Back", callback_data="back_positions")]]))
            await cb.answer()

        @r.callback_query(F.data == "back_positions")
        async def cb_back_pos(cb: CallbackQuery):
            if not self._auth(cb): return
            if not self.bot_instance:
                await cb.answer("Not ready")
                return
            rm = self.bot_instance.risk_manager
            ps = {a: p for a, p in rm.positions.items() if p.status == "open"}
            if not ps:
                await cb.message.edit_text("No positions")
                await cb.answer()
                return
            t = "<b>POSITIONS</b>\n\n"
            for a, p in ps.items():
                t += p.symbol + " | " + str(round(p.entry_sol, 3)) + " SOL | " + p.hold_duration() + "\n"
            await cb.message.edit_text(t, parse_mode="HTML", reply_markup=self._pos_kb(ps))
            await cb.answer()

        @r.callback_query(F.data.startswith("ai_"))
        async def cb_ai(cb: CallbackQuery):
            if not self._auth(cb): return
            target = cb.data.replace("ai_", "")
            if not self.bot_instance:
                await cb.answer("Not ready")
                return
            await cb.message.edit_reply_markup(reply_markup=None)
            await cb.message.answer("AI Analyzing...", parse_mode="HTML")
            try:
                meta = await self.bot_instance.scanner._fetch_meta(target)
                if not meta:
                    meta = {"address": target, "symbol": "???", "name": "Unknown", "price_usd": 0, "market_cap": 0, "volume_24h": 0, "liquidity": 0, "holder_count": 0, "website": "", "twitter": "", "telegram": "", "buys_1h": 0, "sells_1h": 0, "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0}
                report = await self.bot_instance.screener.rug_checker.analyze(meta)
                meta = self._fix_h(meta, report)
                ai = self._ai_analyze(report, meta)
                await cb.message.answer(self._build_ai(ai, report, meta, target), parse_mode="HTML", reply_markup=self._back_kb())
            except Exception as e:
                await cb.message.answer("AI error: " + str(e)[:100])
            await cb.answer()

        @r.callback_query(F.data.startswith("set_"))
        async def cb_set(cb: CallbackQuery):
            if not self._auth(cb): return
            s = cb.data.replace("set_", "")
            h = {"sl": "Ketik: /setsl 30", "tp": "Ketik: /settp 200", "size": "Ketik: /setsize 0.1", "concurrent": "Ketik: /setconcurrent 5", "slippage": "Ketik: /setslippage 500"}
            await cb.answer(h.get(s, "Use command"), show_alert=True)
