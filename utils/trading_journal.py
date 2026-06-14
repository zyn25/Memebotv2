"""
utils/trading_journal.py
Trading Journal - Records all trades for analysis
"""
import json
import os
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from utils.logger import logger


JOURNAL_FILE = "data/journal.json"


@dataclass
class TradeEntry:
    token: str
    symbol: str
    side: str
    amount_sol: float
    price: float
    tokens: float
    timestamp: float
    tx_hash: str = ""
    pnl_sol: float = 0.0
    pnl_pct: float = 0.0
    rug_score: int = 0
    notes: str = ""
    exit_reason: str = ""
    duration_sec: float = 0.0


class TradingJournal:
    def __init__(self):
        self.entries: List[TradeEntry] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(JOURNAL_FILE):
                with open(JOURNAL_FILE, "r") as f:
                    data = json.load(f)
                for d in data:
                    self.entries.append(TradeEntry(**d))
                logger.info("Journal loaded: " + str(len(self.entries)) + " entries")
            else:
                os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
                logger.info("Journal: new file created")
        except Exception as e:
            logger.error("Journal load error: " + str(e))
            self.entries = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
            with open(JOURNAL_FILE, "w") as f:
                json.dump([asdict(e) for e in self.entries], f, indent=2)
        except Exception as e:
            logger.error("Journal save error: " + str(e))

    def add_buy(self, token: str, symbol: str, amount_sol: float,
                price: float, tokens: float, rug_score: int = 0,
                tx_hash: str = "") -> TradeEntry:
        entry = TradeEntry(
            token=token,
            symbol=symbol,
            side="BUY",
            amount_sol=amount_sol,
            price=price,
            tokens=tokens,
            timestamp=time.time(),
            tx_hash=tx_hash,
            rug_score=rug_score,
        )
        self.entries.append(entry)
        self._save()
        logger.info("Journal BUY: " + symbol + " | " + str(amount_sol) + " SOL")
        return entry

    def add_sell(self, token: str, symbol: str, amount_sol: float,
                 price: float, tokens: float, pnl_sol: float = 0.0,
                 pnl_pct: float = 0.0, exit_reason: str = "",
                 tx_hash: str = "") -> TradeEntry:
        entry = TradeEntry(
            token=token,
            symbol=symbol,
            side="SELL",
            amount_sol=amount_sol,
            price=price,
            tokens=tokens,
            timestamp=time.time(),
            tx_hash=tx_hash,
            pnl_sol=pnl_sol,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
        )
        self.entries.append(entry)
        self._save()
        logger.info("Journal SELL: " + symbol + " | PnL: " + str(round(pnl_sol, 4)) + " SOL")
        return entry

    def get_recent(self, count: int = 10) -> List[TradeEntry]:
        return self.entries[-count:]

    def get_today(self) -> List[TradeEntry]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        return [e for e in self.entries if e.timestamp >= today_start]

    def get_wins(self) -> List[TradeEntry]:
        return [e for e in self.entries if e.side == "SELL" and e.pnl_sol > 0]

    def get_losses(self) -> List[TradeEntry]:
        return [e for e in self.entries if e.side == "SELL" and e.pnl_sol < 0]

    def get_total_pnl(self) -> float:
        return sum(e.pnl_sol for e in self.entries if e.side == "SELL")

    def get_win_rate(self) -> float:
        sells = [e for e in self.entries if e.side == "SELL"]
        if not sells:
            return 0.0
        wins = len([e for e in sells if e.pnl_sol > 0])
        return (wins / len(sells)) * 100

    def format_journal(self, count: int = 10) -> str:
        recent = self.get_recent(count)
        if not recent:
            return "\U0001f4dc Journal kosong\n\nBelum ada trade tercatat."

        lines = []
        lines.append("\U0001f4dc <b>TRADING JOURNAL</b>")
        lines.append("=" * 28)
        lines.append("")

        for e in reversed(recent):
            ts = datetime.fromtimestamp(e.timestamp).strftime("%m/%d %H:%M")
            if e.side == "BUY":
                lines.append(
                    "\U0001f7e2 " + ts + " | BUY " + e.symbol + "\n"
                    + "   " + str(round(e.amount_sol, 4)) + " SOL @ $" + str(e.price) + "\n"
                    + "   Rug: " + str(e.rug_score) + "/100"
                )
            else:
                emoji = "\U0001f7e2" if e.pnl_sol >= 0 else "\U0001f534"
                pnl_str = "+" + str(round(e.pnl_sol, 4)) if e.pnl_sol >= 0 else str(round(e.pnl_sol, 4))
                pct_str = "+" + str(round(e.pnl_pct, 1)) if e.pnl_pct >= 0 else str(round(e.pnl_pct, 1))
                lines.append(
                    emoji + " " + ts + " | SELL " + e.symbol + "\n"
                    + "   PnL: " + pnl_str + " SOL (" + pct_str + "%)\n"
                    + "   Reason: " + (e.exit_reason or "manual")
                )
            lines.append("")

        sells = [e for e in self.entries if e.side == "SELL"]
        wins = len([e for e in sells if e.pnl_sol > 0])
        losses = len([e for e in sells if e.pnl_sol < 0])
        total_pnl = self.get_total_pnl()
        wr = self.get_win_rate()

        lines.append("\U0001f4ca <b>SUMMARY</b>")
        lines.append("Total Trades: " + str(len(sells)))
        lines.append("Wins: " + str(wins) + " | Losses: " + str(losses))
        lines.append("Win Rate: " + str(round(wr, 1)) + "%")
        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        pnl_sign = "+" if total_pnl >= 0 else ""
        lines.append("Total PnL: " + pnl_emoji + " " + pnl_sign + str(round(total_pnl, 4)) + " SOL")

        return "\n".join(lines)

    def format_daily(self) -> str:
        today = self.get_today()
        if not today:
            return "\U0001f4c5 <b>DAILY REPORT</b>\n\nBelum ada trade hari ini."

        sells = [e for e in today if e.side == "SELL"]
        wins = len([e for e in sells if e.pnl_sol > 0])
        losses = len([e for e in sells if e.pnl_sol < 0])
        total_pnl = sum(e.pnl_sol for e in sells)
        wr = (wins / len(sells) * 100) if sells else 0

        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        pnl_sign = "+" if total_pnl >= 0 else ""

        return (
            "\U0001f4c5 <b>DAILY REPORT</b>\n"
            + "=" * 28 + "\n\n"
            + "Trades: " + str(len(sells)) + "\n"
            + "Wins: " + str(wins) + " | Losses: " + str(losses) + "\n"
            + "Win Rate: " + str(round(wr, 1)) + "%\n"
            + "PnL: " + pnl_emoji + " " + pnl_sign + str(round(total_pnl, 4)) + " SOL"
        )

    def format_weekly(self) -> str:
        week_ago = time.time() - (7 * 24 * 3600)
        week_entries = [e for e in self.entries if e.timestamp >= week_ago]
        sells = [e for e in week_entries if e.side == "SELL"]

        if not sells:
            return "\U0001f4c5 <b>WEEKLY REPORT</b>\n\nBelum ada trade minggu ini."

        wins = len([e for e in sells if e.pnl_sol > 0])
        losses = len([e for e in sells if e.pnl_sol < 0])
        total_pnl = sum(e.pnl_sol for e in sells)
        wr = (wins / len(sells) * 100) if sells else 0
        best = max(sells, key=lambda e: e.pnl_sol)
        worst = min(sells, key=lambda e: e.pnl_sol)

        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        pnl_sign = "+" if total_pnl >= 0 else ""

        return (
            "\U0001f4c5 <b>WEEKLY REPORT</b>\n"
            + "=" * 28 + "\n\n"
            + "Trades: " + str(len(sells)) + "\n"
            + "Wins: " + str(wins) + " | Losses: " + str(losses) + "\n"
            + "Win Rate: " + str(round(wr, 1)) + "%\n"
            + "PnL: " + pnl_emoji + " " + pnl_sign + str(round(total_pnl, 4)) + " SOL\n\n"
            + "\U0001f3c6 Best: " + best.symbol + " (+" + str(round(best.pnl_sol, 4)) + " SOL)\n"
            + "\U0001f494 Worst: " + worst.symbol + " (" + str(round(worst.pnl_sol, 4)) + " SOL)"
        )


# Singleton instance
journal = TradingJournal()


# ============================================
# COMPATIBILITY FUNCTIONS
# Dipanggil dari file lain yang import nama ini
# ============================================

def get_journal_summary():
    return journal.format_journal(10)

def get_daily_summary():
    return journal.format_daily()

def get_weekly_summary():
    return journal.format_weekly()
