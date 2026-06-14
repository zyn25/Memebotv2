"""
Meme Coin Sniper Bot - Main Entry Point
Railway-optimized + Telegram + Whale + PriceFeed + Multi TP + DCA + Pre-Buy Checks + Auto Withdraw + Safety + Journal
"""
import asyncio
import signal
import sys
import os
import time
import json
import threading
import traceback
from pathlib import Path
from flask import Flask, jsonify
from config import config
from core.scanner import TokenScanner
from core.screener import TokenScreener
from core.executor import TradeExecutor
from core.risk_manager import RiskManager
from core.monitor import PositionMonitor
from core.price_feed import PriceFeed
from dashboard.dashboard import Dashboard
from utils.logger import logger, console
from utils.telegram_notifier import notifier
from utils.helpers import current_timestamp
from utils.trading_journal import journal

try:
    from utils.telegram_bot import TelegramBot
    TG_AVAILABLE = True
except Exception as e:
    print("TelegramBot import error: " + str(e))
    TG_AVAILABLE = False
    TelegramBot = None

try:
    from core.whale_tracker import WhaleTracker
    WHALE_AVAILABLE = True
except Exception as e:
    print("WhaleTracker import error: " + str(e))
    WHALE_AVAILABLE = False
    WhaleTracker = None

try:
    from utils.auto_withdraw import AutoWithdraw
    WITHDRAW_AVAILABLE = True
except Exception as e:
    print("AutoWithdraw import error: " + str(e))
    WITHDRAW_AVAILABLE = False
    AutoWithdraw = None

STATE_DIR = Path("./bot_state")
STATE_FILE = STATE_DIR / "state.json"


def save_state(bot):
    try:
        STATE_DIR.mkdir(exist_ok=True)
        state = {
            "saved_at": current_timestamp(),
            "stats": bot.stats,
            "seen_tokens": list(bot.scanner.seen_tokens),
            "risk_stats": {
                "total_trades": bot.risk_manager.total_trades,
                "winning_trades": bot.risk_manager.winning_trades,
                "losing_trades": bot.risk_manager.losing_trades,
                "daily_pnl": bot.risk_manager.daily_pnl,
                "max_drawdown": bot.risk_manager.max_drawdown,
            },
            "closed_positions": bot.risk_manager.closed_positions[-100:],
            "blacklist": list(bot.token_blacklist),
            "whitelist": list(bot.token_whitelist),
        }
        if bot.auto_withdraw:
            state["withdraw_stats"] = bot.auto_withdraw.get_stats()
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning("Save state failed: " + str(e))


def load_state(bot):
    try:
        if not STATE_FILE.exists():
            logger.info("No previous state, starting fresh")
            return
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        bot.scanner.seen_tokens = set(state.get("seen_tokens", []))
        rs = state.get("risk_stats", {})
        bot.risk_manager.total_trades = rs.get("total_trades", 0)
        bot.risk_manager.winning_trades = rs.get("winning_trades", 0)
        bot.risk_manager.losing_trades = rs.get("losing_trades", 0)
        bot.risk_manager.daily_pnl = rs.get("daily_pnl", 0)
        bot.risk_manager.max_drawdown = rs.get("max_drawdown", 0)
        bot.risk_manager.closed_positions = state.get("closed_positions", [])
        bot.stats.update(state.get("stats", {}))
        bot.token_blacklist = set(state.get("blacklist", []))
        bot.token_whitelist = set(state.get("whitelist", []))
        if bot.auto_withdraw:
            ws = state.get("withdraw_stats", {})
            if ws:
                bot.auto_withdraw.total_withdrawn = ws.get("total_withdrawn", 0)
                bot.auto_withdraw.withdraw_count = ws.get("withdraw_count", 0)
        logger.info("State restored | Seen: " + str(len(bot.scanner.seen_tokens)))
    except Exception as e:
        logger.warning("Load state failed: " + str(e))


