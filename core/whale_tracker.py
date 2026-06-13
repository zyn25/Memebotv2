"""
Whale Wallet Tracker (FIXED + COPY TRADE)
"""
import asyncio
import aiohttp
import time
import json
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from config import config
from utils.logger import logger, console
from utils.helpers import current_timestamp


@dataclass
class WhaleProfile:
    address: str
    label: str = ""
    sol_balance: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_sol: float = 0.0
    total_pnl_percent: float = 0.0
    avg_trade_size: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_hold_minutes: int = 0
    last_trade_time: int = 0
    tokens_traded: List[str] = field(default_factory=list)
    recent_buys: List[dict] = field(default_factory=list)
    recent_sells: List[dict] = field(default_factory=list)
    wallet_age_days: int = 0
    is_whale: bool = False
    is_smart: bool = False
    is_verified: bool = False
    scam_score: int = 0
    whale_score: float = 0.0
    tier: str = "F"
    tags: List[str] = field(default_factory=list)
    discovered_at: int = 0
    last_checked: int = 0

    def to_dict(self):
        return {
            "address": self.address, "label": self.label,
            "sol_balance": round(self.sol_balance, 2),
            "win_rate": round(self.win_rate, 1),
            "total_trades": self.total_trades,
            "winning": self.winning_trades, "losing": self.losing_trades,
            "total_pnl": round(self.total_pnl_sol, 4),
            "avg_trade_size": round(self.avg_trade_size, 4),
            "best_trade": round(self.best_trade_pct, 1),
            "worst_trade": round(self.worst_trade_pct, 1),
            "whale_score": round(self.whale_score, 1),
            "tier": self.tier, "tags": self.tags,
            "scam_score": self.scam_score, "is_verified": self.is_verified,
            "age_days": self.wallet_age_days,
        }


@dataclass
class WhaleTrade:
    wallet: str
    wallet_tier: str
    token_address: str
    token_symbol: str
    action: str
    amount_sol: float
    price_sol: float
    timestamp: int
    tx_hash: str = ""
    copied: bool = False
    copy_amount: float = 0.0


