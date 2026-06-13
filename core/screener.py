"""
Token Screener (ULTIMATE)
- Super lenient basic filter
- Extra scam filters (7 new)
- Rugcheck with safety level
- Advanced anti-rug check
- Momentum scoring
"""
import asyncio
from typing import Optional, List
from dataclasses import dataclass
from config import config
from core.rugpull_checker import RugpullChecker, RugpullReport
from utils.logger import logger, console
from utils.helpers import current_timestamp, risk_level


@dataclass
class ScreenedToken:
    token_data: dict
    rugpull_report: RugpullReport
    screener_score: float
    passed_checks: List[str]
    failed_checks: List[str]


class TokenScreener:
    def __init__(self):
        self.rug_checker = RugpullChecker()
        self.advanced_checker = None

    async def initialize(self):
        await self.rug_checker.initialize()
        try:
            from core.anti_rug_advanced import AdvancedAntiRug
            self.advanced_checker = AdvancedAntiRug()
            await self.advanced_checker.initialize()
        except Exception as e:
            logger.warning("Advanced checker not available: " + str(e))
            self.advanced_checker = None

    async def close(self):
        await self.rug_checker.close()
        if self.advanced_checker:
            await self.advanced_checker.close()

    async def screen_token(self, td: dict) -> Optional[ScreenedToken]:
        addr = td.get("address", "")
        sym = td.get("symbol", "???")

        logger.info("Screening " + sym + " (" + addr[:8] + "...)")

        # ============================================
        # LAYER 1: BASIC FILTER
        # ============================================
        liq = td.get("liquidity", 0)
        holders = td.get("holder_count", 0)
        mcap = td.get("market_cap", 0)
        price = td.get("price_usd", 0)

        # Block zero data
        if liq == 0 and holders == 0 and price == 0:
            logger.info("Skip " + sym + ": zero data")
            return None

        # ============================================
        # LAYER 1.5: EXTRA SCAM FILTERS
        # ============================================

        # Filter 1: Liquidity terlalu kecil
        if liq > 0 and liq < 1000:
            logger.info("Skip " + sym + ": Liquidity too low ($" + str(round(liq)) + ")")
            return None

        # Filter 2: Market cap terlalu kecil
        if mcap > 0 and mcap < 5000:
            logger.info("Skip " + sym + ": MCap too low ($" + str(round(mcap)) + ")")
            return None

        # Filter 3: Volume spike (manipulasi)
        vol_5m = td.get("volume_5m", 0)
        vol_1h = td.get("volume_1h", 0)
        if vol_1h > 0 and vol_5m > 0:
            vol_ratio = vol_5m / (vol_1h / 12)
            if vol_ratio > 10:
                logger.info("Skip " + sym + ": Volume spike (" + str(round(vol_ratio, 1)) + "x) - manipulation")
                return None

        # Filter 4: Buy/sell ratio extreme (pump)
        buys = td.get("buys_1h", 0)
        sells = td.get("sells_1h", 0)
        if sells > 0 and buys > 0:
            ratio = buys / sells
            if ratio > 10:
                logger.info("Skip " + sym + ": Extreme buy ratio (" + str(round(ratio, 1)) + "x) - pump")
                return None

        # Filter 5: Price change extreme (pump & dump)
        pc5m = td.get("price_change_5m", 0)
        pc1h = td.get("price_change_1h", 0)
        if pc5m and abs(pc5m) > 1000:
            logger.info("Skip " + sym + ": Extreme 5m change (" + str(round(pc5m, 1)) + "%) - P&D")
            return None
        if pc1h and pc1h < -90:
            logger.info("Skip " + sym + ": Dumped -90% in 1h")
            return None

        # Filter 6: Liquidity/MCap ratio terlalu rendah
        if mcap > 0 and liq > 0:
            lm_ratio = liq / mcap
            if lm_ratio < 0.01:
                logger.info("Skip " + sym + ": Liq/MCap too low (" + str(round(lm_ratio * 100, 2)) + "%)")
                return None

        # Filter 7: No social + low holders
        has_social = td.get("website") or td.get("twitter") or td.get("telegram")
        if not has_social and holders < 50:
            logger.info("Skip " + sym + ": No social + low holders")
            return None

        # ============================================
        # LAYER 2: RUG CHECK
        # ============================================
        try:
            rug = await self.rug_checker.analyze(td)
        except Exception as e:
            logger.error("Rugcheck error for " + sym + ": " + str(e))
            return None

        if not rug.is_safe:
            safety = getattr(rug, 'safety_level', 'UNKNOWN')
            crit = getattr(rug, 'critical_failures', [])
            logger.info("Rug fail " + sym + ": " + str(rug.score) + "/100 | " + safety + " | Critical: " + str(len(crit)))
            return None

        # ============================================
        # LAYER 3: ADVANCED CHECK (optional)
        # ============================================
        if self.advanced_checker:
            try:
                adv = await self.advanced_checker.full_advanced_check(addr, td)
                if adv.get("emergency"):
                    logger.warning("EMERGENCY " + sym + ": " + str(adv.get("emergency_reason", "")))
                    return None
                if not adv.get("is_safe", True):
                    logger.info("Advanced fail " + sym + ": " + str(adv.get("advanced_score", 0)) + "/100")
                    return None
            except Exception as e:
                logger.debug("Advanced check error: " + str(e)[:50])

        # ============================================
        # LAYER 4: MOMENTUM
        # ============================================
        momentum_score, momentum_details = self._momentum(td)

        # ============================================
        # LAYER 5: FINAL SCORE
        # ============================================
        score = self._calc_score(td, rug, momentum_score)

        passed = []
        failed = []
        for name, detail in rug.details.items():
            if detail["passed"]:
                passed.append(name)
            else:
                failed.append(name)

        screened = ScreenedToken(
            token_data=td,
            rugpull_report=rug,
            screener_score=score,
            passed_checks=passed,
            failed_checks=failed,
        )

        self._print(screened)
        return screened

    def _momentum(self, td: dict) -> tuple:
        score = 50.0
        details = []

        vol = td.get("volume_24h", 0)
        mcap = td.get("market_cap", 0)
        liq = td.get("liquidity", 0)
        price = td.get("price_usd", 0)

        if mcap > 0 and vol > 0:
            vm = vol / mcap
            if vm > 0.5:
                score += 20
                details.append("High VM: " + str(round(vm, 2)))
            elif vm > 0.1:
                score += 10
                details.append("Good VM: " + str(round(vm, 2)))
            elif vm > 0.01:
                score += 5

        if price > 0:
            score += 10
            details.append("Has price")

        if liq > 0:
            score += 5
            details.append("Has liquidity")

        if mcap > 0 and liq > 0:
            lm = liq / mcap
            if lm > 0.3:
                score += 15
                details.append("Good LM: " + str(round(lm, 2)))
            elif lm > 0.05:
                score += 8

        return min(100, score), details

    def _calc_score(self, td, rug, momentum):
        safety = max(0, 100 - rug.score) * 0.5
        mom = momentum * 0.3
        cr = rug.checks_passed / max(1, rug.checks_total) * 100 * 0.2
        return round(min(100, safety + mom + cr), 1)

    def _print(self, screened):
        r = screened.rugpull_report
        td = screened.token_data
        sym = td.get("symbol", "???")
        safety = getattr(r, 'safety_level', 'UNKNOWN')
        crit = getattr(r, 'critical_failures', [])
        crit_str = ""
        if crit:
            crit_str = "\n  CRITICAL: " + ", ".join(crit)
        console.print(
            "\n" + "=" * 50
            + "\nSCREEN: " + sym
            + "\n  Price: $" + str(td.get("price_usd", 0))
            + "\n  Liq: $" + str(round(td.get("liquidity", 0)))
            + " | Holders: " + str(td.get("holder_count", 0))
            + "\n  Rug: " + safety + " [" + str(r.score) + "/100]"
            + "\n  Checks: " + str(r.checks_passed) + " pass / " + str(r.checks_failed) + " fail"
            + "\n  Score: " + str(screened.screener_score) + "/100"
            + crit_str
            + "\n" + "=" * 50
        )