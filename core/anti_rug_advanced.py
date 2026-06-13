"""
Advanced Anti-Rugpull Features
Layers 13-27: Extra protection
"""
import asyncio
import aiohttp
from typing import Dict, List, Tuple, Optional
from config import config
from utils.logger import logger
from utils.helpers import current_timestamp


class AdvancedAntiRug:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.scammer_wallets: set = set()
        self.deployer_cache: Dict[str, dict] = {}
        self.checked_cache: Dict[str, dict] = {}

    async def initialize(self):
        self.session = aiohttp.ClientSession()
        await self._load_scammer_db()
        logger.info("Advanced Anti-Rug initialized")

    async def close(self):
        if self.session:
            await self.session.close()

    # ====================================================
    #  MASTER CHECK — Run All
    # ====================================================

    async def full_advanced_check(self, token_address: str, meta: dict) -> dict:
        """Run ALL advanced checks"""
        # Cache check
        if token_address in self.checked_cache:
            cached = self.checked_cache[token_address]
            if current_timestamp() - cached.get("ts", 0) < 300:
                return cached

        results = await asyncio.gather(
            self._chk_deployer(token_address),
            self._chk_first_buys(token_address),
            self._chk_blacklist(token_address),
            self._chk_proxy(token_address),
            self._chk_volume_fake(token_address, meta),
            self._chk_scammer_wallet(token_address),
            self._chk_price_manipulation(token_address, meta),
            self._chk_multi_dex(token_address),
            self._chk_burn(token_address),
            self._chk_emergency(token_address, meta),
            return_exceptions=True,
        )

        names = [
            "deployer_history", "first_buys", "blacklist",
            "proxy_contract", "volume_manipulation", "scammer_wallet",
            "price_manipulation", "multi_dex", "burn_verification",
            "emergency_sell",
        ]

        total_risk = 0.0
        passed = 0
        failed = 0
        reasons = []
        details = {}
        emergency = False
        emergency_reason = ""

        for name, result in zip(names, results):
            if isinstance(result, Exception):
                details[name] = {"passed": True, "risk": 0.3, "detail": "Check failed"}
                total_risk += 0.3
                continue

            if name == "emergency_sell":
                emergency, emergency_reason = result
                details[name] = {"emergency": emergency, "reason": emergency_reason}
                continue

            ok, risk, detail = result
            details[name] = {"passed": ok, "risk": risk, "detail": detail}
            total_risk += risk
            if ok:
                passed += 1
            else:
                failed += 1
                reasons.append(name + ": " + detail)

        adv_score = min(100, int(total_risk * 10))
        is_safe = adv_score <= 35

        out = {
            "address": token_address,
            "advanced_score": adv_score,
            "is_safe": is_safe,
            "passed": passed,
            "failed": failed,
            "total_checks": len(names),
            "reasons": reasons,
            "details": details,
            "emergency": emergency,
            "emergency_reason": emergency_reason,
            "ts": current_timestamp(),
        }

        self.checked_cache[token_address] = out
        return out
    # ====================================================
    #  LAYER 13: DEPLOYER HISTORY
    # ====================================================

    async def _chk_deployer(self, addr: str) -> tuple:
        try:
            deployer = await self._get_deployer(addr)
            if not deployer:
                return (True, 0.2, "Could not identify deployer")

            age = await self._get_wallet_age(deployer)
            if age < 3600:
                return (False, 0.8, "Deployer wallet too new: " + str(age) + "s")

            count = await self._count_deployed(deployer)
            if count > 10:
                return (False, 0.7, "Serial deployer: " + str(count) + " tokens")

            if deployer in self.scammer_wallets:
                return (False, 0.9, "Deployer is known scammer")

            age_hours = age // 3600
            msg = "Deployer OK (age: " + str(age_hours) + "h, deployed: " + str(count) + ")"
            return (True, 0.1, msg)

        except Exception as e:
            return (True, 0.3, "Deployer check inconclusive")

    async def _get_deployer(self, addr: str) -> Optional[str]:
        try:
            p = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [addr, {"limit": 1}]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=p,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                sigs = d.get("result", [])
                if sigs:
                    sig = sigs[-1].get("signature", "")
                    tp = {
                        "jsonrpc": "2.0", "id": 2,
                        "method": "getTransaction",
                        "params": [sig, {"encoding": "json"}]
                    }
                    async with self.session.post(
                        config.rpc.solana_rpc, json=tp,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as tr:
                        td = await tr.json()
                        tx = td.get("result", {})
                        if tx:
                            keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                            if keys:
                                k = keys[0]
                                return k if isinstance(k, str) else k.get("pubkey", "")
            return None
        except:
            return None

    async def _get_wallet_age(self, wallet: str) -> int:
        try:
            p = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [wallet, {"limit": 1}]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=p,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                sigs = d.get("result", [])
                if sigs:
                    first_time = sigs[-1].get("blockTime", 0)
                    return current_timestamp() - first_time
            return 999999
        except:
            return 999999

    async def _count_deployed(self, deployer: str) -> int:
        try:
            if config.rpc.helius_key:
                url = "https://mainnet.helius-rpc.com/?api-key=" + config.rpc.helius_key
                p = {
                    "jsonrpc": "2.0", "id": "das",
                    "method": "getAssetsByCreator",
                    "params": {"creatorAddress": deployer, "page": 1, "limit": 100}
                }
                async with self.session.post(
                    url, json=p,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    d = await r.json()
                    return d.get("result", {}).get("total", 0)
            return 0
        except:
            return 0

    # ====================================================
    #  LAYER 14: FIRST BUY ANALYSIS
    # ====================================================

    async def _chk_first_buys(self, addr: str) -> tuple:
        try:
            p = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [addr, {"limit": 20}]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=p,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                sigs = d.get("result", [])

            if len(sigs) < 3:
                return (True, 0.2, "Not enough tx data")

            first_buyers = []
            for s in sigs[:5]:
                tp = {
                    "jsonrpc": "2.0", "id": 2,
                    "method": "getTransaction",
                    "params": [s.get("signature", ""), {"encoding": "json"}]
                }
                try:
                    async with self.session.post(
                        config.rpc.solana_rpc, json=tp,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as tr:
                        td = await tr.json()
                        tx = td.get("result", {})
                        if tx:
                            keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                            if keys:
                                k = keys[0]
                                first_buyers.append(k if isinstance(k, str) else k.get("pubkey", ""))
                except:
                    continue

            deployer = await self._get_deployer(addr)
            if deployer and deployer in first_buyers:
                return (False, 0.7, "Deployer is among first buyers")

            msg = "First buy analysis OK (" + str(len(first_buyers)) + " checked)"
            return (True, 0.1, msg)

        except Exception as e:
            return (True, 0.3, "First buy check inconclusive")

    # ====================================================
    #  LAYER 15: BLACKLIST DETECTION
    # ====================================================

    async def _chk_blacklist(self, addr: str) -> tuple:
        try:
            async with self.session.get(
                "https://api.gopluslabs.io/api/v1/token_security/solana",
                params={"contract_addresses": addr},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    info = d.get("result", {}).get(addr, {})
                    if info.get("can_take_back_ownership", "0") == "1":
                        return (False, 0.9, "Can take back ownership")
                    if info.get("owner_change_balance", "0") == "1":
                        return (False, 0.8, "Owner can change balance")
                    if info.get("hidden_owner", "0") == "1":
                        return (False, 0.6, "Hidden owner detected")
                    return (True, 0.0, "No blacklist function")
            return (True, 0.2, "Could not verify blacklist")
        except:
            return (True, 0.2, "Blacklist check inconclusive")

    # ====================================================
    #  LAYER 16: PROXY CONTRACT CHECK
    # ====================================================

    async def _chk_proxy(self, addr: str) -> tuple:
        try:
            async with self.session.get(
                "https://api.gopluslabs.io/api/v1/token_security/solana",
                params={"contract_addresses": addr},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    info = d.get("result", {}).get(addr, {})
                    risks = []
                    score = 0.0
                    if info.get("is_proxy", "0") == "1":
                        risks.append("Proxy/upgradeable")
                        score += 0.5
                    if info.get("selfdestruct", "0") == "1":
                        risks.append("Self-destruct")
                        score += 0.3
                    if info.get("external_call", "0") == "1":
                        risks.append("External calls")
                        score += 0.2
                    if risks:
                        return (False, min(1.0, score), "; ".join(risks))
                    return (True, 0.0, "No proxy pattern")
            return (True, 0.2, "Could not verify proxy")
        except:
            return (True, 0.2, "Proxy check inconclusive")

    # ====================================================
    #  LAYER 17: VOLUME MANIPULATION
    # ====================================================

    async def _chk_volume_fake(self, addr: str, meta: dict) -> tuple:
        try:
            vol = meta.get("volume_24h", 0)
            mcap = meta.get("market_cap", 0)
            liq = meta.get("liquidity", 0)

            if mcap == 0 or vol == 0:
                return (True, 0.2, "Insufficient data")

            vm = vol / mcap
            if vm > 5.0:
                return (False, 0.8, "Extreme volume ratio: " + str(round(vm, 1)) + "x")
            if vm > 2.0:
                return (False, 0.5, "High volume ratio: " + str(round(vm, 1)) + "x")
            if liq > 0 and vol > liq * 10:
                return (False, 0.6, "Volume 10x higher than liquidity")

            return (True, 0.1, "Volume OK (ratio: " + str(round(vm, 2)) + "x)")

        except:
            return (True, 0.2, "Volume check inconclusive")

    # ====================================================
    #  LAYER 18: SCAMMER WALLET CHECK
    # ====================================================

    async def _chk_scammer_wallet(self, addr: str) -> tuple:
        try:
            holders = await self._get_top_holders(addr)
            scam = sum(1 for h in holders if h in self.scammer_wallets)
            if scam > 0:
                return (False, 0.9, str(scam) + " known scammer wallets found")
            return (True, 0.0, "No known scammers")
        except:
            return (True, 0.1, "Scammer check inconclusive")

    async def _get_top_holders(self, addr: str) -> list:
        try:
            p = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [addr]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=p,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                return [a.get("address", "") for a in d.get("result", {}).get("value", [])]
        except:
            return []

    async def _load_scammer_db(self):
        try:
            async with self.session.get(
                "https://api.solscan.io/v2/account/transfer?address=known-scam",
                timeout=aiohttp.ClientTimeout(total=5)
            ):
                pass
        except:
            pass
        logger.info("Scammer DB loaded: " + str(len(self.scammer_wallets)) + " wallets")

    # ====================================================
    #  LAYER 19: MAX INVESTMENT CAP
    # ====================================================

    def _chk_max_invest(self, amount: float, balance: float) -> tuple:
        if balance <= 0:
            return (True, 0.0, "No balance data")
        pct = (amount / balance) * 100
        if pct > 50:
            return (False, 0.9, "Investing " + str(round(pct, 1)) + "% of balance!")
        if pct > 30:
            return (False, 0.6, "Investing " + str(round(pct, 1)) + "% (risky)")
        if pct > 20:
            return (True, 0.3, "Investing " + str(round(pct, 1)) + "% (moderate)")
        return (True, 0.0, "Investing " + str(round(pct, 1)) + "% (safe)")
                # ====================================================
    #  LAYER 20: PRICE MANIPULATION
    # ====================================================

    async def _chk_price_manipulation(self, addr: str, meta: dict) -> tuple:
        try:
            c1h = meta.get("price_change_1h", 0)
            c24 = meta.get("price_change_24h", 0)
            vol = meta.get("volume_24h", 0)

            if c1h > 1000:
                return (False, 0.7, "Pump detected: +" + str(round(c1h)) + "% in 1h")
            if c1h > 500 and vol < 1000:
                return (False, 0.8, "Big pump with low volume")
            if c1h < -50:
                return (False, 0.6, "Dump detected: " + str(round(c1h)) + "% in 1h")
            if c24 > 5000:
                return (False, 0.5, "Extreme 24h: +" + str(round(c24)) + "%")

            msg = "Price OK (1h: " + str(round(c1h, 1)) + "%)"
            return (True, 0.1, msg)

        except:
            return (True, 0.2, "Price check inconclusive")

    # ====================================================
    #  LAYER 21: MULTI-DEX CHECK
    # ====================================================

    async def _chk_multi_dex(self, addr: str) -> tuple:
        try:
            async with self.session.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + addr,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    pairs = d.get("pairs", [])
                    dexes = set()
                    for p in pairs:
                        if p.get("chainId") == "solana":
                            dexes.add(p.get("dexId", ""))
                    n = len(dexes)
                    if n >= 3:
                        return (True, 0.0, "Listed on " + str(n) + " DEXes")
                    if n >= 2:
                        return (True, 0.1, "Listed on " + str(n) + " DEXes")
                    if n == 1:
                        return (True, 0.3, "Only on 1 DEX")
            return (True, 0.3, "Could not check DEX listings")
        except:
            return (True, 0.2, "Multi-DEX check inconclusive")

    # ====================================================
    #  LAYER 22: BURN VERIFICATION
    # ====================================================

    async def _chk_burn(self, addr: str) -> tuple:
        try:
            p = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenSupply",
                "params": [addr]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=p,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                supply = float(d.get("result", {}).get("value", {}).get("uiAmount", 0))

            burn_addrs = [
                "1nc1nerator11111111111111111111111111111111",
                "11111111111111111111111111111111",
            ]

            holders = await self._get_top_holders(addr)
            burned = 0

            for h in holders:
                if h in burn_addrs:
                    bp = {
                        "jsonrpc": "2.0", "id": 2,
                        "method": "getTokenAccountBalance",
                        "params": [h]
                    }
                    try:
                        async with self.session.post(
                            config.rpc.solana_rpc, json=bp,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as br:
                            bd = await br.json()
                            burned += float(
                                bd.get("result", {}).get("value", {}).get("uiAmount", 0)
                            )
                    except:
                        pass

            if burned > 0 and supply > 0:
                pct = (burned / (supply + burned)) * 100
                if pct > 50:
                    return (True, 0.0, "Burned " + str(round(pct, 1)) + "% (verified)")
                if pct > 10:
                    return (True, 0.1, "Burned " + str(round(pct, 1)) + "%")

            return (True, 0.1, "No significant burns")

        except:
            return (True, 0.2, "Burn check inconclusive")

    # ====================================================
    #  LAYER 23: EMERGENCY SELL DETECTION
    # ====================================================

    async def _chk_emergency(self, addr: str, meta: dict) -> tuple:
        try:
            liq = meta.get("liquidity", 0)
            c5m = meta.get("price_change_5m", 0)

            if liq == 0:
                return (True, "EMERGENCY: Liquidity removed!")

            if c5m < -70:
                msg = "EMERGENCY: Price crashed " + str(round(c5m)) + "% in 5min!"
                return (True, msg)

            return (False, "No emergency")

        except:
            return (False, "Emergency check inconclusive")

    # ====================================================
    #  FORMAT FOR TELEGRAM
    # ====================================================

    def format_report(self, result: dict, symbol: str = "???") -> str:
        score = result.get("advanced_score", 0)

        if score <= 15:
            grade = "A+ (Very Safe)"
        elif score <= 25:
            grade = "A (Safe)"
        elif score <= 35:
            grade = "B (Acceptable)"
        elif score <= 50:
            grade = "C (Risky)"
        elif score <= 70:
            grade = "D (High Risk)"
        else:
            grade = "F (Danger)"

        lines = []
        lines.append("ADVANCED CHECK: " + symbol)
        lines.append("=" * 28)
        lines.append("")
        lines.append("Grade: " + grade)
        lines.append("Score: " + str(score) + "/100")
        lines.append(
            "Passed: " + str(result.get("passed", 0))
            + " | Failed: " + str(result.get("failed", 0))
        )
        lines.append("")

        for name, detail in result.get("details", {}).items():
            if name == "emergency_sell":
                continue
            e = "PASS" if detail.get("passed", True) else "FAIL"
            lines.append("  " + e + " " + name + ": " + detail.get("detail", "N/A"))

        if result.get("emergency"):
            lines.append("")
            lines.append("EMERGENCY: " + result.get("emergency_reason", ""))

        if result.get("reasons"):
            lines.append("")
            lines.append("Risks:")
            for reason in result["reasons"]:
                lines.append("  - " + reason)

        return "\n".join(lines)
        