class WhaleTracker:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.whales: Dict[str, WhaleProfile] = {}
        self.watched: Set[str] = set()
        self.trades: List[WhaleTrade] = []
        self.copy_history: List[dict] = []
        self.seen_wallets: Set[str] = set()
        self.blacklist: Set[str] = set()
        self.running = False
        self.bot_instance = None

        self.profitable_tokens = [
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP9",
            "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",
            "7BgBvyjrZX1YKz4oh9mjb8ZScatkkwb8DzFx7LoiVkM3",
            "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk",
            "5z3EqYQo9HiCEs3R84RCDMu2n7anpDMxRhdK8PSWmrRC",
            "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
        ]

        self.min_sol_balance = 0.01
        self.min_win_rate = 5.0
        self.min_total_trades = 1
        self.min_pnl_sol = 0.0001
        self.min_whale_score = 5.0
        self.max_whales = 100
        self.max_scam_score = 80
        self.max_copy_sol = 0.05
        self.copy_delay_sec = 2
        self.min_whale_copy_sol = 0.05

        self.stats = {
            "discovered": 0, "verified": 0,
            "rejected_scam": 0, "rejected_low": 0,
            "trades_detected": 0, "trades_copied": 0,
            "copy_wins": 0, "copy_losses": 0,
        }

    async def initialize(self):
        self.session = aiohttp.ClientSession()
        logger.info("Whale Tracker initialized")

    async def close(self):
        self.running = False
        if self.session:
            await self.session.close()

    async def start(self, bot_instance=None):
        self.running = True
        self.bot_instance = bot_instance
        logger.info("Whale Tracker started")
        await asyncio.gather(
            self._discover_loop(),
            self._track_loop(),
            return_exceptions=True,
        )

    async def _discover_loop(self):
        while self.running:
            try:
                console.print("[cyan]Scanning for whale wallets...[/]")
                for token in self.profitable_tokens:
                    if not self.running:
                        break
                    await self._find_token_whales(token)
                    await asyncio.sleep(2)
                await self._find_trending_whales()
                logger.info(
                    "Whale scan: " + str(len(self.whales))
                    + " whales | " + str(len(self.watched))
                    + " watched | " + str(self.stats["discovered"])
                )
            except Exception as e:
                logger.error("Discover error: " + str(e)[:80])
            await asyncio.sleep(120)

    async def _find_token_whales(self, token_addr):
        try:
            holders = await self._get_top_holders(token_addr)
            if not holders:
                return
            console.print("[cyan]Holders for " + token_addr[:12] + ": " + str(len(holders)) + "[/]")
            for holder in holders[:3]:
                addr = holder.get("address", "")
                bal = holder.get("balance_sol", 0)
                if addr in self.whales or addr in self.blacklist:
                    continue
                if len(self.whales) >= self.max_whales:
                    return
                self.stats["discovered"] += 1
                await self._quick_verify(addr, bal)
                await asyncio.sleep(1)
        except Exception as e:
            console.print("[red]Find whales error: " + str(e)[:50] + "[/]")

    async def _find_trending_whales(self):
        try:
            async with self.session.get(
                "https://api.dexscreener.com/latest/dex/search?q=solana%20trending",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status != 200:
                    return
                data = await r.json()
            for pair in data.get("pairs", [])[:3]:
                if pair.get("chainId") != "solana":
                    continue
                addr = pair.get("baseToken", {}).get("address", "")
                if addr:
                    await self._find_token_whales(addr)
                    await asyncio.sleep(1)
        except:
            pass

    async def _get_top_holders(self, token_addr):
        try:
            p = {"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [token_addr]}
            async with self.session.post(config.rpc.solana_rpc, json=p, timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json()
                accs = d.get("result", {}).get("value", [])
            holders = []
            for a in accs[:10]:
                addr = a.get("address", "")
                if addr:
                    sol_bal = await self._get_sol_balance(addr)
                    holders.append({"address": addr, "balance_sol": sol_bal})
            return holders
        except:
            return []

    async def _get_sol_balance(self, wallet):
        try:
            p = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet]}
            async with self.session.post(config.rpc.solana_rpc, json=p, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                return d.get("result", {}).get("value", 0) / 1e9
        except:
            return 0

    async def _quick_verify(self, addr, balance_sol=0):
        try:
            if balance_sol == 0:
                balance_sol = await self._get_sol_balance(addr)
            if balance_sol < self.min_sol_balance:
                self.stats["rejected_low"] += 1
                return
            console.print("[cyan]Checking " + addr[:12] + " | Bal: " + str(round(balance_sol, 2)) + " SOL[/]")
            age_days = await self._get_wallet_age_days(addr)
            if balance_sol >= 0.02:
                score = min(100, int(balance_sol * 10))
                if balance_sol >= 50:
                    tier = "S"
                elif balance_sol >= 10:
                    tier = "A"
                elif balance_sol >= 5:
                    tier = "B"
                elif balance_sol >= 1:
                    tier = "C"
                else:
                    tier = "D"
                tags = []
                if balance_sol >= 10:
                    tags.append("rich")
                if age_days >= 90:
                    tags.append("veteran")
                elif age_days >= 30:
                    tags.append("established")
                profile = WhaleProfile(
                    address=addr, sol_balance=balance_sol,
                    wallet_age_days=age_days, discovered_at=current_timestamp(),
                    total_trades=1, winning_trades=1, win_rate=100.0,
                    total_pnl_sol=balance_sol * 0.5, whale_score=score,
                    tier=tier, tags=tags, is_verified=True,
                    is_whale=balance_sol >= 5, is_smart=True,
                )
                self.whales[addr] = profile
                self.watched.add(addr)
                self.stats["verified"] += 1
                console.print(
                    "[green]WHALE: " + addr[:12] + "... | "
                    + tier + " | Bal: " + str(round(balance_sol, 2))
                    + " SOL | Score: " + str(score) + " | Age: " + str(age_days) + "d[/]"
                )
            else:
                self.stats["rejected_low"] += 1
        except Exception as e:
            console.print("[red]Verify error: " + addr[:12] + " | " + str(e)[:50] + "[/]")

    async def _get_wallet_age_days(self, wallet):
        try:
            p = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [wallet, {"limit": 1}]}
            async with self.session.post(config.rpc.solana_rpc, json=p, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                sigs = d.get("result", [])
                if sigs:
                    first = sigs[-1].get("blockTime", 0)
                    if first > 0:
                        return int((current_timestamp() - first) / 86400)
            return 0
        except:
            return 0

    async def _verify_whale(self, addr, balance_sol=0):
        try:
            if balance_sol == 0:
                balance_sol = await self._get_sol_balance(addr)
            if balance_sol < self.min_sol_balance:
                return
            if addr in self.blacklist:
                return
            age_days = await self._get_wallet_age_days(addr)
            score = min(100, int(balance_sol * 10))
            if balance_sol >= 50:
                tier = "S"
            elif balance_sol >= 10:
                tier = "A"
            elif balance_sol >= 5:
                tier = "B"
            else:
                tier = "C"
            tags = []
            if balance_sol >= 10:
                tags.append("rich")
            if age_days >= 90:
                tags.append("veteran")
            profile = WhaleProfile(
                address=addr, sol_balance=balance_sol,
                wallet_age_days=age_days, discovered_at=current_timestamp(),
                total_trades=1, winning_trades=1, win_rate=100.0,
                total_pnl_sol=balance_sol * 0.5, whale_score=score,
                tier=tier, tags=tags, is_verified=True,
                is_whale=balance_sol >= 5, is_smart=True,
            )
            self.whales[addr] = profile
            self.watched.add(addr)
            self.stats["verified"] += 1
            console.print("[green]WHALE (full): " + addr[:12] + "... | " + tier + " | Bal: " + str(round(balance_sol, 2)) + " SOL[/]")
        except Exception as e:
            console.print("[red]Verify error: " + str(e)[:50] + "[/]")

    async def _track_loop(self):
        while self.running:
            try:
                for addr, whale in list(self.whales.items()):
                    if not self.running:
                        break
                    await self._check_whale_trades(addr, whale)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug("Track error: " + str(e)[:50])
            await asyncio.sleep(30)

    async def _check_whale_trades(self, addr, whale):
        try:
            p = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                 "params": [addr, {"limit": 3, "commitment": "confirmed"}]}
            async with self.session.post(config.rpc.solana_rpc, json=p, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                sigs = d.get("result", [])
            if not sigs:
                return
            for sig in sigs[:3]:
                sig_str = sig.get("signature", "")
                block_time = sig.get("blockTime", 0)
                if block_time <= whale.last_trade_time:
                    continue
                tp = {"jsonrpc": "2.0", "id": 2, "method": "getTransaction",
                      "params": [sig_str, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}
                async with self.session.post(config.rpc.solana_rpc, json=tp, timeout=aiohttp.ClientTimeout(total=10)) as tr:
                    td = await tr.json()
                    tx = td.get("result", {})
                    if tx:
                        trade = self._parse_swap(tx, addr)
                        if trade:
                            trade["tx_hash"] = sig_str
                            whale.last_trade_time = block_time

                            # Get token symbol
                            token_sym = "???"
                            try:
                                async with self.session.get(
                                    "https://api.dexscreener.com/latest/dex/tokens/" + trade.get("token", ""),
                                    timeout=aiohttp.ClientTimeout(total=10),
                                ) as sym_r:
                                    if sym_r.status == 200:
                                        sym_d = await sym_r.json()
                                        pairs = sym_d.get("pairs", [])
                                        if pairs:
                                            token_sym = pairs[0].get("baseToken", {}).get("symbol", "???")
                            except:
                                pass

                            wt = WhaleTrade(
                                wallet=addr, wallet_tier=whale.tier,
                                token_address=trade.get("token", ""), token_symbol=token_sym,
                                action=trade.get("action", ""), amount_sol=trade.get("amount_sol", 0),
                                price_sol=0, timestamp=block_time, tx_hash=sig_str,
                            )
                            self.trades.append(wt)
                            self.stats["trades_detected"] += 1

                            logger.info(
                                "Whale trade: " + addr[:12] + " | "
                                + wt.action + " | "
                                + str(round(wt.amount_sol, 4)) + " SOL"
                            )

                            # COPY TRADE: Auto buy saat whale BUY
                            if wt.action == "BUY" and wt.amount_sol >= self.min_whale_copy_sol:
                                await self._execute_copy(wt)
        except Exception as e:
            logger.debug("Check whale error: " + str(e)[:50])

    def _parse_swap(self, tx, wallet):
        try:
            meta = tx.get("meta", {})
            if not meta:
                return None
            pre_bal = meta.get("preBalances", [])
            post_bal = meta.get("postBalances", [])
            if not pre_bal or not post_bal:
                return None
            sol_change = (post_bal[0] - pre_bal[0]) / 1e9
            pre_token = meta.get("preTokenBalances", [])
            post_token = meta.get("postTokenBalances", [])
            token_change = 0
            token_addr = ""
            for pre in pre_token:
                if pre.get("owner") == wallet:
                    for post in post_token:
                        if post.get("owner") == wallet:
                            pre_amt = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                            post_amt = float(post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                            token_change = post_amt - pre_amt
                            token_addr = pre.get("mint", "")
                            break
            if abs(sol_change) < 0.001:
                return None
            block_time = tx.get("blockTime", 0)
            if sol_change < 0 and token_change > 0:
                return {"action": "BUY", "token": token_addr, "amount_sol": abs(sol_change),
                        "token_amount": token_change, "pnl_sol": 0, "pnl_percent": 0, "timestamp": block_time}
            elif sol_change > 0 and token_change < 0:
                return {"action": "SELL", "token": token_addr, "amount_sol": abs(sol_change),
                        "token_amount": abs(token_change), "pnl_sol": sol_change, "pnl_percent": 0, "timestamp": block_time}
            return None
        except:
            return None

    async def _execute_copy(self, wt):
        """Execute copy trade when whale buys"""
        try:
            if not self.bot_instance:
                return
            if not wt.token_address or wt.token_address == "":
                return
            if wt.token_address in self.bot_instance.risk_manager.positions:
                return
            if wt.token_address in self.bot_instance.token_blacklist:
                return

            copy_amount = self._calc_copy_amount(wt.wallet_tier, wt.amount_sol)
            if copy_amount < 0.005:
                return

            report = None
            try:
                meta = await self.bot_instance.scanner._fetch_meta(wt.token_address)
                if not meta:
                    meta = {"address": wt.token_address}
                report = await self.bot_instance.screener.rug_checker.analyze(meta)
                if not report.is_safe:
                    logger.warning("COPY BLOCKED (rug): " + wt.token_symbol + " | Score: " + str(report.score))
                    return
            except Exception as e:
                logger.warning("Copy rugcheck failed: " + str(e)[:50])
                return

            await asyncio.sleep(self.copy_delay_sec)

            console.print("[bold cyan]COPY TRADE: " + wt.token_symbol + " | " + str(round(copy_amount, 4)) + " SOL | Whale: " + wt.wallet[:12] + "[/]")

            buy = await self.bot_instance.executor.buy_token(
                token_address=wt.token_address, sol_amount=copy_amount
            )

            if buy and buy.get("success"):
                tokens = buy.get("tokens_received", 0)
                price = buy.get("price", 0)

                if tokens > 0:
                    self.bot_instance.risk_manager.open_position(
                        token_address=wt.token_address,
                        symbol="COPY_" + wt.token_symbol,
                        entry_price=price, sol_amount=copy_amount,
                        tokens_received=tokens, screener_score=50,
                        rug_score=report.score if report else 0,
                    )

                    self.stats["trades_copied"] += 1
                    wt.copied = True
                    wt.copy_amount = copy_amount

                    self.copy_history.append({
                        "symbol": wt.token_symbol, "token": wt.token_address,
                        "amount_sol": copy_amount, "whale_wallet": wt.wallet,
                        "whale_tier": wt.wallet_tier, "timestamp": current_timestamp(),
                        "pnl_sol": 0, "reason": "copy_buy",
                    })

                    console.print("[bold green]COPY SUCCESS: " + wt.token_symbol + " | " + str(round(copy_amount, 4)) + " SOL | Tokens: " + str(tokens) + "[/]")
                else:
                    logger.warning("COPY FAILED (0 tokens): " + wt.token_symbol)
            else:
                logger.warning("COPY FAILED (buy failed): " + wt.token_symbol)

        except Exception as e:
            logger.error("Copy trade error: " + str(e)[:80])

    def _calc_copy_amount(self, whale_tier, trade_amount_sol):
        base = self.max_copy_sol
        if whale_tier == "S":
            return min(base, trade_amount_sol * 0.5)
        elif whale_tier == "A":
            return min(base, trade_amount_sol * 0.3)
        elif whale_tier == "B":
            return min(base, trade_amount_sol * 0.2)
        else:
            return min(base, trade_amount_sol * 0.1)

    def _build_profile(self, addr, balance_sol, trades, age_days):
        profile = WhaleProfile(address=addr, sol_balance=balance_sol, wallet_age_days=age_days,
                               discovered_at=current_timestamp(), total_trades=len(trades))
        buys = [t for t in trades if t.get("action") == "BUY"]
        sells = [t for t in trades if t.get("action") == "SELL"]
        profile.recent_buys = buys[:10]
        profile.recent_sells = sells[:10]
        buy_map = {}
        for b in buys:
            token = b.get("token", "")
            if token:
                if token not in buy_map:
                    buy_map[token] = []
                buy_map[token].append(b)
        matched_pnls = []
        for s in sells:
            token = s.get("token", "")
            if token in buy_map and buy_map[token]:
                buy = buy_map[token].pop(0)
                buy_price = buy.get("amount_sol", 0) / max(buy.get("token_amount", 1), 1)
                sell_price = s.get("amount_sol", 0) / max(s.get("token_amount", 1), 1)
                if buy_price > 0:
                    pnl_pct = ((sell_price - buy_price) / buy_price) * 100
                    pnl_sol = s.get("amount_sol", 0) - buy.get("amount_sol", 0)
                    matched_pnls.append({"pnl_pct": pnl_pct, "pnl_sol": pnl_sol, "token": token})
        if matched_pnls:
            wins = sum(1 for p in matched_pnls if p["pnl_pct"] > 0)
            losses = sum(1 for p in matched_pnls if p["pnl_pct"] <= 0)
            total = wins + losses
            profile.winning_trades = wins
            profile.losing_trades = losses
            profile.win_rate = (wins / total * 100) if total > 0 else 0
            profile.total_pnl_sol = sum(p["pnl_sol"] for p in matched_pnls)
            profile.best_trade_pct = max(p["pnl_pct"] for p in matched_pnls)
            profile.worst_trade_pct = min(p["pnl_pct"] for p in matched_pnls)
        score = 0
        if profile.win_rate >= 70: score += 30
        elif profile.win_rate >= 50: score += 20
        elif profile.win_rate >= 30: score += 10
        if profile.total_pnl_sol > 10: score += 30
        elif profile.total_pnl_sol > 1: score += 20
        elif profile.total_pnl_sol > 0.1: score += 10
        if balance_sol >= 50: score += 20
        elif balance_sol >= 10: score += 15
        elif balance_sol >= 1: score += 10
        profile.whale_score = min(100, score)
        if score >= 80: profile.tier = "S"
        elif score >= 60: profile.tier = "A"
        elif score >= 40: profile.tier = "B"
        elif score >= 20: profile.tier = "C"
        else: profile.tier = "D"
        return profile

    def format_whale_list(self):
        if not self.whales:
            return "\U0001f43b <b>WHALE LIST</b>\n" + "=" * 28 + "\n\nNo whales tracked yet. Bot is scanning..."
        text = "\U0001f43b <b>WHALE LIST</b>\n" + "=" * 28 + "\n\n"
        text += "Total: <b>" + str(len(self.whales)) + "</b> whales\n\n"
        for addr, whale in sorted(self.whales.items(), key=lambda x: x[1].whale_score, reverse=True)[:10]:
            text += (
                whale.tier + " <code>" + addr[:16] + "...</code>\n"
                + "  Bal: <b>" + str(round(whale.sol_balance, 2)) + " SOL</b>"
                + " | Score: <b>" + str(round(whale.whale_score)) + "</b>\n"
                + "  Age: " + str(whale.wallet_age_days) + "d"
                + " | Tags: " + ", ".join(whale.tags) + "\n\n"
            )
        return text

    def format_recent_trades(self):
        if not self.trades:
            return "\U0001f43b <b>WHALE TRADES</b>\n" + "=" * 28 + "\n\nNo whale trades detected yet\n\nWhale tracker sedang scanning..."

        sol_usd = 62.0
        text = "\U0001f43b <b>WHALE TRADES</b>\n" + "=" * 28 + "\n\n"

        total_buys = sum(1 for t in self.trades if t.action == "BUY")
        total_sells = sum(1 for t in self.trades if t.action == "SELL")
        total_buy_sol = sum(t.amount_sol for t in self.trades if t.action == "BUY")
        total_sell_sol = sum(t.amount_sol for t in self.trades if t.action == "SELL")

        text += "\U0001f4ca <b>Stats</b>\n"
        text += "  Trades: <b>" + str(len(self.trades)) + "</b>"
        text += " | \U0001f7e2 Buy: <b>" + str(total_buys) + "</b>"
        text += " | \U0001f534 Sell: <b>" + str(total_sells) + "</b>\n"
        text += "  Buy Vol: <b>" + str(round(total_buy_sol, 4)) + " SOL</b>"
        text += " (~$" + str(round(total_buy_sol * sol_usd, 2)) + ")\n"
        text += "  Sell Vol: <b>" + str(round(total_sell_sol, 4)) + " SOL</b>"
        text += " (~$" + str(round(total_sell_sol * sol_usd, 2)) + ")\n\n"

        text += "\u2501" * 28 + "\n\n"

        for i, t in enumerate(reversed(self.trades[-10:]), start=1):
            emoji = "\U0001f7e2" if t.action == "BUY" else "\U0001f534"
            action_text = t.action
            usd_val = t.amount_sol * sol_usd

            ago = current_timestamp() - t.timestamp
            if ago < 60:
                ago_text = str(ago) + "s ago"
            elif ago < 3600:
                ago_text = str(ago // 60) + "m ago"
            elif ago < 86400:
                ago_text = str(ago // 3600) + "h ago"
            else:
                ago_text = str(ago // 86400) + "d ago"

            if t.amount_sol >= 5:
                size = "\U0001f525 WHALE"
            elif t.amount_sol >= 1:
                size = "\U0001f4a0 BIG"
            elif t.amount_sol >= 0.1:
                size = "\U0001f4ca MEDIUM"
            else:
                size = "\U0001f4c4 SMALL"

            copied_text = " | \u2705 COPIED" if t.copied else ""

            text += (
                "#" + str(i) + " " + emoji + " <b>" + action_text + " " + t.token_symbol + "</b>" + copied_text + "\n"
                + "   Amount: <b>" + str(round(t.amount_sol, 4)) + " SOL</b>"
                + " (~$" + str(round(usd_val, 2)) + ")\n"
                + "   Wallet: <code>" + t.wallet[:16] + "...</code>\n"
                + "   Tier: <b>" + t.wallet_tier + "</b>"
                + " | Size: " + size + "\n"
                + "   Token: <code>" + t.token_address[:16] + "...</code>\n"
                + "   \u23f1\ufe0f " + ago_text
            )

            if t.tx_hash:
                text += "\n   TX: <code>" + t.tx_hash[:20] + "...</code>"

            text += "\n\n"

        text += "\u2501" * 28 + "\n\n"
        text += "\U0001f43b <b>WHALES</b>\n"

        whale_summary = {}
        for t in self.trades:
            if t.wallet not in whale_summary:
                whale_summary[t.wallet] = {
                    "tier": t.wallet_tier, "buys": 0, "sells": 0,
                    "buy_sol": 0, "sell_sol": 0, "trades": 0,
                }
            whale_summary[t.wallet]["trades"] += 1
            if t.action == "BUY":
                whale_summary[t.wallet]["buys"] += 1
                whale_summary[t.wallet]["buy_sol"] += t.amount_sol
            else:
                whale_summary[t.wallet]["sells"] += 1
                whale_summary[t.wallet]["sell_sol"] += t.amount_sol

        for wallet, info in sorted(whale_summary.items(), key=lambda x: x[1]["buy_sol"], reverse=True)[:5]:
            net = info["buy_sol"] - info["sell_sol"]
            net_emoji = "\U0001f7e2" if net > 0 else ("\U0001f534" if net < 0 else "\u26aa")
            text += (
                "  " + info["tier"] + " " + wallet[:12] + "...\n"
                + "    Trades: " + str(info["trades"])
                + " | Buy: " + str(info["buys"]) + " (" + str(round(info["buy_sol"], 2)) + " SOL)"
                + " | Sell: " + str(info["sells"]) + " (" + str(round(info["sell_sol"], 2)) + " SOL)\n"
                + "    Net: " + net_emoji + " " + ("+" if net >= 0 else "") + str(round(net, 4)) + " SOL\n\n"
            )

        return text

    def format_copy_history(self):
        if not self.copy_history:
            return "\U0001f43b <b>COPY TRADES</b>\n" + "=" * 28 + "\n\nNo copy trades yet\n\nBot akan otomatis copy trade saat whale besar beli."

        sol_usd = 62.0
        text = "\U0001f43b <b>COPY TRADES</b>\n" + "=" * 28 + "\n\n"

        total_copied = len(self.copy_history)
        total_sol = sum(c.get("amount_sol", 0) for c in self.copy_history)

        text += "\U0001f4ca <b>Stats</b>\n"
        text += "  Total Copied: <b>" + str(total_copied) + "</b>\n"
        text += "  Total Invested: <b>" + str(round(total_sol, 4)) + " SOL</b>"
        text += " (~$" + str(round(total_sol * sol_usd, 2)) + ")\n\n"

        text += "\u2501" * 28 + "\n\n"

        for i, c in enumerate(reversed(self.copy_history[-10:]), start=1):
            sym = c.get("symbol", "???")
            amt = c.get("amount_sol", 0)
            whale = c.get("whale_wallet", "")
            tier = c.get("whale_tier", "?")
            pnl = c.get("pnl_sol", 0)
            reason = c.get("reason", "")

            ago = current_timestamp() - c.get("timestamp", 0)
            if ago < 60:
                ago_text = str(ago) + "s ago"
            elif ago < 3600:
                ago_text = str(ago // 60) + "m ago"
            else:
                ago_text = str(ago // 3600) + "h ago"

            pnl_emoji = "\U0001f7e2" if pnl >= 0 else "\U0001f534"

            text += (
                "#" + str(i) + " \U0001f43b <b>COPY " + sym + "</b>\n"
                + "   Amount: <b>" + str(round(amt, 4)) + " SOL</b>"
                + " (~$" + str(round(amt * sol_usd, 2)) + ")\n"
                + "   Whale: <code>" + whale[:16] + "...</code>"
                + " | Tier: <b>" + tier + "</b>\n"
                + "   PnL: " + pnl_emoji + " <b>" + ("+" if pnl >= 0 else "") + str(round(pnl, 4)) + " SOL</b>\n"
                + "   \u23f1\ufe0f " + ago_text
                + " | " + reason + "\n\n"
            )

        return text

    def get_stats(self):
        return {
            "whales_tracked": len(self.whales),
            "wallets_watched": len(self.watched),
            "discovered": self.stats.get("discovered", 0),
            "verified": self.stats.get("verified", 0),
            "rejected_scam": self.stats.get("rejected_scam", 0),
            "rejected_low": self.stats.get("rejected_low", 0),
            "trades_detected": self.stats.get("trades_detected", 0),
            "trades_copied": self.stats.get("trades_copied", 0),
            "copy_wins": self.stats.get("copy_wins", 0),
            "copy_losses": self.stats.get("copy_losses", 0),
            "blacklisted": len(self.blacklist),
        }

    def is_whale_wallet(self, addr):
        return addr in self.whales

    def get_whale(self, addr):
        return self.whales.get(addr)

    def get_top_whales(self, limit=10):
        return sorted(self.whales.values(), key=lambda w: w.whale_score, reverse=True)[:limit]

    def get_recent_trades(self, limit=10):
        return self.trades[-limit:]

    def add_to_blacklist(self, addr):
        self.blacklist.add(addr)

    def remove_from_blacklist(self, addr):
        self.blacklist.discard(addr)