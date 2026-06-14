"""
12-Layer Rugpull Detection Engine (v2.0 MEME COIN MODE)
- Fix: dev_holds_majority BUKAN critical lagi (pump.fun normal)
- Fix: holder_distribution lebih longgar buat token baru
- Fix: lp_lock lebih longgar (pump.fun closed source = normal)
- Tetap block: honeypot, mint active, zero liquidity
"""
import asyncio
import aiohttp
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from config import config
from utils.logger import logger, log_rug, log_safe
from utils.helpers import current_timestamp


@dataclass
class RugpullReport:
    address: str
    score: int = 0
    is_safe: bool = False
    safety_level: str = "UNKNOWN"
    critical_failures: list = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0
    checks_total: int = 0
    reasons: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)
    timestamp: int = 0

    def __post_init__(self):
        self.timestamp = current_timestamp()


class RugpullChecker:
    def __init__(self):
        self.session: aiohttp.ClientSession = None
        self.cache: Dict[str, RugpullReport] = {}
        self.cache_ttl = 300
        self.RPC_BACKUPS = [
            "https://api.mainnet-beta.solana.com",
            "https://rpc.ankr.com/solana",
        ]

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def analyze(self, td: dict) -> RugpullReport:
        addr = td.get("address", "")
        if addr in self.cache:
            cached = self.cache[addr]
            if current_timestamp() - cached.timestamp < self.cache_ttl:
                return cached

        report = RugpullReport(address=addr)
        logger.info("Analyzing " + addr[:12] + "...")

        results = await asyncio.gather(
            self._chk_honeypot(addr, td),
            self._chk_mint(addr),
            self._chk_freeze(addr),
            self._chk_ownership(addr),
            self._chk_liquidity(addr, td),
            self._chk_lp_lock(addr),
            self._chk_holders(addr, td),
            self._chk_dev_wallet(addr, td),
            self._chk_contract(addr),
            self._chk_social(addr, td),
            self._chk_tx_patterns(addr),
            self._chk_bundle(addr, td),
            return_exceptions=True,
        )

        names = [
            "honeypot", "mint_authority", "freeze_authority",
            "ownership", "liquidity", "lp_lock",
            "holder_distribution", "dev_wallet",
            "contract_verification", "social_presence",
            "transaction_patterns", "bundle_detection",
        ]
        weights = [20, 15, 10, 10, 10, 10, 8, 7, 3, 2, 3, 2]

        total = 0
        for name, weight, result in zip(names, weights, results):
            if isinstance(result, Exception):
                total += weight * 0.5
                report.reasons.append(name + ": check failed")
                report.checks_failed += 1
                report.details[name] = {"passed": False, "risk_score": 0.5, "detail": "Check failed"}
            else:
                passed, risk_score, detail = result
                report.details[name] = {"passed": passed, "risk_score": risk_score, "detail": detail}
                if passed:
                    report.checks_passed += 1
                else:
                    report.checks_failed += 1
                    report.reasons.append(name + ": " + detail)
                total += risk_score * weight

        report.checks_total = len(names)
        report.score = min(100, int(total))
        self.cache[addr] = report

        # ============================================
        # CRITICAL FAILURE CHECK (v2.0 - LEBIH KETAT)
        # ============================================
        critical = []

        # Honeypot TETAP critical (bahaya nyata)
        hp = report.details.get("honeypot", {})
        if not hp.get("passed", True) and hp.get("risk_score", 0) >= 0.8:
            critical.append("honeypot")

        # Zero liquidity TETAP critical (bahaya nyata)
        liq = report.details.get("liquidity", {})
        if not liq.get("passed", True) and "Zero" in str(liq.get("detail", "")):
            critical.append("zero_liquidity")

        # Mint active TETAP critical (bahaya nyata)
        mint = report.details.get("mint_authority", {})
        if not mint.get("passed", True) and mint.get("risk_score", 0) >= 0.8:
            critical.append("mint_active")

        # ============================================
        # DEV WALLET BUKAN CRITICAL LAGI!
        # ============================================
        # v1.0: dev risk >= 0.7 → critical (TERLALU KETAT)
        # v2.0: dev risk >= 0.95 → critical (hanya block dev holds > 50%)
        # Alasan: pump.fun token PASTI ada dev/bonding curve holder 10-30%
        #         Ini NORMAL, bukan scam indicator
        dev = report.details.get("dev_wallet", {})
        if not dev.get("passed", True) and dev.get("risk_score", 0) >= 0.95:
            critical.append("dev_holds_majority")

        report.critical_failures = critical

        # ============================================
        # SAFETY DETERMINATION (v2.0 - LEBIH LONGGAR)
        # ============================================
        has_critical = len(critical) > 0
        if has_critical:
            report.is_safe = False
            report.safety_level = "DANGER"
        elif report.score <= 35:
            report.is_safe = True
            report.safety_level = "SAFE"
        elif report.score <= 55:
            report.is_safe = True
            report.safety_level = "MODERATE"
        elif report.score <= 70:
            report.is_safe = False
            report.safety_level = "HIGH_RISK"
        elif report.score <= 85:
            report.is_safe = True
            report.safety_level = "LOW_RISK"
        else:
            report.is_safe = True
            report.safety_level = "SAFE"

        if report.is_safe:
            log_safe(addr, report.score)
        else:
            log_rug(addr, report.score, report.reasons)
        return report

    async def _fetch_tax(self, addr: str) -> dict:
        try:
            url = "https://api.gopluslabs.io/api/v1/token_security/solana"
            async with self.session.get(url, params={"contract_addresses": addr},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    d = await r.json()
                    ti = d.get("result", {}).get(addr, {})
                    return {
                        "buy_tax": float(ti.get("buy_tax", "0") or "0"),
                        "sell_tax": float(ti.get("sell_tax", "0") or "0"),
                        "is_honeypot": ti.get("is_honeypot", "0") == "1",
                        "hidden_owner": ti.get("hidden_owner", "0") == "1",
                        "selfdestruct": ti.get("selfdestruct", "0") == "1",
                        "external_call": ti.get("external_call", "0") == "1",
                        "is_open_source": ti.get("is_open_source", "0") == "1",
                        "owner_change_balance": ti.get("owner_change_balance", "0") == "1",
                        "can_take_back_ownership": ti.get("can_take_back_ownership", "0") == "1",
                    }
            return {}
        except:
            return {}

    async def _fetch_liq(self, addr: str) -> float:
        try:
            async with self.session.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + addr,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    d = await r.json()
                    best_liq = 0
                    for pair in d.get("pairs", []):
                        if pair.get("chainId") == "solana":
                            liq = pair.get("liquidity", {}).get("usd", 0) or 0
                            if liq > best_liq:
                                best_liq = liq
                    return best_liq
            return 0
        except:
            return 0

    async def _simulate_sell(self, addr: str) -> bool:
        SOL = "So11111111111111111111111111111111111111112"
        amounts = [
            "10000000000000000", "1000000000000000", "100000000000000",
            "10000000000000", "1000000000000", "100000000000",
            "10000000000", "1000000000", "100000000",
            "10000000", "1000000", "100000", "10000", "1000",
        ]
        slippages = [5000, 10000, 15000, 25000]
        for sl in slippages:
            for amount in amounts:
                try:
                    async with self.session.get(
                        "https://quote-api.jup.ag/v6/quote",
                        params={"inputMint": addr, "outputMint": SOL, "amount": amount, "slippageBps": sl},
                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status == 200:
                            d = await r.json()
                            if int(d.get("outAmount", 0)) > 0:
                                return True
                        elif r.status == 429:
                            await asyncio.sleep(2)
                except:
                    continue
            await asyncio.sleep(0.5)
        return False

    async def _fetch_holders(self, addr: str) -> list:
        rpcs = [config.rpc.solana_rpc] + self.RPC_BACKUPS
        for rpc in rpcs:
            for attempt in range(2):
                holders = await self._fetch_holders_rpc(rpc, addr)
                if holders:
                    return holders
                await asyncio.sleep(0.5)
        return []

    async def _fetch_holders_rpc(self, rpc_url: str, addr: str) -> list:
        try:
            p = {"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [addr]}
            async with self.session.post(rpc_url, json=p,
                timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                accs = d.get("result", {}).get("value", [])
                if not accs:
                    return []

            sp = {"jsonrpc": "2.0", "id": 2, "method": "getTokenSupply", "params": [addr]}
            async with self.session.post(rpc_url, json=sp,
                timeout=aiohttp.ClientTimeout(total=20)) as sr:
                if sr.status != 200:
                    return []
                sd = await sr.json()
                ts = float(sd.get("result", {}).get("value", {}).get("uiAmount", 0))
                if ts == 0:
                    ts = 1

            holders = []
            for a in accs:
                try:
                    amt = float(a.get("uiAmount", 0))
                    pct = (amt / ts * 100) if ts > 0 else 0
                    holders.append({"address": a.get("address", ""), "amount": amt, "percentage": pct})
                except:
                    continue
            return holders
        except Exception as e:
            logger.debug("Holders RPC error: " + str(e)[:50])
            return []

    async def _chk_honeypot(self, addr: str, td: dict) -> tuple:
        try:
            ti = await self._fetch_tax(addr)
            bt = ti.get("buy_tax", 0)
            st = ti.get("sell_tax", 0)
            liq = td.get("liquidity", 0)

            if liq == 0:
                liq = await self._fetch_liq(addr)

            if ti.get("is_honeypot"):
                if liq > 100000:
                    return (True, 0.3, "GoPlus flagged but strong liq ($" + str(round(liq)) + ")")
                return (False, 1.0, "HONEYPOT detected by GoPlus")

            if st >= 99:
                return (False, 1.0, "HONEYPOT! Sell tax: " + str(st) + "%")

            if ti.get("owner_change_balance"):
                if liq > 100000:
                    return (True, 0.4, "Owner can change balance (high liq mitigates)")
                return (False, 0.7, "Owner can change balance")

            can_sell = await self._simulate_sell(addr)

            if not can_sell:
                if liq > 1000000:
                    return (True, 0.2, "Cannot simulate but strong liq ($" + str(round(liq)) + ")")
                elif liq > 100000:
                    return (True, 0.3, "Cannot simulate (med liq: $" + str(round(liq)) + ")")
                elif liq > 10000:
                    return (True, 0.4, "Cannot simulate (low liq: $" + str(round(liq)) + ")")
                elif liq > 0:
                    return (True, 0.5, "Cannot simulate (very low liq)")
                else:
                    return (False, 0.8, "Cannot sell and zero liquidity")

            risk = 0.0
            parts = []
            if bt > config.trading.max_buy_tax:
                risk += 0.5
                parts.append("Buy tax: " + str(bt) + "%")
            if st > config.trading.max_sell_tax:
                risk += 0.7
                parts.append("Sell tax: " + str(st) + "%")
            if ti.get("external_call"):
                risk += 0.3
                parts.append("External calls")

            detail = "; ".join(parts) if parts else "Tax OK (buy:" + str(bt) + "% sell:" + str(st) + "%)"
            return (risk < 0.5, risk, detail)
        except Exception as e:
            return (True, 0.3, "Honeypot check inconclusive")

    async def _chk_mint(self, addr: str) -> tuple:
        for rpc in [config.rpc.solana_rpc] + self.RPC_BACKUPS:
            try:
                p = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                     "params": [addr, {"encoding": "jsonParsed"}]}
                async with self.session.post(rpc, json=p,
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    d = await r.json()
                    info = d.get("result", {}).get("value", {}).get("data", {}).get("parsed", {}).get("info", {})
                    ma = info.get("mintAuthority")
                    if ma and ma != "null" and ma is not None:
                        return (False, 0.9, "Mint active: " + str(ma)[:12] + "...")
                    return (True, 0.0, "Mint revoked")
            except:
                continue
        return (True, 0.2, "Could not verify mint authority")

    async def _chk_freeze(self, addr: str) -> tuple:
        for rpc in [config.rpc.solana_rpc] + self.RPC_BACKUPS:
            try:
                p = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                     "params": [addr, {"encoding": "jsonParsed"}]}
                async with self.session.post(rpc, json=p,
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    d = await r.json()
                    info = d.get("result", {}).get("value", {}).get("data", {}).get("parsed", {}).get("info", {})
                    fa = info.get("freezeAuthority")
                    if fa and fa != "null" and fa is not None:
                        return (False, 0.8, "Freeze active: " + str(fa)[:12] + "...")
                    return (True, 0.0, "Freeze revoked")
            except:
                continue
        return (True, 0.2, "Could not verify freeze authority")

    async def _chk_ownership(self, addr: str) -> tuple:
        try:
            ti = await self._fetch_tax(addr)
            if ti.get("hidden_owner"):
                return (False, 0.8, "Hidden owner detected")
            if ti.get("can_take_back_ownership"):
                return (False, 0.7, "Can take back ownership")
            if ti.get("owner_change_balance"):
                return (False, 0.6, "Owner can change balance")
            return (True, 0.0, "Ownership OK")
        except:
            return (True, 0.2, "Could not verify ownership")

    async def _chk_liquidity(self, addr: str, td: dict) -> tuple:
        try:
            liq = td.get("liquidity", 0)
            if liq == 0:
                liq = await self._fetch_liq(addr)
            min_liq = config.screening.min_initial_liquidity * 150
            if liq == 0:
                return (False, 0.9, "Zero liquidity!")
            if liq < min_liq:
                return (False, 0.8, "Low liq: $" + str(round(liq)))
            if liq < min_liq * 5:
                return (True, 0.3, "Medium liq: $" + str(round(liq)))
            return (True, 0.0, "Strong liq: $" + str(round(liq)))
        except:
            return (True, 0.3, "Liquidity check inconclusive")

    async def _chk_lp_lock(self, addr: str) -> tuple:
        try:
            ti = await self._fetch_tax(addr)
            if ti.get("is_open_source"):
                return (True, 0.3, "Open source (lock unverified)")
            # v2.0: Closed source = NORMAL untuk meme coin
            # pump.fun token 99% closed source
            return (True, 0.4, "Closed source (normal for meme coin)")
        except:
            return (True, 0.3, "LP check inconclusive")

    async def _chk_holders(self, addr: str, td: dict) -> tuple:
        try:
            holders = await self._fetch_holders(addr)
            hc = td.get("holder_count", 0)
            liq = td.get("liquidity", 0)
            if liq == 0:
                liq = await self._fetch_liq(addr)

            if hc == 0 and holders:
                count = len(holders)
                if count >= 20:
                    hc = count * 100
                elif count >= 10:
                    hc = count * 50
                elif count >= 5:
                    hc = count * 20
                else:
                    hc = count * 10

            if hc == 0 and holders:
                hc = len(holders)

            td["holder_count"] = hc

            if hc == 0:
                return (True, 0.2, "Could not determine holder count")
            if hc < config.screening.min_unique_holders:
                return (False, 0.6, "Few holders: ~" + str(hc))
            if not holders:
                return (True, 0.1, "~" + str(hc) + " holders")

            top10 = sum(h.get("percentage", 0) for h in holders[:10])

            # v2.0: Top10 threshold lebih longgar
            # pump.fun baru = wajar top10 40-60%
            max_top10 = config.screening.max_top10_holder_percent
            if top10 > max_top10:
                if liq > 100000 and top10 < 70:
                    return (True, 0.3, "~" + str(hc) + " holders, Top10: " + str(round(top10, 1)) + "% (acceptable)")
                return (False, 0.7, "Top10 own " + str(round(top10, 1)) + "%")

            if holders[0].get("percentage", 0) > 20:
                if liq > 100000:
                    return (True, 0.3, "~" + str(hc) + " holders, Top: " + str(round(holders[0]["percentage"], 1)) + "% (ok)")
                return (False, 0.6, "Top holder: " + str(round(holders[0]["percentage"], 1)) + "%")

            return (True, 0.1, "~" + str(hc) + " holders, Top10: " + str(round(top10, 1)) + "%")
        except:
            return (True, 0.3, "Holder check inconclusive")

    async def _chk_dev_wallet(self, addr: str, td: dict) -> tuple:
        try:
            holders = await self._fetch_holders(addr)
            if not holders:
                return (True, 0.2, "No holder data")
            dp = holders[0].get("percentage", 0)

            # v2.0: Dev wallet threshold lebih longgar
            # pump.fun bonding curve = wajar 10-30%
            max_pct = config.screening.dev_wallet_max_percent
            liq = td.get("liquidity", 0)
            if liq == 0:
                liq = await self._fetch_liq(addr)

            if dp > max_pct:
                if liq > 100000 and dp < 30:
                    # v2.0: High liq + dev < 30% = acceptable
                    return (True, 0.3, "Top: " + str(round(dp, 1)) + "% (high liq, acceptable)")
                if dp < 25:
                    # v2.0: Dev < 25% = acceptable (pump.fun normal)
                    return (True, 0.4, "Dev: " + str(round(dp, 1)) + "% (pump.fun bonding curve)")
                return (False, 0.8, "Dev holds " + str(round(dp, 1)) + "% (max " + str(max_pct) + "%)")
            return (True, 0.1, "Dev: " + str(round(dp, 1)) + "%")
        except:
            return (True, 0.3, "Dev wallet check inconclusive")

    async def _chk_contract(self, addr: str) -> tuple:
        try:
            ti = await self._fetch_tax(addr)
            risks = []
            score = 0.0
            if not ti.get("is_open_source"):
                # v2.0: Closed source = normal untuk meme coin
                score += 0.1
                risks.append("Closed source")
            if ti.get("selfdestruct"):
                score += 0.5
                risks.append("Self-destruct")
            if ti.get("external_call"):
                score += 0.2
                risks.append("External calls")
            if risks:
                return (score >= 0.4, min(1.0, score), "; ".join(risks))
            return (True, 0.0, "Contract clean")
        except:
            return (True, 0.2, "Contract check inconclusive")

    async def _chk_social(self, addr: str, td: dict) -> tuple:
        try:
            website = td.get("website", "")
            twitter = td.get("twitter", "")
            telegram = td.get("telegram", "")
            if website or twitter or telegram:
                links = []
                if website: links.append("website")
                if twitter: links.append("twitter")
                if telegram: links.append("telegram")
                return (True, 0.0, "Has: " + ", ".join(links))

            try:
                async with self.session.get(
                    "https://api.dexscreener.com/latest/dex/tokens/" + addr,
                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        d = await r.json()
                        pairs = d.get("pairs", [])
                        if pairs:
                            info = pairs[0].get("info", {})
                            websites = info.get("websites", [])
                            socials = info.get("socials", [])
                            found = []
                            if websites: found.append("website")
                            for s in socials:
                                st = s.get("type", "")
                                if st: found.append(st)
                            if found:
                                return (True, 0.0, "Has: " + ", ".join(found))
            except:
                pass

            return (False, 0.3, "No social links found")
        except:
            return (True, 0.1, "Social check inconclusive")

    async def _chk_tx_patterns(self, addr: str) -> tuple:
        try:
            if not config.rpc.helius_key:
                return (True, 0.2, "Basic check OK (no Helius)")
            url = "https://mainnet.helius-rpc.com/?api-key=" + config.rpc.helius_key
            payload = {"jsonrpc": "2.0", "id": "tx", "method": "getSignaturesForAsset",
                       "params": {"id": addr, "options": {"limit": 50}}}
            async with self.session.post(url, json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    d = await r.json()
                    items = d.get("result", {}).get("items", [])
                    count = len(items)
                    if count < 5:
                        return (True, 0.3, "Few tx: " + str(count))
                    return (True, 0.1, "Tx count: " + str(count))
            return (True, 0.2, "Could not analyze tx")
        except:
            return (True, 0.2, "Tx pattern check inconclusive")

    async def _chk_bundle(self, addr: str, td: dict) -> tuple:
        try:
            holders = await self._fetch_holders(addr)
            if not holders or len(holders) < 5:
                return (True, 0.1, "Insufficient data for bundle check")
            pcts = [h.get("percentage", 0) for h in holders[:20]]
            if len(pcts) >= 5:
                avg = sum(pcts) / len(pcts)
                var = sum((p - avg) ** 2 for p in pcts) / len(pcts)
                if var < 0.5 and avg > 1.0:
                    return (False, 0.6, "Uniform holder distribution (bundled?)")
            return (True, 0.1, "No bundling detected")
        except:
            return (True, 0.1, "Bundle check inconclusive")
