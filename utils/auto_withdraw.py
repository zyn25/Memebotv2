"""
Auto Withdraw Profit
- Otomatis tarik profit ke wallet lain
- Protect modal awal
- Threshold-based withdrawal
"""
import asyncio
import aiohttp
import base64
from typing import Optional
from config import config
from utils.logger import logger, console


class AutoWithdraw:
    def __init__(self):
        self.enabled = False
        self.withdraw_wallet = ""
        self.initial_balance = 0.0
        self.min_profit_to_withdraw = 0.05
        self.withdraw_percentage = 50
        self.total_withdrawn = 0.0
        self.withdraw_count = 0
        self.last_withdraw_time = 0
        self.min_time_between_withdraws = 3600
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    def setup(self, withdraw_wallet="", initial_balance=0.0,
              min_profit=0.05, percentage=50, min_time=3600):
        """Setup auto withdraw settings"""
        self.withdraw_wallet = withdraw_wallet
        self.initial_balance = initial_balance
        self.min_profit_to_withdraw = min_profit
        self.withdraw_percentage = percentage
        self.min_time_between_withdraws = min_time
        self.enabled = bool(withdraw_wallet and initial_balance > 0)
        if self.enabled:
            logger.info("Auto Withdraw: ENABLED")
            logger.info("  Wallet: " + withdraw_wallet[:16] + "...")
            logger.info("  Initial: " + str(initial_balance) + " SOL")
            logger.info("  Min profit: " + str(min_profit) + " SOL")
            logger.info("  Percentage: " + str(percentage) + "%")
        else:
            logger.info("Auto Withdraw: DISABLED")

    async def check_and_withdraw(self, bot_instance):
        """Check profit dan auto withdraw kalau perlu"""
        if not self.enabled:
            return

        try:
            # Get current balance
            current_balance = await bot_instance.executor.get_sol_balance()

            # Hitung profit
            profit = current_balance - self.initial_balance

            if profit < self.min_profit_to_withdraw:
                return

            # Check time interval
            import time
            now = time.time()
            if now - self.last_withdraw_time < self.min_time_between_withdraws:
                return

            # Hitung jumlah withdraw
            withdraw_amount = profit * (self.withdraw_percentage / 100)

            # Minimum withdraw check
            if withdraw_amount < 0.01:
                return

            # Keep minimum balance di bot
            min_keep = 0.05
            if current_balance - withdraw_amount < min_keep:
                withdraw_amount = current_balance - min_keep

            if withdraw_amount <= 0:
                return

            # Execute withdraw
            success = await self._send_sol(withdraw_amount)

            if success:
                self.total_withdrawn += withdraw_amount
                self.withdraw_count += 1
                self.last_withdraw_time = now

                new_balance = current_balance - withdraw_amount

                console.print(
                    "[bold green]WITHDRAW: "
                    + str(round(withdraw_amount, 4)) + " SOL → "
                    + self.withdraw_wallet[:16] + "...[/]"
                )

                # Telegram notification
                if bot_instance.telegram:
                    try:
                        await bot_instance.telegram._send(
                            "\U0001f4b8 <b>WITHDRAW PROFIT</b>\n\n"
                            + "Amount: <b>" + str(round(withdraw_amount, 4)) + " SOL</b>\n"
                            + "To: <code>" + self.withdraw_wallet[:16] + "...</code>\n\n"
                            + "Balance: " + str(round(new_balance, 4)) + " SOL\n"
                            + "Profit: " + str(round(profit, 4)) + " SOL\n"
                            + "Total Withdrawn: " + str(round(self.total_withdrawn, 4)) + " SOL\n"
                            + "Withdraw Count: " + str(self.withdraw_count)
                        )
                    except:
                        pass
            else:
                logger.error("Withdraw failed!")
                if bot_instance.telegram:
                    try:
                        await bot_instance.telegram._send(
                            "\u274c <b>WITHDRAW FAILED</b>\n\n"
                            + "Amount: " + str(round(withdraw_amount, 4)) + " SOL\n"
                            + "To: " + self.withdraw_wallet[:16] + "..."
                        )
                    except:
                        pass

        except Exception as e:
            logger.error("Auto withdraw error: " + str(e)[:100])

    async def _send_sol(self, amount_sol):
        """Send SOL ke wallet tujuan"""
        if config.dry_run:
            logger.info("DRY WITHDRAW: " + str(round(amount_sol, 4)) + " SOL")
            return True

        try:
            import base58 as b58
            from nacl.signing import SigningKey
            from utils.helpers import sol_to_lamports

            # Build transaction
            lamports = sol_to_lamports(amount_sol)

            # Get recent blockhash
            bh_payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "finalized"}]
            }
            async with self.session.post(
                config.rpc.solana_rpc, json=bh_payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                bh_data = await r.json()
                blockhash = bh_data.get("result", {}).get("value", {}).get("blockhash", "")

            if not blockhash:
                logger.error("Failed to get blockhash")
                return False

            # Build transfer instruction
            from solders.pubkey import Pubkey
            from solders.system_program import TransferParams, transfer
            from solders.transaction import Transaction
            from solders.keypair import Keypair

            sender = Keypair.from_base58_string(config.wallet.private_key)
            recipient = Pubkey.from_string(self.withdraw_wallet)

            ix = transfer(TransferParams(
                from_pubkey=sender.pubkey(),
                to_pubkey=recipient,
                lamports=lamports
            ))

            tx = Transaction()
            tx.add(ix)
            tx.recent_blockhash = blockhash
            tx.sign(sender)

            # Send transaction
            encoded_tx = base64.b64encode(bytes(tx)).decode("utf-8")
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

            async with self.session.post(
                config.rpc.solana_rpc, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "result" in data:
                    tx_hash = data["result"]
                    logger.info("Withdraw TX: " + tx_hash)
                    return True
                else:
                    logger.error("Withdraw error: " + str(data.get("error", {})))
                    return False

        except ImportError:
            logger.error("Missing solders package for withdraw")
            return False
        except Exception as e:
            logger.error("Withdraw error: " + str(e)[:100])
            return False

    def get_stats(self):
        return {
            "enabled": self.enabled,
            "wallet": self.withdraw_wallet[:16] + "..." if self.withdraw_wallet else "N/A",
            "initial_balance": self.initial_balance,
            "min_profit": self.min_profit_to_withdraw,
            "percentage": self.withdraw_percentage,
            "total_withdrawn": self.total_withdrawn,
            "withdraw_count": self.withdraw_count,
        }
