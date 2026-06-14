"""
utils/trading_journal.py
Trading Journal - v2.0 BULLETPROOF
Handles corrupted files, empty files, wrong format, everything.
"""
import json
import os
import time
from typing import List
from dataclasses import dataclass, asdict
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
            if not os.path.exists(JOURNAL_FILE):
                logger.info("Journal: no file, starting fresh")
                return

            with open(JOURNAL_FILE, "r") as f:
                content = f.read().strip()

            if not content or content == "" or content == "null":
                logger.info("Journal: file empty, starting fresh")
                return

            data = json.loads(content)

            if isinstance(data, str):
                logger.warning("Journal: file is string, resetting")
                self.entries = []
                self._save_clean()
                return

            if not isinstance(data, list):
                logger.warning("Journal: file not list, resetting")
                self.entries = []
                self._save_clean()
                return

            count = 0
            for d in data:
                try:
                    if isinstance(d, dict):
                        clean = {}
                        for k, v in d.items():
                            if k in TradeEntry.__dataclass_fields__:
                                clean[k] = v
                        if "token" in clean and "symbol" in clean:
                            self.entries.append(TradeEntry(**clean))
                            count += 1
                except Exception:
                    continue

            logger.info("Journal loaded: " + str(count) + " entries")

        except json.JSONDecodeError:
            logger.warning("Journal: corrupted JSON, resetting")
            self.entries = []
            self._save_clean()
        except Exception as e:
            logger.error("Journal load error: " + str(e))
            self.entries = []

    def _save_clean(self):
        try:
            os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
            with open(JOURNAL_FILE, "w") as f:
                json.dump([], f)
        except Exception as e:
            logger.error("Journal save_clean error: " + str(e))

    def _save(self):
        try:
            os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
            data = []
            for e in self.entries:
                try:
                    data.append(asdict(e))
                except Exception:
                    continue
            with open(JOURNAL_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error("Journal save error: " + str(e))

    def add_buy(self, token="", symbol="", amount_sol=0.0,
                price=0.0, tokens=0.0, rug_score=0,
                tx_hash="", **kwargs):
        try:
            entry = TradeEntry(
                token=str(token),
                symbol=str(symbol),
                side="BUY",
                amount_sol=float(amount_sol),
                price=float(price),
                tokens=float(tokens),
                timestamp=time.time(),
                tx_hash=str(tx_hash),
                rug_score=int(rug_score),
            )
            self.entries.append(entry)
            self._save()
            logger.info("Journal BUY: " + str(symbol) + " | " + str(amount_sol) + " SOL")
            return entry
        except Exception as e:
            logger.error("Journal add_buy error: " + str(e))
            return None

    def add_sell(self, token="", symbol="", amount_sol=0.0,
                 price=0.0, tokens=0.0, pnl_sol=0.0,
                 pnl_pct=0.0, exit_reason="",
                 tx_hash="", **kwargs):
        try:
            entry = TradeEntry(
                token=str(token),
                symbol=str(symbol),
                side="SELL",
                amount_sol=float(amount_sol),
                price=float(price),
                tokens=float(tokens),
                timestamp=time.time(),
                tx_hash=str(tx_hash),
                pnl_sol=float(pnl_sol),
                pnl_pct=float(pnl_pct),
                exit_reason=str(exit_reason),
            )
            self.entries.append(entry)
            self._save()
            logger.info("Journal SELL: " + str(symbol) + " | PnL: " + str(round(pnl_sol, 4)) + " SOL")
            return entry
        except Exception as e:
            logger.error("Journal add_sell error: " + str(e))
            return None

    def get_recent(self, count=10):
        return self.entries[-count:]

    def get_today(self):
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp()
            return [e for e in self.entries if e.timestamp >= today_start]
        except Exception:
            return []

    def get_wins(self):
        return [e for e in self.entries if e.side == "SELL" and e.pnl_sol > 0]

    def get_losses(self):
        return [e for e in self.entries if e.side == "SELL" and e.pnl_sol < 0]

    def get_total_pnl(self):
        try:
            return sum(e.pnl_sol for e in self.entries if e.side == "SELL")
        except Exception:
            return 0.0

    def get_win_rate(self):
        try:
            sells = [e for e in self.entries if e.side == "SELL"]
            if not sells:
                return 0.0
            wins = len([e for e in sells if e.pnl_sol > 0])
            return (wins / len(sells)) * 100
        except Exception:
            return 0.0

    def format_journal(self, count=10):
        try:
            recent = self.get_recent(count)
            if not recent:
                return "\U0001f4dc <b>TRADING JOURNAL</b>\n\nJournal kosong\n\nBelum ada trade tercatat."

            lines = []
            lines.append("\U0001f4dc <b>TRADING JOURNAL</b>")
            lines.append("=" * 28)
            lines.append("")

            for e in reversed(recent):
                try:
                    ts = datetime.fromtimestamp(e.timestamp).strftime("%m/%d %H:%M")
                    if e.side == "BUY":
                        lines.append(
                            "\U0001f7e2 " + ts + " | BUY " + str(e.symbol) + "\n"
                            + "   " + str(round(e.amount_sol, 4)) + " SOL @ $" + str(e.price) + "\n"
                            + "   Rug: " + str(e.rug_score) + "/100"
                        )
                    else:
                        emoji = "\U0001f7e2" if e.pnl_sol >= 0 else "\U0001f534"
                        pnl_str = "+" + str(round(e.pnl_sol, 4)) if e.pnl_sol >= 0 else str(round(e.pnl_sol, 4))
                        pct_str = "+" + str(round(e.pnl_pct, 1)) if e.pnl_pct >= 0 else str(round(e.pnl_pct, 1))
                        lines.append(
                            emoji + " " + ts + " | SELL " + str(e.symbol) + "\n"
                            + "   PnL: " + pnl_str + " SOL (" + pct_str + "%)\n"
                            + "   Reason: " + str(e.exit_reason or "manual")
                        )
                    lines.append("")
                except Exception:
                    continue

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
        except Exception as e:
            return "\U0001f4dc Journal error: " + str(e)

    def format_daily(self):
        try:
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
        except Exception as e:
            return "Daily report error: " + str(e)

    def format_weekly(self):
        try:
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
                + "\U0001f3c6 Best: " + str(best.symbol) + " (+" + str(round(best.pnl_sol, 4)) + " SOL)\n"
                + "\U0001f494 Worst: " + str(worst.symbol) + " (" + str(round(worst.pnl_sol, 4)) + " SOL)"
            )
        except Exception as e:
            return "Weekly report error: " + str(e)


journal = TradingJournal()


def get_journal_summary():
    return journal.format_journal(10)

def get_daily_summary():
    return journal.format_daily()

def get_weekly_summary():
    return journal.format_weekly()
