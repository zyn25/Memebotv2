"""
Token Scanner — Multi-source detection (ULTIMATE)
Sources: Raydium WS + DexScreener + Jupiter + Pump.fun + Helius DAS
+ IMPERSONATOR FILTER
+ ANTI-FOMO FILTER
+ VOLUME DROP CHECK
+ SCANNER AUTO RESET
"""
import asyncio
import json
import aiohttp
import websockets
from typing import Callable, Optional, List
from config import config
from utils.logger import logger, log_scan
from utils.helpers import is_valid_solana_address, current_timestamp


# ============================================
# IMPERSONATOR FILTER
# ============================================
FAKE_TOKEN_SYMBOLS = {
    "SOL", "USDC", "USDT", "BTC", "ETH", "JUP", "RAY",
    "BONK", "WIF", "ORCA", "MNGO", "SAMO", "FIDA",
    "STEP", "PORT", "MEDIA", "ROPE", "TULIP", "SLND",
    "PYTH", "SRM", "FET", "RNDR", "RENDER", "W",
    "TNSR", "JTO", "WEN", "MYRO", "POPCAT", "MEW",
    "CATO", "PONKE", "BOME", "GUMMY", "SLERF",
    "NEAR", "AVAX", "LINK", "UNI", "AAVE", "DOT",
    "ADA", "XRP", "DOGE", "SHIB", "PEPE", "FLOKI",
    "ARB", "OP", "MATIC", "SUI", "APT", "SEI",
}

FAKE_TOKEN_NAMES = {
    "solana", "bitcoin", "ethereum", "jupiter", "tether",
    "usd coin", "binance", "cardano", "dogecoin", "shiba",
    "ripple", "avalanche", "polkadot", "chainlink", "uniswap",
    "aave", "render", "near protocol", "sei",
}


def is_impersonator_token(symbol, name):
    if symbol and symbol.strip().upper() in FAKE_TOKEN_SYMBOLS:
        return True
    if name and name.strip().lower() in FAKE_TOKEN_NAMES:
        return True
    return False


