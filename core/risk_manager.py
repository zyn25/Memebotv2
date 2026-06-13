"""
Risk Management System (OPTIMIZED RISK/REWARD)
- Dynamic trailing stop (FIXED - profit lebih besar)
- Stop loss lebih ketat (20%)
- Take profit realistis (200%)
- Max drawdown auto pause
- Consecutive loss protection
- Time-based exit (2 menit)
- Daily PnL auto reset
- Profit target harian
- Multi TP detection
- DCA with minimum hold time
"""
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from config import config
from utils.logger import logger, console
from utils.helpers import calculate_pnl, current_timestamp


@dataclass
class Position:
    token_address: str
    symbol: str
    entry_price: float
    entry_sol: float
    tokens_held: float
    entry_time: int
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_price: float = 0.0
    highest_price: float = 0.0
    status: str = "open"
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    tp3_price: float = 0.0
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    remaining_pct: float = 1.0
    dca_count: int = 0
    dca_max: int = 2
    total_invested: float = 0.0
    total_sol_received: float = 0.0

    def __post_init__(self):
        self.total_invested = self.entry_sol
        self._setup_multi_tp()

    def _setup_multi_tp(self):
        if self.entry_price > 0:
            self.tp1_price = self.entry_price * 2.0
            self.tp2_price = self.entry_price * 3.0
            self.tp3_price = self.entry_price * 6.0

    def update_price(self, cp):
        if cp > self.highest_price:
            self.highest_price = cp
            # Dynamic trailing stop - FIXED untuk profit lebih besar
            profit_pct = ((cp - self.entry_price) / self.entry_price) * 100
            if profit_pct >= 200:
                self.trailing_stop_price = cp * 0.85
            elif profit_pct >= 100:
                self.trailing_stop_price = cp * 0.80
            elif profit_pct >= 50:
                self.trailing_stop_price = cp * 0.75
            else:
                self.trailing_stop_price = cp * 0.70

    def should_stop_loss(self, cp):
        return cp <= self.stop_loss_price or (
            self.trailing_stop_price > 0 and cp <= self.trailing_stop_price
        )

    def should_take_profit(self, cp):
        return cp >= self.take_profit_price

    def check_multi_tp(self, cp):
        hits = []
        if not self.tp1_hit and self.tp1_price > 0 and cp >= self.tp1_price:
            hits.append(("tp1", 0.30))
            self.tp1_hit = True
            self.remaining_pct -= 0.30
        if not self.tp2_hit and self.tp2_price > 0 and cp >= self.tp2_price:
            hits.append(("tp2", 0.30))
            self.tp2_hit = True
            self.remaining_pct -= 0.30
        if not self.tp3_hit and self.tp3_price > 0 and cp >= self.tp3_price:
            hits.append(("tp3", max(0.01, self.remaining_pct)))
            self.tp3_hit = True
            self.remaining_pct = 0
        return hits

    def should_dca(self, cp):
        if self.entry_price <= 0 or self.dca_count >= self.dca_max:
            return (False, 0, "")
        hold_time = current_timestamp() - self.entry_time
        if hold_time < 30:
            return (False, 0, "")
        drop = ((self.entry_price - cp) / self.entry_price) * 100
        if drop >= 40 and self.dca_count == 0:
            return (True, self.entry_sol * 0.3, "DCA L1: drop 40%")
        if drop >= 60 and self.dca_count == 1:
            return (True, self.entry_sol * 0.2, "DCA L2: drop 60%")
        return (False, 0, "")

    def pnl_percent(self, cp):
        return calculate_pnl(self.entry_price, cp)

    def hold_duration(self):
        diff = current_timestamp() - self.entry_time
        if diff < 60:
            return str(diff) + "s"
        if diff < 3600:
            return str(diff // 60) + "m " + str(diff % 60) + "s"
        return str(diff // 3600) + "h " + str((diff % 3600) // 60) + "m"

    def get_sell_amount(self, pct):
        return max(1, int(self.tokens_held * pct))

    def update_after_partial_sell(self, pct, sol_received):
        self.remaining_pct = max(0, self.remaining_pct - pct)
        self.tokens_held = max(0, self.tokens_held - int(self.tokens_held * pct))
        self.total_invested = self.total_invested * self.remaining_pct


class RiskManager:
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.closed_positions: list = []
        self.daily_pnl: float = 0.0
        self.daily_loss_limit: float = -0.5
        self.daily_profit_target: float = 1.0
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.max_drawdown: float = 0.0
        self.paused_by_drawdown: bool = False
        self.paused_by_profit_target: bool = False
        self.consecutive_losses: int = 0
        self.max_consecutive_losses: int = 3
        self.last_reset_day: int = 0
        self.token_blacklist_rug: set = set()

    def _check_daily_reset(self):
        today = int(current_timestamp() / 86400)
        if today != self.last_reset_day:
            self.daily_pnl = 0.0
            self.last_reset_day = today
            self.paused_by_drawdown = False
            self.paused_by_profit_target = False
            self.consecutive_losses = 0
            logger.info("Daily PnL reset!")

    def can_open_position(self):
        self._check_daily_reset()
        active = len([p for p in self.positions.values() if p.status == "open"])
        if active >= config.trading.max_concurrent:
            return False, "Max concurrent"
        if self.paused_by_drawdown:
            return False, "Paused: drawdown (" + str(round(self.daily_pnl, 4)) + " SOL)"
        if self.paused_by_profit_target:
            return False, "Paused: daily profit target reached!"
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, "Paused: " + str(self.consecutive_losses) + " consecutive losses"
        return True, "OK"

    def calculate_position_size(self, screener_score, rug_score):
        base = config.trading.max_sol_per_trade
        sm = 0.3 + (screener_score / 100) * 0.7
        sf = max(0.3, (100 - rug_score) / 100)
        size = base * sm * sf
        return round(max(0.01, min(base, size)), 4)

    def open_position(self, token_address, symbol, entry_price, sol_amount,
            tokens_received, screener_score, rug_score):
        pos = Position(
            token_address=token_address, symbol=symbol,
            entry_price=entry_price, entry_sol=sol_amount,
            tokens_held=tokens_received, entry_time=current_timestamp(),
            stop_loss_price=entry_price * (1 - config.trading.stop_loss_percent / 100),
            take_profit_price=entry_price * (1 + config.trading.take_profit_percent / 100),
            highest_price=entry_price,
        )
        self.positions[token_address] = pos
        self.total_trades += 1
        logger.info("Position: " + symbol + " | " + str(round(sol_amount, 4)) + " SOL")
        return pos

    def close_position(self, token_address, exit_price, sol_returned, reason="unknown"):
        pos = self.positions.get(token_address)
        if not pos:
            return None

        pnl_sol = sol_returned - pos.total_invested
        if pos.total_invested > 0:
            pnl = ((sol_returned - pos.total_invested) / pos.total_invested) * 100
        else:
            pnl = 0

        pos.status = "closed"
        self._check_daily_reset()
        self.daily_pnl += pnl_sol

        if pnl_sol >= 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            if pnl < -30:
                self.token_blacklist_rug.add(token_address)
                logger.warning("AUTO BLACKLIST: " + pos.symbol + " | Rug " + str(round(pnl, 1)) + "%")

        if self.daily_pnl < self.max_drawdown:
            self.max_drawdown = self.daily_pnl

        if self.daily_pnl < -0.5:
            self.paused_by_drawdown = True
            logger.warning("AUTO PAUSE: Daily loss " + str(round(self.daily_pnl, 4)) + " SOL")
            console.print("[bold red]AUTO PAUSE: Daily loss " + str(round(self.daily_pnl, 4)) + " SOL[/]")

        if self.daily_pnl >= self.daily_profit_target:
            self.paused_by_profit_target = True
            logger.info("AUTO PAUSE: Daily profit target reached! +" + str(round(self.daily_pnl, 4)) + " SOL")
            console.print("[bold green]AUTO PAUSE: Profit target! +" + str(round(self.daily_pnl, 4)) + " SOL[/]")

        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning("AUTO PAUSE: " + str(self.consecutive_losses) + " consecutive losses")
            console.print("[bold red]AUTO PAUSE: " + str(self.consecutive_losses) + " consecutive losses[/]")

        self.closed_positions.append({
            "token": token_address, "symbol": pos.symbol,
            "entry_sol": pos.total_invested, "exit_sol": sol_returned,
            "pnl_percent": pnl, "pnl_sol": pnl_sol,
            "hold_time": pos.hold_duration(), "timestamp": current_timestamp(),
            "multi_tp": pos.tp1_hit or pos.tp2_hit or pos.tp3_hit,
            "dca_count": pos.dca_count, "reason": reason,
        })

        del self.positions[token_address]
        return pos

    def check_exit_conditions(self, addr, cp):
        pos = self.positions.get(addr)
        if not pos:
            return None

        pos.update_price(cp)

        # CHECK 1: Multi TP DETECT ONLY
        tp_detected = False
        if not pos.tp1_hit and pos.tp1_price > 0 and cp >= pos.tp1_price:
            tp_detected = True
        if not pos.tp2_hit and pos.tp2_price > 0 and cp >= pos.tp2_price:
            tp_detected = True
        if not pos.tp3_hit and pos.tp3_price > 0 and cp >= pos.tp3_price:
            tp_detected = True
        if tp_detected:
            return {"action": "multi_tp", "token_address": addr, "symbol": pos.symbol,
                    "current_price": cp, "entry_price": pos.entry_price, "pnl_percent": pos.pnl_percent(cp)}

        # CHECK 2: Stop Loss / Trailing
        if pos.should_stop_loss(cp):
            reason = "trailing"
            if pos.trailing_stop_price <= 0 or cp > pos.trailing_stop_price:
                reason = "stop_loss"
            return {"action": "stop_loss", "token_address": addr, "symbol": pos.symbol,
                    "sell_pct": 1.0, "tokens_to_sell": {addr: pos.get_sell_amount(1.0)},
                    "current_price": cp, "entry_price": pos.entry_price,
                    "pnl_percent": pos.pnl_percent(cp), "reason": reason}

        # CHECK 3: Take Profit
        if pos.should_take_profit(cp):
            return {"action": "take_profit", "token_address": addr, "symbol": pos.symbol,
                    "sell_pct": 1.0, "tokens_to_sell": {addr: pos.get_sell_amount(1.0)},
                    "current_price": cp, "entry_price": pos.entry_price,
                    "pnl_percent": pos.pnl_percent(cp)}

        # CHECK 4: Time-based exit (2 menit, profit <10%)
        hold = current_timestamp() - pos.entry_time
        if hold > 120 and pos.pnl_percent(cp) < 10:
            return {"action": "time_exit", "token_address": addr, "symbol": pos.symbol,
                    "sell_pct": 1.0, "tokens_to_sell": {addr: pos.get_sell_amount(1.0)},
                    "current_price": cp, "entry_price": pos.entry_price,
                    "pnl_percent": pos.pnl_percent(cp)}

        return None

    def check_dca(self, addr, cp):
        pos = self.positions.get(addr)
        if not pos:
            return (False, 0, "")
        return pos.should_dca(cp)

    def get_stats(self):
        wr = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        tp = sum(t.get("pnl_sol", 0) for t in self.closed_positions)
        wins = [t.get("pnl_sol", 0) for t in self.closed_positions if t.get("pnl_sol", 0) > 0]
        losses = [t.get("pnl_sol", 0) for t in self.closed_positions if t.get("pnl_sol", 0) < 0]
        aw = sum(wins) / len(wins) if wins else 0
        al = sum(losses) / len(losses) if losses else 0
        return {
            "total_trades": self.total_trades,
            "winning": self.winning_trades, "losing": self.losing_trades,
            "win_rate": wr, "total_pnl_sol": tp, "daily_pnl": self.daily_pnl,
            "avg_win": aw, "avg_loss": al,
            "profit_factor": abs(aw / al) if al != 0 else float("inf"),
            "active_positions": len([p for p in self.positions.values() if p.status == "open"]),
            "max_drawdown": self.max_drawdown,
        }

    def get_daily_report(self):
        today = current_timestamp() - (current_timestamp() % 86400)
        trades = [t for t in self.closed_positions if t.get("timestamp", 0) >= today]
        wins = sum(1 for t in trades if t.get("pnl_sol", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl_sol", 0) <= 0)
        total_pnl = sum(t.get("pnl_sol", 0) for t in trades)
        best = max(trades, key=lambda t: t.get("pnl_sol", 0), default=None) if trades else None
        worst = min(trades, key=lambda t: t.get("pnl_sol", 0), default=None) if trades else None
        return {"trades": len(trades), "wins": wins, "losses": losses,
                "win_rate": (wins / len(trades) * 100) if trades else 0,
                "total_pnl": total_pnl, "best_trade": best, "worst_trade": worst}

    def get_weekly_report(self):
        week_ago = current_timestamp() - (7 * 86400)
        trades = [t for t in self.closed_positions if t.get("timestamp", 0) >= week_ago]
        wins = sum(1 for t in trades if t.get("pnl_sol", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl_sol", 0) <= 0)
        total_pnl = sum(t.get("pnl_sol", 0) for t in trades)
        return {"trades": len(trades), "wins": wins, "losses": losses,
                "win_rate": (wins / len(trades) * 100) if trades else 0,
                "total_pnl": total_pnl, "avg_pnl": total_pnl / len(trades) if trades else 0}

    def print_stats(self):
        s = self.get_stats()
        console.print("\n" + "=" * 40)
        console.print("TRADING STATS")
        console.print("  Trades: " + str(s["total_trades"]) + " | Win: " + str(round(s["win_rate"], 1)) + "%")
        console.print("  PnL: " + str(round(s["total_pnl_sol"], 4)) + " SOL")
        console.print("  PF: " + str(round(s["profit_factor"], 2)))
        console.print("=" * 40 + "\n")