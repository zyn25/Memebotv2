"""
Position Monitor (ULTIMATE)
- Multi TP + DCA
- Retry sell 3x
- Alert profit besar
- Auto sell token dead
- Early exit (5 detik)
"""
import asyncio
import time
from typing import Optional, TYPE_CHECKING
from config import config
from core.risk_manager import RiskManager, Position
from core.executor import TradeExecutor
from utils.logger import logger, console
from utils.helpers import calculate_pnl, current_timestamp

if TYPE_CHECKING:
    from dashboard.dashboard import Dashboard
    from utils.telegram_notifier import TelegramNotifier


class PositionMonitor:
    def __init__(self, risk_manager: RiskManager, executor: TradeExecutor):
        self.risk_manager = risk_manager
        self.executor = executor
        self.running = False
        self.check_interval = 3
        self.bot_dashboard: Optional["Dashboard"] = None
        self.telegram_notifier: Optional["TelegramNotifier"] = None
        self.bot_instance = None
        self.total_checks = 0
        self.total_exits = 0
        self.total_exit_errors = 0
        self.total_dca = 0

    async def start(self):
        self.running = True
        logger.info("Position Monitor started (ULTIMATE)")
        while self.running:
            try:
                await self._check_all()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor error: " + str(e))
                await asyncio.sleep(5)

    async def stop(self):
        self.running = False

    async def _check_all(self):
        positions = {a: p for a, p in self.risk_manager.positions.items() if p.status == "open"}
        if not positions:
            return
        self.total_checks += 1
        for addr, pos in list(positions.items()):
            try:
                await self._check_one(addr, pos)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Check error " + pos.symbol + ": " + str(e))

    async def _check_one(self, addr, pos):
        cp = await self.executor.get_token_price(addr)
        if cp is None:
            return
        pos.update_price(cp)
        pnl = pos.pnl_percent(cp)

        self._emit_positions(addr, cp)

        # EARLY EXIT: Turun >15% dalam 5 detik pertama
        hold_time = current_timestamp() - pos.entry_time
        if hold_time < 5 and pnl < -15:
            logger.warning("EARLY EXIT: " + pos.symbol + " | " + str(round(pnl, 1)) + "% dalam " + str(hold_time) + "s")
            await self._exit_from_data(pos, cp, {"action": "early_exit"})
            return

        # AUTO SELL: Token dead
        if cp <= 0 or cp < pos.entry_price * 0.01:
            logger.warning("TOKEN DEAD: " + pos.symbol + " | Price: " + str(cp))
            await self._exit_from_data(pos, cp, {"action": "token_dead"})
            return

        # Check DCA
        should_dca, dca_amount, dca_reason = self.risk_manager.check_dca(addr, cp)
        if should_dca and dca_amount > 0:
            await self._execute_dca(pos, cp, dca_amount, dca_reason)

        # Check exit
        exit_data = self.risk_manager.check_exit_conditions(addr, cp)
        if exit_data is None:
            if self.total_checks % 10 == 0:
                if pnl >= 0:
                    console.print("[green]" + pos.symbol + ": " + str(round(pnl, 2)) + "% | " + pos.hold_duration() + "[/]")
                else:
                    console.print("[red]" + pos.symbol + ": " + str(round(pnl, 2)) + "% | SL:" + str(round(pos.stop_loss_price, 10)) + " | " + pos.hold_duration() + "[/]")
            return

        action = exit_data.get("action", "")
        if action == "multi_tp":
            await self._execute_multi_tp(pos, cp)
        elif action in ("stop_loss", "take_profit", "time_exit", "token_dead"):
            await self._exit_from_data(pos, cp, exit_data)

    async def _execute_multi_tp(self, pos, cp):
        tp_hits = pos.check_multi_tp(cp)
        if not tp_hits:
            return
        for tp_name, sell_pct in tp_hits:
            sell_amount = int(pos.tokens_held * sell_pct)
            if sell_amount <= 0:
                continue
            console.print("[bold cyan]MULTI TP: " + tp_name.upper() + " | " + pos.symbol + " | Sell " + str(round(sell_pct * 100)) + "%[/]")
            self._emit_alert("buy", "TP HIT: " + tp_name.upper() + " " + pos.symbol, "Selling " + str(round(sell_pct * 100)) + "%")

            # RETRY SELL 3x
            result = None
            for attempt in range(3):
                result = await self.executor.sell_token(pos.token_address, sell_amount)
                if result and result.get("success"):
                    break
                logger.warning("Sell retry " + str(attempt + 1) + "/3 for " + pos.symbol)
                await asyncio.sleep(1)

            if result and result.get("success"):
                sol_r = result.get("sol_received", 0)
                pos.total_sol_received += sol_r
                partial_invested = pos.total_invested * sell_pct
                pnl_sol = sol_r - partial_invested
                pnl_pct = ((sol_r - partial_invested) / partial_invested) * 100 if partial_invested > 0 else 0

                if self.telegram_notifier:
                    try:
                        await self.telegram_notifier.send_message(
                            "\U0001f680 MULTI TP " + tp_name.upper() + ": " + pos.symbol + "\n\n"
                            + "Sold: " + str(round(sell_pct * 100)) + "%\n"
                            + "Got: " + str(round(sol_r, 4)) + " SOL\n"
                            + "PnL: " + str(round(pnl_pct, 1)) + "% (" + str(round(pnl_sol, 4)) + " SOL)\n"
                            + "Remaining: " + str(round(pos.remaining_pct * 100)) + "%")
                    except:
                        pass

                # ALERT PROFIT BESAR
                if pnl_pct >= 100 and self.telegram_notifier:
                    try:
                        await self.telegram_notifier.send_message(
                            "\U0001f680\U0001f680\U0001f680 BIG WIN!\n\n"
                            + pos.symbol + " +" + str(round(pnl_pct, 1)) + "%\n"
                            + "Profit: " + str(round(sol_r, 4)) + " SOL")
                    except:
                        pass

                self.total_exits += 1
                logger.info("MULTI TP " + tp_name.upper() + ": " + pos.symbol + " | " + str(round(pnl_pct, 1)) + "%")

                if pos.remaining_pct <= 0:
                    total_returned = pos.total_sol_received
                    pnl_final = total_returned - pos.total_invested
                    actual_pnl_final = ((total_returned - pos.total_invested) / pos.total_invested) * 100 if pos.total_invested > 0 else 0
                    is_win_final = total_returned >= pos.total_invested

                    self.risk_manager.close_position(pos.token_address, cp, total_returned, reason="multi_tp_all")

                    trade = {"symbol": pos.symbol, "token": pos.token_address,
                             "entry_sol": pos.total_invested, "exit_sol": total_returned,
                             "pnl_percent": actual_pnl_final, "pnl_sol": pnl_final,
                             "hold_time": pos.hold_duration(), "reason": "multi_tp_all",
                             "tx_hash": result.get("tx_hash", ""),
                             "tokens_sold": sell_amount, "timestamp": int(time.time()),
                             "multi_tp": True, "dca_count": pos.dca_count}

                    if self.bot_dashboard:
                        self.bot_dashboard.add_trade_to_history(trade)
                        e = "WIN" if is_win_final else "LOSS"
                        t = "sell" if is_win_final else "alert"
                        self.bot_dashboard.emit_alert(t, e + ": " + pos.symbol,
                            "PnL: " + str(round(actual_pnl_final, 2)) + "% (" + str(round(pnl_final, 4)) + " SOL) | multi_tp")

                    if self.telegram_notifier:
                        try:
                            await self.telegram_notifier.notify_sell({
                                "symbol": pos.symbol, "address": pos.token_address,
                                "sol_received": total_returned, "pnl_percent": actual_pnl_final,
                                "hold_time": pos.hold_duration(), "reason": "multi_tp_all"})
                        except:
                            pass

                    dr = "DRY" if result.get("dry_run") else "LIVE"
                    c = "green" if is_win_final else "red"
                    e = "WIN" if is_win_final else "LOSS"
                    console.print("\n[bold " + c + "]"
                        + "=" * 50 + "\n  " + e + " " + dr + " SELL (MULTI TP ALL): " + pos.symbol
                        + "\n  Invested: " + str(round(pos.total_invested, 4)) + " SOL"
                        + "\n  Got: " + str(round(total_returned, 4)) + " SOL"
                        + "\n  PnL: " + str(round(actual_pnl_final, 2)) + "% (" + str(round(pnl_final, 4)) + " SOL)"
                        + "\n  Duration: " + pos.hold_duration()
                        + "\n" + "=" * 50 + "[/]\n")
            else:
                logger.error("Multi TP sell failed after 3 retries: " + pos.symbol + " " + tp_name)
                if self.telegram_notifier:
                    try:
                        await self.telegram_notifier.send_message("\u274c SELL FAILED (3 retries): " + pos.symbol + " " + tp_name.upper())
                    except:
                        pass

    async def _exit_from_data(self, pos, cp, exit_data):
        reason = exit_data.get("action", "unknown")
        self.total_exits += 1
        pnl = exit_data.get("pnl_percent", pos.pnl_percent(cp))
        logger.info("EXIT: " + pos.symbol + " | " + reason + " | " + str(round(pnl, 2)) + "%")
        self._emit_alert("alert", "EXIT: " + pos.symbol, "Reason: " + reason + " | PnL: " + str(round(pnl, 2)) + "%")

        sell_pct = max(0.01, pos.remaining_pct)
        sell_amount = int(pos.tokens_held * sell_pct)
        if sell_amount <= 0:
            sell_amount = int(pos.tokens_held)

        # RETRY SELL 3x
        result = None
        for attempt in range(3):
            result = await self.executor.sell_token(pos.token_address, sell_amount)
            if result and result.get("success"):
                break
            logger.warning("Sell retry " + str(attempt + 1) + "/3 for " + pos.symbol)
            await asyncio.sleep(1)

        if not result or not result.get("success"):
            self.total_exit_errors += 1
            logger.error("Sell failed after 3 retries: " + pos.symbol)
            if self.telegram_notifier:
                try:
                    await self.telegram_notifier.send_message("\u274c SELL FAILED (3 retries): " + pos.symbol)
                except:
                    pass
            return

        sol_r = result.get("sol_received", 0)
        pos.total_sol_received += sol_r
        total_returned = pos.total_sol_received
        pnl_sol = total_returned - pos.total_invested
        actual_pnl = ((total_returned - pos.total_invested) / pos.total_invested) * 100 if pos.total_invested > 0 else 0
        is_win = total_returned >= pos.total_invested

        self.risk_manager.close_position(pos.token_address, cp, total_returned, reason=reason)

        trade = {"symbol": pos.symbol, "token": pos.token_address,
                 "entry_sol": pos.total_invested, "exit_sol": total_returned,
                 "pnl_percent": actual_pnl, "pnl_sol": pnl_sol,
                 "hold_time": pos.hold_duration(), "reason": reason,
                 "tx_hash": result.get("tx_hash", ""),
                 "tokens_sold": sell_amount, "timestamp": int(time.time()),
                 "multi_tp": pos.tp1_hit or pos.tp2_hit or pos.tp3_hit,
                 "dca_count": pos.dca_count}

        if self.bot_dashboard:
            self.bot_dashboard.add_trade_to_history(trade)
            e = "WIN" if is_win else "LOSS"
            t = "sell" if is_win else "alert"
            self.bot_dashboard.emit_alert(t, e + ": " + pos.symbol,
                "PnL: " + str(round(actual_pnl, 2)) + "% (" + str(round(pnl_sol, 4)) + " SOL) | " + reason)

        if self.telegram_notifier:
            try:
                await self.telegram_notifier.notify_sell({
                    "symbol": pos.symbol, "address": pos.token_address,
                    "sol_received": total_returned, "pnl_percent": actual_pnl,
                    "hold_time": pos.hold_duration(), "reason": reason})
            except:
                pass

        dr = "DRY" if result.get("dry_run") else "LIVE"
        c = "green" if is_win else "red"
        e = "WIN" if is_win else "LOSS"
        console.print("\n[bold " + c + "]"
            + "=" * 50 + "\n  " + e + " " + dr + " SELL: " + pos.symbol
            + "\n  Invested: " + str(round(pos.total_invested, 4)) + " SOL"
            + "\n  Got: " + str(round(total_returned, 4)) + " SOL"
            + "\n  PnL: " + str(round(actual_pnl, 2)) + "% (" + str(round(pnl_sol, 4)) + " SOL)"
            + "\n  Reason: " + reason
            + "\n  Duration: " + pos.hold_duration()
            + "\n  TX: " + result.get("tx_hash", "N/A")
            + "\n" + "=" * 50 + "[/]\n")

    async def _execute_dca(self, pos, cp, amount, reason):
        if pos.dca_count >= pos.dca_max:
            return
        try:
            if self.bot_instance:
                meta = await self.bot_instance.scanner._fetch_meta(pos.token_address)
                if not meta:
                    meta = {"address": pos.token_address}
                report = await self.bot_instance.screener.rug_checker.analyze(meta)
                if not report.is_safe:
                    logger.warning("DCA BLOCKED: " + pos.symbol + " | Rug score: " + str(report.score))
                    if self.telegram_notifier:
                        try:
                            await self.telegram_notifier.send_message(
                                "\u26d4 DCA BLOCKED: " + pos.symbol + "\n\n"
                                + "Reason: Token unsafe\n"
                                + "Rug Score: " + str(report.score) + "/100\n"
                                + "Safety: " + getattr(report, 'safety_level', 'UNKNOWN'))
                        except:
                            pass
                    return
        except Exception as e:
            logger.warning("DCA rugcheck failed: " + str(e)[:50])

        console.print("[bold yellow]DCA: " + pos.symbol + " | " + str(round(amount, 4)) + " SOL | " + reason + "[/]")
        buy = await self.executor.buy_token(pos.token_address, amount)
        if buy and buy.get("success"):
            pos.dca_count += 1
            pos.total_invested += amount
            tokens = buy.get("tokens_received", 0)
            pos.tokens_held += tokens
            if pos.tokens_held > 0:
                pos.entry_price = pos.total_invested / (pos.tokens_held / (10 ** 9))
            pos._setup_multi_tp()
            self.total_dca += 1
            console.print("[bold yellow]DCA SUCCESS: " + pos.symbol + " | Total: " + str(round(pos.total_invested, 4)) + " SOL[/]")
            self._emit_alert("buy", "DCA: " + pos.symbol, reason + " | " + str(round(amount, 4)) + " SOL")
            if self.telegram_notifier:
                try:
                    await self.telegram_notifier.send_message(
                        "\U0001f504 DCA BUY: " + pos.symbol + "\n\n"
                        + "Amount: " + str(round(amount, 4)) + " SOL\n"
                        + "Reason: " + reason + "\n"
                        + "Total: " + str(round(pos.total_invested, 4)) + " SOL\n"
                        + "DCA: " + str(pos.dca_count) + "/" + str(pos.dca_max))
                except:
                    pass

    def _emit_positions(self, addr, cp):
        if not self.bot_dashboard:
            return
        try:
            ps = []
            for a, p in self.risk_manager.positions.items():
                if p.status == "open":
                    pp = p.pnl_percent(cp if a == addr else p.highest_price)
                    ps.append({"symbol": p.symbol, "address": a,
                               "entry_price": p.entry_price,
                               "current_price": cp if a == addr else p.highest_price,
                               "entry_sol": p.total_invested, "pnl": pp, "pnl_sol": 0,
                               "stop_loss": p.stop_loss_price,
                               "take_profit": p.take_profit_price,
                               "trailing_stop": p.trailing_stop_price,
                               "highest_price": p.highest_price,
                               "duration": p.hold_duration(),
                               "tp1_hit": p.tp1_hit, "tp2_hit": p.tp2_hit,
                               "tp3_hit": p.tp3_hit, "remaining": p.remaining_pct,
                               "dca_count": p.dca_count})
            self.bot_dashboard.emit_update("position_update", ps)
        except:
            pass

    def _emit_alert(self, t, title, desc):
        if self.bot_dashboard:
            try:
                self.bot_dashboard.emit_alert(t, title, desc)
            except:
                pass

    def get_stats(self):
        return {"running": self.running, "check_interval": self.check_interval,
                "total_checks": self.total_checks, "total_exits": self.total_exits,
                "total_exit_errors": self.total_exit_errors, "total_dca": self.total_dca,
                "active": len([p for p in self.risk_manager.positions.values() if p.status == "open"])}