class TokenScanner:
    def __init__(self):
        self.running = False
        self.seen_tokens: set = set()
        self.blocked_tokens: set = set()
        self.callbacks: List[Callable] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        self.TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        self.SOL_MINT = "So11111111111111111111111111111111111111112"
        self.sol_price_cache = 0
        self.sol_price_time = 0

    async def start(self):
        self.running = True
        self.session = aiohttp.ClientSession()
        logger.info("Scanner started (ULTIMATE)")
        await asyncio.gather(
            self._scan_raydium_ws(),
            self._poll_dexscreener(),
            self._poll_jupiter(),
            self._poll_pumpfun(),
            return_exceptions=True,
        )

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()

    def on_new_token(self, cb: Callable):
        self.callbacks.append(cb)

    async def _notify(self, td):
        for cb in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(td)
                else:
                    cb(td)
            except Exception as e:
                logger.error("Callback error: " + str(e))

    # ============================================
    # IMPERSONATOR + ANTI-FOMO CHECK
    # ============================================
    def _check_impersonator(self, td):
        symbol = td.get("symbol", "")
        name = td.get("name", "")
        addr = td.get("address", "")

        # Filter token tanpa nama
        if symbol in ("", "???", "UNKNOWN", "unknown"):
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED NO SYMBOL: " + addr[:16])
            return True

        if name in ("", "Unknown", "unknown", "UNKNOWN"):
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED NO NAME: " + addr[:16])
            return True

        # Check impersonator
        if is_impersonator_token(symbol, name):
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED IMPERSONATOR: " + symbol + " (" + name + ") | " + addr[:16])
            return True

        # Check known scam addresses
        known_scam = {
            "So11111111111111111111111111111111111111112",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        }
        if addr in known_scam:
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED KNOWN MINT: " + addr[:16])
            return True

        # Check supply = 0
        supply = td.get("supply", 0)
        if supply == 0:
            price = td.get("price_usd", 0)
            mcap = td.get("market_cap", 0)
            if price > 0 and mcap == 0:
                logger.warning("BLOCKED ZERO MCAP: " + symbol + " | " + addr[:16])
                self.blocked_tokens.add(addr)
                return True

        # ANTI-FOMO: Sudah pump >200% dalam 5 menit
        pc5m = td.get("price_change_5m", 0)
        if pc5m and pc5m > 200:
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED FOMO: " + symbol + " | +" + str(pc5m) + "% in 5m")
            return True

        # ANTI-FOMO: Sudah pump >500% dalam 1 jam
        pc1h = td.get("price_change_1h", 0)
        if pc1h and pc1h > 500:
            self.blocked_tokens.add(addr)
            logger.warning("BLOCKED FOMO 1H: " + symbol + " | +" + str(pc1h) + "% in 1h")
            return True

        return False

    # ============================================
    # VOLUME DROP CHECK
    # ============================================
    def _check_volume_drop(self, td):
        """Return True kalau volume dropping"""
        sym = td.get("symbol", "???")
        vol_1h = td.get("volume_1h", 0)
        vol_5m = td.get("volume_5m", 0)

        if vol_1h > 0 and vol_5m >= 0:
            expected_5m = vol_1h / 12
            if expected_5m > 0:
                vol_ratio = vol_5m / expected_5m
                if vol_ratio < 0.3:
                    logger.info("SKIP " + sym + ": Volume dropping (" + str(round(vol_ratio, 2)) + ")")
                    return True

        return False

    # SOURCE 1: RAYDIUM WS
    async def _scan_raydium_ws(self):
        fail_count = 0
        max_fails = 5
        while self.running:
            try:
                uri = config.rpc.solana_ws
                if not uri or "mainnet-beta.solana.com" in uri:
                    logger.warning("Raydium WS: Invalid URL, skip")
                    await asyncio.sleep(60)
                    continue

                logger.info("Raydium WS: Connecting to " + uri[:50] + "...")
                async with websockets.connect(
                    uri, ping_interval=20, ping_timeout=10,
                    close_timeout=5, max_size=2**20
                ) as ws:
                    fail_count = 0
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                        "params": [{"mentions": [self.RAYDIUM_AMM]}, {"commitment": "confirmed"}]
                    }))
                    logger.info("Raydium WS: Connected & Subscribed")
                    async for msg in ws:
                        if not self.running:
                            break
                        try:
                            data = json.loads(msg)
                            await self._process_raydium(data)
                        except json.JSONDecodeError:
                            continue
            except websockets.exceptions.ConnectionClosed:
                fail_count += 1
                w = min(30 * fail_count, 300)
                logger.warning("Raydium WS: Disconnected, retry in " + str(w) + "s")
                await asyncio.sleep(w)
            except Exception as e:
                fail_count += 1
                w = min(30 * fail_count, 120) if fail_count < max_fails else 300
                logger.error("Raydium WS error: " + str(e)[:80] + " | retry in " + str(w) + "s")
                await asyncio.sleep(w)

    async def _process_raydium(self, data):
        try:
            if data.get("method") != "logsNotification":
                return
            result = data.get("params", {}).get("result", {})
            sig = result.get("value", {}).get("signature", "")
            logs = result.get("value", {}).get("logs", [])
            if not any("initialize" in l.lower() for l in logs):
                return
            tokens = self._extract_tokens(logs)
            for t in tokens:
                if t in self.seen_tokens:
                    continue
                if t in self.blocked_tokens:
                    continue
                if not is_valid_solana_address(t):
                    continue
                self.seen_tokens.add(t)
                td = await self._fetch_meta(t)
                if td:
                    if self._check_impersonator(td):
                        continue
                    td["source"] = "raydium"
                    td["signature"] = sig
                    td["discovered_at"] = current_timestamp()
                    log_scan(t, "New pool: " + td.get("symbol", "???"))
                    await self._notify(td)
        except Exception as e:
            logger.error("Process Raydium error: " + str(e))

    def _extract_tokens(self, logs):
        tokens = []
        skip = {self.TOKEN_PROGRAM, self.RAYDIUM_AMM, "11111111111111111111111111111111",
                "ComputeBudget111111111111111111111111111111", "SysvarRent111111111111111111111111111111111",
                "SysvarC1ock11111111111111111111111111111111"}
        for l in logs:
            if "mint" in l.lower() or "token" in l.lower():
                for p in l.split():
                    c = p.strip("\"',():")
                    if is_valid_solana_address(c) and c not in skip and len(c) > 30:
                        tokens.append(c)
        return tokens

    # SOURCE 2: DEXSCREENER
    async def _poll_dexscreener(self):
        while self.running:
            try:
                async with self.session.get(
                    "https://api.dexscreener.com/token-profiles/latest/v1",
                    timeout=aiohttp.ClientTimeout(total=30)) as r:

                    if r.status == 200:
                        data = await r.json()
                        for item in data:
                            chain = item.get("chainId", "")
                            addr = item.get("tokenAddress", "")
                            if chain != "solana":
                                continue
                            if addr in self.seen_tokens:
                                continue
                            if addr in self.blocked_tokens:
                                continue
                            if not is_valid_solana_address(addr):
                                continue
                            self.seen_tokens.add(addr)
                            td = await self._fetch_meta(addr)
                            if td:
                                if self._check_impersonator(td):
                                    continue
                                td["source"] = "dexscreener"
                                td["discovered_at"] = current_timestamp()
                                log_scan(addr, "DexScreener: " + td.get("symbol", "???"))
                                await self._notify(td)

                async with self.session.get(
                    "https://api.dexscreener.com/latest/dex/search?q=solana%20new",
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        for pair in data.get("pairs", [])[:30]:
                            if pair.get("chainId") != "solana":
                                continue
                            base = pair.get("baseToken", {})
                            addr = base.get("address", "")
                            if not addr or addr in self.seen_tokens:
                                continue
                            if addr in self.blocked_tokens:
                                continue
                            if not is_valid_solana_address(addr):
                                continue
                            self.seen_tokens.add(addr)
                            td = self._pair_to_data(pair)
                            if td:
                                if self._check_impersonator(td):
                                    continue
                                if self._check_volume_drop(td):
                                    continue
                                td["source"] = "dexscreener"
                                td["discovered_at"] = current_timestamp()
                                log_scan(addr, "Trending: " + td.get("symbol", "???"))
                                await self._notify(td)
            except Exception as e:
                logger.error("DexScreener error: " + str(e))

            # AUTO RESET: Clear seen_tokens kalau >50000
            if len(self.seen_tokens) > 50000:
                logger.info("Scanner reset: clearing " + str(len(self.seen_tokens)) + " seen tokens")
                self.seen_tokens.clear()

            await asyncio.sleep(30)

    # SOURCE 3: JUPITER
    async def _poll_jupiter(self):
        while self.running:
            try:
                async with self.session.get(
                    "https://tokens.jup.ag/tokens?tags=verified",
                    params={"limit": 100},
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        for t in await r.json():
                            a = t.get("address", "")
                            if a and a not in self.seen_tokens:
                                self.seen_tokens.add(a)
            except Exception as e:
                logger.error("Jupiter poll error: " + str(e))
            await asyncio.sleep(120)

    # SOURCE 4: PUMP.FUN
    async def _poll_pumpfun(self):
        while self.running:
            try:
                async with self.session.get(
                    "https://frontend-api-v2.pump.fun/coins/latest",
                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        coins = data if isinstance(data, list) else data.get("coins", [])
                        for coin in coins[:20]:
                            addr = coin.get("mint", "") or coin.get("address", "")
                            if not addr or addr in self.seen_tokens:
                                continue
                            if addr in self.blocked_tokens:
                                continue
                            if not is_valid_solana_address(addr):
                                continue
                            self.seen_tokens.add(addr)
                            mcap = float(coin.get("usd_market_cap", 0) or 0)
                            supply = float(coin.get("total_supply", 1) or 1)
                            td = {
                                "address": addr, "name": coin.get("name", "Unknown"),
                                "symbol": coin.get("symbol", "???"), "decimals": 9,
                                "price_usd": mcap / supply if supply > 0 else 0,
                                "market_cap": mcap, "volume_24h": 0,
                                "liquidity": mcap * 0.1, "holder_count": 0,
                                "created_at": current_timestamp(),
                                "website": coin.get("website", ""), "twitter": coin.get("twitter", ""),
                                "telegram": coin.get("telegram", ""),
                                "buys_1h": 0, "sells_1h": 0,
                                "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0,
                                "source": "pumpfun", "discovered_at": current_timestamp(),
                            }
                            if self._check_impersonator(td):
                                continue
                            log_scan(addr, "PumpFun: " + td.get("symbol", "???"))
                            await self._notify(td)
            except Exception as e:
                logger.debug("PumpFun error: " + str(e)[:50])
            await asyncio.sleep(15)

    # METADATA FETCHING
    async def _fetch_meta(self, addr):
        td = await self._fetch_dexscreener_detail(addr)
        if td and td.get("price_usd", 0) > 0:
            return td

        if config.rpc.birdeye_key:
            try:
                headers = {"X-API-KEY": config.rpc.birdeye_key, "x-chain": "solana"}
                async with self.session.get(
                    "https://public-api.birdeye.so/defi/token_overview",
                    headers=headers, params={"address": addr},
                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        d = (await r.json()).get("data", {})
                        if d.get("symbol"):
                            return {
                                "address": addr, "name": d.get("name", "Unknown"),
                                "symbol": d.get("symbol", "???"), "decimals": d.get("decimals", 9),
                                "price_usd": d.get("price", 0), "market_cap": d.get("mc", 0),
                                "volume_24h": d.get("v24hUSD", 0), "liquidity": d.get("liquidity", 0),
                                "holder_count": d.get("holder", 0), "created_at": d.get("lastTradeUnixTime", 0),
                                "website": "", "twitter": "", "telegram": "",
                                "buys_1h": 0, "sells_1h": 0,
                                "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0,
                            }
            except:
                pass

        td = await self._fetch_meta_helius(addr)
        if td:
            ds = await self._fetch_dexscreener_detail(addr)
            if ds:
                td.update({
                    "price_usd": ds.get("price_usd", td.get("price_usd", 0)),
                    "market_cap": ds.get("market_cap", 0), "volume_24h": ds.get("volume_24h", 0),
                    "liquidity": ds.get("liquidity", 0), "holder_count": ds.get("holder_count", 0),
                    "buys_1h": ds.get("buys_1h", 0), "sells_1h": ds.get("sells_1h", 0),
                    "price_change_5m": ds.get("price_change_5m", 0),
                    "price_change_1h": ds.get("price_change_1h", 0),
                    "price_change_24h": ds.get("price_change_24h", 0),
                    "website": ds.get("website", ""), "twitter": ds.get("twitter", ""),
                    "telegram": ds.get("telegram", ""),
                })
            return td

        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [addr]}
            async with self.session.post(config.rpc.solana_rpc, json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                si = d.get("result", {}).get("value", {})
                return {
                    "address": addr, "name": "Unknown", "symbol": "???",
                    "decimals": si.get("decimals", 9), "supply": float(si.get("uiAmount", 0)),
                    "price_usd": 0, "market_cap": 0, "volume_24h": 0, "liquidity": 0,
                    "holder_count": 0, "buys_1h": 0, "sells_1h": 0,
                    "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0,
                    "website": "", "twitter": "", "telegram": "",
                }
        except:
            return None

    # DEXSCREENER DETAIL
    async def _fetch_dexscreener_detail(self, addr):
        try:
            url = "https://api.dexscreener.com/latest/dex/tokens/" + addr
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    pairs = data.get("pairs", [])
                    if not pairs:
                        return None

                    solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
                    if not solana_pairs:
                        solana_pairs = pairs

                    best_pair = None
                    best_vol = 0
                    for pair in solana_pairs:
                        vol = pair.get("volume", {}).get("h24", 0) or 0
                        if vol > best_vol:
                            best_vol = vol
                            best_pair = pair

                    if not best_pair or best_vol == 0:
                        best_liq = 0
                        for pair in solana_pairs:
                            liq = pair.get("liquidity", {}).get("usd", 0) or 0
                            if liq > best_liq:
                                best_liq = liq
                                best_pair = pair

                    if not best_pair:
                        best_pair = solana_pairs[0]

                    return self._pair_to_data(best_pair)
            return None
        except Exception as e:
            logger.error("DexScreener error: " + str(e))
            return None

    def _pair_to_data(self, pair):
        try:
            base = pair.get("baseToken", {})
            liq = pair.get("liquidity", {})
            txns = pair.get("txns", {})
            h1 = txns.get("h1", {})
            h6 = txns.get("h6", {})
            h24 = txns.get("h24", {})
            pc = pair.get("priceChange", {})
            vol = pair.get("volume", {})
            info = pair.get("info", {})
            websites = info.get("websites", [])
            socials = info.get("socials", [])

            price_str = pair.get("priceUsd", "0") or "0"
            try:
                price = float(price_str)
            except:
                price = 0

            mcap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0
            website = websites[0].get("url", "") if websites else ""
            twitter = ""
            telegram = ""
            for s in socials:
                stype = s.get("type", "")
                if stype == "twitter":
                    twitter = s.get("url", "")
                elif stype == "telegram":
                    telegram = s.get("url", "")

            return {
                "address": base.get("address", ""), "name": base.get("name", "Unknown"),
                "symbol": base.get("symbol", "???"), "decimals": 9,
                "price_usd": price, "market_cap": mcap,
                "volume_24h": vol.get("h24", 0) or 0,
                "volume_6h": vol.get("h6", 0) or 0,
                "volume_1h": vol.get("h1", 0) or 0,
                "volume_5m": vol.get("m5", 0) or 0,
                "liquidity": liq.get("usd", 0) or 0, "holder_count": 0,
                "created_at": pair.get("pairCreatedAt", 0) or 0,
                "price_change_5m": pc.get("m5", 0) or 0,
                "price_change_1h": pc.get("h1", 0) or 0,
                "price_change_6h": pc.get("h6", 0) or 0,
                "price_change_24h": pc.get("h24", 0) or 0,
                "buys_1h": h1.get("buys", 0) or 0, "sells_1h": h1.get("sells", 0) or 0,
                "buys_6h": h6.get("buys", 0) or 0, "sells_6h": h6.get("sells", 0) or 0,
                "buys_24h": h24.get("buys", 0) or 0, "sells_24h": h24.get("sells", 0) or 0,
                "pair_address": pair.get("pairAddress", ""),
                "dex_id": pair.get("dexId", ""), "fdv": pair.get("fdv", 0) or 0,
                "website": website, "twitter": twitter, "telegram": telegram,
            }
        except Exception as e:
            logger.error("Parse pair error: " + str(e))
            return None

    # HELIUS DAS
    async def _fetch_meta_helius(self, addr):
        if not config.rpc.helius_key:
            return None
        try:
            url = "https://mainnet.helius-rpc.com/?api-key=" + config.rpc.helius_key
            payload = {"jsonrpc": "2.0", "id": "meta", "method": "getAsset", "params": {"id": addr}}
            async with self.session.post(url, json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    result = data.get("result", {})
                    content = result.get("content", {}).get("metadata", {})
                    token_info = result.get("token_info", {})
                    return {
                        "address": addr, "name": content.get("name", "Unknown"),
                        "symbol": content.get("symbol", "???"),
                        "decimals": token_info.get("decimals", 9),
                        "supply": float(token_info.get("supply", 0)),
                        "price_usd": 0, "market_cap": 0, "volume_24h": 0,
                        "liquidity": 0, "holder_count": 0,
                        "buys_1h": 0, "sells_1h": 0,
                        "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0,
                        "website": "", "twitter": "", "telegram": "",
                    }
            return None
        except:
            return None

    # JUPITER PRICE
    async def _get_jupiter_price(self, addr):
        try:
            async with self.session.get(
                "https://quote-api.jup.ag/v6/quote",
                params={"inputMint": addr, "outputMint": self.SOL_MINT,
                        "amount": "1000000000", "slippageBps": 100},
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    out = int(data.get("outAmount", 0))
                    if out > 0:
                        return out / 1e9
            return 0
        except:
            return 0

    # SOL PRICE CACHE
    async def _get_sol_price(self):
        now = current_timestamp()
        if self.sol_price_cache > 0 and now - self.sol_price_time < 60:
            return self.sol_price_cache
        try:
            async with self.session.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + self.SOL_MINT,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    pairs = data.get("pairs", [])
                    if pairs:
                        price = float(pairs[0].get("priceUsd", "0") or "0")
                        if price > 0:
                            self.sol_price_cache = price
                            self.sol_price_time = now
                            return price
            return 150.0
        except:
            return 150.0

    # BIRDEYE HELPER
    def _birdeye_to_data(self, t):
        try:
            return {
                "address": t.get("address", ""), "name": t.get("name", "Unknown"),
                "symbol": t.get("symbol", "???"), "decimals": t.get("decimals", 9),
                "price_usd": t.get("price", 0), "market_cap": t.get("mc", 0),
                "volume_24h": t.get("v24hUSD", 0), "liquidity": t.get("liquidity", 0),
                "holder_count": t.get("holder", 0), "created_at": t.get("lastTradeUnixTime", 0),
                "buys_1h": 0, "sells_1h": 0,
                "price_change_5m": 0, "price_change_1h": 0, "price_change_24h": 0,
                "website": "", "twitter": "", "telegram": "",
            }
        except:
            return None