health_app = Flask("health")
_bot_instance = None
_bot_start_time = 0.0


def _fmt_up(s):
    d = int(s // 86400)
    h = int((s % 86400) // 3600)
    m = int((s % 3600) // 60)
    return str(d) + "d " + str(h) + "h " + str(m) + "m"


@health_app.route("/health")
def health():
    global _bot_instance, _bot_start_time
    if not _bot_instance:
        return jsonify({"status": "starting"}), 503
    try:
        st = _bot_instance.risk_manager.get_stats()
        return jsonify({
            "status": "ok",
            "uptime": _fmt_up(time.time() - _bot_start_time),
            "mode": "dry_run" if config.dry_run else "live",
            "trades": st["total_trades"],
            "win_rate": round(st["win_rate"], 1),
            "pnl": round(st["total_pnl_sol"], 4),
            "active": st["active_positions"],
            "scanner": _bot_instance.running,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


class MemeSniperBot:
    def __init__(self):
        self.start_time = time.time()
        self.running = False
        self.circuit_breaker_active = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        self.token_blacklist = set()
        self.token_whitelist = set()
        self.stats = {
            "tokens_scanned": 0,
            "tokens_passed_screening": 0,
            "tokens_failed_screening": 0,
            "rugpulls_blocked": 0,
            "trades_executed": 0,
            "errors": 0,
        }
        self.scanner = TokenScanner()
        self.screener = TokenScreener()
        self.executor = TradeExecutor()
        self.risk_manager = RiskManager()
        self.monitor = PositionMonitor(self.risk_manager, self.executor)
        self.price_feed = PriceFeed()
        self.dashboard = Dashboard(self.risk_manager)
        self.telegram = None
        self.whale_tracker = None
        self.auto_withdraw = None

    async def initialize(self):
        global _bot_instance, _bot_start_time
        _bot_instance = self
        _bot_start_time = self.start_time
        logger.info("Initializing bot...")

        try:
            await self.executor.initialize()
            logger.info("Executor OK")
        except Exception as e:
            logger.error("Executor init failed: " + str(e))
            traceback.print_exc()

        try:
            await self.screener.initialize()
            logger.info("Screener OK")
        except Exception as e:
            logger.error("Screener init failed: " + str(e))
            traceback.print_exc()

        try:
            asyncio.create_task(self.price_feed.start(self))
            logger.info("PriceFeed OK")
        except Exception as e:
            logger.error("PriceFeed init failed: " + str(e))
            traceback.print_exc()

        try:
            self.dashboard.start()
            logger.info("Dashboard OK")
        except AttributeError:
            logger.info("Dashboard OK (no start method)")
        except Exception as e:
            logger.error("Dashboard init failed: " + str(e))
            traceback.print_exc()

        self.scanner.on_new_token(self._on_new_token)
        load_state(self)

        self.monitor.bot_dashboard = self.dashboard
        self.monitor.telegram_notifier = notifier
        self.monitor.bot_instance = self

        if TG_AVAILABLE and TelegramBot:
            try:
                self.telegram = TelegramBot()
                self.telegram.set_bot(self)
                await self.telegram.start()
                logger.info("Telegram OK")
            except Exception as e:
                logger.error("Telegram init failed: " + str(e))
                traceback.print_exc()

        if WHALE_AVAILABLE and WhaleTracker:
            try:
                self.whale_tracker = WhaleTracker()
                await self.whale_tracker.initialize()
                self.whale_tracker.bot_instance = self
                logger.info("WhaleTracker OK")
            except Exception as e:
                logger.error("WhaleTracker init failed: " + str(e))
                traceback.print_exc()

        if WITHDRAW_AVAILABLE and AutoWithdraw:
            try:
                self.auto_withdraw = AutoWithdraw()
                await self.auto_withdraw.initialize()
                withdraw_wallet = os.getenv("WITHDRAW_WALLET", "")
                initial_balance = float(os.getenv("INITIAL_BALANCE", "0"))
                min_profit = float(os.getenv("MIN_PROFIT_WITHDRAW", "0.05"))
                withdraw_pct = int(os.getenv("WITHDRAW_PERCENTAGE", "50"))
                self.auto_withdraw.setup(
                    withdraw_wallet=withdraw_wallet,
                    initial_balance=initial_balance,
                    min_profit=min_profit,
                    percentage=withdraw_pct,
                )
                logger.info("AutoWithdraw OK")
            except Exception as e:
                logger.error("AutoWithdraw init failed: " + str(e))
                traceback.print_exc()

        logger.info("Bot initialized")

    async def show_journal(self, msg):
        txt = journal.format_journal(10)
        if self.telegram:
            await self.telegram._send(txt)

    async def show_daily(self, msg):
        txt = journal.format_daily()
        if self.telegram:
            await self.telegram._send(txt)

    async def show_weekly(self, msg):
        txt = journal.format_weekly()
        if self.telegram:
            await self.telegram._send(txt)

    async def start(self):
        self.running = True
        logger.info("Starting bot...")
        tasks = [self.scanner.start(), self.monitor.start()]
        if self.whale_tracker:
            self.whale_tracker.bot_instance = self
            tasks.append(self.whale_tracker.start(self))
        tasks.append(self._save_loop())
        tasks.append(self._hourly_report_loop())
        tasks.append(self._withdraw_loop())
        tasks.append(self._safety_loop())
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        save_state(self)
        if self.telegram:
            try:
                await self.telegram.stop()
            except:
                pass
        if self.whale_tracker:
            try:
                await self.whale_tracker.close()
            except:
                pass
        if self.auto_withdraw:
            try:
                await self.auto_withdraw.close()
            except:
                pass
        try:
            await self.scanner.stop()
        except:
            pass
        try:
            await self.monitor.stop()
        except:
            pass
        try:
            await self.screener.close()
        except:
            pass
        try:
            await self.executor.close()
        except:
            pass
        try:
            await self.price_feed.stop()
        except:
            pass
        logger.info("Bot stopped")

    async def _save_loop(self):
        while self.running:
            try:
                save_state(self)
            except:
                pass
            await asyncio.sleep(300)

    async def _hourly_report_loop(self):
        while self.running:
            try:
                await asyncio.sleep(3600)
                if not self.running:
                    break
                st = self.risk_manager.get_stats()
                bs = self.stats
                up = time.time() - self.start_time
                sol_p = self.price_feed.get_sol_price()
                ws = self.whale_tracker.get_stats() if self.whale_tracker else {"whales_tracked": 0, "trades_copied": 0}
                bal = await self.executor.get_sol_balance()
                aw = self.auto_withdraw.get_stats() if self.auto_withdraw else {"total_withdrawn": 0, "withdraw_count": 0}
                await notifier.send_message(
                    "\U0001f514 <b>Hourly Report</b>\n\n"
                    + "Uptime: " + _fmt_up(up) + "\n"
                    + "Balance: " + str(round(bal, 4)) + " SOL\n"
                    + "Scanned: " + str(bs["tokens_scanned"]) + "\n"
                    + "Trades: " + str(st["total_trades"]) + "\n"
                    + "Win Rate: " + str(round(st["win_rate"], 1)) + "%\n"
                    + "PnL: " + str(round(st["total_pnl_sol"], 4)) + " SOL\n"
                    + "Monitor: " + str(self.monitor.total_checks) + " checks\n"
                    + "Whales: " + str(ws["whales_tracked"]) + " | Copies: " + str(ws["trades_copied"]) + "\n"
                    + "Withdrawn: " + str(round(aw["total_withdrawn"], 4)) + " SOL (" + str(aw["withdraw_count"]) + "x)\n"
                    + "SOL Price: $" + str(round(sol_p, 2))
                )
            except:
                pass

    async def _withdraw_loop(self):
        while self.running:
            try:
                await asyncio.sleep(3600)
                if not self.running:
                    break
                if self.auto_withdraw:
                    await self.auto_withdraw.check_and_withdraw(self)
            except:
                pass

    async def _safety_loop(self):
        while self.running:
            try:
                await asyncio.sleep(300)
                if not self.running:
                    break

                try:
                    if not config.dry_run:
                        balance = await self.executor.get_sol_balance()
                        if balance < 0.05 and self.telegram:
                            await self.telegram._send(
                                "\u26a0\ufe0f <b>LOW BALANCE WARNING</b>\n\n"
                                + "Balance: <b>" + str(round(balance, 4)) + " SOL</b>\n"
                                + "Minimum: 0.05 SOL\n\n"
                                + "Bot mungkin tidak bisa trade!"
                            )
                except:
                    pass

                rm = self.risk_manager
                if rm.consecutive_losses >= 2 and self.telegram:
                    try:
                        await self.telegram._send(
                            "\u26a0\ufe0f <b>CONSECUTIVE LOSS WARNING</b>\n\n"
                            + "Losses: <b>" + str(rm.consecutive_losses) + "/3</b>\n\n"
                            + "Auto pause di 3 consecutive losses!"
                        )
                    except:
                        pass

                if rm.daily_pnl < -0.3 and self.telegram:
                    try:
                        await self.telegram._send(
                            "\u26a0\ufe0f <b>DAILY LOSS WARNING</b>\n\n"
                            + "Daily PnL: <b>" + str(round(rm.daily_pnl, 4)) + " SOL</b>\n"
                            + "Limit: -0.5 SOL\n\n"
                            + "Approaching daily loss limit!"
                        )
                    except:
                        pass

            except:
                pass

    async def _on_new_token(self, token_data):
        try:
            await self._process_token(token_data)
        except Exception as e:
            logger.error("Process error: " + str(e)[:100])
            traceback.print_exc()
            self.stats["errors"] += 1
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.circuit_breaker_active = True
                logger.error("CIRCUIT BREAKER: " + str(self.consecutive_errors) + " consecutive errors")

    async def _process_token(self, token_data):
        if self.circuit_breaker_active:
            return
        sym = token_data.get("symbol", "???")
        addr = token_data.get("address", "")
        self.stats["tokens_scanned"] += 1

        if addr in self.token_blacklist:
            return

        screened = await self.screener.screen_token(token_data)
        if not screened:
            self.stats["tokens_failed_screening"] += 1
            return
        rug = screened.rugpull_report
        self.stats["tokens_passed_screening"] += 1

        can, reason = self.risk_manager.can_open_position()
        if not can:
            self.dashboard.emit_scanned_token(token_data, "risk_blocked")
            self.dashboard.emit_alert("alert", "RISK BLOCKED: " + sym, reason)
            return

        vol_1h = token_data.get("volume_1h", 0) or 0
        vol_5m = token_data.get("volume_5m", 0) or 0
        if vol_1h > 0 and vol_5m >= 0:
            try:
                expected_5m = vol_1h / 12
                if expected_5m > 0:
                    vol_ratio = vol_5m / expected_5m
                    if vol_ratio < 0.1:
                        logger.info("[SKIP] " + sym + ": Volume dropping (" + str(round(vol_ratio, 2)) + ")")
                        self.stats["tokens_failed_screening"] += 1
                        self.dashboard.emit_scanned_token(token_data, "volume_drop")
                        return
            except Exception:
                pass

        buys_1h = token_data.get("buys_1h", 0) or 0
        sells_1h = token_data.get("sells_1h", 0) or 0
        if sells_1h > 0 and buys_1h > 0:
            try:
                ratio = buys_1h / sells_1h
                if ratio < 0.2:
                    logger.info("[SKIP] " + sym + ": Heavy selling (ratio: " + str(round(ratio, 2)) + ")")
                    self.stats["tokens_failed_screening"] += 1
                    self.dashboard.emit_scanned_token(token_data, "heavy_selling")
                    return
            except Exception:
                pass

        size = self.risk_manager.calculate_position_size(screened.screener_score, rug.score)
        logger.info("[SIZE] " + sym + " = " + str(round(size, 4)) + " SOL")

        logger.info("[BUY] " + sym + " | Rug: " + str(rug.score) + "/100 | Size: " + str(round(size, 4)) + " SOL")
        self.dashboard.emit_scanned_token(token_data, "buying")
        self.dashboard.emit_alert("buy", "BUYING: " + sym, "Size: " + str(round(size, 4)) + " SOL | Rug: " + str(rug.score) + "/100")

        buy = await self.executor.buy_token(token_address=addr, sol_amount=size)

        if not buy or not buy.get("success"):
            logger.error("[FAIL] Buy failed: " + sym)
            self.stats["errors"] += 1
            self.dashboard.emit_scanned_token(token_data, "buy_failed")
            self.dashboard.emit_alert("alert", "BUY FAILED: " + sym, "Could not execute")
            return

        if buy.get("tokens_received", 0) <= 0 and not buy.get("dry_run"):
            logger.error("[FAIL] 0 tokens received: " + sym)
            self.stats["errors"] += 1
            self.dashboard.emit_alert("alert", "BUY FAILED: " + sym, "0 tokens received")
            return

        tokens = buy.get("tokens_received", 0)
        price = buy.get("price", 0)
        pos = self.risk_manager.open_position(
            token_address=addr, symbol=sym, entry_price=price,
            sol_amount=size, tokens_received=tokens,
            screener_score=screened.screener_score, rug_score=rug.score,
        )

        self.stats["trades_executed"] += 1
        self.consecutive_errors = 0

        dr = "DRY" if buy.get("dry_run") else "LIVE"
        logger.info(
            "[" + dr + " BUY] " + sym
            + " | " + str(round(size, 4)) + " SOL"
            + " | Price: $" + str(price)
            + " | Tokens: " + str(tokens)
            + " | Rug: " + str(rug.score) + "/100"
        )

        self.dashboard.emit_alert(
            "buy", "BUY EXECUTED (" + dr + "): " + sym,
            "Amount: " + str(round(size, 4)) + " SOL\n"
            + "Price: $" + str(price) + "\n"
            + "Tokens: " + str(tokens) + "\n"
            + "Rug Score: " + str(rug.score) + "/100"
        )

        if self.telegram:
            try:
                await self.telegram._send(
                    "\U0001f7e2 <b>BUY EXECUTED</b>\n\n"
                    + "Token: " + sym + "\n"
                    + "Amount: " + str(round(size, 4)) + " SOL\n"
                    + "Price: $" + str(price) + "\n"
                    + "Tokens: " + str(tokens) + "\n"
                    + "Rug Score: " + str(rug.score) + "/100"
                )
            except:
                pass

        # Record BUY ke journal
        try:
            journal.add_buy(
                token=addr,
                symbol=sym,
                amount_sol=size,
                price=price,
                tokens=tokens,
                rug_score=rug.score,
            )
        except Exception as e:
            logger.debug("Journal BUY error: " + str(e)[:50])


async def run_bot():
    bot = MemeSniperBot()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot, sig)))
        except NotImplementedError:
            pass
    try:
        await bot.initialize()
        await bot.start()
    except KeyboardInterrupt:
        await bot.stop()
    except Exception as e:
        logger.error("Fatal error: " + str(e))
        traceback.print_exc()
        try:
            await bot.stop()
        except:
            pass


async def shutdown(bot, sig):
    logger.info("Shutdown signal received: " + str(sig))
    await bot.stop()


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    health_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    asyncio.run(run_bot())
