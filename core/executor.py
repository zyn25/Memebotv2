"""
Trade Executor via Jupiter - v2.1 DNS FIX
- Fixed: Removed AsyncResolver (requires aiodns)
- Fixed: Simple TCPConnector with DNS cache
- Multiple Jupiter API endpoints (fallback)
- Better timeout handling
- DexScreener price fallback
"""
import asyncio
import aiohttp
import base64
import random
from typing import Optional, Dict
from config import config
from utils.logger import logger, log_buy, log_sell
from utils.helpers import lamports_to_sol, sol_to_lamports, current_timestamp


class TradeExecutor:
    def __init__(self):
        self.session = None
        self.jupiter_endpoints = [
            "https://api.jup.ag/swap/v6",
            "https://quote-api.jup.ag/v6",
            "https://jupiter-swap-api.quiknode.pro/v6",
            "https://jupiter-api.bonfida.com/v6",
        ]
        self.current_jupiter = 0
        self.SOL = "So11111111111111111111111111111111111111112"
        self.retries = 3
        self.bot_instance = None
        self.buy_count = 0
        self.sell_count = 0
        self.fail_count = 0

    async def initialize(self):
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            connector=connector,
        )
        logger.info("Executor initialized")

    async def close(self):
        if self.session:
            await self.session.close()

    def _get_jupiter(self):
        return self.jupiter_endpoints[self.current_jupiter % len(self.jupiter_endpoints)]

    def _rotate_jupiter(self):
        self.current_jupiter += 1
        logger.info("Jupiter rotated to: " + self._get_jupiter())

    # ====================================================
    #  BUY
    # ====================================================

    async def buy_token(self, token_address, sol_amount, slippage_bps=None):
        if config.dry_run:
            return await self._sim_buy(token_address, sol_amount)
        sl = slippage_bps or config.trading.slippage_bps
        lam = sol_to_lamports(sol_amount)

        for attempt in range(self.retries):
            try:
                q = await self._quote_with_retry(self.SOL, token_address, str(lam), sl)
                if not q:
                    logger.warning("Buy quote failed attempt " + str(attempt + 1) + "/" + str(self.retries))
                    self._rotate_jupiter()
                    await asyncio.sleep(2)
                    continue

                out = int(q.get("outAmount", 0))
                if out == 0:
                    logger.warning("Buy quote returned 0 tokens")
                    continue

                pi = float(q.get("priceImpactPct", 0))
                if pi > 10:
                    logger.warning("Price impact too high: " + str(pi) + "%")
                    return None

                sw = await self._swap_tx_with_retry(q)
                if not sw:
                    logger.warning("Swap tx failed attempt " + str(attempt + 1))
                    self._rotate_jupiter()
                    await asyncio.sleep(2)
                    continue

                tx = await self._sign_send(sw)
                if tx:
                    price = sol_amount / lamports_to_sol(out) if out > 0 else 0
                    self.buy_count += 1
                    log_buy(token_address, sol_amount, price)
                    return {
                        "success": True, "tx_hash": tx,
                        "token_address": token_address, "sol_spent": sol_amount,
                        "tokens_received": out, "price": price,
                        "price_impact": pi, "timestamp": current_timestamp(),
                    }
            except Exception as e:
                logger.error("Buy attempt " + str(attempt + 1) + "/" + str(self.retries) + ": " + str(e))
                self._rotate_jupiter()
                await asyncio.sleep(2)

        self.fail_count += 1
        return None

    async def _sim_buy(self, addr, sol):
        """DRY RUN BUY - Jupiter quote + DexScreener fallback"""
        try:
            lam = sol_to_lamports(sol)
            slippages = [500, 1000, 2000, 5000]

            for ep_idx in range(len(self.jupiter_endpoints)):
                for sl in slippages:
                    try:
                        q = await self._quote_direct(
                            self.jupiter_endpoints[ep_idx],
                            self.SOL, addr, str(lam), sl
                        )
                        if q:
                            out = int(q.get("outAmount", 0))
                            if out > 0:
                                price = sol / lamports_to_sol(out)
                                logger.info("DRY BUY (jupiter " + str(ep_idx) + "): " + str(round(sol, 4)) + " SOL -> " + str(out) + " tokens")
                                return {
                                    "success": True,
                                    "tx_hash": "DRY_" + str(current_timestamp()),
                                    "token_address": addr,
                                    "sol_spent": sol,
                                    "tokens_received": out,
                                    "price": price,
                                    "price_impact": float(q.get("priceImpactPct", 0)),
                                    "timestamp": current_timestamp(),
                                    "dry_run": True,
                                }
                    except:
                        continue
                    await asyncio.sleep(0.2)

            # DexScreener fallback
            dex_price_sol = 0.0
            try:
                async with self.session.get(
                    "https://api.dexscreener.com/latest/dex/tokens/" + addr,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        for pair in d.get("pairs", []):
                            if pair.get("chainId") == "solana":
                                p_usd = float(pair.get("priceUsd", "0") or "0")
                                if p_usd > 0:
                                    sol_usd = await self._get_sol_usd_price()
                                    if sol_usd > 0:
                                        dex_price_sol = p_usd / sol_usd
                                        break
            except:
                pass

            if dex_price_sol > 0:
                tokens = int(sol / dex_price_sol) if dex_price_sol > 0 else 0
                logger.info("DRY BUY (dex): " + str(round(sol, 4)) + " SOL -> " + str(tokens))
                return {
                    "success": True,
                    "tx_hash": "DRY_DEX_" + str(current_timestamp()),
                    "token_address": addr,
                    "sol_spent": sol,
                    "tokens_received": tokens,
                    "price": dex_price_sol,
                    "price_impact": 0,
                    "timestamp": current_timestamp(),
                    "dry_run": True,
                }

            # Last resort
            fake_price = sol / 1000000000
            logger.info("DRY BUY sim: " + str(round(sol, 4)) + " SOL -> " + addr[:12])
            return {
                "success": True,
                "tx_hash": "DRY_SIM_" + str(current_timestamp()),
                "token_address": addr,
                "sol_spent": sol,
                "tokens_received": 1000000000,
                "price": fake_price,
                "price_impact": 0,
                "timestamp": current_timestamp(),
                "dry_run": True,
            }
        except Exception as e:
            logger.error("Sim buy error: " + str(e))
            return {
                "success": True,
                "tx_hash": "DRY_ERR_" + str(current_timestamp()),
                "token_address": addr,
                "sol_spent": sol,
                "tokens_received": 1000000000,
                "price": sol / 1000000000,
                "price_impact": 0,
                "timestamp": current_timestamp(),
                "dry_run": True,
            }

    # ====================================================
    #  SELL
    # ====================================================

    async def sell_token(self, token_address, token_amount, slippage_bps=None):
        if config.dry_run:
            return await self._sim_sell(token_address, token_amount)
        sl = slippage_bps or config.trading.slippage_bps

        for attempt in range(self.retries):
            try:
                q = await self._quote_with_retry(token_address, self.SOL, str(token_amount), sl)
                if not q:
                    logger.warning("Sell quote failed attempt " + str(attempt + 1))
                    self._rotate_jupiter()
                    await asyncio.sleep(2)
                    continue

                out = int(q.get("outAmount", 0))
                if out == 0:
                    continue

                sw = await self._swap_tx_with_retry(q)
                if not sw:
                    self._rotate_jupiter()
                    await asyncio.sleep(2)
                    continue

                tx = await self._sign_send(sw)
                if tx:
                    sol_r = lamports_to_sol(out)
                    self.sell_count += 1
                    log_sell(token_address, sol_r, 0)
                    return {
                        "success": True, "tx_hash": tx,
                        "token_address": token_address,
                        "tokens_sold": token_amount,
                        "sol_received": sol_r,
                        "timestamp": current_timestamp(),
                    }
            except Exception as e:
                logger.error("Sell attempt " + str(attempt + 1) + ": " + str(e))
                self._rotate_jupiter()
                await asyncio.sleep(2)

        self.fail_count += 1
        return None

    async def _sim_sell(self, addr, amt):
        """DRY RUN SELL"""
        slippages = [500, 1000, 2000, 5000]

        for ep_idx in range(len(self.jupiter_endpoints)):
            for sl in slippages:
                try:
                    q = await self._quote_direct(
                        self.jupiter_endpoints[ep_idx],
                        addr, self.SOL, str(amt), sl
                    )
                    if q:
                        out = int(q.get("outAmount", 0))
                        if out > 0:
                            sol_r = lamports_to_sol(out)
                            logger.info("DRY SELL: " + str(amt) + " -> " + str(round(sol_r, 4)) + " SOL")
                            return {
                                "success": True,
                                "tx_hash": "DRY_" + str(current_timestamp()),
                                "token_address": addr,
                                "tokens_sold": amt,
                                "sol_received": sol_r,
                                "timestamp": current_timestamp(),
                                "dry_run": True,
                            }
                except:
                    continue
                await asyncio.sleep(0.2)

        base_sol = 0.06
        if self.bot_instance:
            try:
                for a, p in self.bot_instance.risk_manager.positions.items():
                    if a == addr and p.status == "open":
                        base_sol = p.total_invested
                        break
            except:
                pass

        change = random.uniform(-0.3, 0.5)
        sim_return = base_sol * (1 + change)
        if sim_return < 0:
            sim_return = base_sol * 0.1

        logger.info("DRY SELL sim: " + str(amt) + " -> " + str(round(sim_return, 4)) + " SOL (" + ("+" if change >= 0 else "") + str(round(change * 100, 1)) + "%)")
        return {
            "success": True,
            "tx_hash": "DRY_SIM_" + str(current_timestamp()),
            "token_address": addr,
            "tokens_sold": amt,
            "sol_received": round(sim_return, 6),
            "timestamp": current_timestamp(),
            "dry_run": True,
        }

    # ====================================================
    #  JUPITER API (with retry + failover)
    # ====================================================

    async def _quote_with_retry(self, inp, out, amt, sl=500):
        """Try quote on all endpoints with retry"""
        for ep_idx in range(len(self.jupiter_endpoints)):
            ep = self.jupiter_endpoints[(self.current_jupiter + ep_idx) % len(self.jupiter_endpoints)]
            for attempt in range(2):
                try:
                    q = await self._quote_direct(ep, inp, out, amt, sl)
                    if q:
                        return q
                except:
                    pass
                await asyncio.sleep(0.5)
        return None

    async def _quote_direct(self, endpoint, inp, out, amt, sl=500):
        """Direct quote call"""
        try:
            async with self.session.get(
                endpoint + "/quote",
                params={
                    "inputMint": inp, "outputMint": out,
                    "amount": amt, "slippageBps": sl,
                    "onlyDirectRoutes": "false",
                },
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data and data.get("outAmount"):
                        return data
                elif r.status == 429:
                    logger.warning("Jupiter rate limit on " + endpoint[:40])
                    await asyncio.sleep(3)
            return None
        except asyncio.TimeoutError:
            logger.debug("Jupiter timeout: " + endpoint[:40])
            return None
        except aiohttp.ClientConnectorError:
            logger.debug("Jupiter connect fail: " + endpoint[:40])
            return None
        except Exception as e:
            logger.debug("Jupiter error: " + endpoint[:40] + " -> " + str(e)[:50])
            return None

    async def _swap_tx_with_retry(self, quote):
        """Try swap on all endpoints"""
        for ep_idx in range(len(self.jupiter_endpoints)):
            ep = self.jupiter_endpoints[(self.current_jupiter + ep_idx) % len(self.jupiter_endpoints)]
            try:
                result = await self._swap_tx_direct(ep, quote)
                if result:
                    return result
            except:
                pass
            await asyncio.sleep(0.5)
        return None

    async def _swap_tx_direct(self, endpoint, quote):
        """Direct swap call"""
        try:
            async with self.session.post(
                endpoint + "/swap",
                json={
                    "quoteResponse": quote,
                    "userPublicKey": config.wallet.address,
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": 100000,
                    "asLegacyTransaction": True,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    return await r.json()
            return None
        except:
            return None

    async def _sign_send(self, swap_result):
        try:
            import base58 as b58
            from nacl.signing import SigningKey
            kb = b58.b58decode(config.wallet.private_key)
            if len(kb) == 64:
                seed = kb[:32]
            elif len(kb) == 32:
                seed = kb
            else:
                logger.error("Invalid key length: " + str(len(kb)))
                return None
            sk = SigningKey(seed)
            tx_bytes = base64.b64decode(swap_result["swapTransaction"])
            num_sigs = tx_bytes[0]
            message_start = 1 + (num_sigs * 64)
            message = tx_bytes[message_start:]
            signed = sk.sign(message)
            signed_tx = bytes([1]) + signed.signature + message
            encoded_tx = base64.b64encode(signed_tx).decode("utf-8")
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "sendTransaction",
                "params": [encoded_tx, {
                    "encoding": "base64",
                    "skipPreflight": True,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                }],
            }

            rpcs = [config.rpc.solana_rpc, "https://rpc.ankr.com/solana", "https://api.mainnet-beta.solana.com"]
            for rpc in rpcs:
                try:
                    async with self.session.post(
                        rpc, json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as r:
                        data = await r.json()
                        if "result" in data:
                            tx_hash = data["result"]
                            logger.info("TX sent: " + tx_hash)
                            return tx_hash
                        logger.debug("Send error on " + rpc[:30] + ": " + str(data.get("error", {})))
                except:
                    continue
            return None
        except ImportError as e:
            logger.error("Missing dep: " + str(e))
            return None
        except Exception as e:
            logger.error("Sign error: " + str(e))
            return None

    # ====================================================
    #  PRICE & BALANCE
    # ====================================================

    async def get_token_price(self, addr):
        for ep_idx in range(len(self.jupiter_endpoints)):
            try:
                q = await self._quote_direct(
                    self.jupiter_endpoints[ep_idx],
                    addr, self.SOL, "1000000000", 100
                )
                if q:
                    out = int(q.get("outAmount", 0))
                    if out > 0:
                        return lamports_to_sol(out)
            except:
                continue

        try:
            async with self.session.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + addr,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    for pair in d.get("pairs", []):
                        if pair.get("chainId") == "solana":
                            price_usd = float(pair.get("priceUsd", "0") or "0")
                            if price_usd > 0:
                                sol_usd = await self._get_sol_usd_price()
                                if sol_usd > 0:
                                    return price_usd / sol_usd
        except:
            pass

        return None

    async def _get_sol_usd_price(self):
        try:
            async with self.session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("solana", {}).get("usd", 0)
        except:
            pass
        return 150.0

    async def get_sol_balance(self):
        rpcs = [config.rpc.solana_rpc, "https://rpc.ankr.com/solana"]
        for rpc in rpcs:
            try:
                payload = {
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getBalance",
                    "params": [config.wallet.address],
                }
                async with self.session.post(
                    rpc, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
                    return lamports_to_sol(data.get("result", {}).get("value", 0))
            except:
                continue
        return 0.0
